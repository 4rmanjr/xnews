# 📰 xnews - Smart News Fetcher

**xnews** adalah alat Command Line Interface (CLI) pintar yang dirancang untuk mencari, menyaring, dan melaporkan berita terkini secara efisien. Alat ini tidak sekadar mencari, tetapi juga **membersihkan** hasil pencarian agar Anda mendapatkan informasi yang relevan, bebas duplikat, dan mudah dibaca.

## ✨ Fitur Unggulan

*   🧠 **Smart Deduplication:** Algoritma cerdas yang mendeteksi dan menghapus berita duplikat (judul yang sama atau sangat mirip) dari berbagai sumber.
*   📅 **Freshness Filter:** Secara otomatis menyaring berita lawas dan hanya menampilkan artikel yang dipublikasikan dalam **48 jam terakhir**.
*   🛡️ **Robust & Reliable:** Dilengkapi fitur *Auto-Retry* yang membuat aplikasi tetap berjalan lancar meski koneksi internet tidak stabil.
*   📊 **Dual Output:**
    *   **CSV:** Untuk analisis data mentah.
    *   **Markdown (.md):** Laporan rapi yang siap dibaca atau dipublikasikan.
*   🚀 **Zero Config Setup:** Script peluncur (`jalankan.sh`) otomatis membuat *virtual environment* dan menginstall dependencies. Tidak perlu setup manual!

## 🛠️ Instalasi

### Prasyarat
*   Sistem Operasi: Linux / macOS
*   Python 3.x
*   Koneksi Internet

### Cara Cepat (Langsung Jalan)
Cukup clone repositori ini dan jalankan script utamanya. Script ini akan mengurus sisanya.

```bash
git clone git@github.com:4rmanjr/xnews.git
cd xnews
./jalankan.sh
```

### 🌍 Pasang Secara Global (Opsional)
Agar bisa dijalankan dari folder mana saja dengan perintah `xnews`, tambahkan alias ke konfigurasi shell Anda (`.bashrc` atau `.zshrc`):

```bash
echo "alias xnews='/path/to/your/xnews/jalankan.sh'" >> ~/.zshrc
source ~/.zshrc
```
*(Ganti `/path/to/your/xnews` dengan lokasi folder xnews Anda)*

## 📖 Cara Penggunaan

### 1. Mode Interaktif
Jalankan tanpa argumen, dan aplikasi akan memandu Anda:
```bash
xnews
```

### 2. Mode Cepat (Command Line)
Cari berita langsung dengan satu baris perintah:

**Cari topik umum (Internasional):**
```bash
xnews "Artificial Intelligence"
```

**Cari topik spesifik (Indonesia) dengan limit hasil:**
```bash
xnews "Banjir Jakarta" --indo --limit 50
```

## 📂 Struktur Output

Setiap pencarian akan menghasilkan dua file di folder Anda saat ini:

1.  `news_Topik_Timestamp.csv`: Data mentah berisi Judul, Sumber, Tanggal, URL, dan Snippet.
2.  `Laporan_Topik_Timestamp.md`: Laporan yang diformat rapi dengan judul, kutipan, dan link sumber.

## 🤝 Kontribusi

Pull requests dipersilakan! Untuk perubahan besar, mohon buka *issue* terlebih dahulu untuk mendiskusikan apa yang ingin Anda ubah.

## 📄 Lisensi

[MIT](https://choosealicense.com/licenses/mit/)
