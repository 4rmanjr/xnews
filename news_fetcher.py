#!/usr/bin/env python3
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
from deep_translator import GoogleTranslator

# --- Konfigurasi ---
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_THREADS = 10 
TIMEOUT_SECONDS = 10 
OUTPUT_DIR = "reports" 

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
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def print_banner():
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("="*60)
    print("   PENCARI BERITA PINTAR & TURBO (Smart News Fetcher)")
    print("   (Fitur: Deduplikasi, Full Text, Translator, Folder Rapih)")
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

def translate_text(text, target='id'):
    """
    Menerjemahkan teks panjang dengan memecahnya per paragraf
    agar tidak kena limit Google Translate.
    """
    if not text: return ""
    
    translator = GoogleTranslator(source='auto', target=target)
    translated_parts = []
    
    # Pecah berdasarkan baris baru untuk menjaga struktur paragraf
    paragraphs = text.split('\n')
    
    for p in paragraphs:
        if not p.strip():
            translated_parts.append("")
            continue
            
        try:
            # Jika paragraf terlalu panjang (>4500), deep_translator biasanya handle,
            # tapi kita limit manual untuk keamanan
            if len(p) > 4500:
                # Potong kasar jika sangat panjang (jarang terjadi di berita)
                res = translator.translate(p[:4500])
            else:
                res = translator.translate(p)
            translated_parts.append(res)
        except Exception:
            # Jika gagal translate, kembalikan teks asli
            translated_parts.append(p)
            
    return "\n".join(translated_parts)

def fetch_single_article(news_item, auto_translate=False):
    """
    Fungsi worker: Download HTML -> Ekstrak Teks -> (Opsional) Translate
    """
    url = news_item.get('url')
    news_item['full_text'] = ""
    news_item['is_translated'] = False

    if not url: return news_item

    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            
            if text:
                if auto_translate:
                    # Translate Judul
                    try:
                        news_item['title'] = GoogleTranslator(source='auto', target='id').translate(news_item['title'])
                    except:
                        pass
                    
                    # Translate Isi
                    news_item['full_text'] = translate_text(text, target='id')
                    news_item['is_translated'] = True
                else:
                    news_item['full_text'] = text
                    
    except Exception:
        pass
    
    return news_item

def enrich_news_content(news_list, do_translate=False):
    if not news_list: return []

    action_msg = "mengambil isi penuh & menerjemahkan" if do_translate else "mengambil isi penuh"
    print(f"{Colors.BLUE}[Turbo Mode] Sedang {action_msg} {len(news_list)} artikel...{Colors.ENDC}")
    
    enriched_results = []
    
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        # Kirim flag do_translate ke worker
        future_to_news = {executor.submit(fetch_single_article, item, do_translate): item for item in news_list}
        
        for future in tqdm(as_completed(future_to_news), total=len(news_list), unit="artikel", ncols=80, bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}"):
            try:
                data = future.result()
                enriched_results.append(data)
            except Exception:
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
        except Exception:
            attempt += 1
            time.sleep(RETRY_DELAY)
    return results

def save_to_csv(news_list, filename):
    if not news_list: return
    ensure_output_dir()
    filepath = os.path.join(OUTPUT_DIR, filename)
    keys = ['title', 'source', 'formatted_date', 'url', 'body', 'full_text', 'is_translated']
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
                full_text = news.get('full_text', '')
                is_trans = news.get('is_translated', False)

                # Indikator Terjemahan
                trans_badge = " *(Diterjemahkan)*" if is_trans else ""

                f.write(f"## {i}. {title}{trans_badge}\n")
                f.write(f"_{source} • {date}_

")
                
                if full_text:
                    clean_text = "\n\n".join([p.strip() for p in full_text.split('\n') if p.strip()])
                    f.write(f"{clean_text}\n\n")
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

        region_input = input("Indonesia saja? (y/n) [default: n]: ").lower()
        region = 'id-id' if region_input in ['y', 'yes'] else 'wt-wt'
        
        # Opsi Translate di mode interaktif
        do_trans = False
        if region == 'wt-wt':
            trans_input = input("Terjemahkan ke Indonesia? (y/n) [default: n]: ").lower()
            do_trans = True if trans_input in ['y', 'yes'] else False

        raw = search_topic(topic, region=region, max_results=60)
        if not raw: 
            print("Nihil.")
            continue
        
        filtered = filter_recent_news(raw, days=2)
        if not filtered:
            print("Tidak ada berita baru (<48 jam).")
            continue

        # Enrich + Translate
        final_news = enrich_news_content(filtered, do_translate=do_trans)

        ts = int(time.time())
        safe_topic = "".join([c if c.isalnum() else "_" for c in topic])
        save_to_csv(final_news, f"news_{safe_topic}_{ts}.csv")
        save_to_markdown(final_news, f"Laporan_{safe_topic}_{ts}.md", topic)
        print("-" * 30 + "\n")

def main():
    parser_arg = argparse.ArgumentParser(
        description="Smart News Fetcher Turbo - Mencari & Menerjemahkan Berita Secara Pintar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh Penggunaan:
  xnews "Kecerdasan Buatan" --indo             # Cari berita Indonesia
  xnews "SpaceX" --translate --limit 10        # Cari berita global & terjemahkan
  xnews                                        # Masuk ke mode interaktif
        """
    )
    parser_arg.add_argument("topik", type=str, nargs='?', help="Topik atau kata kunci berita yang dicari")
    parser_arg.add_argument("--indo", action="store_true", help="Fokus mencari berita dari sumber Indonesia (id-id)")
    parser_arg.add_argument("--translate", action="store_true", help="Terjemahkan otomatis artikel asing ke Bahasa Indonesia")
    parser_arg.add_argument("--limit", type=int, default=50, help="Jumlah maksimal berita yang diambil (default: 50)")
    
    args = parser_arg.parse_args()

    ensure_output_dir()

    if not args.topik:
        try: interactive_mode()
        except KeyboardInterrupt: print("\nBye.")
    else:
        region = 'id-id' if args.indo else 'wt-wt'
        raw = search_topic(args.topik, region=region, max_results=args.limit)
        filtered = filter_recent_news(raw, days=2)
        if filtered:
            # Kirim argumen translate
            final_news = enrich_news_content(filtered, do_translate=args.translate)
            safe_topic = "".join([c if c.isalnum() else "_" for c in args.topik])
            save_to_csv(final_news, f"news_{safe_topic}.csv")
            save_to_markdown(final_news, f"Laporan_{safe_topic}.md", args.topik)
        else:
            print("Tidak ada berita valid.")

if __name__ == "__main__":
    main()