import time
from typing import Any, Optional
import threading

class TTLCache:
    """Simple in-memory cache with TTL support."""

    def __init__(self):
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                return None

            return entry["value"]

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL in seconds."""
        with self._lock:
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + ttl,
                "updated_at": time.time()
            }

    def get_updated_at(self, key: str) -> Optional[float]:
        """Get the timestamp when the key was last updated."""
        with self._lock:
            if key in self._cache:
                return self._cache[key].get("updated_at")
            return None


# Global cache instance
cache = TTLCache()
