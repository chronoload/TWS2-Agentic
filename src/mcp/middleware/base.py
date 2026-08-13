import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class MiddlewareAction(Enum):
    CONTINUE = "continue"
    MODIFY = "modify"
    STOP = "stop"
    INJECT = "inject"


@dataclass
class MiddlewareResult:
    action: MiddlewareAction = MiddlewareAction.CONTINUE
    modified_messages: Optional[List[Dict[str, Any]]] = None
    inject_content: Optional[str] = None
    inject_role: str = "user"
    reason: str = ""
    force_stop: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MiddlewareContext:
    session_id: str = ""
    thread_id: str = ""
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    turn_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    started_at: float = field(default_factory=time.time)
    model_id: str = ""
    cancel_event: Any = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self.started_at) * 1000


class AgentMiddleware(ABC):
    name: str = "base"
    order: int = 100

    def before_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    def after_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    def after_model(self, response: Any, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    def before_tool(self, tool_name: str, tool_args: Dict[str, Any], context: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    def after_tool(self, tool_name: str, tool_args: Dict[str, Any], tool_result: str, context: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    def wrap_model_call(self, request_messages: List[Dict[str, Any]], handler: Callable, context: MiddlewareContext) -> Any:
        return handler(request_messages)
