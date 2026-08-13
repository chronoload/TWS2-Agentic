from __future__ import annotations

import fnmatch
import threading
import uuid
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Callable, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Event:
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class Subscription:
    subscription_id: str
    pattern: str
    callback: Callable[[Event], None]
    created_at: float = field(default_factory=time.time)


class EventBus:
    _instance: Optional["EventBus"] = None
    _init_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, Subscription] = {}
        self._pattern_index: Dict[str, List[str]] = {}
        self._history: List[Event] = []
        self._max_history = 200

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def publish(self, event_type: str, data: Dict[str, Any] = None) -> Event:
        event = Event(event_type=event_type, data=data or {})
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            matched_ids = self._find_matching_subscriptions(event_type)
        for sub_id in matched_ids:
            sub = self._subscriptions.get(sub_id)
            if sub is None:
                continue
            try:
                sub.callback(event)
            except Exception:
                logger.exception("EventBus callback error for subscription %s", sub_id)
        return event

    def subscribe(self, pattern: str, callback: Callable[[Event], None]) -> str:
        subscription_id = uuid.uuid4().hex[:12]
        sub = Subscription(
            subscription_id=subscription_id,
            pattern=pattern,
            callback=callback,
        )
        with self._lock:
            self._subscriptions[subscription_id] = sub
            if pattern not in self._pattern_index:
                self._pattern_index[pattern] = []
            self._pattern_index[pattern].append(subscription_id)
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        with self._lock:
            sub = self._subscriptions.pop(subscription_id, None)
            if sub is None:
                return False
            if sub.pattern in self._pattern_index:
                self._pattern_index[sub.pattern] = [
                    sid for sid in self._pattern_index[sub.pattern]
                    if sid != subscription_id
                ]
                if not self._pattern_index[sub.pattern]:
                    del self._pattern_index[sub.pattern]
            return True

    def _find_matching_subscriptions(self, event_type: str) -> List[str]:
        matched = []
        for pattern, sub_ids in self._pattern_index.items():
            if fnmatch.fnmatch(event_type, pattern):
                matched.extend(sub_ids)
        return matched

    def get_history(self, event_type: str = None, limit: int = 50) -> List[Event]:
        with self._lock:
            events = self._history
            if event_type:
                events = [e for e in events if fnmatch.fnmatch(e.event_type, event_type)]
            return events[-limit:]

    def clear_history(self):
        with self._lock:
            self._history.clear()


def get_event_bus() -> EventBus:
    return EventBus.get_instance()


__all__ = ["EventBus", "Event", "Subscription", "get_event_bus"]
