import datetime
import logging
from typing import Any, Dict, List, Optional

from .base import AgentMiddleware, MiddlewareContext, MiddlewareResult, MiddlewareAction

logger = logging.getLogger(__name__)


class DynamicContextMiddleware(AgentMiddleware):
    name = "dynamic_context"
    order = 9

    def __init__(self, memory_provider: Optional[Any] = None):
        self.memory_provider = memory_provider
        self._last_injection_date: Dict[str, str] = {}

    def before_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        session_key = context.session_id or "default"
        today = datetime.date.today().isoformat()
        day_name = datetime.date.today().strftime("%A")
        date_str = f"{today}, {day_name}"

        parts = []

        memory_content = self._get_memory_content(session_key)
        if memory_content:
            parts.append(f"<memory>\n{memory_content}\n</memory>")

        last_date = self._last_injection_date.get(session_key)
        if last_date != today:
            parts.append(f"<current_date>{date_str}</current_date>")
            self._last_injection_date[session_key] = today

        if not parts:
            return MiddlewareResult()

        reminder = "<system-reminder>\n" + "\n".join(parts) + "\n</system-reminder>"

        current = list(messages)
        for i, msg in enumerate(current):
            if msg.get("role") == "user" and msg.get("content"):
                original_id = msg.get("id", f"msg_{i}")
                reminder_msg = {"role": "user", "content": reminder, "id": original_id}
                user_msg = {
                    "role": "user",
                    "content": msg["content"],
                    "id": f"{original_id}__user",
                }
                current[i] = reminder_msg
                current.insert(i + 1, user_msg)
                break

        return MiddlewareResult(
            action=MiddlewareAction.MODIFY,
            modified_messages=current,
        )

    def _get_memory_content(self, session_key: str) -> str:
        if self.memory_provider is None:
            return ""
        try:
            if hasattr(self.memory_provider, "get_relevant"):
                return self.memory_provider.get_relevant(session_key)
            if hasattr(self.memory_provider, "get"):
                return str(self.memory_provider.get(session_key, ""))
        except Exception as e:
            logger.error(f"DynamicContext: memory error: {e}")
        return ""
