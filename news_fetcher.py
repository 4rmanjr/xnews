import csv
import argparse
import sys
import os
import time
import difflib
import random
import warnings
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Library Pihak Ketiga
from dateutil import parser
from duckduckgo_search import DDGS
import trafilatura
from tqdm import tqdm

# --- Konfigurasi ---
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_THREADS = 10  # Jumlah "kurir" download paralel
TIMEOUT_SECONDS = 10 # Batas waktu per artikel
OUTPUT_DIR = "reports" # Folder penyimpanan hasil

# Supress Logs & Warnings
warnings.filterwarnings("ignore", message="This package.*renamed.*ddgs")
logging.getLogger('trafilatura').setLevel(logging.WARNING)

# --- Warna ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def ensure_output_dir():
    """Memastikan folder output tersedia."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def print_banner():
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("="*60)
    print("   PENCARI BERITA PINTAR & TURBO (Smart News Fetcher)")
    print("   (Fitur: Deduplikasi, Full Text, Parallel, Folder Rapih)")
    print("="*60)
    print(f"{Colors.ENDC}")

def clean_title(title):
    return title.lower().strip()

def is_duplicate(news_item, existing_titles, threshold=0.85):
    title = clean_title(news_item.get('title', ''))
    if title in existing_titles: return True
    for existing in existing_titles:
        if difflib.SequenceMatcher(None, title, existing).ratio() > threshold:
            return True
    return False

def fetch_single_article(news_item):
    """
    Fungsi worker untuk mengambil isi berita satu per satu.
    Digunakan oleh ThreadPoolExecutor.
    """
    url = news_item.get('url')
    if not url:
        news_item['full_text'] = ""
        return news_item

    try:
        # Download HTML
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            # Ekstrak Teks Bersih
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            news_item['full_text'] = text if text else ""
        else:
            news_item['full_text'] = ""
    except Exception:
        news_item['full_text'] = ""
    
    return news_item

def enrich_news_content(news_list):
    """
    Mengambil isi berita secara PARALEL (Multithreading).
    Ada Loading Bar (tqdm).
    """
    if not news_list:
        return []

    print(f"\n{Colors.BLUE}[Turbo Mode] Sedang mengambil isi penuh {len(news_list)} artikel...{Colors.ENDC}")
    
    enriched_results = []
    
    # Menjalankan download secara paralel
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        # Submit tugas ke thread pool
        future_to_news = {executor.submit(fetch_single_article, item): item for item in news_list}
        
        # Tampilkan progress bar
        for future in tqdm(as_completed(future_to_news), total=len(news_list), unit="artikel", ncols=80, bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}"):
            try:
                data = future.result()
                enriched_results.append(data)
            except Exception as e:
                # Jika error parah, kembalikan item asli tanpa full text
                item = future_to_news[future]
                item['full_text'] = ""
                enriched_results.append(item)
    
    return enriched_results

def filter_recent_news(news_list, days=2):
    recent_news = []
    seen_titles = set()
    cutoff_date = datetime.now().astimezone() - timedelta(days=days)
    
    print(f"[*] Menyaring tanggal & menghapus duplikat...")

    for item in news_list:
        date_str = item.get('date')
        if not date_str: continue

        try:
            pub_date = parser.parse(date_str)
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
            
            if pub_date >= cutoff_date:
                if is_duplicate(item, seen_titles): continue

                seen_titles.add(clean_title(item.get('title', '')))
                item['_raw_date'] = pub_date
                item['formatted_date'] = pub_date.strftime('%Y-%m-%d %H:%M:%S')
                item['body'] = item.get('body', '') 
                recent_news.append(item)
                
        except (ValueError, TypeError):
            continue
    
    # Sort Descending
    recent_news.sort(key=lambda x: x.get('_raw_date', datetime.min), reverse=True)
    return recent_news

def search_topic(topic, region='wt-wt', max_results=50):
    print(f"{Colors.BLUE}[Proses] Mencari topik: '{topic}'...{Colors.ENDC}")
    results = []
    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            with DDGS() as ddgs:
                ddgs_gen = ddgs.news(keywords=topic, region=region, safesearch='off', timelimit='w', max_results=max_results)
                for r in ddgs_gen: results.append(r)
            break
        except Exception as e:
            attempt += 1
            time.sleep(RETRY_DELAY)
    return results

def save_to_csv(news_list, filename):
    if not news_list: return
    
    ensure_output_dir()
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Tambah kolom full_text
    keys = ['title', 'source', 'formatted_date', 'url', 'body', 'full_text']
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(news_list)
        print(f"{Colors.GREEN}[SUKSES] CSV tersimpan: {filepath}{Colors.ENDC}")
    except IOError as e:
        print(f"{Colors.FAIL}[Gagal CSV] {e}{Colors.ENDC}")

def save_to_markdown(news_list, filename, topic):
    if not news_list: return

    ensure_output_dir()
    filepath = os.path.join(OUTPUT_DIR, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# Laporan Lengkap: {topic}\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"**Total Artikel:** {len(news_list)}\n\n---\n\n")

            for i, news in enumerate(news_list, 1):
                title = news.get('title', 'Tanpa Judul')
                source = news.get('source', 'Unknown')
                date = news.get('formatted_date', '-')
                link = news.get('url', '#')
                snippet = news.get('body', '')
                full_text = news.get('full_text', '')

                f.write(f"## {i}. {title}\n")
                f.write(f"_{source} • {date}_\n\n")
                
                # Prioritaskan Full Text, kalau gagal pakai Snippet
                if full_text:
                    # Bersihkan whitespace berlebih
                    clean_text = "\n\n".join([p.strip() for p in full_text.split('\n') if p.strip()])
                    f.write(f"{clean_text}\n\n")
                elif snippet:
                    f.write(f"> {snippet}\n\n")
                else:
                    f.write("_Tidak ada konten teks._\n\n")

                f.write(f"[🔗 Baca Sumber Asli]({link})\n")
                f.write("---\n\n")
        print(f"{Colors.GREEN}[SUKSES] Laporan Lengkap (.md) tersimpan: {Colors.BOLD}{filepath}{Colors.ENDC}")
    except IOError as e:
        print(f"{Colors.FAIL}[Gagal MD] {e}{Colors.ENDC}")

def interactive_mode():
    print_banner()
    while True:
        try:
            topic = input(f"{Colors.BOLD}Topik berita (atau 'x' untuk keluar): {Colors.ENDC}").strip()
        except EOFError: break
        if topic.lower() == 'x': break
        if not topic: continue

        region = 'id-id' if input("Indonesia saja? (y/n): ").lower() in ['y', 'yes', ''] else 'wt-wt'
        
        # 1. Cari
        raw = search_topic(topic, region=region, max_results=60)
        if not raw: 
            print("Nihil.")
            continue
        
        # 2. Filter & Deduplikasi
        filtered = filter_recent_news(raw, days=2)
        if not filtered:
            print("Tidak ada berita baru (<48 jam).")
            continue

        # 3. Enrich (Download Full Text)
        final_news = enrich_news_content(filtered)

        # 4. Save
        ts = int(time.time())
        safe_topic = "".join([c if c.isalnum() else "_" for c in topic])
        save_to_csv(final_news, f"news_{safe_topic}_{ts}.csv")
        save_to_markdown(final_news, f"Laporan_{safe_topic}_{ts}.md", topic)
        print("-" * 30 + "\n")

def main():
    parser_arg = argparse.ArgumentParser(description="Smart News Fetcher Turbo")
    parser_arg.add_argument("topik", type=str, nargs='?', help="Topik berita")
    parser_arg.add_argument("--indo", action="store_true", help="Fokus Indonesia")
    parser_arg.add_argument("--limit", type=int, default=50, help="Limit pencarian")
    args = parser_arg.parse_args()

    ensure_output_dir() # Pastikan folder ada saat start

    if not args.topik:
        try: interactive_mode()
        except KeyboardInterrupt: print("\nBye.")
    else:
        region = 'id-id' if args.indo else 'wt-wt'
        raw = search_topic(args.topik, region=region, max_results=args.limit)
        filtered = filter_recent_news(raw, days=2)
        if filtered:
            final_news = enrich_news_content(filtered)
            safe_topic = "".join([c if c.isalnum() else "_" for c in args.topik])
            save_to_csv(final_news, f"news_{safe_topic}.csv")
            save_to_markdown(final_news, f"Laporan_{safe_topic}.md", args.topik)
        else:
            print("Tidak ada berita valid.")

if __name__ == "__main__":
    main()
