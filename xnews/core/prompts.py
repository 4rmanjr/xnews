"""
xnews - Prompt Loader Module
Loads and manages AI prompts from YAML file.
"""

import os
from typing import Any, Optional

from rich.console import Console

from xnews.config import PROMPT_FILE

console = Console()

# YAML Support
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class PromptLoader:
    """Handles loading and formatting of prompts from YAML file."""
    
    def __init__(self, filepath: str = PROMPT_FILE) -> None:
        self.filepath: str = filepath
        self.prompts: dict[str, Any] = self._load_prompts()

    def _load_prompts(self) -> dict[str, Any]:
        if not YAML_AVAILABLE:
            return {}
        
        if not os.path.exists(self.filepath):
            console.print(f"[yellow]Warning: {self.filepath} not found. Using internal defaults.[/yellow]")
            return {}
            
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as e:
            console.print(f"[red]Error loading prompts: {e}[/red]")
            return {}

    def get(self, *keys: str, default: Optional[Any] = None) -> Optional[Any]:
        """Deep get for nested dictionary."""
        val: Any = self.prompts
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                return default
        return val if val is not None else default


# Global prompt loader instance
prompt_loader = PromptLoader()
