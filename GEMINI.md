# xnews - Smart News Fetcher Turbo v2.0

## Project Overview
**xnews** is a comprehensive CLI tool for fetching, filtering, analyzing, and summarizing news articles. It combines traditional web scraping with modern AI capabilities to provide curated news updates directly in the terminal.

**Key Features:**
*   **News Fetching:** Uses DuckDuckGo Search (`ddgs`) to find relevant articles.
*   **Content Extraction:** robust text extraction using `trafilatura`.
*   **AI Integration:** Leverages **Groq** (Llama 3.3) for smart summarization, tweet generation, and title refinement.
*   **Sentiment Analysis:** Uses `TextBlob` to classify articles as Positive, Negative, or Neutral.
*   **Translation:** Auto-translates content to Indonesian using `deep-translator`.
*   **Monitoring:** "Watch Mode" for continuous background monitoring of specific topics.
*   **Rich UI:** Interactive terminal interface using the `rich` library.

## Architecture & Key Files

*   **`news_fetcher.py`**: The main application logic. Contains the `fetch_single_article`, `enrich_news_content`, and `main` execution loop.
*   **`xnews.sh`**: The recommended entry point. A Bash wrapper that handles:
    *   Environment detection (Linux/Termux).
    *   Virtual environment (`venv`) creation and management.
    *   Dependency installation (`pip install`).
    *   Execution of the Python script.
*   **`prompts.yaml`**: Configuration file for AI prompts (System/User roles for summaries and tweets).
*   **`.env`**: Stores sensitive configuration (primarily `GROQ_API_KEY`).
*   **`reports/`**: Output directory for generated CSV, JSON, and Markdown reports (organized by date).

## Building and Running

### Prerequisites
*   Python 3.x
*   Groq API Key (for AI features)

### Setup
1.  **Configure Environment:**
    ```bash
    cp .env.example .env
    # Edit .env and add your GROQ_API_KEY
    ```

2.  **Run (Recommended):**
    Use the provided wrapper script to automatically handle dependencies and virtual environments:
    ```bash
    ./xnews.sh
    ```

### Termux (Android) Support
The tool is optimized for Termux. For the best experience:
1.  **Install Termux:API**: Download the "Termux:API" app from F-Droid.
2.  **Install system packages**: The `xnews.sh` script will attempt to install these, but you can also do it manually:
    ```bash
    pkg install termux-api python rust clang binutils libxml2 libxslt libffi openssl
    ```
3.  **Clipboard**: To copy drafts to your Android clipboard, the Termux:API package must be installed.

### Usage Examples
The tool supports both interactive and argument-based execution.

*   **Interactive Mode:**
    ```bash
    ./xnews.sh
    ```
*   **Command Line Arguments:**
    ```bash
    # Search, translate, and summarize
    ./xnews.sh "Artificial Intelligence" --translate --summary

    # Watch a topic (runs every 30 mins)
    ./xnews.sh "Bitcoin" --watch --interval 30

    # Export to JSON
    ./xnews.sh "SpaceX" --json
    ```

## Development Conventions

*   **Style:** Pythonic code style (PEP 8).
*   **Configuration:** Use `prompts.yaml` for all AI-related text/prompts to separate logic from content.
*   **Error Handling:** Extensive use of try-except blocks ensures the scraper is resilient to network failures or bad HTML.
*   **UI:** Output should be routed through `rich.console` for consistent formatting.
*   **Dependencies:** Managed via `requirements.txt`. The `xnews.sh` script automatically checks for updates to this file.
