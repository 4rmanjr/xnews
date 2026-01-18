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
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Third Party Libraries
from dateutil import parser
from duckduckgo_search import DDGS
import trafilatura
import requests
from dotenv import load_dotenv

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

# Groq Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# Suppress Logs & Warnings
warnings.filterwarnings("ignore", message="This package.*renamed.*ddgs")
logging.getLogger('trafilatura').setLevel(logging.WARNING)

# Rich Console Instance
console = Console()

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
            # Twitter-optimized prompt: short, engaging, with emojis
            system_prompt = """Kamu adalah copywriter social media expert. Buat ringkasan berita yang:
1. MAKSIMAL 200 karakter (sangat penting!)
2. Menarik dan engaging seperti tweet viral
3. Gunakan 1-2 emoji yang relevan di awal atau tengah kalimat
4. Bahasa Indonesia yang santai tapi informatif
5. Langsung ke poin utama, tanpa basa-basi

Contoh gaya penulisan:
- "🚀 Tesla catat rekor penjualan! Elon Musk optimis EV bakal dominasi pasar 2026"
- "💰 Bitcoin tembus $100K! Para analis prediksi rally masih berlanjut"
- "🤖 ChatGPT kini bisa 'lihat' dan 'dengar' - revolusi AI makin nyata"

INGAT: Maksimal 200 karakter!"""
            
            user_prompt = f"Buat tweet singkat dari berita ini:\n\n{truncated}"
            max_tokens = 100
        else:
            # Detailed summary prompt with emojis
            system_prompt = f"""Kamu adalah jurnalis berpengalaman. Buat ringkasan berita yang:
1. Terdiri dari {max_sentences} kalimat informatif
2. Gunakan 2-3 emoji yang relevan untuk mempercantik (di awal paragraf atau poin penting)
3. Bahasa Indonesia yang jelas dan profesional
4. Langsung tulis ringkasannya tanpa awalan seperti "Berikut ringkasannya:"

Contoh penggunaan emoji:
- 🚀 untuk teknologi/startup/inovasi
- 💰 untuk bisnis/ekonomi/keuangan
- 🏥 untuk kesehatan
- ⚖️ untuk hukum/politik
- 🌍 untuk isu global/lingkungan
- 📈 untuk pertumbuhan/statistik
- ⚠️ untuk peringatan/masalah"""
            
            user_prompt = f"Ringkaskan berita berikut:\n\n{truncated}"
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
        
        # Ensure Twitter summary doesn't exceed 200 chars
        if for_twitter and len(result) > 200:
            result = result[:197] + "..."
        
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
        safe_topic = topic.replace(" ", "")
        
        system_prompt = """Kamu adalah social media manager profesional yang viral. Buat tweet yang MEMAKSIMALKAN ruang karakter:

ATURAN PENTING:
1. TARGET 240-250 karakter (GUNAKAN SEMUA RUANG, jangan terlalu pendek!)
2. Jika terlalu pendek, TAMBAHKAN detail menarik atau konteks
3. Hook yang menarik perhatian di awal dengan emoji
4. Gunakan 2-3 emoji yang relevan dan eye-catching
5. Gaya bahasa santai, engaging, seperti influencer
6. Buat pembaca penasaran untuk klik link
7. Hindari kalimat generik, buat spesifik dan unik

STRUKTUR IDEAL:
[Emoji] [Hook menarik] + [Fakta/angka spesifik] + [Call to curiosity] [Emoji]

CONTOH BAGUS (240+ karakter):
"🚨 BREAKING: Bitcoin tembus $100K untuk pertama kalinya! Analis prediksi rally masih berlanjut hingga Q2 2026. Apakah ini momentum terbaik untuk masuk? Para whale sudah mulai akumulasi 🐋💰"

JANGAN sertakan hashtag, akan ditambahkan otomatis.
JANGAN gunakan tanda kutip di awal/akhir output."""

        user_prompt = f"""Judul: {title}

Isi berita:
{truncated}

Buat tweet MAKSIMAL yang engaging dari berita di atas. GUNAKAN SEMUA RUANG sampai 250 karakter!"""

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=150  # Increased for longer tweets
        )
        
        tweet_text = response.choices[0].message.content.strip()
        
        # Remove quotes if AI added them
        tweet_text = tweet_text.strip('"\'')
        
        # Add hashtags
        hashtags = f"\n\n#{safe_topic} #BeritaTerkini"
        
        # Ensure total doesn't exceed 280
        max_tweet_len = 280 - len(hashtags)
        if len(tweet_text) > max_tweet_len:
            tweet_text = tweet_text[:max_tweet_len-3] + "..."
        
        return tweet_text + hashtags
        
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
                    keywords=topic, 
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
def save_to_csv(news_list, filename):
    if not news_list:
        return
    ensure_output_dir()
    filepath = os.path.join(OUTPUT_DIR, filename)
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
    filepath = os.path.join(OUTPUT_DIR, filename)
    
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
    """Select emoji based on keywords."""
    text = text.lower()
    if any(k in text for k in ['ai', 'tech', 'robot', 'data', 'cyber', 'app', 'soft', 'hard']):
        return "🤖"
    if any(k in text for k in ['saham', 'uang', 'bisnis', 'ekonomi', 'market', 'stock', 'profit', 'crypto', 'bitcoin', 'btc', 'invest']):
        return "💰"
    if any(k in text for k in ['sehat', 'dokter', 'virus', 'obat', 'medis']):
        return "🏥"
    if any(k in text for k in ['game', 'play', 'esport']):
        return "🎮"
    if any(k in text for k in ['politik', 'presiden', 'hukum', 'negara']):
        return "⚖️"
    return "📢"

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
    remaining_chars = 280 - base_len
    
    if len(summary) > remaining_chars:
        summary = summary[:remaining_chars-3] + "..."
    
    tweet = f"{emoji} {title}\n\n📝 {summary}\n\n{hashtags}"
    return tweet

def save_to_markdown(news_list, filename, topic):
    if not news_list:
        return
    ensure_output_dir()
    filepath = os.path.join(OUTPUT_DIR, filename)
    
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

def display_results_table(news_list):
    """Display results in a rich table."""
    if not news_list:
        return
    
    table = Table(
        title="📊 Hasil Pencarian Berita",
        box=box.ROUNDED,
        show_lines=True
    )
    
    table.add_column("No", style="cyan", width=4)
    table.add_column("Judul", style="white", max_width=50)
    table.add_column("Sumber", style="green", width=15)
    table.add_column("Tanggal", style="yellow", width=12)
    table.add_column("Sentiment", style="magenta", width=10)
    
    for i, news in enumerate(news_list[:10], 1):  # Show max 10 in table
        title = news.get('title', 'N/A')[:47] + "..." if len(news.get('title', '')) > 50 else news.get('title', 'N/A')
        source = news.get('source', 'N/A')[:12]
        date = news.get('formatted_date', 'N/A')[:10]
        sentiment = news.get('sentiment', {})
        sent_str = f"{sentiment.get('emoji', '')} {sentiment.get('label', 'N/A')}"
        
        table.add_row(str(i), title, source, date, sent_str)
    
    console.print(table)
    
    if len(news_list) > 10:
        console.print(f"[dim]... dan {len(news_list) - 10} berita lainnya (lihat file output)[/dim]")

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
    
    console.print(f"Status: {' | '.join(status_items)}\n")
    
    while True:
        try:
            topic = console.input("[bold]📝 Topik berita (atau 'x' untuk keluar): [/bold]").strip()
        except EOFError:
            break
        if topic.lower() == 'x':
            break
        if not topic:
            continue
        
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
        
        # Search & Process
        raw = search_topic(topic, region=region, max_results=20)
        if not raw:
            console.print("[yellow]Tidak ada hasil.[/yellow]")
            continue
        
        filtered = filter_recent_news(raw, days=2)
        if not filtered:
            console.print("[yellow]Tidak ada berita baru (<48 jam).[/yellow]")
            continue
        
        # Enrich
        final_news = enrich_news_content(filtered, do_translate=do_trans, do_summarize=do_summary, do_sentiment=True, topic=topic)
        
        # Display
        display_results_table(final_news)
        
        # Save
        ts = int(time.time())
        safe_topic = "".join([c if c.isalnum() else "_" for c in topic])
        save_to_csv(final_news, f"news_{safe_topic}_{ts}.csv")
        save_to_json(final_news, f"news_{safe_topic}_{ts}.json")
        save_to_markdown(final_news, f"Laporan_{safe_topic}_{ts}.md", topic)
        
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
            display_results_table(final_news)
            
            safe_topic = "".join([c if c.isalnum() else "_" for c in args.topik])
            save_to_csv(final_news, f"news_{safe_topic}.csv")
            save_to_markdown(final_news, f"Laporan_{safe_topic}.md", args.topik)
            
            if args.json:
                save_to_json(final_news, f"news_{safe_topic}.json")
        else:
            console.print("[yellow]Tidak ada berita valid.[/yellow]")

if __name__ == "__main__":
    main()