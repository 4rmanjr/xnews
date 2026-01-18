#!/bin/bash

# Dapatkan lokasi folder ASLI di mana script ini berada (resolve symlink)
# Ini penting agar script tetap bekerja walau dipanggil dari shortcut/symlink
REAL_PATH=$(readlink -f "$0")
DIR=$(dirname "$REAL_PATH")

# Konfigurasi (Gunakan Absolute Path)
VENV_DIR="$DIR/venv"
REQ_FILE="$DIR/requirements.txt"
SCRIPT="$DIR/news_fetcher.py"
INSTALLED_MARKER="$VENV_DIR/.deps_installed"

# Warna
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Fungsi untuk print dengan emoji
print_step() {
    echo -e "${BLUE}$1${NC}"
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}$1${NC}"
}

print_error() {
    echo -e "${RED}$1${NC}"
}

# Fungsi untuk menampilkan progress bar
show_progress() {
    local current=$1
    local total=$2
    local width=40
    local percent=$((current * 100 / total))
    local filled=$((current * width / total))
    local empty=$((width - filled))
    
    printf "\r  ${CYAN}["
    printf "%${filled}s" | tr ' ' '█'
    printf "%${empty}s" | tr ' ' '░'
    printf "] ${percent}%%${NC}"
}

# Banner
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║     🚀 XNEWS - Smart News Fetcher Launcher                   ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 1. Cek Python
print_step "🔍 Memeriksa Python..."
if ! command -v python3 &> /dev/null; then
    print_error "❌ Python3 tidak ditemukan!"
    echo -e "   Silakan install Python3 terlebih dahulu:"
    echo -e "   ${CYAN}• Ubuntu/Debian: sudo apt install python3 python3-venv${NC}"
    echo -e "   ${CYAN}• Fedora: sudo dnf install python3${NC}"
    echo -e "   ${CYAN}• macOS: brew install python3${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
print_success "✅ Python $PYTHON_VERSION ditemukan"

# 2. Setup Virtual Environment
FIRST_RUN=false
if [ ! -d "$VENV_DIR" ]; then
    FIRST_RUN=true
    
    echo ""
    print_step "🆕 Pertama kali dijalankan - menyiapkan environment..."
    echo -e "   ${CYAN}Ini hanya dilakukan sekali saat pertama kali.${NC}"
    echo ""
    
    print_step "📦 Membuat virtual environment..."
    
    # Try normal venv creation first
    if python3 -m venv "$VENV_DIR" 2>/dev/null; then
        print_success "✅ Virtual environment berhasil dibuat"
    else
        # Fallback: create without pip, then install pip manually
        print_warning "⚠️  ensurepip tidak tersedia, menggunakan fallback..."
        
        if python3 -m venv --without-pip "$VENV_DIR" 2>&1; then
            # Download and install pip manually
            source "$VENV_DIR/bin/activate"
            print_step "   📥 Mengunduh pip..."
            curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
            python /tmp/get-pip.py --quiet 2>&1
            rm -f /tmp/get-pip.py
            deactivate
            print_success "✅ Virtual environment berhasil dibuat (fallback mode)"
        else
            print_error "❌ Gagal membuat virtual environment!"
            echo -e "   ${CYAN}Coba install: sudo apt install python3-venv${NC}"
            exit 1
        fi
    fi
fi

# 3. Aktivasi Virtual Environment
source "$VENV_DIR/bin/activate"

# 4. Cek dan Install Dependencies
NEED_INSTALL=false

# Cek apakah perlu install (first run atau requirements berubah)
if [ ! -f "$INSTALLED_MARKER" ]; then
    NEED_INSTALL=true
elif [ "$REQ_FILE" -nt "$INSTALLED_MARKER" ]; then
    NEED_INSTALL=true
    print_warning "⚠️  Terdeteksi perubahan pada requirements.txt"
fi

if [ "$NEED_INSTALL" = true ]; then
    echo ""
    print_step "📥 Menginstall dependencies..."
    echo -e "   ${CYAN}Mohon tunggu, proses ini mungkin memerlukan waktu beberapa saat.${NC}"
    echo ""
    
    # Update pip terlebih dahulu (quietly)
    pip install --upgrade pip -q 2>&1
    
    # Hitung jumlah dependencies
    TOTAL_DEPS=$(grep -v '^#' "$REQ_FILE" | grep -v '^$' | wc -l)
    CURRENT=0
    
    # Install dependencies satu per satu dengan progress
    while IFS= read -r package || [ -n "$package" ]; do
        # Skip comment lines dan empty lines
        [[ "$package" =~ ^#.*$ ]] && continue
        [[ -z "${package// }" ]] && continue
        
        CURRENT=$((CURRENT + 1))
        
        # Tampilkan progress
        show_progress $CURRENT $TOTAL_DEPS
        echo -ne " ${package}                    "
        
        # Install package
        if pip install "$package" -q 2>&1 > /dev/null; then
            # Success - continue silently
            :
        else
            echo ""
            print_warning "   ⚠️  Gagal install $package, mencoba lagi..."
            pip install "$package" 2>&1 | tail -1
        fi
        
    done < "$REQ_FILE"
    
    echo ""
    echo ""
    
    # Verify critical dependencies
    print_step "🔧 Memverifikasi dependencies..."
    
    MISSING_DEPS=()
    
    # Check critical packages
    python3 -c "from ddgs import DDGS" 2>/dev/null || MISSING_DEPS+=("ddgs")
    python3 -c "import trafilatura" 2>/dev/null || MISSING_DEPS+=("trafilatura")
    python3 -c "from rich.console import Console" 2>/dev/null || MISSING_DEPS+=("rich")
    python3 -c "from dotenv import load_dotenv" 2>/dev/null || MISSING_DEPS+=("python-dotenv")
    
    if [ ${#MISSING_DEPS[@]} -eq 0 ]; then
        print_success "✅ Semua dependencies berhasil diinstall!"
        # Create marker file
        touch "$INSTALLED_MARKER"
    else
        print_error "❌ Beberapa dependencies gagal diinstall:"
        for dep in "${MISSING_DEPS[@]}"; do
            echo -e "   • $dep"
        done
        echo ""
        print_warning "🔄 Coba jalankan ulang script ini atau install manual:"
        echo -e "   ${CYAN}pip install ${MISSING_DEPS[*]}${NC}"
        deactivate
        exit 1
    fi
    
    echo ""
    
    if [ "$FIRST_RUN" = true ]; then
        print_success "🎉 Setup selesai! Aplikasi siap digunakan."
        echo ""
    fi
else
    print_step "📦 Dependencies: ${GREEN}✅ OK${NC}"
fi

# 5. Cek .env file
if [ ! -f "$DIR/.env" ]; then
    echo ""
    print_warning "⚠️  File .env tidak ditemukan!"
    echo -e "   ${CYAN}Fitur AI Summary memerlukan GROQ_API_KEY.${NC}"
    echo -e "   ${CYAN}Untuk mengaktifkan, copy .env.example ke .env dan isi API key.${NC}"
    echo ""
fi

# 6. Jalankan Aplikasi
echo ""
print_step "▶️  Menjalankan aplikasi..."
echo "────────────────────────────────────────────────────────────────"
python "$SCRIPT" "$@"
EXIT_CODE=$?
echo "────────────────────────────────────────────────────────────────"

# 7. Selesai
deactivate

if [ $EXIT_CODE -eq 0 ]; then
    print_success "✅ Selesai."
else
    print_warning "⚠️  Aplikasi keluar dengan kode: $EXIT_CODE"
fi