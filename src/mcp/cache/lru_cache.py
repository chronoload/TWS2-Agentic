#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LRU/TTL 缓存 — 线程安全，支持过期
参考 Cline StateManager 的 MODEL_CACHE_TTL_MS 模式
"""

import time
import threading
from collections import OrderedDict
from typing import Any, Dict, Generic, Optional, TypeVar
from dataclasses import dataclass, field

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    timestamp: float = field(default_factory=time.time)
    ttl: Optional[float] = None

    @property
    def expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp


class LRUCache:
    """线程安全 LRU 缓存"""

    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return default

    def set(self, key: str, value: Any):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def delete(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._cache

    def clear(self):
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def keys(self):
        with self._lock:
            return list(self._cache.keys())

    def items(self):
        with self._lock:
            return list(self._cache.items())

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __len__(self) -> int:
        return self.size


class TTLCache:
    """带 TTL 过期的线程安全缓存"""

    def __init__(self, default_ttl: float = 3600.0, max_size: int = 500):
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 60.0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            self._maybe_cleanup()
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.expired:
                del self._cache[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        with self._lock:
            self._maybe_cleanup()
            actual_ttl = ttl if ttl is not None else self._default_ttl
            self._cache[key] = CacheEntry(value=value, ttl=actual_ttl)
            if len(self._cache) > self._max_size:
                self._evict_one()

    def set_batch(self, items: Dict[str, Any], ttl: Optional[float] = None):
        with self._lock:
            for key, value in items.items():
                actual_ttl = ttl if ttl is not None else self._default_ttl
                self._cache[key] = CacheEntry(value=value, ttl=actual_ttl)
            while len(self._cache) > self._max_size:
                self._evict_one()

    def get_or_set(self, key: str, factory, ttl: Optional[float] = None):
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl)
        return value

    def delete(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()

    def invalidate_prefix(self, prefix: str):
        with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._cache[k]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            self._maybe_cleanup()
            expired = sum(1 for e in self._cache.values() if e.expired)
            return {
                "total_entries": len(self._cache),
                "expired": expired,
                "active": len(self._cache) - expired,
                "max_size": self._max_size,
                "default_ttl": self._default_ttl,
            }

    @property
    def size(self) -> int:
        with self._lock:
            self._maybe_cleanup()
            return len(self._cache)

    def _maybe_cleanup(self):
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            self._last_cleanup = now
            expired_keys = [k for k, v in self._cache.items() if v.expired]
            for k in expired_keys:
                del self._cache[k]

    def _evict_one(self):
        if not self._cache:
            return
        oldest = min(self._cache.items(), key=lambda x: x[1].timestamp,
                     default=None)
        if oldest:
            del self._cache[oldest[0]]

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None