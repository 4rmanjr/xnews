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

# --- Text Limits ---
class TextLimits:
    GROQ_MAX_INPUT = 15000
    GEMINI_MAX_INPUT = 100000
    COMBINED_MAX_INPUT = 5000
    SENTIMENT_SAMPLE = 1000
    TRANSLATION_CHUNK = 4500
    TWEET_MAX_LENGTH = 2000

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
