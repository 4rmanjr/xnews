"""
xnews - Cache Manager Module
File-based caching with TTL support.
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from xnews.config import CACHE_DIR, CACHE_TTL_HOURS


class CacheManager:
    """Simple file-based cache system with TTL."""
    
    def __init__(self) -> None:
        self.cache_dir: Path = Path(CACHE_DIR)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_hash(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if exists and not expired."""
        cache_file = self.cache_dir / f"{self._get_hash(key)}.json"
        if not cache_file.exists():
            return None
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            # Check TTL
            cached_time = datetime.fromisoformat(data['cached_at'])
            if datetime.now() - cached_time > timedelta(hours=CACHE_TTL_HOURS):
                cache_file.unlink()
                return None
            return data['content']
        except (json.JSONDecodeError, KeyError, OSError):
            return None
    
    def set(self, key: str, content: Any) -> None:
        """Cache a value with current timestamp."""
        cache_file = self.cache_dir / f"{self._get_hash(key)}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'cached_at': datetime.now().isoformat(),
                    'content': content
                }, f)
        except OSError:
            pass
    
    def clear(self) -> None:
        """Clear all cached files."""
        for f in self.cache_dir.glob("*.json"):
            f.unlink()


# Global cache instance
cache = CacheManager()
