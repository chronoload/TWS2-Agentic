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
    # 会话化：完整消息流（{role: user/assistant/tool, content, tool_calls, ts}）
    # loop 作为 autonomous 对话模式，前端像普通会话那样审核（决策①A：内存 + snapshot 暴露）
    messages: List[Dict[str, Any]] = field(default_factory=list)
    # 审核介入挂起输入：intervene() 设置，下一回合消费为 user 消息（决策③C）
    pending_input: Optional[str] = None
    # 会话级模式切换（决策A）：归属会话（Agent 面板普通会话 session_id）
    session_id: Optional[str] = None
    # 交接笔记（handoff）：终态生成结构化接力笔记 {goal, status, turns, summary,
    # decisions[], artifacts[], open_issues[]}——loop 交接 + macdev 回审双轨（冗余保障）
    handoff: Optional[Dict[str, Any]] = None

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
            "messages": list(self.messages),
            "session_id": self.session_id,
            "handoff": self.handoff,
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
        session_context=None,
    ):
        self.runner = runner
        self.middleware_chain = middleware_chain  # 横切管线挂载点
        self.heartbeat = heartbeat
        self.default_max_turns = max_turns
        self.default_max_duration = max_duration_seconds
        self._event_bus = event_bus  # 事件广播通道（复用 automation.event_bus.EventBus）
        # 会话上下文共享（spec id=4/5）：{get(sid)->msgs, append(sid, msgs)}
        # loop 回合读写同一会话上下文（普通对话+loop 回合同流），目标达成前不停
        self.session_context = session_context
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
               max_duration_seconds: Optional[float] = None,
               auto_start: bool = True,
               session_id: Optional[str] = None) -> str:
        """提交长程任务（入队即返回 task_id；后台自主执行）

        auto_start=True（默认）：提交即自主——loop 处于 IDLE 时自动启动后台线程执行
        （修复：此前 submit 只入队不启动线程，队列永不 drain → 任务永久 pending）；
        PAUSED/STOPPED 状态不强制启动（保持状态机语义）。
        auto_start=False：仅入队，配合 step() 单步驱动（测试/编排用）。
        session_id：归属会话（会话级模式切换，决策A）——loop 回合可同流显示在
        该普通会话的消息流中。
        """
        task = LoopTask(
            task_id=uuid.uuid4().hex[:12],
            goal=goal,
            max_turns=max_turns or self.default_max_turns,
            max_duration_seconds=max_duration_seconds or self.default_max_duration,
            session_id=session_id,
        )
        with self._lock:
            self._tasks[task.task_id] = task
        self._queue.put(task.task_id)
        if auto_start:
            # 仅 IDLE 且无存活线程时启动（PAUSED/STOPPED 保持挂起语义）
            with self._lock:
                need_start = (
                    self._status == LoopStatus.IDLE
                    and (self._thread is None or not self._thread.is_alive())
                )
            if need_start:
                self.start()
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

    # ────────────────────────── 审核介入（会话化，决策③C） ──────────────────────────

    def intervene(self, task_id: str, message: str) -> LoopTask:
        """审核介入：插入 user 消息，下一回合喂给模型。

        loop 是 autonomous 对话模式，审核者可像普通会话一样追加 user 消息。
        约束：loop PAUSED/STOPPED → ValueError（API 层映射 409）；
        任务不存在 → KeyError（API 层映射 404）；已终态（COMPLETED/FAILED）→ ValueError。
        """
        with self._lock:
            if self._status in (LoopStatus.PAUSED, LoopStatus.STOPPED):
                raise ValueError("loop 处于 PAUSED/STOPPED，无法介入")
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                raise ValueError(f"任务已结束（{task.status.value}），无法介入")
            task.pending_input = message
            task.messages.append(
                {"role": "user", "content": message, "ts": datetime.now().isoformat()}
            )
        # 唤醒：入队（后台线程 drain 或下次 start 时处理）
        self._queue.put(task_id)
        return task

    def _build_handoff(self, task: LoopTask) -> Dict[str, Any]:
        """生成结构化交接笔记（loop 交接 + macdev 回审双轨，冗余保障）：
        从消息流提炼文件产出断言（artifacts）与工具决策（decisions），
        供回审验证（macdev audit）与前端注入普通会话。"""
        artifacts: List[str] = []
        decisions: List[str] = []
        for m in task.messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    name = tc.get("name") or ""
                    if not name and isinstance(tc.get("function"), dict):
                        name = tc.get("function", {}).get("name", "")
                    if name:
                        decisions.append(name)
                    args = tc.get("arguments")
                    if isinstance(args, str):
                        try:
                            import json as _json
                            args = _json.loads(args)
                        except Exception:
                            args = None
                    if isinstance(args, dict) and args.get("path"):
                        artifacts.append(f"{name}: {args['path']}")
        return {
            "goal": task.goal,
            "status": task.status.value,
            "turns": task.turn_count,
            "summary": task.result or "",
            "decisions": list(dict.fromkeys(decisions)),
            "artifacts": list(dict.fromkeys(artifacts)),
            "open_issues": [task.error] if task.error else [],
        }

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

        # 上下文源（spec id=4/5）：有 session_id + 会话回调 → 读写同一会话上下文
        # （普通对话 + loop 回合同流，目标达成前不停）；否则独立上下文（兼容 discover 面板/测试）
        session_msgs = None
        if task.session_id and self.session_context:
            try:
                session_msgs = list(self.session_context.get(task.session_id) or [])
            except Exception:
                session_msgs = None
        if session_msgs is not None:
            messages = list(session_msgs)
            # goal 作为上下文组件（spec id=5）：会话中无该目标则追加
            if not any(m.get("role") == "user" and m.get("content") == task.goal for m in messages):
                messages = messages + [{"role": "user", "content": task.goal}]
            # task.messages 只记录 loop 自身回合流（goal + 回合产出），不整体重建为会话历史——
            # 避免普通对话消息污染同流显示 + _written/去重指针错乱（吞消息/闪烁根因，1:1 对齐单例）
            if not task.messages:
                task.messages.append({"role": "user", "content": task.goal, "ts": datetime.now().isoformat()})
        else:
            messages: List[Dict[str, Any]] = [{"role": "user", "content": task.goal}]
            # 会话化：goal 作为 user 消息记录到消息流（仅首次，介入消息不重复 goal）
            if not task.messages:
                task.messages.append({"role": "user", "content": task.goal, "ts": datetime.now().isoformat()})
        _written = len(task.messages)  # 已回写会话的消息数（回合产物增量回写）
        while task.turn_count < task.max_turns:
            # ── 审核介入消息：追加为 user 消息喂给模型（决策③C） ──
            if task.pending_input:
                task.messages.append(
                    {"role": "user", "content": task.pending_input, "ts": datetime.now().isoformat()}
                )
                messages.append({"role": "user", "content": task.pending_input})
                task.pending_input = None

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
                # 防异常打断（spec id=5：目标达成前不停）：记录错误 + 续跑（预算未尽时）
                task.error = f"{type(e).__name__}: {e}"
                task.messages.append({
                    "role": "assistant",
                    "content": f"⚠️ 回合异常：{task.error}，继续尝试推进目标",
                    "tool_calls": None,
                    "ts": datetime.now().isoformat(),
                })
                messages.append({"role": "assistant", "content": f"⚠️ 回合异常：{task.error}"})
                if task.turn_count >= task.max_turns:
                    task.status = TaskStatus.FAILED
                    break
                messages.append({
                    "role": "user",
                    "content": f"（上一回合异常：{task.error}。请继续推进 loop 目标，必要时换一种方式）",
                })
                task.messages.append({
                    "role": "user",
                    "content": f"（上一回合异常：{task.error}，继续推进）",
                    "ts": datetime.now().isoformat(),
                })
                continue

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
                # 会话化：记录 assistant 回合到消息流
                task.messages.append({
                    "role": "assistant",
                    "content": getattr(result, "content", "") or "",
                    "tool_calls": getattr(result, "tool_calls", None),
                    "ts": datetime.now().isoformat(),
                })
                for entry in result.tool_calls:
                    tc = entry.get("tool_call", entry) if isinstance(entry, dict) else entry
                    t_id = tc.get("id", "") if isinstance(tc, dict) else ""
                    content = entry.get("result", "") if isinstance(entry, dict) else str(entry)
                    messages.append(
                        {"role": "tool", "tool_call_id": t_id, "content": content}
                    )
                    # 会话化：记录 tool 消息到消息流
                    task.messages.append({
                        "role": "tool", "tool_call_id": t_id, "content": content,
                        "ts": datetime.now().isoformat(),
                    })
                # 会话级模式切换：每回合广播 turn 事件（前端同流追加显示）
                self._emit("agent_loop.turn", task)
                # 会话上下文回写（同一上下文迭代器：回合产物写回共享流）
                if session_msgs is not None and task.session_id and self.session_context:
                    try:
                        new_msgs = task.messages[_written:]
                        if new_msgs:
                            self.session_context.append(task.session_id, new_msgs)
                            _written = len(task.messages)
                    except Exception:
                        pass
                continue

            # 无 tool_calls：目标达成判定（spec id=5）——loop 目标模式须声明「🎯 目标已达成」才完成，
            # 否则目标达成前不停（续跑）；非 loop 目标模式保持「无 tool_calls → 自然完成」（兼容旧行为）
            _content = getattr(result, "content", "") or ""
            _loop_goal_mode = session_msgs is not None
            if _loop_goal_mode and "🎯 目标已达成" not in _content:
                # 目标达成前不停：记录回复 + 追加继续推进指令，续跑
                task.messages.append({
                    "role": "assistant",
                    "content": _content,
                    "tool_calls": None,
                    "ts": datetime.now().isoformat(),
                })
                messages.append({"role": "assistant", "content": _content})
                task.messages.append({
                    "role": "user",
                    "content": "（继续推进上述 loop 目标，直到达成；每完成一步就继续下一步，若已达成请声明『🎯 目标已达成』）",
                    "ts": datetime.now().isoformat(),
                })
                messages.append({
                    "role": "user",
                    "content": "（继续推进上述 loop 目标，直到达成；若已达成请声明『🎯 目标已达成』）",
                })
            else:
                # 达成 或 非 loop 目标模式 → 自然完成
                task.result = _content
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                task.messages.append({
                    "role": "assistant",
                    "content": _content,
                    "tool_calls": None,
                    "ts": datetime.now().isoformat(),
                })
                messages.append({"role": "assistant", "content": _content})
            # 会话上下文回写
            if session_msgs is not None and task.session_id and self.session_context:
                try:
                    new_msgs = task.messages[_written:]
                    if new_msgs:
                        self.session_context.append(task.session_id, new_msgs)
                        _written = len(task.messages)
                except Exception:
                    pass
            # 会话级模式切换：每回合广播 turn 事件（含最终回合）
            self._emit("agent_loop.turn", task)
            if task.status == TaskStatus.COMPLETED:
                break
            continue
        else:
            # while 因 max_turns 耗尽退出且未 break → 预算用尽，挂起等待人工
            if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.status = TaskStatus.HALTED
                task.error = f"达到 max_turns={task.max_turns}"
                task.completed_at = datetime.now().isoformat()

        # ── 交接笔记（handoff）：终态生成（loop 交接 + macdev 回审双轨，冗余保障） ──
        if task.status in (TaskStatus.COMPLETED, TaskStatus.HALTED, TaskStatus.FAILED):
            try:
                task.handoff = self._build_handoff(task)
            except Exception:
                pass

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
