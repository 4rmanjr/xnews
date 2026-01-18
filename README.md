# 📰 xnews - Smart News Fetcher Turbo

**xnews** adalah alat Command Line Interface (CLI) canggih yang dirancang untuk mencari, menyaring, mengekstrak, dan menerjemahkan berita secara otomatis. Alat ini dibuat untuk riset berita yang efektif, handal, dan pintar.

## ✨ Fitur Utama

*   🚀 **Turbo Mode (Parallel Processing):** Mengambil isi penuh puluhan berita secara bersamaan (Multithreading) dengan kecepatan tinggi.
*   🌍 **Smart Translator:** Terjemahkan berita asing otomatis ke Bahasa Indonesia menggunakan Google Neural Machine Translation (Gratis & Tanpa API Key).
*   📄 **Full Text Extraction:** Tidak hanya ringkasan, aplikasi menarik seluruh isi artikel berita secara bersih (tanpa iklan/sampah).
*   🧠 **Smart Deduplication:** Algoritma cerdas yang menghapus berita duplikat atau sangat mirip.
*   📂 **Organized Output:** Semua laporan tersimpan rapi di folder `reports/` (otomatis diabaikan oleh Git).
*   📊 **Dual Format:** Menghasilkan file CSV (data mentah) dan Markdown (laporan rapi siap baca).
*   📅 **Freshness Filter:** Hanya menampilkan berita yang terbit dalam **48 jam terakhir**.

## 🛠️ Instalasi

Cukup clone repositori ini dan jalankan script peluncur. Script akan otomatis mengatur *virtual environment* dan library yang dibutuhkan.

```bash
git clone git@github.com:4rmanjr/xnews.git
cd xnews
./jalankan.sh
```

### Jalankan Secara Global
Tambahkan alias ke shell Anda (misal `.zshrc` atau `.bashrc`):
```bash
alias xnews='/path/to/xnews/jalankan.sh'
```

## 📖 Panduan Penggunaan

Aplikasi mendukung dua mode penggunaan:

### 1. Mode Interaktif
Jalankan tanpa argumen untuk dipandu langkah demi langkah:
```bash
xnews
```

### 2. Mode Command Line (Dapatkan Bantuan)
Gunakan perintah `--help` untuk melihat semua dokumentasi:
```bash
xnews --help
```

**Contoh Perintah:**
```bash
# Cari berita Indonesia tentang "Ekonomi Digital"
xnews "Ekonomi Digital" --indo

# Cari berita global tentang "SpaceX" dan terjemahkan ke Indonesia
xnews "SpaceX" --translate --limit 10
```

## 📂 Struktur Proyek
```text
xnews/
├── reports/          # SEMUA HASIL (.csv & .md) ada di sini
├── jalankan.sh       # Launcher otomatis
├── news_fetcher.py   # Mesin utama (Turbo Mode)
├── requirements.txt  # Daftar library
└── README.md         # Panduan ini
```

## 📄 Lisensi
[MIT](https://choosealicense.com/licenses/mit/)