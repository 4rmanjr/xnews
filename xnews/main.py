"""
xnews - Smart News Fetcher Turbo v2.0
Main entry point and CLI interface.

This modular version imports from the xnews package structure.
For backward compatibility, the original news_fetcher.py is preserved.
"""

import argparse
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich import box

# Import from modular structure
from xnews.config import (
    AI_PROVIDER, GROQ_API_KEY, GROQ_MODEL, GROQ_MODELS,
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_MODELS,
    save_env_setting, update_runtime_config, IS_TERMUX
)
from xnews.core.cache import cache
from xnews.core.fetcher import (
    search_topic, filter_recent_news, enrich_news_content, fetch_single_article
)
from xnews.ai.providers import ai_generate_tweet_text, GROQ_AVAILABLE, GEMINI_AVAILABLE
from xnews.utils.export import save_to_csv, save_to_json, save_to_markdown, generate_tweet_url
from xnews.utils.text import get_relevant_emoji

console = Console()


def print_banner() -> None:
    """Print application banner."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║     🚀 XNEWS - Smart News Fetcher Turbo v2.0                 ║
║     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━      ║
║     ✨ AI Summarization • Sentiment Analysis • Rich UI       ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(Panel(banner.strip(), style="bold cyan", box=box.DOUBLE))


def ai_settings_menu() -> None:
    """Interactive AI settings menu."""
    # Import mutable globals
    import xnews.config as config
    
    while True:
        groq_status = "[green]✅ Ready[/green]" if GROQ_API_KEY else "[red]❌ No API Key[/red]"
        gemini_status = "[green]✅ Ready[/green]" if GEMINI_API_KEY else "[red]❌ No API Key[/red]"
        groq_active = " [bold yellow]◀ ACTIVE[/bold yellow]" if config.AI_PROVIDER == "groq" else ""
        gemini_active = " [bold yellow]◀ ACTIVE[/bold yellow]" if config.AI_PROVIDER == "gemini" else ""
        current_model = config.GROQ_MODEL if config.AI_PROVIDER == "groq" else config.GEMINI_MODEL
        
        panel_content = f"""
[bold cyan]═══ AI Configuration ═══[/bold cyan]

[bold]Active Provider:[/bold] [yellow]{config.AI_PROVIDER.upper()}[/yellow]
[bold]Active Model:[/bold] [cyan]{current_model}[/cyan]

[dim]─── Providers ───[/dim]
[bold][1][/bold] Groq   {groq_status}{groq_active}
[bold][2][/bold] Gemini {gemini_status}{gemini_active}

[dim]─── Actions ───[/dim]
[bold][m][/bold] Change Model
[bold][s][/bold] Save to .env
[bold][x][/bold] Back
        """
        console.print(Panel(panel_content.strip(), title="🤖 AI Settings", border_style="cyan"))
        
        choice = console.input("[bold]Select > [/bold]").strip().lower()
        
        if choice == 'x' or not choice:
            break
        elif choice == '1':
            if not GROQ_API_KEY:
                console.print("[yellow]⚠️  GROQ_API_KEY belum diatur di .env[/yellow]")
                continue
            config.AI_PROVIDER = "groq"
            save_env_setting("AI_PROVIDER", "groq")
            console.print(f"[bold green]✅ Switched to GROQ[/bold green]")
        elif choice == '2':
            if not GEMINI_API_KEY:
                console.print("[yellow]⚠️  GEMINI_API_KEY belum diatur di .env[/yellow]")
                continue
            config.AI_PROVIDER = "gemini"
            save_env_setting("AI_PROVIDER", "gemini")
            console.print(f"[bold green]✅ Switched to GEMINI[/bold green]")
        elif choice == 'm':
            models = GROQ_MODELS if config.AI_PROVIDER == "groq" else GEMINI_MODELS
            current = config.GROQ_MODEL if config.AI_PROVIDER == "groq" else config.GEMINI_MODEL
            
            console.print(f"\n[bold cyan]Models untuk {config.AI_PROVIDER.upper()}:[/bold cyan]")
            for i, model in enumerate(models, 1):
                active_mark = " [yellow]◀ current[/yellow]" if model == current else ""
                console.print(f"  [bold][{i}][/bold] {model}{active_mark}")
            
            model_choice = console.input("\n[bold]Pilih model > [/bold]").strip()
            try:
                idx = int(model_choice) - 1
                if 0 <= idx < len(models):
                    new_model = models[idx]
                    if config.AI_PROVIDER == "groq":
                        config.GROQ_MODEL = new_model
                    else:
                        config.GEMINI_MODEL = new_model
                    console.print(f"[green]✅ Model changed to: {new_model}[/green]")
            except (ValueError, IndexError):
                pass
        elif choice == 's':
            save_env_setting("AI_PROVIDER", config.AI_PROVIDER)
            if config.AI_PROVIDER == "groq":
                save_env_setting("GROQ_MODEL", config.GROQ_MODEL)
            else:
                save_env_setting("GEMINI_MODEL", config.GEMINI_MODEL)
            console.print("[green]✅ Settings saved to .env[/green]")


def interactive_mode() -> None:
    """Interactive command-line interface."""
    import xnews.config as config
    
    print_banner()
    
    console.print("\n[bold]📋 Menu:[/bold]")
    console.print("  [cyan]Enter topic[/cyan] - Cari berita")
    console.print("  [cyan]ai[/cyan]          - AI settings")
    console.print("  [cyan]clear[/cyan]       - Hapus cache")
    console.print("  [cyan]exit/q[/cyan]      - Keluar")
    
    while True:
        try:
            query = console.input("\n[bold green]🔎 Cari berita > [/bold green]").strip()
            
            if not query:
                continue
            if query.lower() in ['exit', 'quit', 'q']:
                console.print("[yellow]👋 Sampai jumpa![/yellow]")
                break
            if query.lower() == 'ai':
                ai_settings_menu()
                continue
            if query.lower() == 'clear':
                cache.clear()
                console.print("[green]✅ Cache cleared![/green]")
                continue
            
            # Search and process
            raw_results = search_topic(query, max_results=20)
            if not raw_results:
                console.print("[yellow]❌ Tidak ditemukan berita.[/yellow]")
                continue
            
            filtered = filter_recent_news(raw_results, days=3)
            console.print(f"[dim]📰 {len(filtered)} berita ditemukan[/dim]")
            
            # Ask for enrichment options
            console.print("\n[bold]Opsi:[/bold] [1] Quick [2] +Translate [3] +AI Summary [4] Full")
            opt = console.input("[bold]Pilih > [/bold]").strip()
            
            do_translate = opt in ['2', '4']
            do_summarize = opt in ['3', '4']
            do_sentiment = opt in ['4']
            
            # Enrich content
            enriched = enrich_news_content(
                filtered[:10], 
                do_translate=do_translate,
                do_summarize=do_summarize,
                do_sentiment=do_sentiment,
                topic=query
            )
            
            # Display results
            for i, news in enumerate(enriched[:5], 1):
                console.print(f"\n[bold cyan]{i}. {news.get('title', 'N/A')}[/bold cyan]")
                console.print(f"   [dim]{news.get('source', '')} | {news.get('formatted_date', '')}[/dim]")
                if news.get('ai_summary'):
                    console.print(f"   [green]→ {news.get('ai_summary')}[/green]")
                if news.get('ai_tweet'):
                    console.print(f"   [magenta]🐦 {news.get('ai_tweet')[:100]}...[/magenta]")
            
            # Save options
            console.print("\n[bold]Save:[/bold] [c]CSV [j]JSON [m]Markdown [n]Skip")
            save_opt = console.input("[bold]> [/bold]").strip().lower()
            
            safe_topic = query.replace(' ', '_')[:20]
            if 'c' in save_opt:
                save_to_csv(enriched, f"{safe_topic}_news.csv")
            if 'j' in save_opt:
                save_to_json(enriched, f"{safe_topic}_news.json")
            if 'm' in save_opt:
                save_to_markdown(enriched, f"{safe_topic}_news.md", query)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]👋 Interrupted. Bye![/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def main() -> None:
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="xnews - Smart News Fetcher Turbo v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('topic', nargs='?', help='Search topic')
    parser.add_argument('--translate', '-t', action='store_true', help='Auto-translate to Indonesian')
    parser.add_argument('--summary', '-s', action='store_true', help='Generate AI summaries')
    parser.add_argument('--sentiment', action='store_true', help='Analyze sentiment')
    parser.add_argument('--json', '-j', action='store_true', help='Export to JSON')
    parser.add_argument('--csv', '-c', action='store_true', help='Export to CSV')
    parser.add_argument('--markdown', '-m', action='store_true', help='Export to Markdown')
    parser.add_argument('--limit', '-l', type=int, default=10, help='Max results')
    parser.add_argument('--watch', '-w', action='store_true', help='Watch mode')
    parser.add_argument('--interval', '-i', type=int, default=30, help='Watch interval (minutes)')
    parser.add_argument('--clear-cache', action='store_true', help='Clear cache')
    parser.add_argument('--url', '-u', help='Process single URL')
    
    args = parser.parse_args()
    
    # Clear cache
    if args.clear_cache:
        cache.clear()
        console.print("[green]✅ Cache cleared![/green]")
        return
    
    # Interactive mode if no topic
    if not args.topic and not args.url:
        interactive_mode()
        return
    
    # Process single URL
    if args.url:
        print_banner()
        console.print(f"[bold]🔗 Processing URL:[/bold] {args.url}")
        news_item = {
            'url': args.url,
            'title': 'URL Processing...',
            'source': 'Direct URL',
            'formatted_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        result = fetch_single_article(
            news_item, 
            auto_translate=args.translate,
            do_summarize=args.summary,
            do_sentiment=args.sentiment,
            topic=args.topic or "news"
        )
        
        console.print(f"\n[bold cyan]{result.get('title')}[/bold cyan]")
        if result.get('ai_summary'):
            console.print(f"[green]→ {result.get('ai_summary')}[/green]")
        if result.get('ai_tweet'):
            console.print(f"\n[bold magenta]🐦 Tweet Draft:[/bold magenta]")
            console.print(result.get('ai_tweet'))
        return
    
    # Search mode
    print_banner()
    raw_results = search_topic(args.topic, max_results=args.limit * 2)
    
    if not raw_results:
        console.print("[yellow]❌ No results found.[/yellow]")
        return
    
    filtered = filter_recent_news(raw_results, days=3)[:args.limit]
    console.print(f"[dim]📰 {len(filtered)} articles found[/dim]")
    
    enriched = enrich_news_content(
        filtered,
        do_translate=args.translate,
        do_summarize=args.summary,
        do_sentiment=args.sentiment,
        topic=args.topic
    )
    
    # Display results
    for i, news in enumerate(enriched[:5], 1):
        console.print(f"\n[bold cyan]{i}. {news.get('title', 'N/A')}[/bold cyan]")
        if news.get('ai_summary'):
            console.print(f"   [green]→ {news.get('ai_summary')}[/green]")
    
    # Export
    safe_topic = args.topic.replace(' ', '_')[:20]
    if args.json:
        save_to_json(enriched, f"{safe_topic}_news.json")
    if args.csv:
        save_to_csv(enriched, f"{safe_topic}_news.csv")
    if args.markdown:
        save_to_markdown(enriched, f"{safe_topic}_news.md", args.topic)


if __name__ == "__main__":
    main()
