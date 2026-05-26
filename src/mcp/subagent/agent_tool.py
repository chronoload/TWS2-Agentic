from __future__ import annotations

from typing import Any, Dict, Optional

from .coordinator import Coordinator
from .types import SubAgentStatus

AGENT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "sub_agent",
        "description": "委派任务给专门的子Agent执行。可用角色: coder(编程), task(任务), research(研究), review(审查)。",
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "要使用的Agent名称: coder, task, research, review",
                },
                "prompt": {
                    "type": "string",
                    "description": "给子Agent的任务描述",
                },
                "context": {
                    "type": "object",
                    "description": "传递给子Agent的上下文信息",
                },
            },
            "required": ["agent", "prompt"],
        },
    },
}


class AgentTool:

    def __init__(self, coordinator: Coordinator):
        self.coordinator = coordinator

    @staticmethod
    def to_schema() -> Dict[str, Any]:
        return AGENT_TOOL_SCHEMA

    def __call__(self, agent: str, prompt: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        result = self.coordinator.run(agent, prompt, context)
        if result.status == SubAgentStatus.COMPLETED:
            output = result.content
            if result.reasoning_content:
                output = f"💭 推理:\n{result.reasoning_content}\n\n📝 结果:\n{output}"
            output += f"\n\n[子Agent: {result.agent_name} | 轮次: {result.tool_calls_count} | tokens: {result.prompt_tokens}+{result.completion_tokens} | 耗时: {result.duration_ms}ms]"
            return output
        elif result.status == SubAgentStatus.CANCELLED:
            return f"子Agent '{agent}' 已取消"
        else:
            return f"子Agent '{agent}' 执行失败: {result.error}"
