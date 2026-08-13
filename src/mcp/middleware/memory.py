import logging
import threading
from collections import deque
from typing import Any, Callable, Dict, List, Optional

from .base import AgentMiddleware, MiddlewareContext, MiddlewareResult, MiddlewareAction

logger = logging.getLogger(__name__)


class MemoryQueue:
    def __init__(self, max_size: int = 200, flush_interval: float = 5.0):
        self._queue: deque = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._flush_interval = flush_interval
        self._provider: Optional[Any] = None

    def set_provider(self, provider: Any):
        self._provider = provider

    def enqueue(self, session_id: str, role: str, content: str):
        with self._lock:
            self._queue.append({
                "session_id": session_id,
                "role": role,
                "content": content,
            })

    def flush(self):
        items = []
        with self._lock:
            items = list(self._queue)
            self._queue.clear()

        if not items or not self._provider:
            return

        try:
            for item in items:
                if hasattr(self._provider, "add"):
                    self._provider.add(
                        session_id=item["session_id"],
                        role=item["role"],
                        content=item["content"],
                    )
        except Exception as e:
            logger.error(f"MemoryQueue flush error: {e}")


class MemoryMiddleware(AgentMiddleware):
    name = "memory"
    order = 9

    def __init__(self, memory_provider: Optional[Any] = None):
        self._queue = MemoryQueue()
        if memory_provider:
            self._queue.set_provider(memory_provider)

    def set_provider(self, provider: Any):
        self._queue.set_provider(provider)

    def after_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        session_key = context.session_id or "default"

        user_content = ""
        assistant_content = ""

        for msg in reversed(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not content or not isinstance(content, str):
                continue
            if role == "user" and not user_content:
                user_content = content[:500]
            elif role == "assistant" and not assistant_content:
                assistant_content = content[:500]
            if user_content and assistant_content:
                break

        if user_content:
            self._queue.enqueue(session_key, "user", user_content)
        if assistant_content:
            self._queue.enqueue(session_key, "assistant", assistant_content)

        self._queue.flush()

        return MiddlewareResult()
