"""
xnews - Core Fetcher Module
Article fetching, searching, and enrichment.
"""

import os
import re
import time
import shutil
import subprocess
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import trafilatura
import requests
from dateutil import parser
from ddgs import DDGS

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from xnews.config import (
    MAX_RETRIES, RETRY_DELAY, MAX_THREADS, TIMEOUT_SECONDS,
    GROQ_API_KEY, GROQ_MODEL, AI_PROVIDER
)
from xnews.core.cache import cache
from xnews.ai.providers import ai_generate_combined, ai_summarize, GROQ_AVAILABLE
from xnews.utils.text import (
    analyze_sentiment, apply_translation, clean_title, 
    is_duplicate, validate_url
)

console = Console()

# Lazy import for Groq (title generation fallback)
try:
    from groq import Groq
except ImportError:
    Groq = None


def fetch_single_article(
    news_item: dict[str, Any], 
    auto_translate: bool = False, 
    do_summarize: bool = False, 
    do_sentiment: bool = False, 
    topic: str = ""
) -> dict[str, Any]:
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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Referer": "https://www.google.com/",
        }
        
        extracted_text = None
        raw_html = None
        
        # --- LAYER 1: Trafilatura ---
        try:
            raw_html = trafilatura.fetch_url(url)
            if raw_html:
                extracted_text = trafilatura.extract(raw_html, include_comments=False, include_tables=False)
        except (requests.RequestException, OSError) as e:
            console.print(f"[dim]Layer 1 fetch error: {e}[/dim]")
            
        # --- LAYER 2: Requests ---
        if not extracted_text or len(extracted_text) < 200:
            try:
                resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
                raw_html = resp.text
                extracted_text = trafilatura.extract(raw_html, include_comments=False, include_tables=False)
            except requests.exceptions.SSLError:
                console.print(f"[dim]SSL Verify error for {url}. Switching to Layer 3 fallback.[/dim]")
            except (requests.RequestException, OSError) as e:
                console.print(f"[dim]Layer 2 fetch error: {e}[/dim]")

        # --- LAYER 3: cURL ---
        if (not extracted_text or len(extracted_text) < 200) and shutil.which("curl") and validate_url(url):
            try:
                cmd = [
                    "curl", "-s", "-L", 
                    "-A", headers["User-Agent"],
                    "--max-time", str(TIMEOUT_SECONDS),
                    url
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
                if result.returncode == 0 and len(result.stdout) > 500:
                    raw_html = result.stdout
                    extracted_text = trafilatura.extract(raw_html, include_comments=False, include_tables=False)
            except (subprocess.SubprocessError, OSError) as e:
                console.print(f"[dim]Layer 3 cURL error: {e}[/dim]")
        
        # Extract metadata
        downloaded = raw_html
        if extracted_text:
            try:
                metadata = trafilatura.bare_extraction(downloaded)
                if metadata:
                    if metadata.get('title'):
                        news_item['title'] = metadata['title']
                    if metadata.get('date'):
                        news_item['formatted_date'] = metadata['date']
                    if metadata.get('sitename'):
                        news_item['source'] = metadata['sitename']
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Fallback title from <title> tag
        if news_item.get('title') == 'URL Processing...' and downloaded:
            match = re.search(r'<title>([^<]+)</title>', downloaded, re.IGNORECASE)
            if match:
                news_item['title'] = match.group(1).strip()
        
        if extracted_text:
            news_item['full_text'] = extracted_text
            cache.set(url, extracted_text)
    
    # --- Content Processing ---
    text_to_process = news_item.get('full_text', '')
    
    if text_to_process and len(text_to_process) > 100:
        # Translation
        if auto_translate:
            text_to_process = apply_translation(news_item, text_to_process)
            news_item['full_text'] = text_to_process
            news_item['is_translated'] = True
        
        # AI Summary + Tweet (Combined call)
        if do_summarize:
            title = news_item.get('title', topic)
            combined = ai_generate_combined(title, text_to_process, topic)
            news_item['ai_summary'] = combined.get('summary', '')
            news_item['ai_tweet'] = combined.get('tweet', '')
            
            # AI Title generation fallback
            if news_item.get('title') == 'URL Processing...' and GROQ_AVAILABLE and Groq:
                try:
                    from xnews.core.prompts import prompt_loader
                    system_prompt = prompt_loader.get('title_generation', 'system')
                    user_prompt_tpl = prompt_loader.get('title_generation', 'user')
                    if system_prompt and user_prompt_tpl:
                        user_prompt = user_prompt_tpl.format(text=text_to_process[:500])
                        client = Groq(api_key=GROQ_API_KEY)
                        t_resp = client.chat.completions.create(
                            model=GROQ_MODEL, messages=[{"role": "user", "content": user_prompt}], max_tokens=20
                        )
                        generated_title = t_resp.choices[0].message.content.strip().strip('"')
                        if generated_title:
                            news_item['title'] = generated_title
                except (ValueError, AttributeError, KeyError, ConnectionError) as e:
                    console.print(f"[dim]Title generation error: {e}[/dim]")
        
        # Sentiment Analysis
        if do_sentiment:
            news_item['sentiment'] = analyze_sentiment(text_to_process)
    
    return news_item


def enrich_news_content(
    news_list: list[dict[str, Any]], 
    do_translate: bool = False, 
    do_summarize: bool = False, 
    do_sentiment: bool = False, 
    topic: str = ""
) -> list[dict[str, Any]]:
    """Enrich news with full text, translation, summary, sentiment, and AI tweet."""
    if not news_list:
        return []
    
    features: list[str] = []
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
    
    enriched_results: list[dict[str, Any]] = []
    
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
                except (OSError, RuntimeError) as e:
                    console.print(f"[dim]Article fetch error: {e}[/dim]")
                    item = future_to_news[future]
                    item['full_text'] = ""
                    enriched_results.append(item)
                progress.update(task, advance=1)
    
    return enriched_results


def filter_recent_news(news_list: list[dict[str, Any]], days: int = 2) -> list[dict[str, Any]]:
    """Filter news to recent items and remove duplicates."""
    recent_news: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
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


def search_topic(topic: str, region: str = 'wt-wt', max_results: int = 50) -> list[dict[str, Any]]:
    """Search for news on a topic using DuckDuckGo."""
    console.print(f"\n[bold green]🔍 Mencari:[/bold green] '{topic}'")
    
    # Check cache
    cache_key = f"search_{topic}_{region}_{max_results}"
    cached = cache.get(cache_key)
    if cached:
        console.print("[dim]📦 Menggunakan cache...[/dim]")
        return cached
    
    results: list[dict[str, Any]] = []
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
                wait_time = RETRY_DELAY * (2 ** attempt)
                console.print(f"[yellow]⚠ Retry {attempt}/{MAX_RETRIES} in {wait_time}s...[/yellow]")
                time.sleep(wait_time)
    
    if results:
        cache.set(cache_key, results)
    
    return results
