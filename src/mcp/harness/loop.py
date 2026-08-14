# -*- coding: utf-8 -*-
"""AgentLoop —— 自主循环引擎（长程任务驱动）

职责：提交即自主。用户 submit(goal) 后，loop 在后台线程串行执行任务队列，
每个任务多回合（复用 HarnessRunner.run_turn）直到：

- 某回合无 tool_calls → 任务 COMPLETED（自然完成）
- 达 max_turns 预算 → 任务 HALTED（等待人工/总指挥介入，T2 完善广播）
- runner 异常 → 任务 FAILED

loop 本身是状态机：IDLE / RUNNING / PAUSED / STOPPED。

设计要点（langdriven）：
- 消息泵（Actor 模型）：queue.Queue 承载任务事件，submit 显式唤醒；
  后台线程 queue.get(timeout=heartbeat) 阻塞等待 —— 事件驱动 + 心跳兜底。
- step() 是同步可测核心（手动模式），线程仅做外层驱动 —— TDD 确定性。
- 复用：HarnessRunner.run_turn（单回合）+ MiddlewareChain（横切，T1 预留）。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LoopStatus(Enum):
    """AgentLoop 生命周期状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class TaskStatus(Enum):
    """长程任务生命周期状态"""
    PENDING = "pending"      # 排队中
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 自然完成（回合无 tool_calls）
    FAILED = "failed"        # 执行异常
    HALTED = "halted"        # 预算用尽/需人工介入（等待总指挥）


@dataclass
class LoopTask:
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    turn_count: int = 0
    max_turns: int = 30
    max_duration_seconds: Optional[float] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None

    def snapshot(self) -> Dict[str, Any]:
        """状态快照（前端轮询/事件广播用）"""
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "turn_count": self.turn_count,
            "max_turns": self.max_turns,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }


class AgentLoop:
    """自主循环引擎：状态机 + queue 消息泵 + 串行 FIFO 任务队列"""

    def __init__(
        self,
        runner=None,
        middleware_chain=None,
        heartbeat: float = 1.0,
        max_turns: int = 30,
        max_duration_seconds: float = 1800.0,
        event_bus=None,
    ):
        self.runner = runner
        self.middleware_chain = middleware_chain  # 横切管线挂载点
        self.heartbeat = heartbeat
        self.default_max_turns = max_turns
        self.default_max_duration = max_duration_seconds
        self._event_bus = event_bus  # 事件广播通道（复用 automation.event_bus.EventBus）
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._tasks: Dict[str, LoopTask] = {}
        self._lock = threading.RLock()
        self._status = LoopStatus.IDLE
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ────────────────────────── 状态机 ──────────────────────────

    @property
    def status(self) -> LoopStatus:
        return self._status

    def set_runner(self, runner):
        """注入/替换执行器（真实 HarnessRunner 或测试 fake）"""
        self.runner = runner

    def start(self):
        """启动后台 loop 线程（幂等）"""
        with self._lock:
            if self._status == LoopStatus.RUNNING:
                return
            self._status = LoopStatus.RUNNING
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="agent-loop"
        )
        self._thread.start()
        logger.info("AgentLoop started")

    def stop(self):
        """停止 loop（幂等；唤醒阻塞线程并 join）"""
        with self._lock:
            self._status = LoopStatus.STOPPED
        self._stop_event.set()
        try:
            self._queue.put_nowait("")  # 唤醒 queue.get 阻塞
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("AgentLoop stopped")

    def pause(self):
        """暂停：不再 drain 新任务（已提交任务保留在队列）"""
        with self._lock:
            if self._status == LoopStatus.RUNNING:
                self._status = LoopStatus.PAUSED
        try:
            self._queue.put_nowait("")  # 唤醒线程及时响应暂停
        except Exception:
            pass

    def resume(self):
        """恢复处理"""
        with self._lock:
            if self._status == LoopStatus.PAUSED:
                self._status = LoopStatus.RUNNING

    # ────────────────────────── 任务接口 ──────────────────────────

    def submit(self, goal: str, max_turns: Optional[int] = None,
               max_duration_seconds: Optional[float] = None) -> str:
        """提交长程任务（入队即返回 task_id；后台自主执行）"""
        task = LoopTask(
            task_id=uuid.uuid4().hex[:12],
            goal=goal,
            max_turns=max_turns or self.default_max_turns,
            max_duration_seconds=max_duration_seconds or self.default_max_duration,
        )
        with self._lock:
            self._tasks[task.task_id] = task
        self._queue.put(task.task_id)
        logger.info("AgentLoop task submitted: %s goal=%r", task.task_id, goal[:60])
        return task.task_id

    def get_task(self, task_id: str) -> Optional[LoopTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[LoopTask]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    # ────────────────────────── 核心：step（同步可测） ──────────────────────────

    def step(self, timeout: float = 0.0) -> Optional[str]:
        """处理一个任务（直到该任务完成/挂起/预算用尽）。返回 task_id 或 None。

        手动模式（测试/单步）直接调用；后台线程内部以 heartbeat 为 timeout 调用。
        """
        if self._status in (LoopStatus.PAUSED, LoopStatus.STOPPED):
            return None
        try:
            task_id = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if not task_id:
            return None
        return self._run_task(task_id)

    def _run_task(self, task_id: str) -> str:
        task = self.get_task(task_id)
        if task is None:
            return task_id
        if task.status == TaskStatus.COMPLETED:
            return task_id

        with self._lock:
            task.status = TaskStatus.RUNNING
            task.started_at = task.started_at or datetime.now().isoformat()
        self._emit("agent_loop.task_started", task)

        messages: List[Dict[str, Any]] = [{"role": "user", "content": task.goal}]
        while task.turn_count < task.max_turns:
            # ── 时长预算检查（超时 → 挂起，等待人工） ──
            if task.max_duration_seconds and task.started_at:
                elapsed = time.time() - _parse_ts(task.started_at)
                if elapsed > task.max_duration_seconds:
                    task.status = TaskStatus.HALTED
                    task.error = f"达到 max_duration={task.max_duration_seconds}s"
                    task.completed_at = datetime.now().isoformat()
                    break

            task.turn_count += 1

            if self.runner is None:
                task.status = TaskStatus.FAILED
                task.error = "runner 未配置"
                break

            # ── middleware 横切：before_agent ──
            mw_context = None
            if self.middleware_chain is not None:
                try:
                    from ..middleware.base import MiddlewareContext
                    mw_context = MiddlewareContext(
                        session_id=task_id, turn_count=task.turn_count,
                    )
                    msgs = self.middleware_chain.run_before_agent(messages, mw_context)
                    if msgs is not None:
                        messages = msgs
                except Exception as e:
                    logger.warning("AgentLoop middleware before_agent error: %s", e)

            try:
                result = self.runner.run_turn(messages)
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = f"{type(e).__name__}: {e}"
                break

            # ── middleware 横切：after_agent ──
            if mw_context is not None:
                try:
                    self.middleware_chain.run_after_agent(messages, mw_context)
                except Exception as e:
                    logger.warning("AgentLoop middleware after_agent error: %s", e)

            if getattr(result, "tool_calls", None):
                # 还有工具调用 → 拼接 assistant + tool 回合，继续下一回合
                messages.append(
                    {"role": "assistant", "content": getattr(result, "content", "") or ""}
                )
                for entry in result.tool_calls:
                    tc = entry.get("tool_call", entry) if isinstance(entry, dict) else entry
                    t_id = tc.get("id", "") if isinstance(tc, dict) else ""
                    content = entry.get("result", "") if isinstance(entry, dict) else str(entry)
                    messages.append(
                        {"role": "tool", "tool_call_id": t_id, "content": content}
                    )
                continue

            # 无 tool_calls → 自然完成
            task.result = getattr(result, "content", "") or ""
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()
            break
        else:
            # while 因 max_turns 耗尽退出且未 break → 预算用尽，挂起等待人工
            if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.status = TaskStatus.HALTED
                task.error = f"达到 max_turns={task.max_turns}"
                task.completed_at = datetime.now().isoformat()

        # ── 终态广播（前端轮询/通知通道） ──
        if task.status == TaskStatus.COMPLETED:
            self._emit("agent_loop.task_completed", task)
        elif task.status == TaskStatus.FAILED:
            self._emit("agent_loop.task_failed", task)
        elif task.status == TaskStatus.HALTED:
            self._emit("agent_loop.task_halted", task)

        logger.info(
            "AgentLoop task %s -> %s (turns=%d)",
            task_id, task.status.value, task.turn_count,
        )
        return task_id

    def _emit(self, event_type: str, task: LoopTask):
        """向 EventBus 广播任务状态事件（松耦合：无总线则静默跳过）"""
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(event_type, task.snapshot())
        except Exception:
            logger.exception("AgentLoop emit %s error", event_type)

    # ────────────────────────── 后台线程 ──────────────────────────

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self.step(timeout=self.heartbeat)
            except Exception:
                logger.exception("AgentLoop tick error")


def _parse_ts(iso: str) -> float:
    """ISO 时间戳 → epoch 秒（解析失败降级为当前时间，避免预算检查崩溃）"""
    from datetime import datetime as _dt
    try:
        return _dt.fromisoformat(iso).timestamp()
    except (ValueError, TypeError):
        return time.time()


def get_agent_loop(**kwargs) -> AgentLoop:
    """模块级单例入口（与服务接线对齐 automation 风格）"""
    global _default_loop
    if _default_loop is None:
        _default_loop = AgentLoop(**kwargs)
    return _default_loop


_default_loop: Optional[AgentLoop] = None


__all__ = [
    "AgentLoop", "LoopTask", "LoopStatus", "TaskStatus",
    "get_agent_loop",
]
