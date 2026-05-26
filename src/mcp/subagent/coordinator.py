from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .session import SessionAgent
from .types import AgentRole, AgentSpec, SubAgentResult, SubAgentStatus


class Coordinator:
    def __init__(self, llm=None, tool_registry=None, max_workers: int = 3):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_workers = max_workers
        self._agents: Dict[str, SessionAgent] = {}
        self._specs: Dict[str, AgentSpec] = {}
        self._agent_llms: Dict[str, Any] = {}

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
            agent = self._agents.get(name)
            if agent:
                agent.cancel()
        else:
            for agent in self._agents.values():
                agent.cancel()

    def run(self, agent_name: str, prompt: str, context=None) -> SubAgentResult:
        spec = self._specs.get(agent_name)
        if spec is None:
            result = SubAgentResult(agent_name=agent_name)
            result.mark_failed(error=f"Agent '{agent_name}' not found")
            return result

        tools = self._build_tools(spec)
        # 使用为该 Agent 指定的 LLM，或回退到 Coordinator 的默认 LLM
        agent_llm = self._agent_llms.get(agent_name, self.llm)
        agent = SessionAgent(
            spec=spec,
            llm=agent_llm,
            tools=tools,
            tool_executor=self._execute_tool,
        )
        self._agents[agent_name] = agent
        try:
            return agent.run(prompt, context)
        finally:
            self._agents.pop(agent_name, None)

    def run_parallel(self, tasks: List[Dict]) -> List[SubAgentResult]:
        results: List[Optional[SubAgentResult]] = [None] * len(tasks)

        def _run_task(index: int, task: Dict) -> None:
            results[index] = self.run(
                agent_name=task["agent"],
                prompt=task["prompt"],
                context=task.get("context"),
            )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(_run_task, i, task) for i, task in enumerate(tasks)
            ]
            for future in futures:
                future.result()

        return results

    def _build_tools(self, spec: AgentSpec) -> List[Dict]:
        if self.tool_registry is None:
            return []

        all_tools = list(self.tool_registry.values()) if isinstance(self.tool_registry, dict) else list(self.tool_registry)

        if spec.allowed_tools is not None:
            allowed = set(spec.allowed_tools)
            all_tools = [t for t in all_tools if t.get("name") in allowed]

        if spec.denied_tools is not None:
            denied = set(spec.denied_tools)
            all_tools = [t for t in all_tools if t.get("name") not in denied]

        return all_tools

    def _execute_tool(self, tool_call) -> Any:
        if self.tool_registry is None:
            return None

        name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
        handler = self.tool_registry.get(name) if isinstance(self.tool_registry, dict) else None

        if handler is None:
            return None

        arguments = tool_call.get("arguments", {}) if isinstance(tool_call, dict) else getattr(tool_call, "arguments", {})
        return handler(**arguments)


def create_default_coordinator(llm=None, tool_registry=None) -> Coordinator:
    coordinator = Coordinator(llm=llm, tool_registry=tool_registry)

    coordinator.register_agent(AgentSpec(
        name="coder",
        role=AgentRole.CODER,
        system_prompt="You are a coding assistant. Write clean, efficient, and well-structured code.",
        max_turns=15,
    ))

    coordinator.register_agent(AgentSpec(
        name="task",
        role=AgentRole.TASK,
        system_prompt="You are a task execution assistant. Complete tasks accurately and efficiently.",
        max_turns=10,
    ))

    coordinator.register_agent(AgentSpec(
        name="research",
        role=AgentRole.RESEARCH,
        system_prompt="You are a research assistant. Find and synthesize information from available sources.",
        max_turns=8,
        allowed_tools=["web_search", "web_fetch", "read_file", "list_directory"],
    ))

    coordinator.register_agent(AgentSpec(
        name="review",
        role=AgentRole.REVIEW,
        system_prompt="You are a code review assistant. Analyze code for quality, correctness, and best practices.",
        max_turns=5,
        allowed_tools=["read_file", "list_directory", "grep"],
    ))

    return coordinator
