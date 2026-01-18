#!/usr/bin/env python3
import csv
import argparse
import sys
import time
import difflib
import random
import warnings
from datetime import datetime, timedelta
from dateutil import parser
from duckduckgo_search import DDGS

# Abaikan warning rename package agar tampilan bersih
warnings.filterwarnings("ignore", message="This package.*renamed.*ddgs")

# --- Konfigurasi ---
MAX_RETRIES = 3
RETRY_DELAY = 2  # detik

# --- Warna untuk Tampilan Terminal ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_banner():
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("="*60)
    print("   PENCARI BERITA PINTAR & FAKTUAL (Smart News Fetcher)")
    print("   (Fitur: Deduplikasi, Auto-Retry, Filter < 48 Jam)")
    print("="*60)
    print(f"{Colors.ENDC}")

def clean_title(title):
    """Membersihkan judul untuk perbandingan (lowercase, hapus tanda baca umum)."""
    return title.lower().strip()

def is_duplicate(news_item, existing_titles, threshold=0.85):
    """
Mengecek apakah berita duplikat berdasarkan kemiripan judul.
    Menggunakan SequenceMatcher untuk mendeteksi judul yang mirip.
    """
    title = clean_title(news_item.get('title', ''))
    
    # Cek duplikat persis
    if title in existing_titles:
        return True
    
    # Cek kemiripan (fuzzy matching)
    # Ini membuat agen "Pintar" membedakan berita yang sama tapi judul sedikit beda
    for existing in existing_titles:
        ratio = difflib.SequenceMatcher(None, title, existing).ratio()
        if ratio > threshold:
            return True
            
    return False

def filter_recent_news(news_list, days=2):
    """
    Menyaring berita agar hanya menyertakan yang dipublikasikan dalam X hari terakhir.
    Juga melakukan DEDUPLIKASI berita.
    """
    recent_news = []
    seen_titles = set()
    
    cutoff_date = datetime.now().astimezone() - timedelta(days=days)
    
    print(f"[*] Menyaring berita & menghapus duplikat (cutoff: {cutoff_date.strftime('%Y-%m-%d %H:%M')})...")

    for item in news_list:
        date_str = item.get('date')
        if not date_str:
            continue

        try:
            # Parsing tanggal yang fleksibel
            pub_date = parser.parse(date_str)
            
            # Pastikan zona waktu sinkron
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
            
            # Cek rentang waktu
            if pub_date >= cutoff_date:
                # Cek Duplikasi ("Smart Feature")
                if is_duplicate(item, seen_titles):
                    continue

                # Simpan judul untuk cek berikutnya
                seen_titles.add(clean_title(item.get('title', '')))
                
                # Simpan objek datetime asli untuk sorting yang akurat
                item['_raw_date'] = pub_date
                
                # Format ulang untuk tampilan
                item['formatted_date'] = pub_date.strftime('%Y-%m-%d %H:%M:%S')
                item['body'] = item.get('body', '') 
                
                recent_news.append(item)
                
        except (ValueError, TypeError):
            continue
    
    # Sorting: Berita Terbaru di Atas (Descending)
    recent_news.sort(key=lambda x: x.get('_raw_date', datetime.min), reverse=True)
            
    return recent_news

def search_topic(topic, region='wt-wt', max_results=50):
    """
    Mencari berita menggunakan DuckDuckGo News Search dengan Retry Logic ("Handal").
    """
    print(f"{Colors.BLUE}[Proses] Mencari: '{topic}' | Region: {region} | Max: {max_results}...{Colors.ENDC}")
    
    results = []
    attempt = 0
    
    while attempt < MAX_RETRIES:
        try:
            with DDGS() as ddgs:
                # timelimit='w' (minggu ini) untuk data segar
                ddgs_gen = ddgs.news(
                    keywords=topic, 
                    region=region, 
                    safesearch='off', 
                    timelimit='w', 
                    max_results=max_results
                )
                for r in ddgs_gen:
                    results.append(r)
            
            # Jika sukses dan dapat hasil (atau kosong valid), keluar loop
            break
            
        except Exception as e:
            attempt += 1
            wait_time = RETRY_DELAY * attempt + random.uniform(0, 1)
            print(f"{Colors.WARNING}[Warn] Gagal percobaan ke-{attempt}: {e}. Retrying in {wait_time:.1f}s...{Colors.ENDC}")
            time.sleep(wait_time)
            
    if attempt == MAX_RETRIES:
        print(f"{Colors.FAIL}[Error] Gagal total setelah {MAX_RETRIES} percobaan.{Colors.ENDC}")
        return []

    return results

def save_to_csv(news_list, filename="hasil_berita.csv"):
    if not news_list:
        return

    # Menambahkan 'body' untuk konteks lebih lengkap
    keys = ['title', 'source', 'formatted_date', 'url', 'body']
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(news_list)
        print(f"{Colors.GREEN}[SUKSES] {len(news_list)} artikel disimpan ke: {Colors.BOLD}{filename}{Colors.ENDC}")
    except IOError as e:
        print(f"{Colors.FAIL}[Gagal] Tidak bisa menulis file CSV: {e}{Colors.ENDC}")

def save_to_markdown(news_list, filename="hasil_berita.md", topic="Berita"):
    if not news_list:
        return

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            # Header Laporan
            f.write(f"# Laporan Berita: {topic}\n")
            f.write(f"**Dibuat pada:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write("---\n\n")

            for i, news in enumerate(news_list, 1):
                title = news.get('title', 'Tanpa Judul')
                source = news.get('source', 'Unknown')
                date = news.get('formatted_date', '-')
                link = news.get('url', '#')
                body = news.get('body', '')

                # Format Item Berita
                f.write(f"## {i}. {title}\n")
                f.write(f"_{source} • {date}_\n\n")
                if body:
                    f.write(f"> {body}\n\n")
                f.write(f"[Baca Selengkapnya]({link})\n")
                f.write("---\n\n")
        
        print(f"{Colors.GREEN}[SUKSES] Laporan rapi disimpan ke: {Colors.BOLD}{filename}{Colors.ENDC}")
    except IOError as e:
        print(f"{Colors.FAIL}[Gagal] Tidak bisa menulis file Markdown: {e}{Colors.ENDC}")

def interactive_mode():
    print_banner()
    
    while True:
        try:
            topic = input(f"{Colors.BOLD}Topik berita (atau 'x' untuk keluar): {Colors.ENDC}").strip()
        except EOFError:
            break
            
        if topic.lower() == 'x':
            print("Sampai jumpa!")
            break
        if not topic:
            print(f"{Colors.WARNING}Topik tidak boleh kosong.{Colors.ENDC}")
            continue

        region_choice = input(f"{Colors.BOLD}Cari berita Indonesia saja? (y/n) [default: y]: {Colors.ENDC}").strip().lower()
        region = 'id-id' if region_choice in ['y', 'yes', ''] else 'wt-wt'

        raw_results = search_topic(topic, region=region, max_results=60) 
        
        if not raw_results:
            print(f"{Colors.WARNING}Tidak ditemukan berita.{Colors.ENDC}\n")
            continue

        print(f"   -> Mendapat {len(raw_results)} data mentah. Memproses...")
        
        valid_news = filter_recent_news(raw_results, days=2)
        
        if valid_news:
            timestamp = int(time.time())
            safe_topic = "".join([c if c.isalnum() else "_" for c in topic])
            
            # Simpan CSV (Data Mentah)
            filename_csv = f"news_{safe_topic}_{timestamp}.csv"
            save_to_csv(valid_news, filename_csv)

            # Simpan Markdown (Laporan Rapih)
            filename_md = f"Laporan_{safe_topic}_{timestamp}.md"
            save_to_markdown(valid_news, filename_md, topic)
            
            print(f"\n{Colors.BOLD}--- Preview Berita ---{Colors.ENDC}")
            for i, news in enumerate(valid_news[:3], 1):
                print(f"{i}. [{news['source']}] {news['title']}")
                if news.get('body'):
                    snippet = (news['body'][:75] + '...') if len(news['body']) > 75 else news['body']
                    print(f"   \"{snippet}\"")
                print(f"   {Colors.BLUE}{news['url']}{Colors.ENDC}")
            
            if len(valid_news) > 3:
                print(f"... dan {len(valid_news)-3} lainnya.")
            print("-" * 30 + "\n")
        else:
            print(f"{Colors.FAIL}Tidak ada berita yang memenuhi kriteria (< 2 hari & unik).{Colors.ENDC}\n")

def main():
    parser_arg = argparse.ArgumentParser(description="Smart News Fetcher")
    parser_arg.add_argument("topik", type=str, nargs='?', help="Topik berita")
    parser_arg.add_argument("--indo", action="store_true", help="Fokus Indonesia")
    parser_arg.add_argument("--limit", type=int, default=50, help="Limit pencarian")
    
    args = parser_arg.parse_args()

    if not args.topik:
        try:
            interactive_mode()
        except KeyboardInterrupt:
            print("\nProgram dihentikan.")
    else:
        region = 'id-id' if args.indo else 'wt-wt'
        raw_results = search_topic(args.topik, region=region, max_results=args.limit)
        valid_news = filter_recent_news(raw_results, days=2)
        if valid_news:
            safe_topic = "".join([c if c.isalnum() else "_" for c in args.topik])
            
            # Simpan CSV
            filename_csv = f"news_{safe_topic}.csv"
            save_to_csv(valid_news, filename_csv)
            
            # Simpan Markdown
            filename_md = f"Laporan_{safe_topic}.md"
            save_to_markdown(valid_news, filename_md, args.topik)
        else:
            print("Tidak ada berita valid ditemukan.")

if __name__ == "__main__":
    main()