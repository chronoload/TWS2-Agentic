import time
import uuid
from collections import deque
from enum import Enum
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Dict, List, Optional


class EventType(Enum):
    TURN_START = "turn_start"
    TURN_COMPLETE = "turn_complete"
    TURN_ERROR = "turn_error"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    TOOL_CALL_DENIED = "tool_call_denied"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_STREAM_TOKEN = "llm_stream_token"
    HOOK_EXECUTED = "hook_executed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    AGENT_MESSAGE = "agent_message"
    SUB_AGENT_START = "sub_agent_start"
    SUB_AGENT_COMPLETE = "sub_agent_complete"
    SANDBOX_EXEC_START = "sandbox_exec_start"
    SANDBOX_EXEC_COMPLETE = "sandbox_exec_complete"
    SESSION_CREATED = "session_created"
    SESSION_CLOSED = "session_closed"


@dataclass
class Event:
    type: EventType
    data: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


class EventStream:
    def __init__(self, max_history: int = 1000):
        self._listeners: Dict[EventType, List[Callable]] = {}
        self._global_listeners: List[Callable] = []
        self._history: deque = deque(maxlen=max_history)
        self._lock = Lock()

    def on(self, event_type: EventType, listener: Callable):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def on_any(self, listener: Callable):
        self._global_listeners.append(listener)

    def emit(self, event_type: EventType, **data):
        event = Event(type=event_type, data=data)
        with self._lock:
            self._history.append(event)
        listeners = self._listeners.get(event_type, [])
        for listener in listeners + self._global_listeners:
            try:
                listener(event)
            except Exception:
                pass

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        with self._lock:
            if event_type is None:
                return list(self._history)[-limit:]
            return [e for e in self._history if e.type == event_type][-limit:]

    def clear(self):
        with self._lock:
            self._history.clear()
