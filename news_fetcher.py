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
import re
from datetime import datetime, timedelta
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Third Party Libraries
from dateutil import parser
from ddgs import DDGS
import trafilatura
import requests
from dotenv import load_dotenv
# Lazy load pyperclip (may fail on Termux/headless systems)
pyperclip = None
PYPERCLIP_AVAILABLE = False

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
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

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
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

# AI Provider Configuration
# Default: groq
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()
if AI_PROVIDER not in ["groq", "gemini"]:
    AI_PROVIDER = "groq"

# Path to .env file for persistence
ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def save_env_setting(key, value):
    """Update or add a setting in the .env file."""
    try:
        lines = []
        found = False
        
        if os.path.exists(ENV_FILE_PATH):
            with open(ENV_FILE_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        
        # Update existing key or mark for addition
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
        
        # Add new key if not found
        if not found:
            lines.append(f"\n{key}={value}\n")
        
        with open(ENV_FILE_PATH, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        return True
    except Exception as e:
        console.print(f"[dim]⚠ Gagal menyimpan ke .env: {e}[/dim]")
        return False

# Suppress Logs & Warnings
warnings.filterwarnings("ignore", message="This package.*renamed.*ddgs")
logging.getLogger('trafilatura').setLevel(logging.WARNING)

# Rich Console Instance
console = Console()

# Termux Detection (Android)
IS_TERMUX = bool(os.environ.get('TERMUX_VERSION') or 
                 (os.environ.get('PREFIX', '').startswith('/data/data/com.termux')))

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
        return hashlib.sha256(key.encode()).hexdigest()
    
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

# --- Internal AI Logic (Isolated) ---

def _groq_summarize(text: str, max_sentences: int = 3, for_twitter: bool = False) -> str:
    """Summarize text using Groq LLM (Original Logic)."""
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return ""
    
    if not text or len(text) < 100:
        return ""
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        truncated = text[:15000] if len(text) > 15000 else text
        
        if for_twitter:
            system_prompt = prompt_loader.get('summary', 'twitter', 'system', default="You are a social media expert.")
            user_prompt_tpl = prompt_loader.get('summary', 'twitter', 'user', default="Summarize this:\n\n{text}")
            user_prompt = user_prompt_tpl.format(text=truncated)
            max_tokens = 1024
        else:
            system_prompt_tpl = prompt_loader.get('summary', 'standard', 'system', default="Summarize in {max_sentences} sentences.")
            try:
                system_prompt = system_prompt_tpl.format(max_sentences=max_sentences)
            except:
                system_prompt = system_prompt_tpl
                
            user_prompt_tpl = prompt_loader.get('summary', 'standard', 'user', default="Summarize:\n\n{text}")
            user_prompt = user_prompt_tpl.format(text=truncated)
            max_tokens = 1024
        
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=max_tokens
        )
        
        result = response.choices[0].message.content.strip()
        if for_twitter and len(result) > 2000:
            result = result[:1997] + "..."
        return result
    except Exception as e:
        console.print(f"[dim]Groq Summary error: {e}[/dim]")
        return ""

def _gemini_summarize(text: str, max_sentences: int = 3, for_twitter: bool = False) -> str:
    """Summarize text using Gemini LLM."""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        return ""
    
    if not text or len(text) < 100:
        return ""
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        truncated = text[:100000] if len(text) > 100000 else text
        
        if for_twitter:
            system_prompt = prompt_loader.get('summary', 'twitter', 'system', default="You are a social media expert.")
            user_prompt_tpl = prompt_loader.get('summary', 'twitter', 'user', default="Summarize this:\n\n{text}")
        else:
            system_prompt_tpl = prompt_loader.get('summary', 'standard', 'system', default="Summarize in {max_sentences} sentences.")
            try:
                system_prompt = system_prompt_tpl.format(max_sentences=max_sentences)
            except:
                system_prompt = system_prompt_tpl
            user_prompt_tpl = prompt_loader.get('summary', 'standard', 'user', default="Summarize:\n\n{text}")
        
        user_prompt = user_prompt_tpl.format(text=truncated)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.5,
                max_output_tokens=2048
            )
        )
        
        result = response.text.strip()
        if for_twitter and len(result) > 2000:
            result = result[:1997] + "..."
        return result
    except Exception as e:
        console.print(f"[dim]Gemini Summary error: {e}[/dim]")
        return ""

# --- Combined Generation (Summary + Tweet in one call) ---

def _groq_generate_combined(title: str, text: str, topic: str) -> dict:
    """Generate both summary and tweet in single Groq API call. Saves 50% quota."""
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return {"tweet": "", "summary": ""}
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        # Optimized: reduced from 15000 to 5000 chars
        truncated = text[:5000] if len(text) > 5000 else text
        
        system_prompt = prompt_loader.get('combined_generation', 'system', 
            default="Output JSON with 'tweet' and 'summary' keys.")
        user_prompt_tpl = prompt_loader.get('combined_generation', 'user', 
            default="Title: {title}\nText: {text}")
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,
            max_tokens=800  # Reduced from 1024+512
        )
        
        raw_output = response.choices[0].message.content.strip()
        
        # Parse JSON from response
        return _parse_combined_json(raw_output)
        
    except Exception as e:
        console.print(f"[dim]Groq Combined error: {e}[/dim]")
        return {"tweet": "", "summary": ""}

def _gemini_generate_combined(title: str, text: str, topic: str) -> dict:
    """Generate both summary and tweet in single Gemini API call. Saves 50% quota."""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        return {"tweet": "", "summary": ""}
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # Optimized: reduced from 30000 to 5000 chars
        truncated = text[:5000] if len(text) > 5000 else text
        
        system_prompt = prompt_loader.get('combined_generation', 'system', 
            default="Output JSON with 'tweet' and 'summary' keys.")
        user_prompt_tpl = prompt_loader.get('combined_generation', 'user', 
            default="Title: {title}\nText: {text}")
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        console.print(f"[dim]📤 Gemini Combined: Sending {len(full_prompt)} chars...[/dim]")

        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.6,
                max_output_tokens=1024
            )
        )
        
        if not response.text:
            console.print(f"[red]❌ Gemini returned empty response[/red]")
            return {"tweet": "", "summary": ""}
        
        raw_output = response.text.strip()
        result = _parse_combined_json(raw_output)
        
        console.print(f"[dim]✅ Gemini Combined: Got tweet ({len(result.get('tweet', ''))} chars) + summary[/dim]")
        return result
        
    except Exception as e:
        console.print(f"[red]❌ Gemini Combined error: {type(e).__name__}: {e}[/red]")
        return {"tweet": "", "summary": ""}

def _parse_combined_json(raw_output: str) -> dict:
    """Parse JSON from AI response with fallback handling."""
    import json
    
    # Clean markdown code blocks if present
    cleaned = raw_output
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].split("```")[0]
    
    cleaned = cleaned.strip()
    
    try:
        data = json.loads(cleaned)
        tweet = data.get("tweet", "").strip().replace('**', '').replace('__', '')
        summary = data.get("summary", "").strip()
        
        if len(tweet) > 2000:
            tweet = tweet[:1997] + "..."
        
        return {"tweet": tweet, "summary": summary}
    except json.JSONDecodeError:
        # Fallback: try to extract content manually
        console.print("[dim]JSON parse failed, using fallback extraction[/dim]")
        return {"tweet": raw_output[:750] if raw_output else "", "summary": ""}

def ai_generate_combined(title: str, text: str, topic: str, provider: str = None) -> dict:
    """Public wrapper for combined AI generation (summary + tweet)."""
    target_provider = provider or AI_PROVIDER
    
    if target_provider == "gemini":
        return _gemini_generate_combined(title, text, topic)
    else:
        return _groq_generate_combined(title, text, topic)

# --- Standalone Tweet Generation (for regenerate feature) ---

def _groq_generate_tweet(title: str, text: str, topic: str) -> str:
    """Generate tweet using Groq (for regenerate only)."""
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return ""
    try:
        client = Groq(api_key=GROQ_API_KEY)
        truncated = text[:5000] if len(text) > 5000 else text
        system_prompt = prompt_loader.get('tweet_generation', 'system', default="You are a twitter expert.")
        user_prompt_tpl = prompt_loader.get('tweet_generation', 'user', default="Title: {title}\nText: {text}")
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,
            max_tokens=300
        )
        
        tweet_text = response.choices[0].message.content.strip()
        tweet_text = tweet_text.strip('"\'').replace('**', '').replace('__', '')
        if len(tweet_text) > 2000:
            tweet_text = tweet_text[:1997] + "..."
        return tweet_text
    except Exception as e:
        console.print(f"[dim]Groq Tweet error: {e}[/dim]")
        return ""

def _gemini_generate_tweet(title: str, text: str, topic: str) -> str:
    """Generate tweet using Gemini."""
    if not GEMINI_AVAILABLE:
        console.print("[red]❌ Gemini SDK tidak tersedia. Install: pip install google-generativeai[/red]")
        return ""
    if not GEMINI_API_KEY:
        console.print("[red]❌ GEMINI_API_KEY tidak ditemukan di .env[/red]")
        return ""
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        truncated = text[:30000] if len(text) > 30000 else text
        
        # Load prompts with debug info
        system_prompt = prompt_loader.get('tweet_generation', 'system')
        user_prompt_tpl = prompt_loader.get('tweet_generation', 'user')
        
        if not system_prompt:
            console.print("[yellow]⚠ prompts.yaml: 'tweet_generation.system' tidak ditemukan, pakai default[/yellow]")
            system_prompt = "You are a twitter expert."
        
        if not user_prompt_tpl:
            console.print("[yellow]⚠ prompts.yaml: 'tweet_generation.user' tidak ditemukan, pakai default[/yellow]")
            user_prompt_tpl = "Title: {title}\nText: {text}"
        
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Debug: Show prompt length
        console.print(f"[dim]📤 Gemini Tweet: Sending {len(full_prompt)} chars to {GEMINI_MODEL}...[/dim]")

        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048
            )
        )
        
        # Check if response has text
        if not response.text:
            console.print(f"[red]❌ Gemini returned empty response. Candidates: {response.candidates}[/red]")
            return ""
        
        tweet_text = response.text.strip()
        tweet_text = tweet_text.strip('"\'').replace('**', '').replace('__', '')
        
        # Debug: Show result length
        console.print(f"[dim]✅ Gemini Tweet: Received {len(tweet_text)} chars[/dim]")
        
        if len(tweet_text) > 2000:
            tweet_text = tweet_text[:1997] + "..."
        return tweet_text
        
    except Exception as e:
        console.print(f"[red]❌ Gemini Tweet Error: {type(e).__name__}: {e}[/red]")
        return ""

# --- Public AI Functions (Wrappers) ---

def ai_summarize(text: str, max_sentences: int = 3, for_twitter: bool = False, provider: str = None) -> str:
    """Public wrapper for AI summarization."""
    target_provider = provider or AI_PROVIDER
    
    if target_provider == "gemini":
        return _gemini_summarize(text, max_sentences, for_twitter)
    else:
        return _groq_summarize(text, max_sentences, for_twitter)

def ai_generate_tweet_text(title: str, text: str, topic: str, provider: str = None) -> str:
    """Public wrapper for AI tweet generation."""
    target_provider = provider or AI_PROVIDER
    
    if target_provider == "gemini":
        return _gemini_generate_tweet(title, text, topic)
    else:
        return _groq_generate_tweet(title, text, topic)

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
    
    if not url or not url.startswith(('http://', 'https://')):
        return news_item
    
    # Check cache first
    cached = cache.get(url)
    if cached:
        news_item['full_text'] = cached
    else:
        # Modern User-Agent headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Referer": "https://www.google.com/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1"
        }
        
        extracted_text = ""
        
        # --- LAYER 1: Trafilatura Native Fetch ---
        try:
            raw_html = trafilatura.fetch_url(url)
            if raw_html:
                extracted_text = trafilatura.extract(raw_html, include_comments=False, include_tables=False)
        except Exception:
            pass
            
        # If Layer 1 failed to produce meaningful text, try Layer 2
        # --- LAYER 2: Requests Library (Better Headers) ---
        if not extracted_text or len(extracted_text) < 200:
            try:
                # SSL verification is enabled for security
                response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS, verify=True)
                if response.status_code == 200:
                    raw_html = response.text
                    extracted_text = trafilatura.extract(raw_html, include_comments=False, include_tables=False)
            except requests.exceptions.SSLError:
                # Log SSL error but continue to Layer 3 (cURL) which might handle it differently
                console.print(f"[dim]SSL Verify error for {url}. Switching to Layer 3 fallback.[/dim]")
            except Exception:
                pass

        # If Layer 2 also failed, try Layer 3
        # --- LAYER 3: System cURL (Linux/Termux Superpower) ---
        # Bypasses many TLS Fingerprint blocks that Python requests fail on
        if (not extracted_text or len(extracted_text) < 200) and shutil.which("curl"):
            try:
                cmd = [
                    "curl", "-s", "-L", 
                    "-A", headers["User-Agent"],
                    "--max-time", str(TIMEOUT_SECONDS),
                    url
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
                if result.returncode == 0 and len(result.stdout) > 500: # Ensure we got substantial data
                    raw_html = result.stdout
                    extracted_text = trafilatura.extract(raw_html, include_comments=False, include_tables=False)
            except Exception:
                pass
        
        # Use whatever raw_html we have for metadata fallback if text extraction failed but we have HTML
        downloaded = locals().get('raw_html', None)
        
        # Fallback to snippet body if extraction failed completely
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
             if (AI_PROVIDER == "groq" and GROQ_API_KEY) or (AI_PROVIDER == "gemini" and GEMINI_API_KEY):
                 def _try_gen_title(prov):
                    try:
                        if prov == "gemini" and GEMINI_API_KEY:
                            genai.configure(api_key=GEMINI_API_KEY)
                            model = genai.GenerativeModel(GEMINI_MODEL)
                            user_prompt_tpl = prompt_loader.get('title_generation', 'user', default="Create title from:\n\n{text}")
                            user_prompt = user_prompt_tpl.format(text=text_to_process[:500])
                            t_resp = model.generate_content(user_prompt, generation_config={"max_output_tokens": 100})
                            return t_resp.text.strip().strip('"')
                        elif prov == "groq" and GROQ_API_KEY:
                            client = Groq(api_key=GROQ_API_KEY)
                            user_prompt_tpl = prompt_loader.get('title_generation', 'user', default="Create title from:\n\n{text}")
                            user_prompt = user_prompt_tpl.format(text=text_to_process[:500])
                            t_resp = client.chat.completions.create(
                                model=GROQ_MODEL, messages=[{"role": "user", "content": user_prompt}], max_tokens=20
                            )
                            return t_resp.choices[0].message.content.strip().strip('"')
                    except:
                        pass
                    return None

                 # Step 1: Active Provider
                 new_title = _try_gen_title(AI_PROVIDER)
                 
                 if new_title:
                    news_item['title'] = new_title

        # AI Summarization + Tweet (Combined in single API call for efficiency)
        if do_summarize and ((AI_PROVIDER == "groq" and GROQ_API_KEY) or (AI_PROVIDER == "gemini" and GEMINI_API_KEY)):
            title = news_item.get('title', '')
            
            # Single API call for both summary and tweet (saves 50% quota)
            combined_result = ai_generate_combined(title, text_to_process, topic)
            
            news_item['ai_summary'] = combined_result.get('summary', '')
            news_item['ai_tweet'] = combined_result.get('tweet', '')
        
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
    """Generate path with date-based subdirectory structure and sanitized filename."""
    # Sanitize filename to prevent path traversal
    filename = re.sub(r'[^\w\.-]', '_', os.path.basename(filename))
    
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
    remaining_chars = 750 - base_len
    
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
                    if len(clean_text) > 10000:
                        clean_text = clean_text[:10000] + "\n\n_... (teks dipotong agar file tidak terlalu besar)_"
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
    
    # Responsive column sizing for narrow terminals (Termux/mobile)
    term_width = shutil.get_terminal_size((80, 20)).columns
    is_narrow = term_width < 100 or IS_TERMUX
    
    title_width = 25 if is_narrow else 40
    source_width = 8 if is_narrow else 12
    
    table = Table(
        title=f"📊 Hasil Pencarian Berita: {topic}",
        box=box.ROUNDED,
        show_lines=True,
        width=min(term_width - 2, 120) if is_narrow else None
    )
    
    table.add_column("No", style="cyan", width=3)
    table.add_column("Judul", style="white", max_width=title_width)
    table.add_column("Sumber", style="green", width=source_width)
    if not is_narrow:
        table.add_column("Sentiment", style="magenta", width=10)
    table.add_column("Action", style="bold blue", justify="center")
    
    for i, news in enumerate(news_list[:10], 1):  # Show max 10 in table
        title = news.get('title', 'N/A')
        max_title_len = title_width - 3
        disp_title = title[:max_title_len] + "..." if len(title) > title_width else title
        source_name = news.get('source', 'N/A')[:source_width]
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
        
        if is_narrow:
            table.add_row(str(i), disp_title, source_link, action_link)
        else:
            table.add_row(str(i), disp_title, source_link, sent_str, action_link)
    
    console.print(table)
    
    if len(news_list) > 10:
        console.print(f"[dim]... dan {len(news_list) - 10} berita lainnya (lihat file output)[/dim]")

def interactive_copy_selection(news_list, topic=""):
    """Interactive prompt to copy content to clipboard or regenerate AI content."""
    if not news_list:
        return

    # Menu yang lebih jelas untuk pengguna awam
    menu_text = """
[bold cyan]1, 2, 3...[/bold cyan]  → Copy draft ke clipboard (siap paste ke X/Twitter)
[bold magenta]r1, r2...[/bold magenta]  → Regenerate ulang jika kurang puas
[bold green]Enter[/bold green]      → Kembali ke pencarian baru
"""
    console.print(Panel(menu_text.strip(), title="📋 Apa yang mau dilakukan?", border_style="yellow"))
    
    while True:
        choice = console.input("\n[bold]Pilih > [/bold]").strip()
        
        if not choice:
            console.print("[dim]🔄 Kembali ke menu pencarian...[/dim]")
            break
        
        # --- REGENERATE COMMAND (r1, r2, etc.) ---
        if choice.lower().startswith('r') and len(choice) > 1 and choice[1:].isdigit():
            idx = int(choice[1:]) - 1
            if 0 <= idx < len(news_list):
                item = news_list[idx]
                console.print(f"\n[yellow]🔄 Regenerating AI content for article #{idx+1}...[/yellow]")
                
                # Get stored text (already downloaded, no re-fetch needed)
                text = item.get('full_text') or item.get('body', '')
                title = item.get('title', '')
                
                if text and len(text) > 50:
                    # Regenerate AI Tweet (primary output)
                    console.print("[dim]Generating new tweet draft...[/dim]")
                    new_tweet = ai_generate_tweet_text(title, text, topic)
                    
                    if new_tweet:
                        item['ai_tweet'] = new_tweet
                        console.print(f"\n[green]✅ Regenerated successfully![/green]")
                        console.print(Panel(new_tweet, title="🐦 New Draft", border_style="cyan"))
                        console.print(f"[dim]{len(new_tweet)} karakter[/dim]")
                        console.print(f"[yellow]💡 Ketik '{idx+1}' untuk copy ke clipboard, atau 'r{idx+1}' untuk regenerate lagi[/yellow]")
                    else:
                        console.print("[red]❌ Gagal generate. Cek API key dan quota.[/red]")
                else:
                    console.print("[red]❌ Tidak ada teks artikel untuk di-regenerate.[/red]")
            else:
                console.print(f"[red]❌ Nomor {choice[1:]} tidak ada.[/red]")
            continue
        
        # --- COPY COMMAND (just number) ---
        if not choice.isdigit():
            console.print("[red]❌ Masukkan nomor yang valid atau 'r + nomor'![/red]")
            continue
            
        idx = int(choice) - 1
        if 0 <= idx < len(news_list):
            item = news_list[idx]
            # Prioritize AI Tweet, then AI Summary, then Full Text
            content = item.get('ai_tweet') or item.get('ai_summary') or item.get('full_text') or ""
            
            if content:
                try:
                    # Termux Clipboard (priority for Android)
                    if IS_TERMUX or shutil.which("termux-clipboard-set"):
                        subprocess.run(
                            ["termux-clipboard-set", content], 
                            check=True,
                            input=content.encode('utf-8')
                        )
                        clipboard_method = "Termux API"
                    else:
                        # Lazy-load pyperclip on desktop
                        global pyperclip, PYPERCLIP_AVAILABLE
                        if pyperclip is None:
                            try:
                                import pyperclip as _pyperclip
                                pyperclip = _pyperclip
                                PYPERCLIP_AVAILABLE = True
                            except Exception:
                                PYPERCLIP_AVAILABLE = False
                        
                        if PYPERCLIP_AVAILABLE:
                            pyperclip.copy(content)
                            clipboard_method = "System Clipboard"
                        else:
                            raise Exception("No clipboard backend available")
                        
                    title_preview = item.get('title', 'No Title')[:20]
                    console.print(f"[green]✅ Tersalin ({clipboard_method}):[/green] {title_preview}...")
                    console.print("[dim](Paste di Twitter/X atau medsos lain)[/dim]")
                except Exception as e:
                    console.print(f"[red]❌ Gagal copy: {e}[/red]")
                    if IS_TERMUX:
                        console.print("[dim]Di Termux: pkg install termux-api, lalu install app Termux:API dari F-Droid.[/dim]")
                    else:
                        console.print("[dim]Di Linux pastikan xclip/xsel ada (apt install xclip).[/dim]")
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
    global AI_PROVIDER, GROQ_MODEL, GEMINI_MODEL
    print_banner()
    
    # Show status
    status_items = []
    if GROQ_API_KEY:
        status_items.append("[green]✓ Groq[/green]")
    else:
        status_items.append("[red]✗ Groq[/red]")
        
    if GEMINI_API_KEY:
        status_items.append("[green]✓ Gemini[/green]")
    else:
        status_items.append("[red]✗ Gemini[/red]")
    
    current_ai = AI_PROVIDER.upper()
    current_model = GROQ_MODEL if AI_PROVIDER == "groq" else GEMINI_MODEL
    status_items.append(f"[bold yellow]Active: {current_ai}[/bold yellow] ({current_model})")

    if TEXTBLOB_AVAILABLE:
        status_items.append("[green]✓ Sentiment[/green]")
    if YAML_AVAILABLE:
        status_items.append("[green]✓ Custom Prompts[/green]")
    else:
        status_items.append("[yellow]⚠ Default Prompts (no yaml)[/yellow]")
    if IS_TERMUX:
        status_items.append("[cyan]📱 Termux[/cyan]")
    
    console.print(f"Status: {' | '.join(status_items)}\n")
    
    while True:
        try:
            # Active AI Indicator
            active_info = f"[bold cyan]AI: {AI_PROVIDER.upper()}[/bold cyan] ([dim]{GROQ_MODEL if AI_PROVIDER == 'groq' else GEMINI_MODEL}[/dim])"
            console.print(f"\n{active_info} ─── 🔍 [bold cyan]Pencarian Baru[/bold cyan]")
            console.print("[dim]Ketik 'info' untuk bantuan | 'x' Keluar[/dim]")
            topic = console.input("[bold]📝 Masukkan Topik atau URL: [/bold]").strip()
        except EOFError:
            break
        if topic.lower() == 'x':
            break
        
        if topic.lower() == 'info':
            help_panel = """
[bold green]Perintah Interactive Mode:[/bold green]
• [bold]ai groq[/bold]     : Gunakan AI dari Groq (Default)
• [bold]ai gemini[/bold]   : Gunakan AI dari Google Gemini
• [bold]model [nama][/bold] : Ganti model AI yang sedang aktif
• [bold]x[/bold]            : Keluar dari aplikasi

[bold yellow]Model Terpopuler:[/bold yellow]
- [cyan]Groq:[/cyan] llama-3.3-70b-versatile, mixtral-8x7b-32768
- [cyan]Gemini:[/cyan] gemini-2.0-flash-001, gemini-3-pro-preview, gemini-3-flash-preview
            """
            console.print(Panel(help_panel.strip(), title="ℹ️ Bantuan Perintah", border_style="cyan"))
            continue

        # --- Tambahan: Switch AI Provider via Command ---
        if topic.lower().startswith("ai "):
            cmd_parts = topic.split()
            if len(cmd_parts) >= 2:
                new_provider = cmd_parts[1].lower()
                if new_provider in ["groq", "gemini"]:
                    AI_PROVIDER = new_provider
                    # Reset model to default when provider changes to avoid mismatch
                    if AI_PROVIDER == "groq":
                        GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
                    else:
                        GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
                    
                    # Auto-save to .env for persistence
                    if save_env_setting("AI_PROVIDER", new_provider):
                        console.print(f"[bold green]✅ Provider berhasil diubah ke: {AI_PROVIDER.upper()}[/bold green]")
                        console.print(f"[dim]💾 Tersimpan ke .env (akan aktif saat restart)[/dim]")
                    else:
                        console.print(f"[bold green]✅ Provider berhasil diubah ke: {AI_PROVIDER.upper()}[/bold green]")
                    
                    console.print(f"[dim]Model default: {GROQ_MODEL if AI_PROVIDER == 'groq' else GEMINI_MODEL}[/dim]")
                    
                    ai_key = GROQ_API_KEY if AI_PROVIDER == "groq" else GEMINI_API_KEY
                    if not ai_key:
                        console.print(f"[yellow]⚠️  Peringatan: {AI_PROVIDER.upper()}_API_KEY belum diatur![/yellow]")
                    continue
                else:
                    console.print("[red]❌ Provider tidak dikenal. Pilih: groq atau gemini[/red]")
                    continue

        # --- Tambahan: Switch AI Model via Command ---
        if topic.lower().startswith("model "):
            cmd_parts = topic.split(maxsplit=1)
            if len(cmd_parts) >= 2:
                new_model = cmd_parts[1].strip()
                
                # Basic Validation to prevent mismatch (User typing 'gemini' for Groq)
                if AI_PROVIDER == "groq" and "gemini" in new_model.lower():
                    console.print("[yellow]⚠️  Sepertinya Anda mencoba memakai model Gemini di provider Groq.[/yellow]")
                    console.print("[yellow]   Ketik 'ai gemini' dulu jika ingin pindah ke Gemini.[/yellow]")
                    continue
                elif AI_PROVIDER == "gemini" and ("llama" in new_model.lower() or "mixtral" in new_model.lower()):
                    console.print("[yellow]⚠️  Sepertinya Anda mencoba memakai model Llama/Groq di provider Gemini.[/yellow]")
                    console.print("[yellow]   Ketik 'ai groq' dulu jika ingin pindah ke Groq.[/yellow]")
                    continue

                if AI_PROVIDER == "groq":
                    GROQ_MODEL = new_model
                else:
                    GEMINI_MODEL = new_model
                console.print(f"[bold green]✅ Model {AI_PROVIDER.upper()} diubah ke: {new_model}[/bold green]")
                continue

        if not topic:
            continue
        
        # URL Check in Interactive Mode
        is_url = topic.startswith(('http://', 'https://'))
        
        # SMART DEFAULTS: No more questions - just process!
        region = 'wt-wt'  # Always global search
        do_trans = True   # Always translate to Indonesian
        do_summary = (AI_PROVIDER == "groq" and GROQ_API_KEY) or (AI_PROVIDER == "gemini" and GEMINI_API_KEY)
        
        # Search or URL Processing
        if is_url:
            console.print(f"\n[dim]⚡ Mengekstrak konten dari URL...[/dim]")
            filtered = [{
                'url': topic,
                'title': 'URL Processing...',
                'source': 'Direct Link',
                'formatted_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'body': ''
            }]
            actual_topic = "Direct Link"
        else:
            console.print(f"\n[dim]🔍 Mencari berita tentang '{topic}'...[/dim]")
            raw = search_topic(topic, region=region, max_results=10)
            if not raw:
                console.print("[yellow]Tidak ada hasil.[/yellow]")
                continue
            
            filtered = filter_recent_news(raw, days=2)
            if not filtered:
                console.print("[yellow]Tidak ada berita baru (<48 jam).[/yellow]")
                continue
            actual_topic = topic
        
        # Enrich with AI (always on if API available)
        console.print(f"[dim]🧠 Memproses dengan AI {AI_PROVIDER.upper()}...[/dim]")
        final_news = enrich_news_content(filtered, do_translate=do_trans, do_summarize=do_summary, do_sentiment=True, topic=actual_topic)
        
        if is_url and not (final_news and final_news[0].get('full_text')):
            console.print("[red]❌ Gagal mengekstrak konten dari URL tersebut.[/red]")
            continue

        # === NEW STREAMLINED OUTPUT ===
        current_idx = 0
        total_articles = len(final_news)
        
        while True:
            article = final_news[current_idx]
            draft = article.get('ai_tweet') or article.get('ai_summary') or ''
            
            # Display current draft
            console.print(f"\n[bold cyan]📰 Artikel {current_idx + 1}/{total_articles}:[/bold cyan] {article.get('title', 'N/A')[:60]}...")
            console.print(f"[dim]{article.get('source', '')} • {article.get('formatted_date', '')}[/dim]")
            
            if draft:
                console.print(Panel(draft, title="🐦 Draft untuk X/Twitter", border_style="cyan"))
                console.print(f"[dim]{len(draft)} karakter[/dim]")
            else:
                console.print("[yellow]⚠ Tidak ada draft tersedia untuk artikel ini.[/yellow]")
            
            # Action menu
            menu_text = f"""
[bold cyan]c[/bold cyan] → Copy ke clipboard
[bold magenta]r[/bold magenta] → Regenerate draft
[bold yellow]n[/bold yellow] → Artikel berikutnya ({current_idx + 1}/{total_articles})
[bold green]Enter[/bold green] → Selesai, cari topik baru
"""
            console.print(Panel(menu_text.strip(), title="⚡ Aksi", border_style="yellow"))
            
            action = console.input("[bold]Pilih > [/bold]").strip().lower()
            
            if not action:  # Enter = done
                break
            
            elif action == 'c':  # Copy
                if draft:
                    try:
                        if IS_TERMUX or shutil.which("termux-clipboard-set"):
                            subprocess.run(["termux-clipboard-set"], input=draft.encode('utf-8'), check=True)
                            console.print("[green]✅ Tersalin ke clipboard (Termux)! Paste ke X/Twitter.[/green]")
                        else:
                            global pyperclip, PYPERCLIP_AVAILABLE
                            if pyperclip is None:
                                try:
                                    import pyperclip as _pyperclip
                                    pyperclip = _pyperclip
                                    PYPERCLIP_AVAILABLE = True
                                except:
                                    PYPERCLIP_AVAILABLE = False
                            if PYPERCLIP_AVAILABLE:
                                pyperclip.copy(draft)
                                console.print("[green]✅ Tersalin ke clipboard! Paste ke X/Twitter.[/green]")
                            else:
                                console.print("[red]❌ Clipboard tidak tersedia.[/red]")
                    except Exception as e:
                        console.print(f"[red]❌ Gagal copy: {e}[/red]")
                else:
                    console.print("[yellow]⚠ Tidak ada draft untuk dicopy.[/yellow]")
            
            elif action == 'r':  # Regenerate
                text = article.get('full_text') or article.get('body', '')
                title = article.get('title', '')
                if text and len(text) > 50:
                    console.print("[dim]🔄 Regenerating...[/dim]")
                    new_tweet = ai_generate_tweet_text(title, text, actual_topic)
                    if new_tweet:
                        article['ai_tweet'] = new_tweet
                        console.print(f"[green]✅ Regenerated![/green]")
                    else:
                        console.print("[red]❌ Regenerate gagal. Cek quota API.[/red]")
                else:
                    console.print("[red]❌ Tidak ada teks untuk regenerate.[/red]")
            
            elif action == 'n':  # Next article
                current_idx = (current_idx + 1) % total_articles
                console.print(f"[dim]→ Pindah ke artikel {current_idx + 1}[/dim]")
            
            else:
                console.print("[dim]Perintah tidak dikenal. Ketik c/r/n atau Enter.[/dim]")
        
        # Save reports
        ts = int(time.time())
        if is_url and final_news[0].get('title') != 'URL Processing...':
            safe_topic = "".join([c if c.isalnum() else "_" for c in final_news[0]['title'][:30]])
        else:
            safe_topic = "".join([c if c.isalnum() else "_" for c in topic[:30]])
        
        save_to_csv(final_news, f"news_{safe_topic}_{ts}.csv")
        save_to_json(final_news, f"news_{safe_topic}_{ts}.json")
        save_to_markdown(final_news, f"Laporan_{safe_topic}_{ts}.md", final_news[0].get('title', actual_topic))
        
        console.print("\n" + "─" * 50 + "\n")

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
    parser_arg.add_argument("--summary", action="store_true", help="Aktifkan AI Summarization (Groq/Gemini)")
    parser_arg.add_argument("--provider", type=str, choices=["groq", "gemini"], help="Pilih AI provider (default: dari .env atau groq)")
    parser_arg.add_argument("--gemini", action="store_true", help="Shortcut untuk menggunakan Gemini AI")
    parser_arg.add_argument("--sentiment", action="store_true", help="Aktifkan Sentiment Analysis")
    parser_arg.add_argument("--limit", type=int, default=50, help="Jumlah maksimal berita (default: 50)")
    parser_arg.add_argument("--json", action="store_true", help="Export ke format JSON")
    parser_arg.add_argument("--watch", action="store_true", help="Mode watch (monitoring berkelanjutan)")
    parser_arg.add_argument("--interval", type=int, default=30, help="Interval watch mode dalam menit (default: 30)")
    parser_arg.add_argument("--clear-cache", action="store_true", help="Hapus cache")
    
    args = parser_arg.parse_args()
    
    # Update AI Provider from args
    global AI_PROVIDER
    if args.gemini:
        AI_PROVIDER = "gemini"
    elif args.provider:
        AI_PROVIDER = args.provider
    
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
                    interactive_copy_selection(final_news, args.topik)
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
