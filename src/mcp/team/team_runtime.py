"""轻量级团队运行时（AgentTeamsRuntime）。

设计思路：
- 与 agent_team（面向真实子代理的高级封装）不同，本模块是"执行器无关"的通用
  运行时：成员执行任务的方式通过 executor 可调用对象注入，因此既可用于真实
  LLM 子代理，也可在测试中直接注入简单函数。
- 核心机制：
  * run_queue：待执行 run 的等待队列，按"提交顺序 + 依赖关系"调度；
  * 依赖解析：每个 run 可声明 depends_on 其他 run_id，只有前置 run 全部
    completed 后才能开始；
  * 并发控制：同时运行的 run 数不超过 max_concurrent_runs；
  * mailbox：成员间异步消息邮箱（单播/广播/已读标记）；
  * mission_log：使命日志，记录团队的长期目标与关键进展；
  * Outcome：协作产物生命周期 draft -> in_review -> finalized；
  * 生命周期：pending -> running -> completed / failed / cancelled。

与 Cline 的对应关系：对应 Cline Teams 中主代理侧的任务队列、运行状态、
消息邮箱、使命日志与产物沉淀等运行时能力。
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional

from .types import Outcome, TeamEvent, TeamMessage, TeamRunRecord, TeamTask

# 终态集合：处于这些状态的 run 不会再被调度执行，也不会再变化
TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class AgentTeamsRuntime:
    """团队任务运行时：成员管理、任务队列、邮箱、日志与产物生命周期。

    线程安全：所有共享状态的读写都通过 self._lock 保护；执行中的 run 在线程池
    中运行，通过 threading.Event 通知等待方（await_run）。
    """

    def __init__(
        self,
        max_concurrent_runs: int = 3,
        executor: Optional[Callable] = None,
        on_event: Optional[Callable[[TeamEvent], None]] = None,
        coordinator: Any = None,
    ):
        """初始化运行时。

        Args:
            max_concurrent_runs: 最大并行运行数，至少为 1（内部强制下界）。
            executor: 默认执行器，成员未单独指定执行器时使用。
            on_event: 运行状态变化事件回调（如 RunCompleted / RunFailed）。
            coordinator: 可选的协调器引用，仅作为上下文存储，不参与本类调度。
        """
        self.max_concurrent_runs = max(1, int(max_concurrent_runs))
        self._default_executor = executor
        self._on_event = on_event
        self._coordinator = coordinator
        self._members: Dict[str, Dict[str, Any]] = {}
        self._runs: Dict[str, TeamRunRecord] = {}
        # run_id -> 完成事件，await_run 通过它阻塞等待
        self._run_events: Dict[str, threading.Event] = {}
        # run_id -> 依赖的 run_id 列表，调度前必须全部 completed
        self._run_deps: Dict[str, List[str]] = {}
        self._tasks: Dict[str, TeamTask] = {}
        # agent_id -> 未读/已读消息队列
        self._mailbox: Dict[str, List[TeamMessage]] = {}
        self._mission_log: List[Dict[str, Any]] = []
        self._outcomes: Dict[str, Outcome] = {}
        # 执行池：容量与并发上限一致，保证同一时刻真正执行的 run 数受控
        self._pool = ThreadPoolExecutor(max_workers=max(1, self.max_concurrent_runs))
        self._lock = threading.Lock()

    def add_member(
        self,
        agent_id: str,
        role: str = "teammate",
        kind: str = "teammate",
        system_prompt: str = "",
        executor: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """注册一个团队成员。

        Args:
            agent_id: 成员唯一 ID，重复注册抛出 ValueError。
            role: 角色描述。
            kind: 成员类型（teammate/subagent）。
            system_prompt: 系统提示词。
            executor: 该成员的专属执行器；None 时回退到默认执行器。

        Returns:
            Dict[str, Any]: 成员信息的副本（含 status=idle 初始状态）。

        Raises:
            ValueError: 同名成员已存在时抛出，避免静默覆盖。
        """
        with self._lock:
            if agent_id in self._members:
                raise ValueError(f'Team member "{agent_id}" already exists')
            member = {
                "agent_id": agent_id,
                "role": role,
                "kind": kind,
                "system_prompt": system_prompt,
                "executor": executor,
                "status": "idle",
            }
            self._members[agent_id] = member
            return dict(member)

    def remove_member(self, agent_id: str) -> bool:
        """移除成员。

        Returns:
            bool: 是否确实移除。

        Raises:
            KeyError: 成员不存在时抛出。
        """
        with self._lock:
            member = self._members.pop(agent_id, None)
        if member is None:
            raise KeyError(f'Team member "{agent_id}" was not found')
        return True

    def list_members(self) -> List[Dict[str, Any]]:
        """返回全部成员的快照列表（每项为成员字典的副本）。"""
        with self._lock:
            return [dict(m) for m in self._members.values()]

    def create_task(self, agent_id: str, message: str, depends_on: Optional[List[str]] = None) -> TeamTask:
        """创建共享团队任务（TeamTask），仅登记任务描述，不进入执行队列。

        Args:
            agent_id: 负责该任务的成员 ID。
            message: 任务内容。
            depends_on: 依赖的任务 ID 列表。

        Returns:
            TeamTask: 新创建的任务对象（含自动生成的 task_id）。
        """
        task = TeamTask(
            agent_id=agent_id,
            message=message,
            depends_on=list(depends_on or []),
        )
        with self._lock:
            self._tasks[task.task_id] = task
        return task

    def list_tasks(self, agent_id: str = "") -> List[TeamTask]:
        """列出团队任务；传入 agent_id 时仅返回该成员的任务。"""
        with self._lock:
            return [t for t in self._tasks.values() if not agent_id or t.agent_id == agent_id]

    def submit_task(self, agent_id: str, message: str, depends_on: Optional[List[str]] = None) -> str:
        """提交一个任务到运行队列并立即尝试调度。

        Args:
            agent_id: 执行该任务的成员 ID，须已注册。
            message: 任务消息。
            depends_on: 依赖的 run_id 列表（前置 run 完成后本 run 才会执行）。

        Returns:
            str: 新 run 的 run_id。

        Raises:
            KeyError: 目标成员未注册时抛出。

        设计意图：先登记 run 记录/完成事件/依赖关系，再触发 dispatch_queued，
        让新提交的 run 有机会立刻被调度执行。
        """
        with self._lock:
            if agent_id not in self._members:
                raise KeyError(f'Agent "{agent_id}" was not found')
            run = TeamRunRecord(
                run_id=uuid.uuid4().hex[:12],
                agent_id=agent_id,
                message=message,
                status="pending",
                created_at=time.time(),
            )
            self._runs[run.run_id] = run
            self._run_events[run.run_id] = threading.Event()
            self._run_deps[run.run_id] = list(depends_on or [])
        self.dispatch_queued()
        return run.run_id

    @property
    def run_queue(self) -> List[str]:
        """返回当前处于 pending（排队中）状态的 run_id 列表。"""
        with self._lock:
            return [run_id for run_id, run in self._runs.items() if run.status == "pending"]

    def dispatch_queued(self):
        """把满足条件（有并发名额 + 依赖已解析）的 pending run 送入执行池。

        设计意图：在锁内循环填充并发名额，每轮按提交顺序挑选第一个满足
        依赖的 pending run 并置为 running，然后提交到线程池执行；
        执行结束时 _execute_run 会再次调用本方法，形成"完成一个、补一个"
        的连续调度。
        """
        with self._lock:
            while self._running_count() < self.max_concurrent_runs:
                next_run_id = None
                for run_id, run in self._runs.items():
                    if run.status != "pending":
                        continue
                    # 依赖未全部完成的 run 跳过，等待前置 run 完成后再来
                    if not self._deps_resolved(run_id):
                        continue
                    next_run_id = run_id
                    break
                if next_run_id is None:
                    break
                run = self._runs[next_run_id]
                run.status = "running"
                self._pool.submit(self._execute_run, next_run_id)

    def await_run(self, run_id: str, timeout: Optional[float] = None) -> TeamRunRecord:
        """阻塞等待单个 run 达到终态。

        Args:
            run_id: 目标 run。
            timeout: 超时秒数；None 表示无限等待。

        Returns:
            TeamRunRecord: run 的最终记录。

        Raises:
            KeyError: run 不存在时抛出。
        """
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f'Run "{run_id}" was not found')
        event = self._run_events.get(run_id)
        if event is not None:
            event.wait(timeout=timeout)
        return self._runs[run_id]

    def await_runs(self, run_ids: List[str], timeout: Optional[float] = None) -> List[TeamRunRecord]:
        """依次等待一组 run 完成，返回对应的最终记录列表。"""
        results = []
        for run_id in run_ids:
            results.append(self.await_run(run_id, timeout=timeout))
        return results

    def await_all_runs(self, timeout: Optional[float] = None) -> List[TeamRunRecord]:
        """等待当前所有 pending/running 的 run 全部结束。

        实现：轮询检查是否仍有活跃 run，配合 deadline 实现超时退出；
        返回时运行中的所有 run 记录。
        """
        deadline = time.time() + timeout if timeout else None
        while True:
            with self._lock:
                active = [run_id for run_id, run in self._runs.items() if run.status in ("pending", "running")]
            if not active:
                break
            if deadline is not None and time.time() >= deadline:
                break
            time.sleep(0.02)
        return self.list_runs()

    def cancel_run(self, run_id: str) -> TeamRunRecord:
        """取消一个 pending 或 running 的 run。

        Args:
            run_id: 目标 run。

        Returns:
            TeamRunRecord: 取消后的记录（已处于终态的 run 原样返回）。

        设计意图：置状态为 cancelled 并唤醒等待者；随后重新调度队列，
        让被占用的并发名额由其他 pending run 顶上。
        """
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(f'Run "{run_id}" was not found')
            if run.status not in ("pending", "running"):
                return run
            run.status = "cancelled"
            run.completed_at = time.time()
        event = self._run_events.get(run_id)
        if event is not None:
            event.set()
        self.dispatch_queued()
        return run

    def get_run(self, run_id: str) -> Optional[TeamRunRecord]:
        """按 run_id 获取 run 记录；不存在时返回 None。"""
        with self._lock:
            run = self._runs.get(run_id)
            return run

    def list_runs(self, agent_id: str = "") -> List[TeamRunRecord]:
        """列出全部 run 记录；传入 agent_id 时仅返回该成员的 run。"""
        with self._lock:
            return [run for run in self._runs.values() if not agent_id or run.agent_id == agent_id]

    def cleanup(self, older_than_seconds: Optional[float] = None) -> int:
        """清理已结束（非 pending/running）的 run 记录。

        Args:
            older_than_seconds: 只清理完成时间早于当前时间该秒数的记录；
                None 表示清理全部已结束记录。

        Returns:
            int: 被清理的 run 数量。
        """
        with self._lock:
            cutoff = time.time() - older_than_seconds if older_than_seconds else None
            removed = 0
            for run_id in list(self._runs.keys()):
                run = self._runs[run_id]
                # 仍在执行或排队的 run 一律保留
                if run.status in ("pending", "running"):
                    continue
                if cutoff is not None:
                    # 以完成时间（无则回退创建时间）判断是否够旧
                    reference = run.completed_at or run.created_at
                    if reference >= cutoff:
                        continue
                self._runs.pop(run_id, None)
                self._run_events.pop(run_id, None)
                self._run_deps.pop(run_id, None)
                removed += 1
        return removed

    def send_message(self, to_agent_id: str, from_agent_id: str, content: str) -> TeamMessage:
        """向指定成员发送一条邮箱消息（单播）。

        Raises:
            KeyError: 收件人未注册时抛出，防止投递到未知成员。
        """
        with self._lock:
            if to_agent_id not in self._members:
                raise KeyError(f'Unknown recipient "{to_agent_id}"')
            message = TeamMessage(
                to_agent_id=to_agent_id,
                from_agent_id=from_agent_id,
                content=content,
            )
            self._mailbox.setdefault(to_agent_id, []).append(message)
            return message

    def broadcast(self, from_agent_id: str, content: str) -> List[TeamMessage]:
        """向除发件人外的所有成员广播消息。

        Raises:
            KeyError: 发件人未注册时抛出。
        """
        with self._lock:
            if from_agent_id not in self._members:
                raise KeyError(f'Unknown sender "{from_agent_id}"')
            sent = []
            for agent_id in self._members:
                # 跳过发件人自己，避免"自己给自己发广播"
                if agent_id == from_agent_id:
                    continue
                message = TeamMessage(
                    to_agent_id=agent_id,
                    from_agent_id=from_agent_id,
                    content=content,
                )
                self._mailbox.setdefault(agent_id, []).append(message)
                sent.append(message)
            return sent

    def read_mailbox(self, agent_id: str) -> List[TeamMessage]:
        """读取成员邮箱全部消息，读取后统一标记为已读。"""
        with self._lock:
            messages = list(self._mailbox.get(agent_id, []))
            for message in messages:
                message.read = True
            return messages

    def append_mission_log(self, content: str, agent_id: str = "") -> Dict[str, Any]:
        """向使命日志追加一条记录。

        Returns:
            Dict[str, Any]: 新日志条目（含自动生成的 id 与时间戳）。
        """
        entry = {
            "id": uuid.uuid4().hex[:12],
            "agent_id": agent_id,
            "content": content,
            "ts": time.time(),
        }
        with self._lock:
            self._mission_log.append(entry)
        return dict(entry)

    def read_mission_log(self) -> List[Dict[str, Any]]:
        """返回使命日志的全部条目（副本列表）。"""
        with self._lock:
            return [dict(e) for e in self._mission_log]

    def create_outcome(self, title: str, owner_agent_id: str = "") -> Outcome:
        """创建一份协作产物（Outcome），初始状态为 draft。"""
        outcome = Outcome(title=title, owner_agent_id=owner_agent_id)
        with self._lock:
            self._outcomes[outcome.outcome_id] = outcome
        return outcome

    def create(self, title: str, owner_agent_id: str = "") -> Outcome:
        """create_outcome 的别名，语义更贴近 Cline 的产物创建动作。"""
        return self.create_outcome(title, owner_agent_id)

    def attach_outcome_fragment(
        self,
        outcome_id: str,
        content: str,
        author_agent_id: str = "",
    ) -> Dict[str, Any]:
        """向产物追加一个片段，并把产物状态从 draft 提升为 in_review。

        Args:
            outcome_id: 目标产物 ID。
            content: 片段内容。
            author_agent_id: 片段作者（贡献该内容的成员）。

        Returns:
            Dict[str, Any]: 新片段字典（含 fragment_id 与审查状态）。

        Raises:
            KeyError: 产物不存在时抛出。
        """
        with self._lock:
            outcome = self._require_outcome(outcome_id)
            fragment = {
                "fragment_id": uuid.uuid4().hex[:12],
                "outcome_id": outcome_id,
                "content": content,
                "author_agent_id": author_agent_id,
                "review_status": "pending",
                "comment": "",
                "created_at": time.time(),
                "reviewed_at": None,
            }
            outcome.fragments.append(fragment)
            # 首个片段加入后即进入审查阶段，标记需要审阅
            if outcome.status == "draft":
                outcome.status = "in_review"
            outcome.updated_at = time.time()
            return dict(fragment)

    def review_outcome_fragment(
        self,
        outcome_id: str,
        fragment_id: str,
        status: str,
        comment: str = "",
    ) -> Dict[str, Any]:
        """审查产物的一个片段。

        Args:
            outcome_id: 产物 ID。
            fragment_id: 片段 ID。
            status: 审查结论，仅允许 "approve" / "reject"。
            comment: 审查意见。

        Returns:
            Dict[str, Any]: 更新后的片段字典（含 review_status）。

        Raises:
            KeyError: 产物或片段不存在时抛出。
            ValueError: status 不是 approve/reject 时抛出。
        """
        with self._lock:
            outcome = self._require_outcome(outcome_id)
            fragment = next(
                (f for f in outcome.fragments if f["fragment_id"] == fragment_id),
                None,
            )
            if fragment is None:
                raise KeyError(f'Fragment "{fragment_id}" was not found')
            if status not in ("approve", "reject"):
                raise ValueError(f'Invalid review status "{status}"')
            fragment["review_status"] = "approved" if status == "approve" else "rejected"
            fragment["comment"] = comment
            fragment["reviewed_at"] = time.time()
            outcome.updated_at = time.time()
            return dict(fragment)

    def finalize_outcome(self, outcome_id: str) -> Outcome:
        """定稿产物：要求至少有一个已批准的片段。

        Raises:
            KeyError: 产物不存在时抛出。
            RuntimeError: 没有任何 approved 片段时抛出，防止"空定稿"。
        """
        with self._lock:
            outcome = self._require_outcome(outcome_id)
            if not any(f["review_status"] == "approved" for f in outcome.fragments):
                raise RuntimeError("Outcome cannot be finalized without at least one approved fragment")
            outcome.status = "finalized"
            outcome.updated_at = time.time()
            return outcome

    def list_outcomes(self, status: str = "") -> List[Outcome]:
        """列出产物；传入 status 时按状态过滤（draft/in_review/finalized）。"""
        with self._lock:
            return [o for o in self._outcomes.values() if not status or o.status == status]

    def get_snapshot(self) -> Dict[str, Any]:
        """返回团队当前状态的聚合快照，供 team_status 工具直接展示。

        快照包含：成员摘要、运行中/排队任务、未读邮箱数、使命日志条数与
        产物状态统计。
        """
        with self._lock:
            members = [
                {
                    "agent_id": m["agent_id"],
                    "role": m["role"],
                    "kind": m["kind"],
                    "status": m["status"],
                }
                for m in self._members.values()
            ]
            running_tasks = [asdict(run) for run in self._runs.values() if run.status == "running"]
            pending_tasks = [asdict(run) for run in self._runs.values() if run.status == "pending"]
            mailbox_unread = sum(
                1 for messages in self._mailbox.values() for message in messages if not message.read
            )
            # 统计各状态的产物数量（draft/in_review/finalized）
            outcome_counts = {"draft": 0, "in_review": 0, "finalized": 0}
            for outcome in self._outcomes.values():
                outcome_counts[outcome.status] = outcome_counts.get(outcome.status, 0) + 1
            mission_log_entries = len(self._mission_log)
        return {
            "members": members,
            "running_tasks": running_tasks,
            "pending_tasks": pending_tasks,
            "mailbox_unread": mailbox_unread,
            "mission_log_entries": mission_log_entries,
            "outcomes": outcome_counts,
        }

    def shutdown(self):
        """关闭执行池；wait=False 表示不等待正在执行的 run 结束。"""
        self._pool.shutdown(wait=False)

    def _running_count(self) -> int:
        """统计当前 running 状态的 run 数量，用于并发上限判断。"""
        return sum(1 for run in self._runs.values() if run.status == "running")

    def _deps_resolved(self, run_id: str) -> bool:
        """判断 run 的依赖是否全部满足（前置 run 均已 completed）。

        前置 run 不存在（被清理/取消）也视为依赖未满足，宁可等待，
        避免破坏依赖语义。
        """
        for dep in self._run_deps.get(run_id, []):
            dep_run = self._runs.get(dep)
            if dep_run is None or dep_run.status != "completed":
                return False
        return True

    def _execute_run(self, run_id: str):
        """在线程池中真正执行一个 run（调度器回调入口）。

        流程：查找成员 -> 选用成员执行器或默认执行器 -> 调用执行 -> 记录结果；
        异常时标记 failed；finally 中唤醒等待者、广播事件并触发下一轮调度。
        已 cancelled 的 run 不再改写其结果/状态。
        """
        run = self._runs.get(run_id)
        if run is None:
            return
        try:
            member = self._members.get(run.agent_id)
            if member is None:
                raise RuntimeError(f'Agent "{run.agent_id}" was not found')
            executor = member.get("executor") or self._default_executor
            if executor is None:
                raise RuntimeError("no executor configured for run")
            result = self._call_executor(executor, run.message, {"agent_id": run.agent_id, "run_id": run_id})
            # 执行期间被取消的 run 不再覆盖为 completed
            if run.status != "cancelled":
                run.result = self._normalize_result(result)
                run.status = "completed"
                run.completed_at = time.time()
        except Exception as e:
            if run.status != "cancelled":
                run.status = "failed"
                run.error = str(e)
                run.completed_at = time.time()
        finally:
            # 无论成功失败都唤醒 await 等待方，并广播状态事件
            event = self._run_events.get(run_id)
            if event is not None:
                event.set()
            self._emit(
                TeamEvent(
                    type=self._event_type_for_status(run.status),
                    agent_id=run.agent_id,
                    payload={"run_id": run_id, "status": run.status},
                )
            )
            # 本 run 结束释放并发名额，立刻尝试调度下一个
            self.dispatch_queued()

    @staticmethod
    def _call_executor(executor: Callable, message: str, context: Dict[str, Any]) -> Any:
        # 兼容两种执行器签名：executor(message, context) 或 executor(message)
        try:
            return executor(message, context)
        except TypeError:
            return executor(message)

    @staticmethod
    def _normalize_result(result: Any) -> str:
        """把执行器返回值统一规范化为字符串结果。

        直接返回 str 则原样保留；对象带 content 属性取 content；
        其余对象用 str() 兜底，保证 result 字段始终为文本。
        """
        if isinstance(result, str):
            return result
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    @staticmethod
    def _event_type_for_status(status: str) -> str:
        """把 run 状态映射为事件类型名（终态事件，供外部监听）。"""
        if status == "completed":
            return "RunCompleted"
        if status == "failed":
            return "RunFailed"
        if status == "cancelled":
            return "RunCancelled"
        return "RunFinished"

    def _require_outcome(self, outcome_id: str) -> Outcome:
        """获取产物并校验存在性；缺失时抛出 KeyError。"""
        outcome = self._outcomes.get(outcome_id)
        if outcome is None:
            raise KeyError(f'Outcome "{outcome_id}" was not found')
        return outcome

    def _emit(self, event: TeamEvent):
        """广播事件；回调异常被吞掉，避免影响运行时主流程。"""
        if not self._on_event:
            return
        try:
            self._on_event(event)
        except Exception:
            pass
