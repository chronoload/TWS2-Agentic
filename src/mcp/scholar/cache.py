import time
import hashlib
import json
import threading
from typing import Any, Optional, Dict


class RequestCache:
    def __init__(self, default_ttl: int = 3600, max_size: int = 1000):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_size = max_size

    def _make_key(self, method: str, url: str, params: Optional[Dict] = None) -> str:
        raw = f"{method}:{url}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, method: str, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        key = self._make_key(method, url, params)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                return None
            return entry["data"]

    def set(self, method: str, url: str, params: Optional[Dict] = None,
            data: Optional[Dict] = None, ttl: Optional[int] = None):
        key = self._make_key(method, url, params)
        expires_at = time.time() + (ttl or self._default_ttl)
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._evict()
            self._cache[key] = {"data": data, "expires_at": expires_at}

    def _evict(self):
        now = time.time()
        expired = [k for k, v in self._cache.items() if now > v["expires_at"]]
        for k in expired:
            del self._cache[k]
        if len(self._cache) >= self._max_size:
            sorted_keys = sorted(self._cache, key=lambda k: self._cache[k]["expires_at"])
            for k in sorted_keys[: len(self._cache) - self._max_size // 2]:
                del self._cache[k]

    def clear(self):
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)
