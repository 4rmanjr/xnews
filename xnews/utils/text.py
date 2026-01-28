"""
xnews - Text Utilities Module
Translation, sentiment analysis, and text processing utilities.
"""

import difflib
import urllib.parse
from typing import Any, Optional

from rich.console import Console

from xnews.config import TextLimits

console = Console()

# --- Sentiment Analysis ---
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False

# --- Translation ---
from deep_translator import GoogleTranslator


def analyze_sentiment(text: str) -> dict[str, Any]:
    """Analyze sentiment of text using TextBlob."""
    if not TEXTBLOB_AVAILABLE or not text:
        return {"label": "Unknown", "score": 0.0, "emoji": "❓"}
    
    try:
        blob = TextBlob(text[:TextLimits.SENTIMENT_SAMPLE])
        polarity = blob.sentiment.polarity
        
        if polarity > 0.1:
            return {"label": "Positif", "score": polarity, "emoji": "😊"}
        elif polarity < -0.1:
            return {"label": "Negatif", "score": polarity, "emoji": "😟"}
        else:
            return {"label": "Netral", "score": polarity, "emoji": "😐"}
    except (ValueError, AttributeError) as e:
        console.print(f"[dim]Sentiment analysis error: {e}[/dim]")
        return {"label": "Unknown", "score": 0.0, "emoji": "❓"}


def translate_text(text: str, target: str = 'id') -> str:
    """Translate long text by splitting into paragraphs."""
    if not text:
        return ""
    
    translator = GoogleTranslator(source='auto', target=target)
    translated_parts: list[str] = []
    paragraphs = text.split('\n')
    
    for p in paragraphs:
        if not p.strip():
            translated_parts.append("")
            continue
        try:
            if len(p) > TextLimits.TRANSLATION_CHUNK:
                res = translator.translate(p[:TextLimits.TRANSLATION_CHUNK])
            else:
                res = translator.translate(p)
            translated_parts.append(res)
        except (ValueError, ConnectionError, TimeoutError) as e:
            console.print(f"[dim]Translation skipped: {e}[/dim]")
            translated_parts.append(p)
    
    return "\n".join(translated_parts)


def apply_translation(news_item: dict[str, Any], text: str, target: str = 'id') -> str:
    """Helper to translate title and text."""
    try:
        orig_title = news_item.get('title', '')
        if orig_title:
            news_item['title'] = GoogleTranslator(source='auto', target=target).translate(orig_title)
    except (ValueError, ConnectionError, TimeoutError):
        pass  # Keep original title on translation failure
    return translate_text(text, target=target)


def clean_title(title: str) -> str:
    """Normalize title for comparison."""
    return title.lower().strip()


def is_duplicate(news_item: dict[str, Any], existing_titles: set[str], threshold: float = 0.85) -> bool:
    """Check if news item is duplicate based on title similarity."""
    title = clean_title(news_item.get('title', ''))
    if title in existing_titles:
        return True
    for existing in existing_titles:
        if difflib.SequenceMatcher(None, title, existing).ratio() > threshold:
            return True
    return False


def validate_url(url: str) -> bool:
    """Validate URL to prevent command injection in subprocess calls.
    
    Args:
        url: URL string to validate
        
    Returns:
        True if URL is valid and safe, False otherwise
    """
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        # Only allow http/https schemes
        if parsed.scheme not in ('http', 'https'):
            return False
        # Must have a hostname
        if not parsed.netloc:
            return False
        # Block suspicious characters that could be used for injection
        dangerous_chars = [';', '|', '&', '$', '`', '\n', '\r']
        if any(char in url for char in dangerous_chars):
            console.print(f"[yellow]⚠ URL contains suspicious characters: {url[:50]}...[/yellow]")
            return False
        return True
    except (ValueError, AttributeError):
        return False


def get_relevant_emoji(text: str) -> str:
    """Select emoji based on topic and country keywords."""
    text = text.lower()
    emojis: list[str] = []

    # Topic Emoji
    topic_icon = "📢"
    if any(k in text for k in ['ai', 'tech', 'robot', 'data', 'cyber', 'app', 'soft', 'hard']):
        topic_icon = "🤖"
    elif any(k in text for k in ['saham', 'uang', 'bisnis', 'ekonomi', 'market', 'stock', 'profit', 'crypto', 'bitcoin', 'btc', 'invest']):
        topic_icon = "💰"
    elif any(k in text for k in ['sehat', 'dokter', 'virus', 'obat', 'medis']):
        topic_icon = "🏥"
    elif any(k in text for k in ['game', 'play', 'esport']):
        topic_icon = "🎮"
    elif any(k in text for k in ['politik', 'presiden', 'hukum', 'negara', 'dpr', 'mpr', 'partai']):
        topic_icon = "⚖️"
    
    emojis.append(topic_icon)

    # Country Flags
    country_map = {
        'indonesia': '🇮🇩', 'jakarta': '🇮🇩', 'rupiah': '🇮🇩', 'jokowi': '🇮🇩', 'prabowo': '🇮🇩',
        'amerika': '🇺🇸', 'usa': '🇺🇸', 'united states': '🇺🇸', 'biden': '🇺🇸', 'trump': '🇺🇸', 'dollar': '🇺🇸',
        'china': '🇨🇳', 'tiongkok': '🇨🇳', 'beijing': '🇨🇳', 'xi jinping': '🇨🇳', 'yuan': '🇨🇳',
        'jepang': '🇯🇵', 'japan': '🇯🇵', 'tokyo': '🇯🇵', 'yen': '🇯🇵',
        'korea': '🇰🇷', 'seoul': '🇰🇷', 'k-pop': '🇰🇷',
        'rusia': '🇷🇺', 'russia': '🇷🇺', 'moskow': '🇷🇺', 'putin': '🇷🇺',
        'ukraina': '🇺🇦', 'ukraine': '🇺🇦', 'kiev': '🇺🇦', 'kyiv': '🇺🇦',
        'inggris': '🇬🇧', 'uk': '🇬🇧', 'london': '🇬🇧',
        'eropa': '🇪🇺', 'europe': '🇪🇺', 'eu': '🇪🇺',
        'palestina': '🇵🇸', 'gaza': '🇵🇸', 'hamas': '🇵🇸',
        'israel': '🇮🇱', 'tel aviv': '🇮🇱',
        'arab': '🇸🇦', 'saudi': '🇸🇦', 'mekkah': '🇸🇦',
        'malaysia': '🇲🇾', 'kuala lumpur': '🇲🇾',
        'singapura': '🇸🇬', 'singapore': '🇸🇬',
        'india': '🇮🇳', 'new delhi': '🇮🇳',
        'jerman': '🇩🇪', 'germany': '🇩🇪',
        'prancis': '🇫🇷', 'france': '🇫🇷'
    }

    found_flags: set[str] = set()
    for keyword, flag in country_map.items():
        if keyword in text:
            found_flags.add(flag)
    
    if found_flags:
        sorted_flags = sorted(list(found_flags))
        emojis.extend(sorted_flags[:2])

    return " ".join(emojis)
