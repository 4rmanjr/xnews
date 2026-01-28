"""
xnews - AI Providers Module
Groq and Gemini AI integration for summarization and tweet generation.
"""

from typing import Any, Optional
import json

from rich.console import Console

from xnews.config import (
    GROQ_API_KEY, GROQ_MODEL, 
    GEMINI_API_KEY, GEMINI_MODEL,
    AI_PROVIDER, TextLimits
)
from xnews.core.prompts import prompt_loader

console = Console()

# --- AI Library Imports ---
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# --- Groq Functions ---

def _groq_summarize(text: str, max_sentences: int = 3, for_twitter: bool = False) -> str:
    """Summarize text using Groq LLM."""
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return ""
    
    if not text or len(text) < 100:
        return ""
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        truncated = text[:TextLimits.GROQ_MAX_INPUT] if len(text) > TextLimits.GROQ_MAX_INPUT else text
        
        if for_twitter:
            system_prompt = prompt_loader.get('summary', 'twitter', 'system', default="You are a social media expert.")
            user_prompt_tpl = prompt_loader.get('summary', 'twitter', 'user', default="Summarize this:\n\n{text}")
            user_prompt = user_prompt_tpl.format(text=truncated)
        else:
            system_prompt_tpl = prompt_loader.get('summary', 'standard', 'system', default="Summarize in {max_sentences} sentences.")
            try:
                system_prompt = system_prompt_tpl.format(max_sentences=max_sentences)
            except (KeyError, ValueError):
                system_prompt = system_prompt_tpl
                
            user_prompt_tpl = prompt_loader.get('summary', 'standard', 'user', default="Summarize:\n\n{text}")
            user_prompt = user_prompt_tpl.format(text=truncated)
        
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=1024
        )
        
        result = response.choices[0].message.content.strip()
        if for_twitter and len(result) > TextLimits.TWEET_MAX_LENGTH:
            result = result[:TextLimits.TWEET_MAX_LENGTH - 3] + "..."
        return result
    except Exception as e:
        console.print(f"[dim]Groq Summary error: {e}[/dim]")
        return ""


def _groq_generate_tweet(title: str, text: str, topic: str) -> str:
    """Generate tweet using Groq."""
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return ""
    try:
        client = Groq(api_key=GROQ_API_KEY)
        truncated = text[:TextLimits.COMBINED_MAX_INPUT] if len(text) > TextLimits.COMBINED_MAX_INPUT else text
        system_prompt = prompt_loader.get('tweet_generation', 'system', default="You are a twitter expert.")
        user_prompt_tpl = prompt_loader.get('tweet_generation', 'user', default="Title: {title}\nText: {text}")
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,
            max_tokens=300
        )
        
        tweet_text = response.choices[0].message.content.strip()
        tweet_text = tweet_text.strip('"\'').replace('**', '').replace('__', '')
        if len(tweet_text) > TextLimits.TWEET_MAX_LENGTH:
            tweet_text = tweet_text[:TextLimits.TWEET_MAX_LENGTH - 3] + "..."
        return tweet_text
    except Exception as e:
        console.print(f"[dim]Groq Tweet error: {e}[/dim]")
        return ""


def _groq_generate_combined(title: str, text: str, topic: str) -> dict[str, str]:
    """Generate both summary and tweet in single Groq API call."""
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return {"tweet": "", "summary": ""}
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        truncated = text[:TextLimits.COMBINED_MAX_INPUT] if len(text) > TextLimits.COMBINED_MAX_INPUT else text
        
        system_prompt = prompt_loader.get('combined_generation', 'system', 
            default="Output JSON with 'tweet' and 'summary' keys.")
        user_prompt_tpl = prompt_loader.get('combined_generation', 'user', 
            default="Title: {title}\nText: {text}")
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,
            max_tokens=800
        )
        
        raw_output = response.choices[0].message.content.strip()
        return _parse_combined_json(raw_output)
        
    except Exception as e:
        console.print(f"[dim]Groq Combined error: {e}[/dim]")
        return {"tweet": "", "summary": ""}


# --- Gemini Functions ---

def _gemini_summarize(text: str, max_sentences: int = 3, for_twitter: bool = False) -> str:
    """Summarize text using Gemini LLM."""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        return ""
    
    if not text or len(text) < 100:
        return ""
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        truncated = text[:TextLimits.GEMINI_MAX_INPUT] if len(text) > TextLimits.GEMINI_MAX_INPUT else text
        
        if for_twitter:
            system_prompt = prompt_loader.get('summary', 'twitter', 'system', default="You are a social media expert.")
            user_prompt_tpl = prompt_loader.get('summary', 'twitter', 'user', default="Summarize this:\n\n{text}")
        else:
            system_prompt_tpl = prompt_loader.get('summary', 'standard', 'system', default="Summarize in {max_sentences} sentences.")
            try:
                system_prompt = system_prompt_tpl.format(max_sentences=max_sentences)
            except (KeyError, ValueError):
                system_prompt = system_prompt_tpl
            user_prompt_tpl = prompt_loader.get('summary', 'standard', 'user', default="Summarize:\n\n{text}")
        
        user_prompt = user_prompt_tpl.format(text=truncated)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.5,
                max_output_tokens=2048
            )
        )
        
        result = response.text.strip()
        if for_twitter and len(result) > TextLimits.TWEET_MAX_LENGTH:
            result = result[:TextLimits.TWEET_MAX_LENGTH - 3] + "..."
        return result
    except Exception as e:
        console.print(f"[dim]Gemini Summary error: {e}[/dim]")
        return ""


def _gemini_generate_tweet(title: str, text: str, topic: str) -> str:
    """Generate tweet using Gemini."""
    if not GEMINI_AVAILABLE:
        console.print("[red]❌ Gemini SDK tidak tersedia. Install: pip install google-generativeai[/red]")
        return ""
    if not GEMINI_API_KEY:
        console.print("[red]❌ GEMINI_API_KEY tidak ditemukan di .env[/red]")
        return ""
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        truncated = text[:30000] if len(text) > 30000 else text
        
        system_prompt = prompt_loader.get('tweet_generation', 'system')
        user_prompt_tpl = prompt_loader.get('tweet_generation', 'user')
        
        if not system_prompt:
            system_prompt = "You are a twitter expert."
        if not user_prompt_tpl:
            user_prompt_tpl = "Title: {title}\nText: {text}"
        
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        console.print(f"[dim]📤 Gemini Tweet: Sending {len(full_prompt)} chars to {GEMINI_MODEL}...[/dim]")

        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048
            )
        )
        
        if not response.text:
            console.print(f"[red]❌ Gemini returned empty response. Candidates: {response.candidates}[/red]")
            return ""
        
        tweet_text = response.text.strip()
        tweet_text = tweet_text.strip('"\'').replace('**', '').replace('__', '')
        
        console.print(f"[dim]✅ Gemini Tweet: Received {len(tweet_text)} chars[/dim]")
        
        if len(tweet_text) > TextLimits.TWEET_MAX_LENGTH:
            tweet_text = tweet_text[:TextLimits.TWEET_MAX_LENGTH - 3] + "..."
        return tweet_text
        
    except Exception as e:
        console.print(f"[red]❌ Gemini Tweet Error: {type(e).__name__}: {e}[/red]")
        return ""


def _gemini_generate_combined(title: str, text: str, topic: str) -> dict[str, str]:
    """Generate both summary and tweet in single Gemini API call."""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        return {"tweet": "", "summary": ""}
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        truncated = text[:TextLimits.COMBINED_MAX_INPUT] if len(text) > TextLimits.COMBINED_MAX_INPUT else text
        
        system_prompt = prompt_loader.get('combined_generation', 'system', 
            default="Output JSON with 'tweet' and 'summary' keys.")
        user_prompt_tpl = prompt_loader.get('combined_generation', 'user', 
            default="Title: {title}\nText: {text}")
        user_prompt = user_prompt_tpl.format(title=title, text=truncated)
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        console.print(f"[dim]📤 Gemini Combined: Sending {len(full_prompt)} chars...[/dim]")

        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.6,
                max_output_tokens=1024
            )
        )
        
        if not response.text:
            console.print(f"[red]❌ Gemini returned empty response[/red]")
            return {"tweet": "", "summary": ""}
        
        raw_output = response.text.strip()
        result = _parse_combined_json(raw_output)
        
        console.print(f"[dim]✅ Gemini Combined: Got tweet ({len(result.get('tweet', ''))} chars) + summary[/dim]")
        return result
        
    except Exception as e:
        console.print(f"[red]❌ Gemini Combined error: {type(e).__name__}: {e}[/red]")
        return {"tweet": "", "summary": ""}


# --- Helper Functions ---

def _parse_combined_json(raw_output: str) -> dict[str, str]:
    """Parse JSON from AI response with fallback handling."""
    # Clean markdown code blocks if present
    cleaned = raw_output
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].split("```")[0]
    
    cleaned = cleaned.strip()
    
    try:
        data = json.loads(cleaned)
        tweet = data.get("tweet", "").strip().replace('**', '').replace('__', '')
        summary = data.get("summary", "").strip()
        
        if len(tweet) > TextLimits.TWEET_MAX_LENGTH:
            tweet = tweet[:TextLimits.TWEET_MAX_LENGTH - 3] + "..."
        
        return {"tweet": tweet, "summary": summary}
    except json.JSONDecodeError:
        console.print("[dim]JSON parse failed, using fallback extraction[/dim]")
        return {"tweet": raw_output[:750] if raw_output else "", "summary": ""}


# --- Public API Functions ---

def ai_summarize(text: str, max_sentences: int = 3, for_twitter: bool = False, provider: Optional[str] = None) -> str:
    """Public wrapper for AI summarization."""
    target_provider = provider or AI_PROVIDER
    
    if target_provider == "gemini":
        return _gemini_summarize(text, max_sentences, for_twitter)
    else:
        return _groq_summarize(text, max_sentences, for_twitter)


def ai_generate_tweet_text(title: str, text: str, topic: str, provider: Optional[str] = None) -> str:
    """Public wrapper for AI tweet generation."""
    target_provider = provider or AI_PROVIDER
    
    if target_provider == "gemini":
        return _gemini_generate_tweet(title, text, topic)
    else:
        return _groq_generate_tweet(title, text, topic)


def ai_generate_combined(title: str, text: str, topic: str, provider: Optional[str] = None) -> dict[str, str]:
    """Public wrapper for combined AI generation (summary + tweet)."""
    target_provider = provider or AI_PROVIDER
    
    if target_provider == "gemini":
        return _gemini_generate_combined(title, text, topic)
    else:
        return _groq_generate_combined(title, text, topic)
