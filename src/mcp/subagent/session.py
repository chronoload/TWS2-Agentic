from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Dict, List, Optional

from .types import AgentRole, AgentSpec, SubAgentResult, SubAgentStatus

logger = logging.getLogger(__name__)


class SessionAgent:
    def __init__(
        self,
        spec: AgentSpec,
        llm: Any = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[Callable] = None,
    ):
        self.spec = spec
        self.llm = llm
        self.tools = tools or []
        self.tool_executor = tool_executor
        self.session_id = uuid.uuid4().hex[:12]
        self.messages: List[Dict[str, Any]] = []
        self._cancelled = False
        self._result = SubAgentResult(
            agent_name=spec.name,
            role=spec.role,
        )

    @property
    def is_busy(self) -> bool:
        return self._result.status == SubAgentStatus.RUNNING

    def cancel(self):
        self._cancelled = True
        self._result.mark_cancelled()

    def run(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> SubAgentResult:
        self._result.mark_started()
        self.messages = []

        system_msg = {"role": "system", "content": self.spec.system_prompt}
        if context:
            system_msg["content"] += "\n\n上下文信息:\n"
            for k, v in context.items():
                system_msg["content"] += f"- {k}: {v}\n"

        self.messages.append(system_msg)
        self.messages.append({"role": "user", "content": prompt})

        try:
            for turn in range(self.spec.max_turns):
                if self._cancelled:
                    break

                response = self._call_llm()
                if not response:
                    break

                if hasattr(response, "message"):
                    self.messages.append(response.message)
                elif hasattr(response, "content"):
                    self.messages.append({"role": "assistant", "content": str(response.content)})

                self._result.prompt_tokens += getattr(response, "prompt_tokens", 0)
                self._result.completion_tokens += getattr(response, "completion_tokens", 0)
                self._result.tool_calls_count += len(getattr(response, "tool_calls", []))

                if getattr(response, "reasoning_content", ""):
                    self._result.reasoning_content = response.reasoning_content

                if not getattr(response, "tool_calls", []):
                    content = ""
                    if hasattr(response, "content"):
                        content = response.content
                    elif isinstance(response, dict):
                        content = response.get("content", "")
                    self._result.mark_completed(content=str(content))
                    return self._result

                for tc in getattr(response, "tool_calls", []):
                    if self._cancelled:
                        break
                    tool_result = self._execute_tool(tc)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id if hasattr(tc, "id") else "",
                        "content": str(tool_result),
                    })

            if not self._cancelled and self._result.status == SubAgentStatus.RUNNING:
                last_content = ""
                for msg in reversed(self.messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        last_content = msg["content"]
                        break
                self._result.mark_completed(content=last_content or "达到最大轮次限制")

        except Exception as e:
            logger.error(f"SessionAgent {self.spec.name} failed: {e}")
            self._result.mark_failed(error=str(e))

        return self._result

    def _call_llm(self):
        if not self.llm:
            return None
        try:
            tools_param = self.tools if self.tools else None
            return self.llm.chat(self.messages, tools=tools_param)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _execute_tool(self, tool_call) -> Any:
        if self.tool_executor:
            try:
                return self.tool_executor(tool_call)
            except Exception as e:
                return f"tool error: {e}"
        return f"tool {getattr(tool_call, 'name', 'unknown')} no executor"
