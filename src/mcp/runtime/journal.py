import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class JournalEventType(Enum):
    RUN_START = "run_start"
    RUN_END = "run_end"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    MIDDLEWARE = "middleware"
    CHECKPOINT = "checkpoint"
    ERROR = "error"


@dataclass
class JournalEntry:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    run_id: str = ""
    event_type: JournalEventType = JournalEventType.RUN_START
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class RunJournal:
    def __init__(self, journal_dir: Optional[str] = None, max_entries: int = 10000):
        self._entries: List[JournalEntry] = []
        self._lock = Lock()
        self._max_entries = max_entries
        self._journal_dir = Path(journal_dir) if journal_dir else None
        self._total_prompt_tokens: Dict[str, int] = {}
        self._total_completion_tokens: Dict[str, int] = {}

    def record(self, run_id: str, event_type: JournalEventType, **data) -> JournalEntry:
        entry = JournalEntry(
            run_id=run_id,
            event_type=event_type,
            data=data,
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

            if event_type == JournalEventType.LLM_CALL:
                self._total_prompt_tokens[run_id] = (
                    self._total_prompt_tokens.get(run_id, 0) + data.get("prompt_tokens", 0)
                )
                self._total_completion_tokens[run_id] = (
                    self._total_completion_tokens.get(run_id, 0) + data.get("completion_tokens", 0)
                )

        self._flush_entry(entry)
        return entry

    def get_token_usage(self, run_id: str) -> Dict[str, int]:
        return {
            "prompt_tokens": self._total_prompt_tokens.get(run_id, 0),
            "completion_tokens": self._total_completion_tokens.get(run_id, 0),
            "total_tokens": (
                self._total_prompt_tokens.get(run_id, 0)
                + self._total_completion_tokens.get(run_id, 0)
            ),
        }

    def get_entries(
        self,
        run_id: str = "",
        event_type: Optional[JournalEventType] = None,
        limit: int = 100,
    ) -> List[JournalEntry]:
        with self._lock:
            entries = list(self._entries)
        if run_id:
            entries = [e for e in entries if e.run_id == run_id]
        if event_type:
            entries = [e for e in entries if e.event_type == event_type]
        return entries[-limit:]

    def flush(self):
        if not self._journal_dir:
            return
        self._journal_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = self._journal_dir / f"journal_{timestamp}.jsonl"
        try:
            with open(path, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            with self._lock:
                self._entries.clear()
            logger.info(f"Journal flushed {len(entries)} entries to {path}")
        except Exception as e:
            logger.error(f"Journal flush error: {e}")

    def _flush_entry(self, entry: JournalEntry):
        if not self._journal_dir:
            return
        self._journal_dir.mkdir(parents=True, exist_ok=True)
        date_str = time.strftime("%Y%m%d")
        path = self._journal_dir / f"journal_{date_str}.jsonl"
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Journal entry flush error: {e}")
