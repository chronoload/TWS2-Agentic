from __future__ import annotations

import logging
import threading
import time
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
        cancel_event: Optional[threading.Event] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.spec = spec
        self.llm = llm
        self.tools = tools or []
        self.tool_executor = tool_executor
        self.cancel_event = cancel_event or threading.Event()
        self.on_event = on_event  # 执行进度事件回调（转发到主 Agent 流式通道）
        self.session_id = uuid.uuid4().hex[:12]
        self.messages: List[Dict[str, Any]] = []
        self._cancelled = False
        self._timeout = spec.timeout_seconds
        self._start_time: float = 0
        self._result = SubAgentResult(
            agent_name=spec.name,
            role=spec.role,
        )

    def _emit(self, event: Dict[str, Any]):
        """安全触发执行进度事件（自动附加 agent 名）"""
        if not self.on_event:
            return
        try:
            self.on_event({**event, "agent": self.spec.name})
        except Exception as e:
            logger.debug(f"SessionAgent on_event error: {e}")

    @property
    def is_busy(self) -> bool:
        return self._result.status == SubAgentStatus.RUNNING

    def cancel(self):
        self._cancelled = True
        self.cancel_event.set()
        self._result.mark_cancelled()

    def _check_cancelled(self) -> bool:
        if self._cancelled or self.cancel_event.is_set():
            if self._result.status == SubAgentStatus.RUNNING:
                self._result.mark_cancelled(messages=list(self.messages))
            return True
        # 超时检查
        if self._timeout and self._start_time:
            elapsed = time.time() - self._start_time
            if elapsed > self._timeout:
                logger.warning(f"SessionAgent {self.spec.name} timed out after {elapsed:.1f}s (limit={self._timeout}s)")
                self._result.mark_failed(
                    error=f"执行超时（{elapsed:.1f}s > {self._timeout}s）",
                    messages=list(self.messages)
                )
                return True
        return False

    def run(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> SubAgentResult:
        self._result.mark_started()
        self._start_time = time.time()
        self.messages = []

        system_msg = {"role": "system", "content": self.spec.system_prompt}
        if context:
            system_msg["content"] += "\n\n上下文信息:\n"
            for k, v in context.items():
                system_msg["content"] += f"- {k}: {v}\n"

        self.messages.append(system_msg)
        self.messages.append({"role": "user", "content": prompt})

        try:
            max_turns = self.spec.max_turns
            max_retries = getattr(self.spec, "max_retries", 3)
            consecutive_errors = 0
            turn = 0
            while max_turns <= 0 or turn < max_turns:
                turn += 1
                if self._check_cancelled():
                    break

                self._emit({"event": "llm", "turn": turn})
                try:
                    response = self._call_llm()
                except Exception as e:
                    # loop 防异常打断：LLM 异常 → 记录错误并继续下一轮，连续超限才失败
                    consecutive_errors += 1
                    if consecutive_errors > max_retries:
                        logger.error(f"SessionAgent {self.spec.name} LLM 连续异常 {consecutive_errors} 次，终止")
                        self._result.mark_failed(
                            error=f"LLM 连续异常 {consecutive_errors} 次: {e}",
                            messages=list(self.messages),
                        )
                        self._emit({"event": "end", "status": "failed", "error": str(e)[:200]})
                        return self._result
                    self.messages.append({
                        "role": "system",
                        "content": f"[loop-recovery] LLM 调用异常（第 {consecutive_errors} 次）：{e}。请继续。",
                    })
                    continue
                if response is None:
                    if not self.llm:
                        break  # LLM 未配置：重试无意义
                    consecutive_errors += 1
                    if consecutive_errors > max_retries:
                        logger.error(f"SessionAgent {self.spec.name} LLM 连续无响应 {consecutive_errors} 次，终止")
                        self._result.mark_failed(
                            error=f"LLM 连续无响应 {consecutive_errors} 次",
                            messages=list(self.messages),
                        )
                        self._emit({"event": "end", "status": "failed", "error": "LLM 连续无响应"})
                        return self._result
                    self.messages.append({
                        "role": "system",
                        "content": f"[loop-recovery] LLM 无响应（第 {consecutive_errors} 次）。请继续。",
                    })
                    continue
                consecutive_errors = 0

                self._result.prompt_tokens += getattr(response, "prompt_tokens", 0)
                self._result.completion_tokens += getattr(response, "completion_tokens", 0)
                self._result.tool_calls_count += len(getattr(response, "tool_calls", []))

                if getattr(response, "reasoning_content", ""):
                    self._result.reasoning_content = response.reasoning_content

                if not getattr(response, "tool_calls", []):
                    content = ""
                    if hasattr(response, "content"):
                        content = response.content
                    elif isinstance(response, "dict"):
                        content = response.get("content", "")
                    # 追加纯文本 assistant 消息
                    self.messages.append({"role": "assistant", "content": str(content)})
                    self._result.mark_completed(content=str(content), messages=list(self.messages))
                    self._emit({"event": "end", "status": "completed", "content": str(content)[:300]})
                    return self._result

                # 将 assistant 消息（含 tool_calls）加入历史
                assistant_msg = {"role": "assistant", "content": getattr(response, "content", "") or ""}
                tool_calls_list = getattr(response, "tool_calls", [])
                if tool_calls_list:
                    import json as _json
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id if hasattr(tc, "id") else "",
                            "type": "function",
                            "function": {
                                "name": tc.name if hasattr(tc, "name") else "",
                                "arguments": _json.dumps(tc.arguments, ensure_ascii=False) if isinstance(getattr(tc, "arguments", None), dict) else getattr(tc, "arguments", "{}"),
                            },
                        }
                        for tc in tool_calls_list
                    ]
                self.messages.append(assistant_msg)

                for tc in tool_calls_list:
                    if self._check_cancelled():
                        break
                    tc_name = tc.name if hasattr(tc, "name") else ""
                    tc_args = tc.arguments if hasattr(tc, "arguments") else {}
                    self._emit({"event": "tool_call", "turn": turn + 1, "tool_name": tc_name, "tool_args": tc_args})
                    tool_result = self._execute_tool(tc)
                    self._emit({
                        "event": "tool_result", "turn": turn,
                        "tool_name": tc_name,
                        "preview": str(tool_result)[:200],
                    })
                    tc_id = tc.id if hasattr(tc, "id") else ""
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": str(tool_result),
                    })

            if not self._cancelled and self._result.status == SubAgentStatus.RUNNING:
                last_content = ""
                for msg in reversed(self.messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        last_content = msg["content"]
                        break
                self._result.mark_completed(content=last_content or "达到最大轮次限制", messages=list(self.messages))
                self._emit({"event": "end", "status": "completed", "content": last_content[:300]})

        except Exception as e:
            logger.error(f"SessionAgent {self.spec.name} failed: {e}")
            self._result.mark_failed(error=str(e), messages=list(self.messages))
            self._emit({"event": "end", "status": "failed", "error": str(e)[:200]})

        return self._result

    def _call_llm(self):
        if not self.llm:
            return None
        # 异常不在此吞掉：抛给 run() 的 loop 恢复机制处理（防异常打断）
        tools_param = self.tools if self.tools else None
        return self.llm.chat(self.messages, tools=tools_param)

    def _execute_tool(self, tool_call) -> Any:
        if self.tool_executor:
            try:
                return self.tool_executor(tool_call)
            except Exception as e:
                return f"tool error: {e}"

        # 解析工具名
        if isinstance(tool_call, dict):
            name = tool_call.get("name", "") or tool_call.get("function", {}).get("name", "")
        else:
            name = getattr(tool_call, "name", "")
            if not name and hasattr(tool_call, "function"):
                name = getattr(tool_call.function, "name", "")

        return f"tool '{name}' no executor"
