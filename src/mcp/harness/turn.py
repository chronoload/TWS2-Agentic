import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class TurnStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


@dataclass
class TurnResult:
    id: str
    status: TurnStatus
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: List[Dict] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    items: List[Dict] = field(default_factory=list)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at is not None and self.completed_at is not None:
            return (self.completed_at - self.started_at) * 1000
        return None

    @property
    def final_response(self) -> Optional[str]:
        if self.content:
            return self.content
        if self.items:
            for item in reversed(self.items):
                if item.get("role") == "assistant" and item.get("content"):
                    return item["content"]
        return None


class Turn:
    def __init__(self, turn_id: Optional[str] = None):
        self._result = TurnResult(
            id=turn_id or uuid.uuid4().hex[:8],
            status=TurnStatus.PENDING,
        )

    @property
    def result(self) -> TurnResult:
        return self._result

    @property
    def id(self) -> str:
        return self._result.id

    @property
    def status(self) -> TurnStatus:
        return self._result.status

    @property
    def is_cancelled(self) -> bool:
        return self._result.status == TurnStatus.CANCELLED

    def start(self):
        self._result.status = TurnStatus.RUNNING
        self._result.started_at = time.time()

    def complete(self, content: str, **kwargs):
        self._result.status = TurnStatus.COMPLETED
        self._result.content = content
        self._result.completed_at = time.time()
        for k, v in kwargs.items():
            if hasattr(self._result, k):
                setattr(self._result, k, v)

    def fail(self, error: str):
        self._result.status = TurnStatus.FAILED
        self._result.error = error
        self._result.completed_at = time.time()

    def cancel(self):
        self._result.status = TurnStatus.CANCELLED
        self._result.completed_at = time.time()

    def interrupt(self):
        self._result.status = TurnStatus.INTERRUPTED
        self._result.completed_at = time.time()

    def add_item(self, role: str, content: Any, **kwargs):
        item = {"role": role, "content": content}
        item.update(kwargs)
        self._result.items.append(item)
