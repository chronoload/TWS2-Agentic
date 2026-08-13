"""EventBus 全量事件：emit/subscribe + NDJSON 落盘（机器可读轨）。"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Callable

Handler = Callable[[dict], None]


class EventBus:
    def __init__(self, sink: Path | None = None) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._sink = sink

    def set_sink(self, sink: Path) -> None:
        self._sink = sink

    def subscribe(self, event: str, handler: Handler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, data: dict) -> None:
        record = {"ts": time.time(), "event": event, "data": data}
        for h in self._handlers.get(event, []):
            h(record)
        if self._sink is not None:
            with self._sink.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
