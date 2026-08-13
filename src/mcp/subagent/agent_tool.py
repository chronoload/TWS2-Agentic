from __future__ import annotations

import json
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
        # on_event：子代理执行进度回调（转发到主 Agent 流式通道，前端可实时显示）
        on_event = kwargs.pop("on_event", None)
        result = self.coordinator.run(agent, prompt, context, on_event=on_event)
        # 返回结构化JSON，前端可识别 __sub_agent__ 标记做特殊渲染
        # 关键：包含子代理的完整历史 (messages)，用于状态机持久化和回退
        structured = {
            "__sub_agent__": True,
            "agent_name": result.agent_name,
            "role": result.role.value if hasattr(result.role, "value") else str(result.role),
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "content": result.content,
            "reasoning_content": result.reasoning_content,
            "tool_calls_count": result.tool_calls_count,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "duration_ms": result.duration_ms,
            "error": result.error,
            "nested_history": result.messages,  # 子代理的完整对话历史
        }
        return json.dumps(structured, ensure_ascii=False)
