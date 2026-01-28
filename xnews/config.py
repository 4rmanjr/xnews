"""
xnews - Smart News Fetcher Turbo v2.0
Configuration and constants module.
"""

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()

# --- Path Configuration ---
BASE_DIR = Path(__file__).parent.parent  # Points to xnews project root
OUTPUT_DIR = "reports"
CACHE_DIR = ".cache"
PROMPT_FILE = "prompts.yaml"
ENV_FILE_PATH = BASE_DIR / ".env"

# --- Network Configuration ---
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_THREADS = 10
TIMEOUT_SECONDS = 15
CACHE_TTL_HOURS = 1

# --- Text & Processing Limits ---
class TextLimits:
    """Named constants for text processing limits (replacing magic numbers)."""
    
    # AI Input Limits
    GROQ_MAX_INPUT = 15000           # Max chars to send to Groq
    GEMINI_MAX_INPUT = 100000        # Max chars to send to Gemini
    COMBINED_MAX_INPUT = 5000        # Max chars for combined summary+tweet
    
    # AI Output Limits  
    TWEET_MAX_LENGTH = 2000          # Max tweet draft length
    SUMMARY_MAX_TOKENS = 1024        # Token limit for summaries
    TWEET_MAX_TOKENS = 300           # Token limit for tweets
    COMBINED_MAX_TOKENS = 800        # Token limit for combined output
    
    # Text Processing
    SENTIMENT_SAMPLE = 1000          # Chars to analyze for sentiment
    TRANSLATION_CHUNK = 4500         # Max chars per translation chunk
    MIN_ARTICLE_LENGTH = 100         # Min chars for valid article
    MIN_EXTRACTED_LENGTH = 200       # Min chars for valid extraction
    
    # Display & Export
    TABLE_MAX_ITEMS = 10             # Max items in results table
    MARKDOWN_TRUNCATE = 10000        # Max chars in markdown export
    TITLE_MAX_LENGTH = 20            # Max title length for filenames
    
    # Filtering
    DEFAULT_MAX_RESULTS = 50         # Default search results limit
    DEFAULT_FILTER_DAYS = 2          # Default days filter
    DUPLICATE_THRESHOLD = 0.85       # Similarity threshold for duplicates

# --- Groq Configuration ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile", 
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
]

# --- Gemini Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

GEMINI_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-001",
    "gemini-3-flash-preview",
    "gemini-3-pro-preview"
]

# --- AI Provider Configuration ---
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()
if AI_PROVIDER not in ["groq", "gemini"]:
    AI_PROVIDER = "groq"

# --- Termux Detection ---
IS_TERMUX = bool(os.environ.get('TERMUX_VERSION') or 
                 (os.environ.get('PREFIX', '').startswith('/data/data/com.termux')))

# --- Helper Functions ---

def save_env_setting(key: str, value: str) -> bool:
    """Update or add a setting in the .env file."""
    from rich.console import Console
    console = Console()
    
    try:
        lines: list[str] = []
        found = False
        
        if ENV_FILE_PATH.exists():
            with open(ENV_FILE_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        
        # Update existing key or mark for addition
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
        
        # Add new key if not found
        if not found:
            lines.append(f"\n{key}={value}\n")
        
        with open(ENV_FILE_PATH, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        return True
    except OSError as e:
        console.print(f"[dim]⚠ Gagal menyimpan ke .env: {e}[/dim]")
        return False

def update_runtime_config(key: str, value: Any) -> None:
    """Update runtime configuration (in-memory only)."""
    global AI_PROVIDER, GROQ_MODEL, GEMINI_MODEL
    
    if key == "AI_PROVIDER":
        AI_PROVIDER = value
    elif key == "GROQ_MODEL":
        GROQ_MODEL = value
    elif key == "GEMINI_MODEL":
        GEMINI_MODEL = value
