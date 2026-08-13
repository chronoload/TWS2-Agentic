"""高级团队编排封装（AgentTeam）。

设计思路：
- 在 team_runtime（轻量级队列运行时）之上，本模块面向"真实子代理"提供更上层的
  编排 API：成员注册、单次路由、延续会话、并行/串行/流水线执行。
- 成员的执行方式按优先级依次回退：自定义 executor -> SessionAgent 会话 ->
  Coordinator 协调器（真正驱动 LLM 子代理）。executor/session 可注入，因此
  在测试中无需真实 LLM 即可验证编排逻辑。
- 所有对外编排动作通过 _emit 广播 TaskStart / TaskEnd 事件，方便外部监听进度。

与 Cline 的对应关系：Cline Teams 中主代理（Lead）通过 agent 工具创建子代理后，
以并行/顺序方式分派任务并汇总结果；本类的 route_to / run_parallel /
run_sequential / run_pipeline 即对应这套编排模式。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from ..subagent.coordinator import Coordinator
from ..subagent.session import SessionAgent
from ..subagent.types import AgentRole, AgentSpec, SubAgentResult
from .types import TeamEvent, TeamMemberConfig


class _MemberWrapper:
    """团队成员在 AgentTeam 内部的包装对象。

    把成员的配置（TeamMemberConfig）、子代理规范（AgentSpec）以及可选的
    SessionAgent / 自定义 executor 聚合在一起，供 _dispatch 按优先级选用执行方式。
    """

    def __init__(
        self,
        agent_id: str,
        config: TeamMemberConfig,
        spec: AgentSpec,
        session: Optional[SessionAgent] = None,
        executor: Optional[Callable] = None,
    ):
        self.agent_id = agent_id
        self.config = config
        self.spec = spec
        self.session = session
        self.executor = executor


class AgentTeam:
    """面向会话内子代理的团队编排器。

    负责把团队成员的配置注册到 Coordinator，并对外提供：
    - route_to / continue_to：向单个成员派发一次性任务或延续对话；
    - run_parallel / run_sequential / run_pipeline：多种任务编排模式；
    - abort_all / clear：团队级的中止与清理。

    线程安全：成员字典的读写统一通过 self._lock 保护，可安全用于多线程并行派发。
    """

    def __init__(
        self,
        configs: Optional[Dict[str, TeamMemberConfig]] = None,
        coordinator: Optional[Coordinator] = None,
        llm: Any = None,
        on_event: Optional[Callable[[TeamEvent], None]] = None,
        executor: Optional[Callable] = None,
        max_workers: int = 3,
    ):
        """初始化团队。

        Args:
            configs: 预置成员配置字典 {agent_id: TeamMemberConfig}，构造时直接注册。
            coordinator: 子代理协调器；为 None 时基于 llm/max_workers 新建。
            llm: 供新建 Coordinator 使用的 LLM 实例。
            on_event: 团队事件回调，收到 TaskStart/TaskEnd 等事件。
            executor: 团队默认执行器（无成员级执行器时的兜底）。
            max_workers: 新建 Coordinator 时的最大工作线程数。
        """
        self._coordinator = coordinator or Coordinator(llm=llm, max_workers=max_workers)
        self._members: Dict[str, _MemberWrapper] = {}
        self._default_executor = executor
        self._on_event = on_event
        self._lock = threading.Lock()
        if configs:
            for agent_id, config in configs.items():
                self.add_agent(agent_id, config)

    @property
    def agent_ids(self) -> List[str]:
        """返回团队内全部成员的 agent_id 列表。"""
        with self._lock:
            return list(self._members.keys())

    @property
    def size(self) -> int:
        """返回团队当前成员数量。"""
        with self._lock:
            return len(self._members)

    def add_agent(self, agent_id: str, config: TeamMemberConfig, executor: Optional[Callable] = None):
        """向团队注册一个新成员。

        Args:
            agent_id: 成员唯一 ID，重复注册会抛出 ValueError。
            config: 成员配置（角色/系统提示词/工具白黑名单等）。
            executor: 该成员的专属执行器；为 None 时回退到团队默认执行器。

        Raises:
            ValueError: 同名成员已存在时抛出，避免静默覆盖造成状态混乱。
        """
        with self._lock:
            if agent_id in self._members:
                raise ValueError(f'Agent "{agent_id}" already exists in the team')
            # 尝试把配置中的角色字符串解析为 AgentRole；非法角色名回退为 CUSTOM，
            # 保证任意自定义角色都能被接受
            try:
                role = AgentRole(config.role) if config.role else AgentRole.CUSTOM
            except ValueError:
                role = AgentRole.CUSTOM
            # 把成员配置转成子代理规范（AgentSpec）并注册到 Coordinator，
            # 之后该成员即可通过协调器真正以子代理身份运行
            spec = AgentSpec(
                role=role,
                name=agent_id,
                system_prompt=config.system_prompt,
                kind=config.kind,
                max_turns=config.max_turns,
                timeout_seconds=config.timeout_seconds,
                allowed_tools=config.allowed_tools,
                denied_tools=config.denied_tools,
            )
            self._coordinator.register_agent(spec)
            self._members[agent_id] = _MemberWrapper(
                agent_id,
                config,
                spec,
                executor=executor if executor is not None else self._default_executor,
            )

    def remove_agent(self, agent_id: str) -> bool:
        """从团队移除一个成员并同步注销其子代理注册。

        Args:
            agent_id: 要移除的成员 ID。

        Returns:
            bool: 是否确实移除（成员不存在时返回 False，不抛异常）。
        """
        with self._lock:
            member = self._members.pop(agent_id, None)
            if member is None:
                return False
            self._coordinator.unregister_agent(agent_id)
            return True

    def get_agent(self, agent_id: str) -> Optional[_MemberWrapper]:
        """按 agent_id 获取成员包装对象；不存在时返回 None。"""
        with self._lock:
            return self._members.get(agent_id)

    def route_to(self, agent_id: str, message: str) -> SubAgentResult:
        """向单个成员派发一次任务并等待其结果（单次路由）。

        Args:
            agent_id: 目标成员 ID，不存在时抛出 KeyError。
            message: 任务消息。

        Returns:
            SubAgentResult: 成员执行结果（含状态/内容/错误）。

        设计意图：路由前后广播 TaskStart / TaskEnd 事件；执行异常同样以
        TaskEnd 事件上报 error 后原样抛出，保证调用方能感知失败。
        """
        self._require_member(agent_id)
        self._emit(TeamEvent(type="TaskStart", agent_id=agent_id, payload={"message": message}))
        try:
            result = self._dispatch(agent_id, message)
            self._emit(TeamEvent(type="TaskEnd", agent_id=agent_id, payload={"result": self._result_to_dict(result)}))
            return result
        except Exception as e:
            self._emit(TeamEvent(type="TaskEnd", agent_id=agent_id, payload={"error": str(e)}))
            raise

    def continue_to(self, agent_id: str, message: str) -> SubAgentResult:
        """在成员既有会话上延续对话（而非重新开启新会话）。

        Args:
            agent_id: 目标成员 ID。
            message: 延续会话的新消息。

        Returns:
            SubAgentResult: 延续执行的结果。

        设计意图：优先使用 executor / SessionAgent 暴露的 continue 方法以保留
        上下文；若两者都没有 continue 能力，则退化为普通 route_to 派发。
        """
        member = self._require_member(agent_id)
        self._emit(TeamEvent(type="TaskStart", agent_id=agent_id, payload={"message": message}))
        continue_fn = None
        # 依次从自定义 executor 与 SessionAgent 上探测 continue 能力
        if member.executor is not None:
            continue_fn = getattr(member.executor, "continue", None)
        if continue_fn is None and member.session is not None:
            continue_fn = getattr(member.session, "continue", None)
        try:
            if callable(continue_fn):
                result = continue_fn(message)
                result = self._normalize(result, agent_id)
            else:
                result = self._dispatch(agent_id, message)
            self._emit(TeamEvent(type="TaskEnd", agent_id=agent_id, payload={"result": self._result_to_dict(result)}))
            return result
        except Exception as e:
            self._emit(TeamEvent(type="TaskEnd", agent_id=agent_id, payload={"error": str(e)}))
            raise

    def run_parallel(self, tasks: List[Dict]) -> List[SubAgentResult]:
        """并行执行一组任务，所有任务结束后统一返回。

        Args:
            tasks: 任务字典列表，每项支持 agent_id / message / metadata 键。

        Returns:
            List[SubAgentResult]: 与入参顺序一一对应的结果列表；
            单个任务失败不会中断其他任务，而是以 mark_failed 记录在对应位置。

        设计意图：用 ThreadPoolExecutor 按任务数开线程并发派发；
        results 预分配固定下标，保证返回顺序稳定可预期。
        """
        results: List[Optional[SubAgentResult]] = [None] * len(tasks)

        # 线程内执行单个任务：失败不抛出，转为失败结果，避免污染其他任务
        def _run(index: int, task: Dict):
            agent_id = task.get("agent_id", "")
            metadata = task.get("metadata")
            try:
                result = self.route_to(agent_id, task.get("message", ""))
            except Exception as e:
                result = SubAgentResult(agent_name=agent_id)
                result.mark_failed(error=str(e))
            if metadata is not None:
                result.metadata = metadata
            results[index] = result

        with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
            futures = [pool.submit(_run, i, task) for i, task in enumerate(tasks)]
            for future in futures:
                future.result()
        return [r for r in results if r is not None]

    def run_sequential(self, tasks: List[Dict]) -> List[SubAgentResult]:
        """顺序执行一组任务：前一个完成后才执行下一个。

        Args:
            tasks: 任务字典列表，每项支持 agent_id / message / metadata 键。

        Returns:
            List[SubAgentResult]: 与入参顺序一致的结果列表；单个任务失败以
            mark_failed 记录并继续执行后续任务。

        设计意图：适用于有隐含顺序依赖或需要严格控制资源占用的场景。
        """
        results: List[SubAgentResult] = []
        for task in tasks:
            agent_id = task.get("agent_id", "")
            metadata = task.get("metadata")
            try:
                result = self.route_to(agent_id, task.get("message", ""))
            except Exception as e:
                result = SubAgentResult(agent_name=agent_id)
                result.mark_failed(error=str(e))
            if metadata is not None:
                result.metadata = metadata
            results.append(result)
        return results

    def run_pipeline(self, stages: List[Dict], transformers: Optional[Dict] = None) -> List[SubAgentResult]:
        """流水线执行：上一阶段的输出作为下一阶段的输入前缀。

        Args:
            stages: 阶段列表，每项支持 agent_id/agent、message/prompt 键
                （两组键名都兼容）。
            transformers: {阶段序号: 转换函数}，自定义"上一结果 -> 前缀文本"的拼接
                方式；未提供的阶段默认拼成 "阶段结果:\n{content}"。

        Returns:
            List[SubAgentResult]: 每个阶段的结果；某个阶段失败时以 mark_failed
            记录并立即终止后续阶段（break）。

        设计意图：支持跨阶段上下文传递，模拟 Cline 中多代理接力完成长任务。
        """
        transformers = transformers or {}
        results: List[SubAgentResult] = []
        for index, stage in enumerate(stages):
            agent_id = stage.get("agent_id", stage.get("agent", ""))
            message = stage.get("message", stage.get("prompt", ""))
            # 除第一阶段外，把上一阶段结果拼到本次消息前面
            if results:
                prev = results[-1]
                transformer = transformers.get(index - 1)
                if transformer is not None:
                    prefix = self._apply_transformer(transformer, prev)
                else:
                    content = prev.content if prev.content else "(空)"
                    prefix = f"阶段结果:\n{content}"
                message = f"{prefix}\n\n{message}"
            try:
                results.append(self.route_to(agent_id, message))
            except Exception as e:
                failed = SubAgentResult(agent_name=agent_id)
                failed.mark_failed(error=str(e))
                results.append(failed)
                break
        return results

    def abort_all(self):
        """中止团队内所有正在运行的会话与协调器任务。"""
        for member in self._members.values():
            if member.session is not None:
                member.session.cancel()
        self._coordinator.cancel()

    def clear(self):
        """中止全部执行并清空团队：先 abort，再注销所有成员注册。"""
        self.abort_all()
        with self._lock:
            for agent_id in list(self._members.keys()):
                self._coordinator.unregister_agent(agent_id)
            self._members.clear()

    @staticmethod
    def _apply_transformer(transformer: Callable, result: SubAgentResult) -> str:
        # 转换函数可能只接受 SubAgentResult，也可能只接受其文本内容，
        # 用 TypeError 回退兼顾两种签名
        try:
            return transformer(result)
        except TypeError:
            return transformer(result.content)

    def _require_member(self, agent_id: str) -> _MemberWrapper:
        """获取成员并校验存在性；缺失时抛出 KeyError。"""
        member = self._members.get(agent_id)
        if member is None:
            raise KeyError(f'Agent "{agent_id}" not found in team')
        return member

    def _dispatch(self, agent_id: str, message: str, context: Optional[Dict] = None) -> SubAgentResult:
        """按优先级把任务交给成员执行：executor -> session -> Coordinator。"""
        member = self._require_member(agent_id)
        if member.executor is not None:
            return self._normalize(self._call_executor(member.executor, message, context), agent_id)
        if member.session is not None:
            return self._normalize(member.session.run(message, context), agent_id)
        return self._coordinator.run(agent_id, message, context)

    @staticmethod
    def _call_executor(executor: Callable, message: str, context: Optional[Dict]) -> Any:
        # 兼容两种执行器签名：executor(message, context) 或 executor(message)
        try:
            return executor(message, context)
        except TypeError:
            return executor(message)

    @staticmethod
    def _normalize(result: Any, agent_id: str) -> SubAgentResult:
        """把任意执行结果统一包装为 SubAgentResult。

        已返回 SubAgentResult 则原样透传；其余情况（str 或其他对象）以
        mark_completed 记录其字符串内容，保证下游处理接口一致。
        """
        if isinstance(result, SubAgentResult):
            return result
        normalized = SubAgentResult(agent_name=agent_id)
        if isinstance(result, str):
            normalized.mark_completed(content=result)
        else:
            normalized.mark_completed(content=str(result))
        return normalized

    @staticmethod
    def _result_to_dict(result: SubAgentResult) -> Dict[str, Any]:
        # 转成可 JSON 化的普通字典，便于放进事件 payload
        return {
            "agent_name": result.agent_name,
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "content": result.content,
            "error": result.error,
        }

    def _emit(self, event: TeamEvent):
        """广播团队事件；回调异常被吞掉，避免影响主流程。"""
        if not self._on_event:
            return
        try:
            self._on_event(event)
        except Exception:
            pass
