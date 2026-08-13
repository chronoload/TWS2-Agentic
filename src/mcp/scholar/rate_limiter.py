import time
import threading
from typing import Dict


class RateLimiter:
    def __init__(self, min_interval: float = 1.0):
        self._min_interval = min_interval
        self._last_request: Dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, api_name: str):
        with self._lock:
            now = time.time()
            last = self._last_request.get(api_name, 0.0)
            elapsed = now - last
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
                time.sleep(wait)
            self._last_request[api_name] = time.time()

    def get_remaining(self, api_name: str) -> str:
        return "unknown"

    def update_from_headers(self, api_name: str, headers: dict):
        pass
