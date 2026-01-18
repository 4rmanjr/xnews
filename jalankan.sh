#!/bin/bash

# Dapatkan lokasi folder ASLI di mana script ini berada (resolve symlink)
# Ini penting agar script tetap bekerja walau dipanggil dari shortcut/symlink
REAL_PATH=$(readlink -f "$0")
DIR=$(dirname "$REAL_PATH")

# Konfigurasi (Gunakan Absolute Path)
VENV_DIR="$DIR/venv"
REQ_FILE="$DIR/requirements.txt"
SCRIPT="$DIR/news_fetcher.py"

# Warna
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Smart News Fetcher Launcher ===${NC}"

# 1. Cek Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python3 tidak ditemukan. Harap install Python3.${NC}"
    exit 1
fi

# 2. Setup Virtual Environment (Otomatis & Handal)
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${BLUE}[Setup] Membuat virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Gagal membuat virtual environment.${NC}"
        exit 1
    fi
fi

# 3. Aktivasi & Install Dependencies
echo -e "${BLUE}[Setup] Memeriksa dependencies...${NC}"
source "$VENV_DIR/bin/activate"

# Pastikan pip terupdate agar instalasi lancar
pip install --upgrade pip -q

if [ -f "$REQ_FILE" ]; then
    # Install hanya jika ada perubahan (lebih cepat)
    pip install -r "$REQ_FILE" -q
else
    echo -e "${RED}File $REQ_FILE tidak ditemukan!${NC}"
    deactivate
    exit 1
fi

# 4. Jalankan Aplikasi
echo -e "${GREEN}[Start] Menjalankan aplikasi...${NC}"
echo "----------------------------------------"
python "$SCRIPT" "$@"

# 5. Selesai
echo "----------------------------------------"
deactivate
echo -e "${GREEN}Selesai.${NC}"