import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    TIMEOUT = "timeout"


class DisconnectMode(Enum):
    CANCEL = "cancel"
    CONTINUE = "continue"


class MultitaskStrategy(Enum):
    REJECT = "reject"
    INTERRUPT = "interrupt"
    ROLLBACK = "rollback"


@dataclass
class RunRecord:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    thread_id: str = ""
    status: RunStatus = RunStatus.PENDING
    on_disconnect: DisconnectMode = DisconnectMode.CANCEL
    multitask_strategy: MultitaskStrategy = MultitaskStrategy.INTERRUPT
    metadata: Dict[str, Any] = field(default_factory=dict)
    task: Optional[asyncio.Task] = None
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    error: Optional[str] = None
    model_name: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0
    pre_run_checkpoint_id: Optional[str] = None

    @property
    def duration_ms(self) -> int:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at) * 1000)
        return 0

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            RunStatus.SUCCESS,
            RunStatus.ERROR,
            RunStatus.INTERRUPTED,
            RunStatus.TIMEOUT,
        )


class RunManager:
    def __init__(self, store=None):
        self._runs: Dict[str, RunRecord] = {}
        self._store = store
        self._lock = None
        try:
            loop = asyncio.get_running_loop()
            self._lock = asyncio.Lock()
        except RuntimeError:
            pass

    def create_or_reject(
        self,
        thread_id: str,
        model_name: str = "",
        multitask_strategy: MultitaskStrategy = MultitaskStrategy.INTERRUPT,
        metadata: Optional[Dict] = None,
    ) -> RunRecord:
        existing = self._find_running_by_thread(thread_id)
        if existing is not None:
            if multitask_strategy == MultitaskStrategy.REJECT:
                raise RuntimeError(f"线程 {thread_id} 已有运行中的任务")
            elif multitask_strategy == MultitaskStrategy.INTERRUPT:
                self.cancel(existing.run_id)
            elif multitask_strategy == MultitaskStrategy.ROLLBACK:
                self.cancel(existing.run_id)

        record = RunRecord(
            thread_id=thread_id,
            model_name=model_name,
            multitask_strategy=multitask_strategy,
            metadata=metadata or {},
        )
        self._runs[record.run_id] = record
        return record

    def mark_running(self, run_id: str):
        record = self._runs.get(run_id)
        if record:
            record.status = RunStatus.RUNNING
            record.started_at = time.time()

    def mark_success(self, run_id: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        record = self._runs.get(run_id)
        if record:
            record.status = RunStatus.SUCCESS
            record.completed_at = time.time()
            record.prompt_tokens = prompt_tokens
            record.completion_tokens = completion_tokens
            self._persist(record)

    def mark_error(self, run_id: str, error: str):
        record = self._runs.get(run_id)
        if record:
            record.status = RunStatus.ERROR
            record.error = error
            record.completed_at = time.time()
            self._persist(record)

    def mark_interrupted(self, run_id: str):
        record = self._runs.get(run_id)
        if record:
            record.status = RunStatus.INTERRUPTED
            record.completed_at = time.time()
            self._persist(record)

    def mark_timeout(self, run_id: str):
        record = self._runs.get(run_id)
        if record:
            record.status = RunStatus.TIMEOUT
            record.completed_at = time.time()
            self._persist(record)

    def cancel(self, run_id: str):
        record = self._runs.get(run_id)
        if record and not record.is_terminal:
            record.abort_event.set()
            if record.task and not record.task.done():
                record.task.cancel()
            self.mark_interrupted(run_id)

    def get(self, run_id: str) -> Optional[RunRecord]:
        return self._runs.get(run_id)

    def get_running(self, thread_id: str) -> Optional[RunRecord]:
        return self._find_running_by_thread(thread_id)

    def list_runs(self, thread_id: str = "", limit: int = 50) -> List[RunRecord]:
        runs = list(self._runs.values())
        if thread_id:
            runs = [r for r in runs if r.thread_id == thread_id]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    def cleanup(self, max_age_seconds: int = 3600):
        now = time.time()
        to_remove = []
        for run_id, record in self._runs.items():
            if record.is_terminal and record.completed_at:
                if now - record.completed_at > max_age_seconds:
                    to_remove.append(run_id)
        for run_id in to_remove:
            del self._runs[run_id]

    def _find_running_by_thread(self, thread_id: str) -> Optional[RunRecord]:
        for record in self._runs.values():
            if record.thread_id == thread_id and record.status == RunStatus.RUNNING:
                return record
        return None

    def _persist(self, record: RunRecord):
        if self._store and hasattr(self._store, "save_run"):
            try:
                self._store.save_run(record)
            except Exception as e:
                logger.error(f"RunManager persist error: {e}")
