import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .session import SessionAgent
from .types import AgentRole, AgentSpec, SubAgentResult, SubAgentStatus

logger = logging.getLogger(__name__)


class _SubagentResultHolder:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.result: Optional[SubAgentResult] = None
        self.completed = threading.Event()


class Coordinator:
    def __init__(self, llm=None, tool_registry=None, max_workers: int = 3):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_workers = max_workers
        self._agents: Dict[str, SessionAgent] = {}
        self._specs: Dict[str, AgentSpec] = {}
        self._agent_llms: Dict[str, Any] = {}
        self._scheduler_pool = ThreadPoolExecutor(max_workers=max_workers)
        self._pending_tasks: Dict[str, _SubagentResultHolder] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._swarm_enabled: bool = False  # 大规模 Swarm 集群模式（并行调度），默认禁用
        self._swarm_reason: str = ""

    @property
    def enabled(self) -> bool:
        """子 Agent 单次调用始终可用；swarm_enabled 控制大规模并行调度"""
        return True  # 单次调用始终可用

    @property
    def swarm_enabled(self) -> bool:
        """大规模 Swarm 集群模式是否启用"""
        return self._swarm_enabled

    def enable_swarm(self, reason: str = "") -> bool:
        """启用大规模 Swarm 集群模式（并行调度多 Agent）"""
        if not self.llm:
            logger.warning("Swarm 启用失败：LLM 未配置")
            return False
        self._swarm_enabled = True
        self._swarm_reason = reason
        logger.info(f"Swarm 集群模式已启用 (原因: {reason})")
        return True

    def disable_swarm(self):
        """禁用大规模 Swarm 集群模式"""
        self._swarm_enabled = False
        self.cancel()
        logger.info("Swarm 集群模式已禁用")

    def register_agent(self, spec: AgentSpec, llm=None):
        self._specs[spec.name] = spec
        if llm is not None:
            self._agent_llms[spec.name] = llm

    def unregister_agent(self, name: str):
        self._specs.pop(name, None)
        self._agents.pop(name, None)
        self._agent_llms.pop(name, None)

    def get_agent(self, name: str) -> Optional[SessionAgent]:
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        return list(self._specs.keys())

    def is_busy(self, name: str = "") -> bool:
        if name:
            agent = self._agents.get(name)
            return agent.is_busy if agent else False
        return any(agent.is_busy for agent in self._agents.values())

    def cancel(self, name: str = ""):
        if name:
            event = self._cancel_events.get(name)
            if event:
                event.set()
            agent = self._agents.get(name)
            if agent:
                agent.cancel()
        else:
            for event in self._cancel_events.values():
                event.set()
            for agent in self._agents.values():
                agent.cancel()

    def run(self, agent_name: str, prompt: str, context=None, on_event: Optional[Callable] = None,
            max_turns: Optional[int] = None) -> SubAgentResult:
        spec = self._specs.get(agent_name)
        if spec is None:
            result = SubAgentResult(agent_name=agent_name)
            result.mark_failed(error=f"Agent '{agent_name}' not found")
            return result

        # 工具轨：per-call max_turns 覆盖角色默认（副本替换，不改注册 spec；None = 用 spec 值）
        if max_turns is not None:
            import dataclasses
            spec = dataclasses.replace(spec, max_turns=max_turns)

        cancel_event = threading.Event()
        self._cancel_events[agent_name] = cancel_event

        # 上下文衔接：如果 context 中有前置 Agent 结果，注入到 prompt
        enhanced_prompt = prompt
        if context and isinstance(context, dict):
            prev_results = context.get("previous_results")
            if prev_results:
                chain_parts = ["[前置 Agent 结果]"]
                for pr in prev_results:
                    agent_nm = pr.get("agent", "unknown")
                    pr_content = pr.get("content", "")
                    pr_status = pr.get("status", "unknown")
                    chain_parts.append(f"--- {agent_nm} ({pr_status}) ---")
                    chain_parts.append(pr_content[:2000] if len(pr_content) > 2000 else pr_content)
                    chain_parts.append("")
                chain_parts.append(f"[当前任务 - {agent_name}]")
                chain_parts.append(prompt)
                enhanced_prompt = "\n".join(chain_parts)

            parent_summary = context.get("parent_summary")
            if parent_summary:
                enhanced_prompt = f"[主 Agent 上下文摘要]\n{parent_summary}\n\n{enhanced_prompt}"

        tools = self._build_tools(spec)
        agent_llm = self._agent_llms.get(agent_name, self.llm)
        agent = SessionAgent(
            spec=spec,
            llm=agent_llm,
            tools=tools,
            tool_executor=self._execute_tool,
            cancel_event=cancel_event,
            on_event=on_event,
        )
        self._agents[agent_name] = agent
        try:
            return agent.run(enhanced_prompt, context)
        finally:
            self._agents.pop(agent_name, None)
            self._cancel_events.pop(agent_name, None)

    def run_async(self, agent_name: str, prompt: str, context=None, on_event: Optional[Callable] = None,
                  max_turns: Optional[int] = None) -> str:
        task_id = uuid.uuid4().hex[:12]
        holder = _SubagentResultHolder(task_id)
        self._pending_tasks[task_id] = holder

        def _worker():
            try:
                result = self.run(agent_name, prompt, context, on_event=on_event, max_turns=max_turns)
                holder.result = result
            except Exception as e:
                holder.result = SubAgentResult(agent_name=agent_name)
                holder.result.mark_failed(error=str(e))
            finally:
                holder.completed.set()

        self._scheduler_pool.submit(_worker)
        return task_id

    def poll_result(self, task_id: str, timeout: float = 0.0) -> Optional[SubAgentResult]:
        holder = self._pending_tasks.get(task_id)
        if holder is None:
            return None
        if holder.completed.wait(timeout=timeout):
            self._pending_tasks.pop(task_id, None)
            return holder.result
        return None

    def run_parallel(self, tasks: List[Dict]) -> List[SubAgentResult]:
        """并行运行多个子 Agent

        - 4个以内：默认可用
        - 超过4个：需要 Swarm 集群模式已启用
        """
        if len(tasks) > 4 and not self._swarm_enabled:
            logger.warning(f"run_parallel 请求 {len(tasks)} 个任务但 Swarm 集群模式未启用（>4 需启用）")
            failed_results = []
            for t in tasks:
                r = SubAgentResult(agent_name=t.get("agent", "unknown"))
                r.mark_failed(error=f"并行任务数({len(tasks)})超过4个，需先启用 Swarm 集群模式。")
                failed_results.append(r)
            return failed_results

        results: List[Optional[SubAgentResult]] = [None] * len(tasks)

        def _run_task(index: int, task: Dict) -> None:
            results[index] = self.run(
                agent_name=task["agent"],
                prompt=task["prompt"],
                context=task.get("context"),
                max_turns=task.get("max_turns"),
            )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(_run_task, i, task) for i, task in enumerate(tasks)
            ]
            for future in futures:
                future.result()

        return results

    def run_sequential(self, tasks: List[Dict], on_event: Optional[Callable] = None) -> List[SubAgentResult]:
        """按序执行多个子 Agent 任务，每个任务的 prompt 注入前序结果

        对应 Cline AgentTeam 编排中按顺序逐个调用子代理的语义：
        - 任务列表严格按给定顺序串行执行（前一任务完成才启动下一个）；
        - 从第二个任务起，把此前所有任务的执行结果（agent/内容/状态）打包为
          context["previous_results"] 传入，模拟 Cline 中把前序 Agent 输出
          作为后续 Agent 上下文（context window）传递的衔接方式；
        - 各任务间不共享会话状态，仅通过 previous_results 上下文衔接。
        """
        results: List[SubAgentResult] = []
        for task in tasks:
            agent_name = task["agent"]
            prompt = task["prompt"]
            # 首个任务没有前置结果，直接执行；后续任务收集全部历史结果作为上下文
            context = None
            if results:
                prev_results = []
                for r in results:
                    # 将结果归一化为字典：status 统一转为字符串，便于下游拼接
                    status = r.status.value if isinstance(r.status, SubAgentStatus) else str(r.status)
                    prev_results.append({
                        "agent": r.agent_name,
                        "content": r.content,
                        "status": status,
                    })
                context = {"previous_results": prev_results}
            results.append(self.run(agent_name, prompt, context=context, on_event=on_event))
        return results

    def run_pipeline(self, stages: List[Dict], transformers: Optional[Dict] = None, on_event: Optional[Callable] = None) -> List[SubAgentResult]:
        """流水线执行多个阶段，每阶段输出经 transformer 转换后作为下一阶段输入

        相比 run_sequential 的多结果累积，run_pipeline 更贴近 Cline AgentTeam
        中"逐级接力"的流水线语义：
        - stages 中的每个阶段按顺序执行，阶段输出只向前传递最近一个阶段的结果；
        - transformers 以"阶段序号 -> 转换器"的形式提供，转换器针对第 i 个阶段的
          输出、在第 i+1 个阶段前生效（键 i 对应 stages[i] 与 stages[i+1] 之间）；
        - transformer 支持两种形态（见 _transform_prompt）：
            1. 可调用对象：接收上一阶段 SubAgentResult（或其 content 字符串）返回新 prompt；
            2. 普通字符串：直接作为前缀文本拼接到下一阶段 prompt 之前；
        - 未提供 transformer 时，默认把上一阶段 content 以"阶段结果:" 前缀拼接。
        """
        results: List[SubAgentResult] = []
        transformers = transformers or {}
        for index, stage in enumerate(stages):
            agent_name = stage["agent"]
            prompt = stage["prompt"]
            # 除首个阶段外，都要把上一阶段输出作为本阶段输入的上下文
            if results:
                prev_result = results[-1]
                # 键 index-1 对应"从第 index-1 个阶段到第 index 个阶段"的转换器
                transformer = transformers.get(index - 1)
                if transformer is not None:
                    # 可调用形态：交由 _transform_prompt 兼容两种调用签名
                    if callable(transformer):
                        prompt = f"{self._transform_prompt(transformer, prev_result)}\n\n{prompt}"
                    # 字符串形态：直接把固定文本作为前缀注入
                    else:
                        prompt = f"{transformer}\n\n{prompt}"
                else:
                    # 无转换器时的默认衔接：直接透传上一阶段内容
                    content = prev_result.content if prev_result.content else "(空)"
                    prompt = f"阶段结果:\n{content}\n\n{prompt}"
            results.append(self.run(agent_name, prompt, on_event=on_event))
        return results

    @staticmethod
    def _transform_prompt(transformer: Callable, result: SubAgentResult) -> str:
        """执行流水线 transformer，兼容两种调用形态

        - transformer(result)：直接接收完整的 SubAgentResult 对象（可访问
          content/status/agent_name 等元信息），适合需要结构化上下文转换的场景；
        - transformer(result.content)：当直接传对象抛出 TypeError 时，回退为
          仅传入上一阶段的内容字符串，兼容只关心文本的简单转换器。
        两种形态对应 Cline AgentTeam 中输出处理器既可拿结构化结果、也可拿
        纯文本的两种使用方式。
        """
        try:
            return transformer(result)
        except TypeError:
            return transformer(result.content)

    def _build_tools(self, spec: AgentSpec) -> List[Dict]:
        """根据 AgentSpec 构建工具 schema 列表（LLM 可直接使用的格式）"""
        if self.tool_registry is None:
            return []

        all_tools = list(self.tool_registry.values()) if isinstance(self.tool_registry, dict) else list(self.tool_registry)

        def _tool_name(t):
            if isinstance(t, dict):
                return t.get("name", "")
            return getattr(t, "name", "")

        if spec.allowed_tools is not None:
            allowed = set(spec.allowed_tools)
            all_tools = [t for t in all_tools if _tool_name(t) in allowed]

        if spec.denied_tools is not None:
            denied = set(spec.denied_tools)
            all_tools = [t for t in all_tools if _tool_name(t) not in denied]

        # 将 Tool 对象转换为 LLM 可用的 schema 格式
        schemas = []
        for t in all_tools:
            if isinstance(t, dict):
                # 已经是 schema 格式
                schemas.append(t)
            elif hasattr(t, 'name') and hasattr(t, 'parameters'):
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": getattr(t, 'description', ''),
                        "parameters": t.parameters,
                    },
                })
        return schemas

    def _execute_tool(self, tool_call) -> Any:
        """执行工具调用，兼容 ToolCall 对象和 dict 格式"""
        if self.tool_registry is None:
            return None

        # 解析工具名和参数
        if isinstance(tool_call, dict):
            name = tool_call.get("name", "") or tool_call.get("function", {}).get("name", "")
            arguments = tool_call.get("arguments", {}) or tool_call.get("function", {}).get("arguments", {})
        else:
            name = getattr(tool_call, "name", "")
            if not name and hasattr(tool_call, "function"):
                name = getattr(tool_call.function, "name", "")
            # 获取 arguments
            if hasattr(tool_call, "function"):
                raw_args = getattr(tool_call.function, "arguments", "{}")
            else:
                raw_args = getattr(tool_call, "arguments", "{}")
            # arguments 可能是 JSON 字符串
            if isinstance(raw_args, str):
                try:
                    import json
                    arguments = json.loads(raw_args)
                except Exception:
                    arguments = {}
            elif isinstance(raw_args, dict):
                arguments = raw_args
            else:
                arguments = {}

        handler = self.tool_registry.get(name) if isinstance(self.tool_registry, dict) else None

        if handler is None:
            return f"tool '{name}' not found"

        try:
            # Tool 对象使用 execute 方法调用（不是 __call__）
            if hasattr(handler, 'execute'):
                return handler.execute(**arguments)
            else:
                return handler(**arguments)
        except Exception as e:
            return f"tool error: {e}"

    def shutdown(self):
        self._scheduler_pool.shutdown(wait=False)


def create_default_coordinator(llm=None, tool_registry=None) -> Coordinator:
    coordinator = Coordinator(llm=llm, tool_registry=tool_registry)

    coordinator.register_agent(AgentSpec(
        name="coder",
        role=AgentRole.CODER,
        system_prompt=(
            "你是一个专业的编程助手（Coder Agent），隶属于 TS2 Swarm 集群。\n\n"
            "## 你的职责\n"
            "- 根据用户需求编写高质量、结构清晰的代码\n"
            "- 遵循项目现有的代码风格和架构约定\n"
            "- 编写必要的错误处理和边界检查\n\n"
            "## 工作规范\n"
            "- 优先复用项目已有的工具函数和模块\n"
            "- 代码修改应最小化，只做必要的改动\n"
            "- 如果上下文中有其他 Agent 的执行结果，请基于其结论继续工作\n"
            "- 完成后简要说明修改内容和原因\n\n"
            "## 上下文衔接\n"
            "- 如果 prompt 中包含 [前置 Agent 结果]，请仔细阅读并在此基础上工作\n"
            "- 如果发现前置 Agent 的结果有问题，请明确指出并给出修正方案"
        ),
        timeout_seconds=3600,
    ))

    coordinator.register_agent(AgentSpec(
        name="task",
        role=AgentRole.TASK,
        system_prompt=(
            "你是一个任务执行助手（Task Agent），隶属于 TS2 Swarm 集群。\n\n"
            "## 你的职责\n"
            "- 准确理解并执行用户分配的任务\n"
            "- 将复杂任务分解为可执行的步骤\n"
            "- 按步骤执行并汇报进度\n\n"
            "## 工作规范\n"
            "- 执行前先确认任务目标，避免理解偏差\n"
            "- 遇到不确定的情况，选择最安全的方案\n"
            "- 完成后给出明确的执行结果摘要\n\n"
            "## 上下文衔接\n"
            "- 如果 prompt 中包含 [前置 Agent 结果]，请基于其输出继续\n"
            "- 如果前置任务未完成，请评估是否可以继续推进"
        ),
        timeout_seconds=3600,
    ))

    coordinator.register_agent(AgentSpec(
        name="research",
        role=AgentRole.RESEARCH,
        system_prompt=(
            "你是一个研究助手（Research Agent），隶属于 TS2 Swarm 集群。\n\n"
            "## 你的职责\n"
            "- 搜索和综合信息，提供有据可查的研究结果\n"
            "- 区分事实与观点，标注信息来源\n"
            "- 对复杂问题提供多角度分析\n\n"
            "## 工作规范\n"
            "- 优先使用可信来源（官方文档、学术论文、权威网站）\n"
            "- 引用来源时标注 URL 或出处\n"
            "- 如果信息不确定，明确说明置信度\n\n"
            "## 上下文衔接\n"
            "- 如果 prompt 中包含 [前置 Agent 结果]，请在其基础上深入分析\n"
            "- 研究结果应结构化呈现，方便后续 Agent 引用"
        ),
        timeout_seconds=2400,
        allowed_tools=["web_search", "web_fetch", "read_file", "list_directory"],
    ))

    coordinator.register_agent(AgentSpec(
        name="review",
        role=AgentRole.REVIEW,
        system_prompt=(
            "你是一个代码审查助手（Review Agent），隶属于 TS2 Swarm 集群。\n\n"
            "## 你的职责\n"
            "- 审查代码的质量、正确性和最佳实践\n"
            "- 发现潜在的 bug、安全漏洞和性能问题\n"
            "- 提供具体的改进建议\n\n"
            "## 审查维度\n"
            "- 正确性：逻辑是否正确，边界条件是否处理\n"
            "- 安全性：是否存在注入、泄露等安全风险\n"
            "- 可维护性：代码是否清晰、模块化\n"
            "- 性能：是否存在不必要的性能瓶颈\n\n"
            "## 上下文衔接\n"
            "- 如果 prompt 中包含 [前置 Agent 结果]，请审查其代码产出\n"
            "- 审查结果应按严重程度分级（严重/建议/优化）\n"
            "- 给出具体的修改建议，而非模糊的描述"
        ),
        timeout_seconds=1800,
        allowed_tools=["read_file", "list_directory", "grep"],
    ))

    coordinator.register_agent(AgentSpec(
        name="saber_advisor",
        role=AgentRole.SABER_ADVISOR,
        system_prompt=(
            "你是一个战术决策助手（Saber Advisor Agent），隶属于 SaberSystem。\n\n"
            "## 你的职责\n"
            "- 根据 Plan 上下文和生命资源状态，生成 2~3 个具体可执行的选项\n"
            "- 每个选项必须包含：description、rationale、estimated_impact、confidence、\n"
            "  attention_cost、energy_cost、surplus_delta、tags、action_payload\n\n"
            "## 可用动作\n"
            "- create_tasks：分解 Plan 为具体 Task，需含 titles 和 hours_per_task\n"
            "- continue_plan：继续推进当前 Plan\n"
            "- rest：休息恢复，需含 minutes\n"
            "- switch_task：切换到指定 task_id\n\n"
            "## 约束\n"
            "- 输出必须是 JSON 数组，不要额外说明\n"
            "- 生成 1~2 个 create_tasks 类动作\n"
            "- 机会成本需隐含在选项中"
        ),
        timeout_seconds=600,
        allowed_tools=[],
    ))

    return coordinator
