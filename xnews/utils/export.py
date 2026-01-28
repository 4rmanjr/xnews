"""
xnews - Export Utilities Module
Save news results to CSV, JSON, and Markdown formats.
"""

import os
import re
import csv
import json
import urllib.parse
from datetime import datetime
from typing import Any

from rich.console import Console

from xnews.config import OUTPUT_DIR

console = Console()


def ensure_output_dir() -> None:
    """Create output directory if it doesn't exist."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)


def get_dated_output_path(filename: str) -> str:
    """Generate path with date-based subdirectory structure and sanitized filename."""
    # Sanitize filename to prevent path traversal
    filename = re.sub(r'[^\w\.-]', '_', os.path.basename(filename))
    
    today = datetime.now().strftime('%Y-%m-%d')
    target_dir = os.path.join(OUTPUT_DIR, today)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    return os.path.join(target_dir, filename)


def save_to_csv(news_list: list[dict[str, Any]], filename: str) -> None:
    """Save news list to CSV file."""
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


def save_to_json(news_list: list[dict[str, Any]], filename: str) -> None:
    """Save news list to JSON file."""
    if not news_list:
        return
    ensure_output_dir()
    filepath = get_dated_output_path(filename)
    
    # Clean data for JSON
    export_data: list[dict[str, Any]] = []
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


def save_to_markdown(news_list: list[dict[str, Any]], filename: str, topic: str = "") -> None:
    """Save news list to Markdown file."""
    if not news_list:
        return
    ensure_output_dir()
    filepath = get_dated_output_path(filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 📰 News Report: {topic or 'Latest News'}\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Total Articles:** {len(news_list)}\n\n")
            f.write("---\n\n")
            
            for i, item in enumerate(news_list, 1):
                sentiment = item.get('sentiment', {})
                f.write(f"## {i}. {item.get('title', 'No Title')}\n\n")
                f.write(f"**Source:** {item.get('source', 'Unknown')} | ")
                f.write(f"**Date:** {item.get('formatted_date', 'N/A')} | ")
                f.write(f"**Sentiment:** {sentiment.get('emoji', '❓')} {sentiment.get('label', 'Unknown')}\n\n")
                
                if item.get('ai_summary'):
                    f.write(f"**Summary:** {item['ai_summary']}\n\n")
                
                if item.get('ai_tweet'):
                    f.write(f"**Tweet Draft:** {item['ai_tweet']}\n\n")
                
                f.write(f"🔗 [Read More]({item.get('url', '#')})\n\n")
                f.write("---\n\n")
        
        console.print(f"[green]✅ Markdown tersimpan:[/green] {filepath}")
    except IOError as e:
        console.print(f"[red]❌ Gagal Markdown: {e}[/red]")


def generate_tweet_url(text: str, url: str = "") -> str:
    """Generate Twitter/X intent URL for sharing."""
    tweet_content = text
    if url:
        tweet_content = f"{text}\n\n{url}"
    
    encoded = urllib.parse.quote(tweet_content, safe='')
    return f"https://twitter.com/intent/tweet?text={encoded}"
