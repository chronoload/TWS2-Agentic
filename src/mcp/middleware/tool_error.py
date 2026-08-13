import logging
import traceback
from typing import Any, Dict, List

from .base import AgentMiddleware, MiddlewareContext, MiddlewareResult, MiddlewareAction

logger = logging.getLogger(__name__)


class ToolErrorMiddleware(AgentMiddleware):
    name = "tool_error"
    order = 5

    def __init__(self, max_retries: int = 0, fallback_message: str = ""):
        self.max_retries = max_retries
        self.fallback_message = fallback_message
        self._error_counts: Dict[str, int] = {}

    def after_tool(self, tool_name: str, tool_args: dict, tool_result: str, context: MiddlewareContext) -> MiddlewareResult:
        is_error = False
        if isinstance(tool_result, str):
            lower = tool_result.lower()
            if lower.startswith('{"success":false') or "error" in lower[:50].lower():
                is_error = True

        if is_error:
            key = f"{context.session_id}:{tool_name}"
            self._error_counts[key] = self._error_counts.get(key, 0) + 1
            count = self._error_counts[key]

            if count >= 3:
                logger.warning(f"ToolError: {tool_name} failed {count} times in session {context.session_id}")
                return MiddlewareResult(
                    action=MiddlewareAction.INJECT,
                    inject_content=(
                        f"[工具错误提示] 工具 {tool_name} 已连续失败 {count} 次。"
                        f"请考虑换一种方法或检查参数是否正确。"
                    ),
                    inject_role="user",
                    reason=f"tool {tool_name} failed {count} times",
                )

        return MiddlewareResult()

    def before_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        session_key_prefix = f"{context.session_id}:"
        keys_to_reset = [k for k in self._error_counts if k.startswith(session_key_prefix)]
        for k in keys_to_reset:
            del self._error_counts[k]
        return MiddlewareResult()

    def wrap_exception_as_tool_message(self, tool_call_id: str, tool_name: str, error: Exception) -> Dict[str, Any]:
        error_msg = f"工具 {tool_name} 执行失败: {type(error).__name__}: {str(error)}"
        logger.error(f"ToolError wrapping: {error_msg}")
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": error_msg,
        }
