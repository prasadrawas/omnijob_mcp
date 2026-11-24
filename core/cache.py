"""
Shared Thread-Safe TTL Cache for OmniJob MCP.
Caches job searches, JD lookups, and candidate profiles to minimize duplicate API roundtrips.
"""
import time
from threading import Lock
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    """Thread-safe in-memory cache with time-to-live expiration."""

    def __init__(self, default_ttl: int = 180, default_ttl_seconds: Optional[int] = None, max_size: int = 1000):
        self.default_ttl = default_ttl_seconds if default_ttl_seconds is not None else default_ttl
        self.max_size = max_size
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value if key exists and has not expired."""
        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None
            value, expiry = self._store[key]
            if time.time() > expiry:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None, ttl_seconds: Optional[int] = None) -> None:
        """Store value with specified TTL (in seconds) or default TTL."""
        effective_ttl = ttl if ttl is not None else (ttl_seconds if ttl_seconds is not None else self.default_ttl)
        expiry = time.time() + effective_ttl
        with self._lock:
            if len(self._store) >= self.max_size:
                now = time.time()
                expired = [k for k, (_, exp) in self._store.items() if now > exp]
                for k in expired:
                    del self._store[k]
                if len(self._store) >= self.max_size:
                    oldest = min(self._store.keys(), key=lambda k: self._store[k][1])
                    del self._store[oldest]
            self._store[key] = (value, expiry)

    def invalidate(self, prefix: str = "") -> None:
        """Invalidate keys matching prefix, or all keys if prefix is empty."""
        with self._lock:
            if not prefix:
                self._store.clear()
            else:
                keys_to_del = [k for k in self._store if k.startswith(prefix)]
                for k in keys_to_del:
                    del self._store[k]

    def clear(self) -> None:
        """Purge all entries."""
        self.invalidate("")

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def size(self) -> int:
        """Return total items in store."""
        with self._lock:
            return len(self._store)

    def stats(self) -> Dict[str, Any]:
        """Return cache metrics."""
        with self._lock:
            now = time.time()
            active_keys = sum(1 for _, exp in self._store.values() if now <= exp)
            total = self._hits + self._misses
            hit_ratio = round((self._hits / total) * 100, 2) if total > 0 else 0.0
            return {
                "active_items": active_keys,
                "total_items": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio_pct": hit_ratio,
            }
