import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..worktree import remove_worktree

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
    # 本次运行关联的 git worktree 路径（由 mcp/worktree.py 的 create_task_worktree 创建）。
    # 非空表示该次任务在隔离的 worktree 中执行，用于实验性改动或并行任务隔离。
    worktree_path: Optional[str] = None
    # 任务结束后是否保留 worktree（True 表示保留，False 表示随任务结束自动清理）。
    # 由 cleanup_worktree(run_id, keep=True) 置位，用于调试期或需要人工复查的场景。
    keep_worktree: bool = False

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
            self._cleanup_worktree_if_any(record)
            self._persist(record)

    def mark_error(self, run_id: str, error: str):
        record = self._runs.get(run_id)
        if record:
            record.status = RunStatus.ERROR
            record.error = error
            record.completed_at = time.time()
            self._cleanup_worktree_if_any(record)
            self._persist(record)

    def mark_interrupted(self, run_id: str):
        record = self._runs.get(run_id)
        if record:
            record.status = RunStatus.INTERRUPTED
            record.completed_at = time.time()
            self._cleanup_worktree_if_any(record)
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

    def attach_worktree(self, run_id: str, worktree_path: str):
        """将已创建好的 worktree 关联到指定运行记录

        与 mcp/worktree.py 的 create_task_worktree 联动：外部先调用
        create_task_worktree 创建隔离工作区，再把返回的 path 登记到
        RunRecord 上。此后该任务终结时（见 _cleanup_worktree_if_any）
        会按此路径自动清理。
        """
        record = self._runs.get(run_id)
        if record:
            record.worktree_path = worktree_path
            self._persist(record)

    def cleanup_worktree(self, run_id: str, keep: bool = False) -> bool:
        """主动清理运行记录关联的 worktree

        - keep=True：标记保留（置 keep_worktree=True 并持久化），后续
          任务终结时的自动清理将跳过该 worktree，方便调试复查；
        - keep=False：调用 mcp/worktree.py 的 remove_worktree 删除，
          成功后清空 worktree_path 并持久化。
        返回清理是否成功（无可清理对象时视为成功）。
        """
        record = self._runs.get(run_id)
        # 记录不存在或尚未关联 worktree：无需清理，直接视为成功
        if not record or not record.worktree_path:
            return True
        if keep:
            # 保留模式：只打标记，不执行删除
            record.keep_worktree = True
            self._persist(record)
            return True
        removed = remove_worktree(record.worktree_path)
        if removed:
            record.worktree_path = None
            self._persist(record)
        return removed

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

    def _cleanup_worktree_if_any(self, record: RunRecord):
        """任务终结时的 worktree 自动清理（生命周期清理策略）

        在 mark_success / mark_error / mark_interrupted 等终结状态转换时被调用：
        - 仅当记录关联了 worktree（worktree_path 非空）且未被标记保留
          （keep_worktree=False）时才执行删除；
        - 复用 mcp/worktree.py 的 remove_worktree 完成 git worktree remove，
          删除成功后清空 worktree_path，避免重复清理；
        - 清理失败只记录错误日志，不阻断任务收尾流程。
        """
        if record.worktree_path and not record.keep_worktree:
            try:
                if remove_worktree(record.worktree_path):
                    record.worktree_path = None
            except Exception as exc:
                logger.error(f"RunManager worktree cleanup error: {exc}")

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
