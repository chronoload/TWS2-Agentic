import logging
from typing import Any, Callable, Dict, List, Optional

from .base import AgentMiddleware, MiddlewareContext, MiddlewareResult, MiddlewareAction

logger = logging.getLogger(__name__)


class MiddlewareChain:
    def __init__(self):
        self._middlewares: List[AgentMiddleware] = []

    def add(self, middleware: AgentMiddleware) -> "MiddlewareChain":
        self._middlewares.append(middleware)
        self._middlewares.sort(key=lambda m: m.order)
        return self

    def remove(self, name: str) -> bool:
        before = len(self._middlewares)
        self._middlewares = [m for m in self._middlewares if m.name != name]
        return len(self._middlewares) < before

    def insert_before(self, target_name: str, middleware: AgentMiddleware) -> bool:
        for i, m in enumerate(self._middlewares):
            if m.name == target_name:
                self._middlewares.insert(i, middleware)
                return True
        self._middlewares.append(middleware)
        return False

    def insert_after(self, target_name: str, middleware: AgentMiddleware) -> bool:
        for i, m in enumerate(self._middlewares):
            if m.name == target_name:
                self._middlewares.insert(i + 1, middleware)
                return True
        self._middlewares.append(middleware)
        return False

    @property
    def middlewares(self) -> List[AgentMiddleware]:
        return list(self._middlewares)

    def run_before_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> Optional[List[Dict[str, Any]]]:
        current = messages
        for mw in self._middlewares:
            try:
                result = mw.before_agent(current, context)
                if result.action == MiddlewareAction.STOP:
                    logger.info(f"Middleware {mw.name} stopped before_agent: {result.reason}")
                    return None
                if result.action == MiddlewareAction.MODIFY and result.modified_messages is not None:
                    current = result.modified_messages
                if result.action == MiddlewareAction.INJECT and result.inject_content:
                    inject_msg = {"role": result.inject_role, "content": result.inject_content}
                    current = current + [inject_msg]
            except Exception as e:
                logger.error(f"Middleware {mw.name} error in before_agent: {e}")
        return current

    def run_after_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> List[Dict[str, Any]]:
        current = messages
        for mw in self._middlewares:
            try:
                result = mw.after_agent(current, context)
                if result.action == MiddlewareAction.MODIFY and result.modified_messages is not None:
                    current = result.modified_messages
            except Exception as e:
                logger.error(f"Middleware {mw.name} error in after_agent: {e}")
        return current

    def run_after_model(self, response: Any, messages: List[Dict[str, Any]], context: MiddlewareContext) -> Optional[MiddlewareResult]:
        for mw in self._middlewares:
            try:
                result = mw.after_model(response, messages, context)
                if result.action == MiddlewareAction.STOP:
                    logger.info(f"Middleware {mw.name} stopped after_model: {result.reason}")
                    return result
                if result.action == MiddlewareAction.INJECT and result.inject_content:
                    return result
            except Exception as e:
                logger.error(f"Middleware {mw.name} error in after_model: {e}")
        return None

    def run_before_tool(self, tool_name: str, tool_args: Dict[str, Any], context: MiddlewareContext) -> MiddlewareResult:
        for mw in self._middlewares:
            try:
                result = mw.before_tool(tool_name, tool_args, context)
                if result.action == MiddlewareAction.STOP:
                    return result
                if result.action == MiddlewareAction.MODIFY and result.modified_messages is None:
                    tool_args.update(result.metadata)
            except Exception as e:
                logger.error(f"Middleware {mw.name} error in before_tool: {e}")
        return MiddlewareResult()

    def run_after_tool(self, tool_name: str, tool_args: Dict[str, Any], tool_result: str, context: MiddlewareContext) -> MiddlewareResult:
        for mw in self._middlewares:
            try:
                result = mw.after_tool(tool_name, tool_args, tool_result, context)
                if result.action == MiddlewareAction.STOP:
                    return result
            except Exception as e:
                logger.error(f"Middleware {mw.name} error in after_tool: {e}")
        return MiddlewareResult()

    def run_wrap_model_call(self, request_messages: List[Dict[str, Any]], handler: Callable, context: MiddlewareContext) -> Any:
        wrapped = handler
        for mw in reversed(self._middlewares):
            prev = wrapped
            _mw = mw
            def _make_wrapper(middleware, inner):
                def _wrapper(msgs):
                    return middleware.wrap_model_call(msgs, inner, context)
                return _wrapper
            wrapped = _make_wrapper(_mw, prev)
        return wrapped(request_messages)
