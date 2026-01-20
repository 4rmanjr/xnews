# 📰 xnews - Smart News Fetcher Turbo v2.0

**xnews** adalah alat CLI canggih untuk mencari, menyaring, mengekstrak, meringkas dengan AI, dan menerjemahkan berita secara otomatis.

## ✨ Fitur Utama

| Fitur | Deskripsi |
|-------|-----------|
| 🚀 **Turbo Mode** | Parallel processing untuk kecepatan tinggi |
| 🧠 **AI Summarization** | Ringkasan cerdas dengan Groq LLama 3.3 70B |
| 📊 **Sentiment Analysis** | Analisis sentimen Positif/Negatif/Netral |
| 🌍 **Smart Translator** | Terjemahan otomatis ke Bahasa Indonesia |
| 📄 **Full Text Extraction** | Ekstrak isi lengkap artikel (tanpa iklan) |
| 🧹 **Smart Deduplication** | Hapus berita duplikat secara cerdas |
| 📦 **Smart Caching** | Cache untuk menghindari fetch ulang |
| 👁️ **Watch Mode** | Monitoring berita baru secara real-time |
| 🎨 **Rich Console UI** | Tampilan tabel interaktif dengan warna |
| 📊 **Multi-Format Export** | CSV, JSON, dan Markdown |

## 🛠️ Instalasi

```bash
git clone git@github.com:4rmanjr/xnews.git
cd xnews
cp .env.example .env
# Edit .env dan masukkan GROQ_API_KEY Anda
./xnews.sh
```

### Dapatkan Groq API Key (Gratis)
1. Daftar di [console.groq.com](https://console.groq.com)
2. Generate API key
3. Masukkan ke file `.env`

### Jalankan Secara Global
```bash
alias xnews='/path/to/xnews/xnews.sh'
```

## 📖 Panduan Penggunaan

### Mode Interaktif
```bash
xnews
```

### Mode CLI

```bash
# Lihat semua opsi
xnews --help

# Cari berita Indonesia dengan AI Summary
xnews "Ekonomi Digital" --indo --summary

# Cari berita global, terjemahkan & ringkas
xnews "SpaceX" --translate --summary --limit 10

# Dengan Sentiment Analysis
xnews "Bitcoin" --summary --sentiment

# Export ke JSON
xnews "startup Indonesia" --indo --json

# Watch Mode: monitoring setiap 30 menit
xnews "Crypto" --watch --interval 30

# Hapus cache
xnews --clear-cache
```

## 📊 Opsi CLI Lengkap

| Opsi | Deskripsi |
|------|-----------|
| `--indo` | Fokus berita Indonesia |
| `--translate` | Terjemahkan ke Bahasa Indonesia |
| `--summary` | Aktifkan AI Summarization (Groq) |
| `--sentiment` | Aktifkan Sentiment Analysis |
| `--limit N` | Jumlah maksimal berita (default: 50) |
| `--json` | Export ke format JSON |
| `--watch` | Mode monitoring berkelanjutan |
| `--interval N` | Interval watch dalam menit (default: 30) |
| `--clear-cache` | Hapus cache |

## 📂 Struktur Proyek

```
xnews/
├── reports/          # Semua hasil (.csv, .json, .md)
├── .cache/           # Cache artikel (auto-generated)
├── .env              # Groq API Key (jangan commit!)
├── .env.example      # Template environment
├── xnews.sh       # Launcher otomatis
├── news_fetcher.py   # Mesin utama v2.0
├── requirements.txt  # Dependencies (9 library)
└── README.md         # Panduan ini
```

## 📦 Dependencies

```
duckduckgo-search    # Search engine
python-dateutil      # Date parsing
trafilatura          # Text extraction
tqdm                 # Progress bar
deep-translator      # Translation
groq                 # AI Summarization
textblob             # Sentiment Analysis
rich                 # Console UI
python-dotenv        # Environment variables
```

## 📄 Lisensi

[MIT](https://choosealicense.com/licenses/mit/)