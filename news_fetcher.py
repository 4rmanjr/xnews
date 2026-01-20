#!/usr/bin/env python3
"""
xnews - Smart News Fetcher Turbo v2.0
Enhanced with AI Summarization, Sentiment Analysis, Rich Console, and more!
"""

import csv
import json
import argparse
import sys
import os
import time
import difflib
import hashlib
import warnings
import logging
import urllib.parse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Third Party Libraries
from dateutil import parser
from ddgs import DDGS
import trafilatura
import requests
from dotenv import load_dotenv
import pyperclip

# YAML Support for Prompts
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Rich Console
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.live import Live
from rich.markdown import Markdown
from rich import box

# AI & Analysis
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False

# Deep Translator
from deep_translator import GoogleTranslator

# --- Load Environment Variables ---
load_dotenv()

# --- Configuration ---
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_THREADS = 10
TIMEOUT_SECONDS = 15
OUTPUT_DIR = "reports"
CACHE_DIR = ".cache"
CACHE_TTL_HOURS = 1
PROMPT_FILE = "prompts.yaml"

# Groq Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# Suppress Logs & Warnings
warnings.filterwarnings("ignore", message="This package.*renamed.*ddgs")
logging.getLogger('trafilatura').setLevel(logging.WARNING)

# Rich Console Instance
console = Console()

# --- Prompt Loader ---
class PromptLoader:
    """Handles loading and formatting of prompts from YAML file."""
    
    def __init__(self, filepath=PROMPT_FILE):
        self.filepath = filepath
        self.prompts = self._load_prompts()

    def _load_prompts(self):
        if not YAML_AVAILABLE:
            # console.print("[dim]PyYAML not installed. Using internal defaults (if any).[/dim]")
            return {}
        
        if not os.path.exists(self.filepath):
            console.print(f"[yellow]Warning: {self.filepath} not found. Using internal defaults.[/yellow]")
            return {}
            
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            console.print(f"[red]Error loading prompts: {e}[/red]")
            return {}

    def get(self, *keys, default=None):
        """Deep get for nested dictionary."""
        val = self.prompts
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                return default
        return val if val is not None else default

prompt_loader = PromptLoader()

# --- Cache Manager ---
class CacheManager:
    """Simple file-based cache system."""
    
    def __init__(self):
        self.cache_dir = Path(CACHE_DIR)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_hash(self, key: str) -> str:
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, key: str):
        cache_file = self.cache_dir / f"{self._get_hash(key)}.json"
        if not cache_file.exists():
            return None
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            # Check TTL
            cached_time = datetime.fromisoformat(data['cached_at'])
            if datetime.now() - cached_time > timedelta(hours=CACHE_TTL_HOURS):
                cache_file.unlink()
                return None
            return data['content']
        except Exception:
            return None
    
    def set(self, key: str, content):
        cache_file = self.cache_dir / f"{self._get_hash(key)}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'cached_at': datetime.now().isoformat(),
                    'content': content
                }, f)
        except Exception:
            pass
    
    def clear(self):
        for f in self.cache_dir.glob("*.json"):
            f.unlink()

cache = CacheManager()

# --- AI Summarization with Groq ---
def ai_summarize(text: str, max_sentences: int = 3, for_twitter: bool = False) -> str:
    """
    Summarize text using Groq LLM.
    
    Args:
        text: The text to summarize
        max_sentences: Number of sentences for detailed summary
        for_twitter: If True, creates a short, engaging summary with emojis (max 200 chars)
    """
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return ""
    
    if not text or len(text) < 100:
        return ""
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        
        # Truncate for API limit
        truncated = text[:4000] if len(text) > 4000 else text
        
        if for_twitter:
            # Load from YAML
            system_prompt = prompt_loader.get('summary', 'twitter', 'system', default="You are a social media expert.")
            user_prompt_tpl = prompt_loader.get('summary', 'twitter', 'user', default="Summarize this:\n\n{text}")
            user_prompt = user_prompt_tpl.format(text=truncated)
            max_tokens = 300
        else:
            # Load from YAML
            system_prompt_tpl = prompt_loader.get('summary', 'standard', 'system', default="Summarize in {max_sentences} sentences.")
            # Handle potential formatting in system prompt if it exists
            try:
                system_prompt = system_prompt_tpl.format(max_sentences=max_sentences)
            except:
                system_prompt = system_prompt_tpl
                
            user_prompt_tpl = prompt_loader.get('summary', 'standard', 'user', default="Summarize:\n\n{text}")
            user_prompt = user_prompt_tpl.format(text=truncated)
            max_tokens = 300
        
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,  # Slightly higher for more creative output
            max_tokens=max_tokens
        )
        
        result = response.choices[0].message.content.strip()
        
        # Ensure Twitter summary doesn't exceed 500 chars
        if for_twitter and len(result) > 500:
            result = result[:497] + "..."
        
        return result
    except Exception as e:
        console.print(f"[dim]AI Summary error: {e}[/dim]")
        return ""


def ai_generate_tweet_text(title: str, text: str, topic: str) -> str:
    """Generate a complete, engaging tweet using AI."""
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return ""
    
    if not text:
        return ""
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        
        truncated = text[:2000] if len(text) > 2000 else text
        
        # Load from YAML
        system_prompt = prompt_loader.get('tweet_generation', 'system', default="You are a twitter expert.")
        user_prompt_tpl = prompt_loader.get('tweet_generation', 'user', default="Title: {title}\nText: {text}")
        
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=350
        )
        
        tweet_text = response.choices[0].message.content.strip()
        
        # Remove quotes and markdown formatting (bold/italic)
        tweet_text = tweet_text.strip('"\'').replace('**', '').replace('__', '')
        
        # Ensure total doesn't exceed 500
        if len(tweet_text) > 500:
            tweet_text = tweet_text[:497] + "..."
        
        return tweet_text
        
    except Exception as e:
        console.print(f"[dim]AI Tweet error: {e}[/dim]")
        return ""

# --- Sentiment Analysis ---
def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment of text."""
    if not TEXTBLOB_AVAILABLE or not text:
        return {"label": "Unknown", "score": 0.0, "emoji": "❓"}
    
    try:
        blob = TextBlob(text[:1000])  # Limit for performance
        polarity = blob.sentiment.polarity
        
        if polarity > 0.1:
            return {"label": "Positif", "score": polarity, "emoji": "😊"}
        elif polarity < -0.1:
            return {"label": "Negatif", "score": polarity, "emoji": "😟"}
        else:
            return {"label": "Netral", "score": polarity, "emoji": "😐"}
    except Exception:
        return {"label": "Unknown", "score": 0.0, "emoji": "❓"}

# --- Utility Functions ---
def ensure_output_dir():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def print_banner():
    banner = """
╔══════════════════════════════════════════════════════════════╗
║     🚀 XNEWS - Smart News Fetcher Turbo v2.0                 ║
║     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━      ║
║     ✨ AI Summarization • Sentiment Analysis • Rich UI       ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(Panel(banner.strip(), style="bold cyan", box=box.DOUBLE))

def clean_title(title):
    return title.lower().strip()

def is_duplicate(news_item, existing_titles, threshold=0.85):
    title = clean_title(news_item.get('title', ''))
    if title in existing_titles:
        return True
    for existing in existing_titles:
        if difflib.SequenceMatcher(None, title, existing).ratio() > threshold:
            return True
    return False

def translate_text(text, target='id'):
    """Translate long text by splitting into paragraphs."""
    if not text:
        return ""
    
    translator = GoogleTranslator(source='auto', target=target)
    translated_parts = []
    paragraphs = text.split('\n')
    
    for p in paragraphs:
        if not p.strip():
            translated_parts.append("")
            continue
        try:
            if len(p) > 4500:
                res = translator.translate(p[:4500])
            else:
                res = translator.translate(p)
            translated_parts.append(res)
        except Exception:
            translated_parts.append(p)
    
    return "\n".join(translated_parts)

def apply_translation(news_item, text, target='id'):
    """Helper to translate title and text."""
    try:
        orig_title = news_item.get('title', '')
        if orig_title:
            news_item['title'] = GoogleTranslator(source='auto', target=target).translate(orig_title)
    except:
        pass
    return translate_text(text, target=target)

# --- Article Fetching ---
def fetch_single_article(news_item, auto_translate=False, do_summarize=False, do_sentiment=False, topic=""):
    """Worker function: Download HTML -> Extract Text -> (Optional) Translate/Summarize/Sentiment/AI Tweet"""
    url = news_item.get('url')
    news_item['full_text'] = ""
    news_item['is_translated'] = False
    news_item['ai_summary'] = ""
    news_item['ai_tweet'] = ""
    news_item['sentiment'] = {"label": "Unknown", "score": 0.0, "emoji": "❓"}
    
    if not url:
        return news_item
    
    # Check cache first
    cached = cache.get(url)
    if cached:
        news_item['full_text'] = cached
    else:
        # Fake User-Agent headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/"
        }
        
        extracted_text = ""
        
        try:
            # Attempt 1: Use trafilatura fetch_url
            downloaded = trafilatura.fetch_url(url)
            
            # Attempt 2: Use requests manually
            if not downloaded:
                try:
                    response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
                    response.raise_for_status()
                    downloaded = response.text
                except Exception:
                    pass
            
            # Extract Text
            if downloaded:
                extracted_text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        except Exception:
            pass
        
        # Fallback to snippet body
        if not extracted_text:
            extracted_text = news_item.get('body', '')
        
        # If we have downloaded content but no title (direct URL case), try to extract metadata
        if downloaded and news_item.get('title') == 'URL Processing...':
            try:
                metadata = trafilatura.bare_extraction(downloaded)
                if metadata:
                    if metadata.get('title'):
                        news_item['title'] = metadata['title']
                    if metadata.get('date'):
                        news_item['formatted_date'] = metadata['date']
                    if metadata.get('sitename'):
                        news_item['source'] = metadata['sitename']
            except Exception:
                pass
        
        # Fallback: Extract title from <title> tag using regex if trafilatura failed
        if news_item.get('title') == 'URL Processing...' and downloaded:
             import re
             match = re.search(r'<title>(.*?)</title>', downloaded, re.IGNORECASE)
             if match:
                 news_item['title'] = match.group(1).split('|')[0].strip() # Take first part before pipe

        news_item['full_text'] = extracted_text
        
        # Cache the result
        if extracted_text:
            cache.set(url, extracted_text)
    
    # --- Content Processing ---
    text_to_process = news_item['full_text']
    
    if text_to_process:
        # Translation
        if auto_translate:
            news_item['full_text'] = apply_translation(news_item, text_to_process, target='id')
            news_item['is_translated'] = True
            text_to_process = news_item['full_text']
        
        # If title is still placeholder (even after trans), try to generate/fix it using AI or first sentence
        current_title = news_item.get('title', '')
        if 'URL Processing' in current_title or 'Pemrosesan URL' in current_title:
             # Use AI to generate title from text
             if GROQ_API_KEY:
                 try:
                    client = Groq(api_key=GROQ_API_KEY)
                    user_prompt_tpl = prompt_loader.get('title_generation', 'user', default="Create title from:\n\n{text}")
                    user_prompt = user_prompt_tpl.format(text=text_to_process[:500])
                    
                    t_resp = client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": user_prompt}],
                        max_tokens=20
                    )
                    news_item['title'] = t_resp.choices[0].message.content.strip().strip('"')
                 except:
                    pass

        # AI Summarization
        if do_summarize and GROQ_API_KEY:
            news_item['ai_summary'] = ai_summarize(text_to_process)
            # Also generate AI Tweet
            title = news_item.get('title', '')
            news_item['ai_tweet'] = ai_generate_tweet_text(title, text_to_process, topic)
        
        # Sentiment Analysis
        if do_sentiment:
            news_item['sentiment'] = analyze_sentiment(text_to_process)
    
    return news_item

def enrich_news_content(news_list, do_translate=False, do_summarize=False, do_sentiment=False, topic=""):
    """Enrich news with full text, translation, summary, sentiment, and AI tweet."""
    if not news_list:
        return []
    
    features = []
    if do_translate:
        features.append("translate")
    if do_summarize:
        features.append("AI summary")
    if do_sentiment:
        features.append("sentiment")
    
    action_msg = "mengambil artikel"
    if features:
        action_msg += f" + {', '.join(features)}"
    
    console.print(f"\n[bold cyan]⚡ Turbo Mode:[/bold cyan] {action_msg} untuk {len(news_list)} berita...")
    
    enriched_results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Processing articles...", total=len(news_list))
        
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            future_to_news = {
                executor.submit(fetch_single_article, item, do_translate, do_summarize, do_sentiment, topic): item 
                for item in news_list
            }
            
            for future in as_completed(future_to_news):
                try:
                    data = future.result()
                    enriched_results.append(data)
                except Exception:
                    item = future_to_news[future]
                    item['full_text'] = ""
                    enriched_results.append(item)
                progress.update(task, advance=1)
    
    return enriched_results

# --- Filtering ---
def filter_recent_news(news_list, days=2):
    recent_news = []
    seen_titles = set()
    cutoff_date = datetime.now().astimezone() - timedelta(days=days)
    
    console.print("[dim]Menyaring berita terbaru & menghapus duplikat...[/dim]")
    
    for item in news_list:
        date_str = item.get('date')
        if not date_str:
            continue
        try:
            pub_date = parser.parse(date_str)
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
            if pub_date >= cutoff_date:
                if is_duplicate(item, seen_titles):
                    continue
                seen_titles.add(clean_title(item.get('title', '')))
                item['_raw_date'] = pub_date
                item['formatted_date'] = pub_date.strftime('%Y-%m-%d %H:%M:%S')
                item['body'] = item.get('body', '')
                recent_news.append(item)
        except (ValueError, TypeError):
            continue
    
    recent_news.sort(key=lambda x: x.get('_raw_date', datetime.min), reverse=True)
    return recent_news

# --- Search ---
def search_topic(topic, region='wt-wt', max_results=50):
    console.print(f"\n[bold green]🔍 Mencari:[/bold green] '{topic}'")
    
    # Check cache
    cache_key = f"search_{topic}_{region}_{max_results}"
    cached = cache.get(cache_key)
    if cached:
        console.print("[dim]📦 Menggunakan cache...[/dim]")
        return cached
    
    results = []
    attempt = 0
    
    while attempt < MAX_RETRIES:
        try:
            with DDGS() as ddgs:
                ddgs_gen = ddgs.news(
                    query=topic, 
                    region=region, 
                    safesearch='off', 
                    timelimit='w', 
                    max_results=max_results
                )
                for r in ddgs_gen:
                    results.append(r)
            break
        except Exception as e:
            attempt += 1
            if attempt < MAX_RETRIES:
                wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                console.print(f"[yellow]⚠ Retry {attempt}/{MAX_RETRIES} in {wait_time}s...[/yellow]")
                time.sleep(wait_time)
    
    if results:
        cache.set(cache_key, results)
    
    return results

# --- Save Functions ---
def get_dated_output_path(filename):
    """Generate path with date-based subdirectory structure."""
    today = datetime.now().strftime('%Y-%m-%d')
    target_dir = os.path.join(OUTPUT_DIR, today)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    return os.path.join(target_dir, filename)

def save_to_csv(news_list, filename):
    if not news_list:
        return
    ensure_output_dir()
    filepath = get_dated_output_path(filename)
    keys = ['title', 'source', 'formatted_date', 'url', 'body', 'full_text', 'ai_summary', 'sentiment', 'is_translated']
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            writer.writeheader()
            for item in news_list:
                row = item.copy()
                row['sentiment'] = f"{item.get('sentiment', {}).get('label', '')} ({item.get('sentiment', {}).get('score', 0):.2f})"
                writer.writerow(row)
        console.print(f"[green]✅ CSV tersimpan:[/green] {filepath}")
    except IOError as e:
        console.print(f"[red]❌ Gagal CSV: {e}[/red]")

def save_to_json(news_list, filename):
    if not news_list:
        return
    ensure_output_dir()
    filepath = get_dated_output_path(filename)
    
    # Clean data for JSON
    export_data = []
    for item in news_list:
        clean_item = {
            'title': item.get('title', ''),
            'source': item.get('source', ''),
            'date': item.get('formatted_date', ''),
            'url': item.get('url', ''),
            'summary': item.get('ai_summary', ''),
            'full_text': item.get('full_text', ''),
            'sentiment': item.get('sentiment', {}),
            'is_translated': item.get('is_translated', False)
        }
        export_data.append(clean_item)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': datetime.now().isoformat(),
                'total_articles': len(export_data),
                'articles': export_data
            }, f, ensure_ascii=False, indent=2)
        console.print(f"[green]✅ JSON tersimpan:[/green] {filepath}")
    except IOError as e:
        console.print(f"[red]❌ Gagal JSON: {e}[/red]")

def get_relevant_emoji(text):
    """Select emoji based on topic and country keywords."""
    text = text.lower()
    emojis = []

    # 1. Topic Emoji (Primary)
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

    # 2. Country Flags Detection
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

    found_flags = set()
    for keyword, flag in country_map.items():
        if keyword in text:
            found_flags.add(flag)
    
    if found_flags:
        sorted_flags = sorted(list(found_flags))
        emojis.extend(sorted_flags[:2]) # Max 2 flags

    return " ".join(emojis)

def generate_twitter_intent_url(text):
    """Generate a click-to-tweet URL."""
    base_url = "https://twitter.com/intent/tweet"
    encoded_text = urllib.parse.quote(text)
    return f"{base_url}?text={encoded_text}"

def generate_tweet(title, text, topic, ai_summary=""):
    """Create interactive tweet draft, max 280 characters."""
    emoji = get_relevant_emoji(title + " " + topic)
    safe_topic = topic.replace(" ", "")
    hashtags = f"#{safe_topic} #BeritaTerkini #xnews"
    
    # Use AI summary if available, otherwise use first sentence
    if ai_summary:
        summary = ai_summary.split('.')[0].strip() + "."
    elif text:
        summary = text.split('.')[0].strip() + "."
    else:
        summary = "Simak informasi selengkapnya."
    
    base_len = len(emoji) + 1 + len(title) + 5 + len(hashtags)
    remaining_chars = 500 - base_len
    
    if len(summary) > remaining_chars:
        summary = summary[:remaining_chars-3] + "..."
    
    tweet = f"{emoji} {title}\n\n📝 {summary}\n\n{hashtags}"
    return tweet

def save_to_markdown(news_list, filename, topic):
    if not news_list:
        return
    ensure_output_dir()
    filepath = get_dated_output_path(filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 📰 Laporan Lengkap: {topic}\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"**Total Artikel:** {len(news_list)}\n\n")
            
            # Statistics
            sentiments = [n.get('sentiment', {}).get('label', 'Unknown') for n in news_list]
            pos_count = sentiments.count('Positif')
            neg_count = sentiments.count('Negatif')
            neu_count = sentiments.count('Netral')
            
            f.write(f"**Sentiment Overview:** 😊 Positif: {pos_count} | 😟 Negatif: {neg_count} | 😐 Netral: {neu_count}\n\n")
            f.write("---\n\n")
            
            for i, news in enumerate(news_list, 1):
                title = news.get('title', 'Tanpa Judul')
                source = news.get('source', 'Unknown')
                date = news.get('formatted_date', '-')
                link = news.get('url', '#')
                full_text = news.get('full_text', '')
                ai_summary = news.get('ai_summary', '')
                sentiment = news.get('sentiment', {})
                is_trans = news.get('is_translated', False)
                
                trans_badge = " *(Diterjemahkan)*" if is_trans else ""
                sentiment_badge = f" {sentiment.get('emoji', '')} {sentiment.get('label', '')}"
                
                f.write(f"## {i}. {title}{trans_badge}\n")
                f.write(f"_{source} • {date}_ |{sentiment_badge}\n\n")
                
                # AI Summary Section
                if ai_summary:
                    f.write("### 🧠 AI Summary\n")
                    f.write(f"> {ai_summary}\n\n")
                
                # Tweet Draft - Use AI tweet if available
                ai_tweet = news.get('ai_tweet', '')
                if ai_tweet:
                    tweet_draft = ai_tweet
                else:
                    # Fallback to manual generation
                    content_for_tweet = full_text if full_text else news.get('body', '')
                    tweet_draft = generate_tweet(title, content_for_tweet, topic, ai_summary)
                
                f.write("### 🐦 Draft X/Twitter (Copy-Paste Ready)\n")
                f.write(f"_{len(tweet_draft)} karakter_\n")
                f.write("```text\n")
                f.write(tweet_draft)
                f.write("\n```\n\n")
                
                # Full Text
                if full_text:
                    clean_text = "\n\n".join([p.strip() for p in full_text.split('\n') if p.strip()])
                    # Truncate for readability
                    if len(clean_text) > 2000:
                        clean_text = clean_text[:2000] + "\n\n_... (teks dipotong)_"
                    f.write(f"{clean_text}\n\n")
                else:
                    f.write("_Tidak ada konten teks._\n\n")
                
                f.write(f"[🔗 Baca Sumber Asli]({link})\n\n")
                f.write("---\n\n")
        
        console.print(f"[green]✅ Laporan MD tersimpan:[/green] [bold]{filepath}[/bold]")
    except IOError as e:
        console.print(f"[red]❌ Gagal MD: {e}[/red]")

def display_results_table(news_list, topic=""):
    """Display results in a rich table."""
    if not news_list:
        return
    
    table = Table(
        title=f"📊 Hasil Pencarian Berita: {topic}",
        box=box.ROUNDED,
        show_lines=True
    )
    
    table.add_column("No", style="cyan", width=4)
    table.add_column("Judul", style="white", max_width=40)
    table.add_column("Sumber", style="green", width=12)
    table.add_column("Sentiment", style="magenta", width=10)
    table.add_column("Action", style="bold blue", justify="center")
    
    for i, news in enumerate(news_list[:10], 1):  # Show max 10 in table
        title = news.get('title', 'N/A')
        disp_title = title[:37] + "..." if len(title) > 40 else title
        source_name = news.get('source', 'N/A')[:12]
        url = news.get('url', '#')
        
        sentiment = news.get('sentiment', {})
        sent_str = f"{sentiment.get('emoji', '')} {sentiment.get('label', 'N/A')}"
        
        # Clickable Source
        source_link = f"[link={url}]{source_name}[/link]"
        
        # Prepare Tweet
        ai_tweet = news.get('ai_tweet', '')
        if ai_tweet:
            tweet_text = ai_tweet
        else:
            tweet_text = generate_tweet(title, news.get('full_text', ''), topic, news.get('ai_summary', ''))
            
        tweet_url = generate_twitter_intent_url(tweet_text)
        action_link = f"[link={tweet_url}]🐦 Post[/link]"
        
        table.add_row(str(i), disp_title, source_link, sent_str, action_link)
    
    console.print(table)
    
    if len(news_list) > 10:
        console.print(f"[dim]... dan {len(news_list) - 10} berita lainnya (lihat file output)[/dim]")

def interactive_copy_selection(news_list):
    """Interactive prompt to copy content to clipboard."""
    if not news_list:
        return

    console.print("\n[bold yellow]📋 Opsi Copy:[/bold yellow]")
    console.print("• Ketik [bold cyan]nomor urut[/bold cyan] untuk copy draft.")
    console.print("• Tekan [bold green]Enter[/bold green] (kosong) untuk cari berita lain.")
    
    while True:
        choice = console.input("\n[bold]Pilih Nomor (Enter utk Lanjut) > [/bold]").strip()
        
        if not choice:
            console.print("[dim]🔄 Kembali ke menu pencarian...[/dim]")
            break
            
        if not choice.isdigit():
            console.print("[red]❌ Masukkan nomor yang valid![/red]")
            continue
            
        idx = int(choice) - 1
        if 0 <= idx < len(news_list):
            item = news_list[idx]
            # Prioritize AI Tweet, then AI Summary, then Full Text
            content = item.get('ai_tweet') or item.get('ai_summary') or item.get('full_text') or ""
            
            if content:
                try:
                    pyperclip.copy(content)
                    title_preview = item.get('title', 'No Title')[:20]
                    console.print(f"[green]✅ Tersalin ke clipboard:[/green] {title_preview}...")
                    console.print("[dim](Paste di Twitter/X atau medsos lain)[/dim]")
                except Exception as e:
                    console.print(f"[red]❌ Gagal copy: {e}[/red]")
                    console.print("[dim]Pastikan 'xclip' atau 'xsel' terinstall di Linux.[/dim]")
            else:
                console.print("[yellow]⚠ Tidak ada konten untuk disalin.[/yellow]")
        else:
            console.print(f"[red]❌ Nomor {choice} tidak ada.[/red]")

# --- Watch Mode ---
def watch_mode(topic, region='wt-wt', interval_minutes=30, do_translate=False, do_summarize=False):
    """Continuously monitor for new news."""
    console.print(f"\n[bold yellow]👁️ Watch Mode Aktif[/bold yellow]")
    console.print(f"Topik: [cyan]{topic}[/cyan] | Interval: {interval_minutes} menit")
    console.print("[dim]Tekan Ctrl+C untuk berhenti[/dim]\n")
    
    seen_urls = set()
    
    try:
        while True:
            raw = search_topic(topic, region=region, max_results=20)
            filtered = filter_recent_news(raw, days=1)
            
            # Find new articles
            new_articles = [n for n in filtered if n.get('url') not in seen_urls]
            
            if new_articles:
                console.print(f"\n[bold green]🆕 {len(new_articles)} berita baru ditemukan![/bold green]")
                
                # Enrich only new articles
                enriched = enrich_news_content(new_articles, do_translate, do_summarize, do_sentiment=True, topic=topic)
                
                for article in enriched:
                    seen_urls.add(article.get('url'))
                    console.print(f"\n[cyan]• {article.get('title', 'N/A')}[/cyan]")
                    console.print(f"  [dim]{article.get('source', '')} | {article.get('formatted_date', '')}[/dim]")
                    if article.get('ai_summary'):
                        console.print(f"  [green]→ {article.get('ai_summary')}[/green]")
            else:
                console.print(f"[dim]⏳ {datetime.now().strftime('%H:%M:%S')} - Tidak ada berita baru[/dim]")
            
            # Wait for next check
            time.sleep(interval_minutes * 60)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Watch mode dihentikan.[/yellow]")

# --- Interactive Mode ---
def interactive_mode():
    print_banner()
    
    # Show status
    status_items = []
    if GROQ_API_KEY:
        status_items.append("[green]✓ Groq AI[/green]")
    else:
        status_items.append("[red]✗ Groq AI (no API key)[/red]")
    if TEXTBLOB_AVAILABLE:
        status_items.append("[green]✓ Sentiment[/green]")
    if YAML_AVAILABLE:
        status_items.append("[green]✓ Custom Prompts[/green]")
    else:
        status_items.append("[yellow]⚠ Default Prompts (no yaml)[/yellow]")
    
    console.print(f"Status: {' | '.join(status_items)}\n")
    
    while True:
        try:
            console.print("\n[bold cyan]─── 🔍 Pencarian Baru ───[/bold cyan]")
            topic = console.input("[bold]📝 Masukkan Topik / Link URL (atau 'x' keluar): [/bold]").strip()
        except EOFError:
            break
        if topic.lower() == 'x':
            break
        if not topic:
            continue
        
        # URL Check in Interactive Mode
        is_url = topic.startswith(('http://', 'https://'))
        
        if is_url:
            region = 'wt-wt' # Default for URLs
        else:
            region_input = console.input("🌍 Indonesia saja? (y/n) [default: n]: ").lower()
            region = 'id-id' if region_input in ['y', 'yes'] else 'wt-wt'
        
        do_trans = False
        if region == 'wt-wt':
            trans_input = console.input("🔄 Terjemahkan ke Indonesia? (y/n) [default: n]: ").lower()
            do_trans = trans_input in ['y', 'yes']
        
        do_summary = False
        if GROQ_API_KEY:
            summary_input = console.input("🧠 Aktifkan AI Summary? (y/n) [default: y]: ").lower()
            do_summary = summary_input not in ['n', 'no']
        
        # Search or URL Processing
        if is_url:
            filtered = [{
                'url': topic,
                'title': 'URL Processing...', # Placeholder, will be updated in fetch_single_article
                'source': 'Direct Link',
                'formatted_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'body': ''
            }]
            actual_topic = "Direct Link"
        else:
            raw = search_topic(topic, region=region, max_results=20)
            if not raw:
                console.print("[yellow]Tidak ada hasil.[/yellow]")
                continue
            
            filtered = filter_recent_news(raw, days=2)
            if not filtered:
                console.print("[yellow]Tidak ada berita baru (<48 jam).[/yellow]")
                continue
            actual_topic = topic
        
        # Enrich
        final_news = enrich_news_content(filtered, do_translate=do_trans, do_summarize=do_summary, do_sentiment=True, topic=actual_topic)
        
        if is_url and not (final_news and final_news[0].get('full_text')):
            console.print("[red]❌ Gagal mengekstrak konten dari URL tersebut.[/red]")
            continue

        # Display
        display_results_table(final_news, actual_topic)
        
        # Interactive Copy
        interactive_copy_selection(final_news)
        
        # Save
        ts = int(time.time())
        if is_url and final_news[0].get('title') != 'URL Processing...':
            safe_topic = "".join([c if c.isalnum() else "_" for c in final_news[0]['title'][:30]])
        else:
            safe_topic = "".join([c if c.isalnum() else "_" for c in topic[:30]])
        
        save_to_csv(final_news, f"news_{safe_topic}_{ts}.csv")
        save_to_json(final_news, f"news_{safe_topic}_{ts}.json")
        save_to_markdown(final_news, f"Laporan_{safe_topic}_{ts}.md", final_news[0].get('title', actual_topic))
        
        console.print("\n" + "-" * 50 + "\n")

# --- Main ---
def main():
    parser_arg = argparse.ArgumentParser(
        description="xnews v2.0 - Smart News Fetcher with AI Summarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh Penggunaan:
  xnews "AI Technology" --translate --summary    # Cari, terjemahkan & ringkas dengan AI
  xnews "Bitcoin" --watch --interval 30          # Monitor berita setiap 30 menit
  xnews "SpaceX" --limit 10 --json               # Export ke JSON
  xnews                                          # Mode interaktif
        """
    )
    parser_arg.add_argument("topik", type=str, nargs='?', help="Topik atau kata kunci berita")
    parser_arg.add_argument("--indo", action="store_true", help="Fokus berita Indonesia (id-id)")
    parser_arg.add_argument("--translate", action="store_true", help="Terjemahkan ke Bahasa Indonesia")
    parser_arg.add_argument("--summary", action="store_true", help="Aktifkan AI Summarization (Groq)")
    parser_arg.add_argument("--sentiment", action="store_true", help="Aktifkan Sentiment Analysis")
    parser_arg.add_argument("--limit", type=int, default=50, help="Jumlah maksimal berita (default: 50)")
    parser_arg.add_argument("--json", action="store_true", help="Export ke format JSON")
    parser_arg.add_argument("--watch", action="store_true", help="Mode watch (monitoring berkelanjutan)")
    parser_arg.add_argument("--interval", type=int, default=30, help="Interval watch mode dalam menit (default: 30)")
    parser_arg.add_argument("--clear-cache", action="store_true", help="Hapus cache")
    
    args = parser_arg.parse_args()
    
    ensure_output_dir()
    
    # Clear cache if requested
    if args.clear_cache:
        cache.clear()
        console.print("[green]Cache dibersihkan.[/green]")
        return
    
    if not args.topik:
        try:
            interactive_mode()
        except KeyboardInterrupt:
            console.print("\n[yellow]Bye![/yellow]")
    else:
        # Check if input is a URL
        if args.topik.startswith(('http://', 'https://')):
            console.print(f"\n[bold green]🔗 Mendeteksi URL langsung:[/bold green] {args.topik}")
            
            # Create single item list
            filtered = [{
                'url': args.topik,
                'title': 'URL Processing...', # Placeholder, will be updated in fetch_single_article
                'source': 'Direct Link',
                'formatted_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'body': ''
            }]
            
            # Force enable summary/sentiment for direct link if not specified (optional, but good UX)
            # But let's stick to flags to be consistent, or maybe enable them by default for single link?
            # Let's respect flags, but user usually wants to process this link. 
            
            final_news = enrich_news_content(
                filtered, 
                do_translate=args.translate, 
                do_summarize=args.summary, 
                do_sentiment=args.sentiment,
                topic="Direct URL"
            )
            
            if final_news and final_news[0].get('full_text'):
                # Update topic for filename based on extracted title
                safe_topic = "Direct_Link"
                if final_news[0].get('title') != 'URL Processing...':
                     safe_topic = "".join([c if c.isalnum() else "_" for c in final_news[0]['title'][:30]])
                
                display_results_table(final_news, "Direct Link")
                save_to_markdown(final_news, f"Laporan_{safe_topic}.md", final_news[0].get('title', 'Direct Link'))
                if args.json:
                    save_to_json(final_news, f"news_{safe_topic}.json")
            else:
                 console.print("[red]❌ Gagal mengekstrak konten dari URL tersebut.[/red]")
            
            return

        # Watch mode
        if args.watch:
            region = 'id-id' if args.indo else 'wt-wt'
            watch_mode(args.topik, region, args.interval, args.translate, args.summary)
            return
        
        # Normal mode
        region = 'id-id' if args.indo else 'wt-wt'
        raw = search_topic(args.topik, region=region, max_results=args.limit)
        filtered = filter_recent_news(raw, days=2)
        
        if filtered:
            final_news = enrich_news_content(
                filtered, 
                do_translate=args.translate, 
                do_summarize=args.summary, 
                do_sentiment=args.sentiment,
                topic=args.topik
            )
            
            # Display table
            display_results_table(final_news, args.topik)
            
            # Interactive Copy
            if not args.watch: # Don't block watch mode
                try:
                    interactive_copy_selection(final_news)
                except KeyboardInterrupt:
                    pass

            safe_topic = "".join([c if c.isalnum() else "_" for c in args.topik])
            save_to_csv(final_news, f"news_{safe_topic}.csv")
            save_to_markdown(final_news, f"Laporan_{safe_topic}.md", args.topik)
            
            if args.json:
                save_to_json(final_news, f"news_{safe_topic}.json")
        else:
            console.print("[yellow]Tidak ada berita valid.[/yellow]")

if __name__ == "__main__":
    main()
