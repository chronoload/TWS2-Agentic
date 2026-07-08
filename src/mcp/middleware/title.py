import logging
import re
from typing import Any, Callable, Dict, List, Optional

from .base import AgentMiddleware, MiddlewareContext, MiddlewareResult

logger = logging.getLogger(__name__)


class TitleMiddleware(AgentMiddleware):
    name = "title"
    order = 50

    def __init__(self, title_callback: Optional[Callable[[str, str], None]] = None):
        self._title_callback = title_callback
        self._titled_sessions: set = set()

    def set_title_callback(self, callback: Callable[[str, str], None]):
        self._title_callback = callback

    def after_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        sid = context.session_id
        if sid in self._titled_sessions:
            return MiddlewareResult()
        assistant_responses = [m for m in messages if m.get("role") == "assistant" and m.get("content")]
        if len(assistant_responses) < 1:
            return MiddlewareResult()
        user_messages = [m for m in messages if m.get("role") == "user" and m.get("content")]
        if not user_messages:
            return MiddlewareResult()
        title = self._generate_title(user_messages[0]["content"])
        if title and self._title_callback:
            try:
                self._title_callback(sid, title)
                self._titled_sessions.add(sid)
                logger.info(f"Auto-generated title for session {sid}: {title}")
            except Exception as e:
                logger.warning(f"Title callback failed: {e}")
        return MiddlewareResult()

    @staticmethod
    def _generate_title(user_message: str) -> str:
        text = user_message.strip()
        text = re.sub(r'[\n\r\t]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        cleaned = text.strip()
        if not cleaned:
            return ""
        max_len = 50
        if len(cleaned) <= max_len:
            return cleaned
        sentences = re.split(r'[。！？.!?\n]', cleaned)
        first_sentence = next((s.strip() for s in sentences if len(s.strip()) > 3), "")
        if first_sentence and len(first_sentence) <= max_len:
            return first_sentence
        return cleaned[:max_len].rstrip() + "..."
