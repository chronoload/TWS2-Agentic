from typing import Dict, List, Optional

from .events import EventStream, EventType
from .turn import Turn, TurnResult, TurnStatus
from .hooks import HookPipeline, HookResult, HookDecision
from .approval import ApprovalManager, ApprovalDecision, ApprovalMode
from .session_store import SessionStore


class HarnessRunner:
    def __init__(
        self,
        llm=None,
        tool_registry=None,
        approval_mode=ApprovalMode.SUGGEST,
        event_stream=None,
        hook_pipeline=None,
        session_store=None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry or {}
        self.event_stream = event_stream or EventStream()
        self.hooks = hook_pipeline or HookPipeline()
        self.approval = ApprovalManager(mode=approval_mode)
        self.sessions = session_store or SessionStore()
        self._active_turns: Dict[str, Turn] = {}

    def run_turn(
        self,
        messages: List[Dict],
        tools=None,
        session_id=None,
    ) -> TurnResult:
        turn = Turn()
        self._active_turns[turn.id] = turn
        try:
            turn.start()
            self.event_stream.emit(EventType.TURN_START, turn_id=turn.id)

            if not self.llm:
                turn.fail("LLM未配置")
                self.event_stream.emit(EventType.TURN_ERROR, turn_id=turn.id, error="LLM未配置")
                return turn.result

            self.event_stream.emit(EventType.LLM_REQUEST, turn_id=turn.id, messages=messages)

            response = self.llm.chat(messages, tools=tools)

            self.event_stream.emit(EventType.LLM_RESPONSE, turn_id=turn.id, response=response)

            content = getattr(response, "content", None) or response.get("content") if isinstance(response, dict) else getattr(response, "content", None)
            reasoning_content = getattr(response, "reasoning_content", None) or (response.get("reasoning_content") if isinstance(response, dict) else None)
            tool_calls = getattr(response, "tool_calls", None) or (response.get("tool_calls") if isinstance(response, dict) else None) or []
            prompt_tokens = getattr(response, "prompt_tokens", 0) or (response.get("prompt_tokens", 0) if isinstance(response, dict) else 0)
            completion_tokens = getattr(response, "completion_tokens", 0) or (response.get("completion_tokens", 0) if isinstance(response, dict) else 0)

            turn.result.prompt_tokens = prompt_tokens
            turn.result.completion_tokens = completion_tokens

            if tool_calls:
                executed_tool_calls = []
                for tc in tool_calls:
                    result = self._execute_tool_with_pipeline(tc, turn.id)
                    if result is None:
                        turn.cancel()
                        break
                    tc_entry = {
                        "tool_call": tc,
                        "result": result,
                    }
                    executed_tool_calls.append(tc_entry)
                else:
                    turn.complete(
                        content=content or "",
                        reasoning_content=reasoning_content,
                        tool_calls=executed_tool_calls,
                    )
            else:
                turn.complete(
                    content=content or "",
                    reasoning_content=reasoning_content,
                )

            self.event_stream.emit(EventType.TURN_COMPLETE, turn_id=turn.id, result=turn.result)
            return turn.result
        finally:
            self._active_turns.pop(turn.id, None)

    def cancel_turn(self, turn_id: str):
        turn = self._active_turns.get(turn_id)
        if turn:
            turn.cancel()

    def _execute_tool_with_pipeline(self, tool_call, turn_id: str) -> Optional[str]:
        if isinstance(tool_call, dict):
            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
            tool_args = tool_call.get("arguments") or tool_call.get("function", {}).get("arguments", {})
            if isinstance(tool_args, str):
                import json
                try:
                    tool_args = json.loads(tool_args)
                except Exception:
                    tool_args = {}
        else:
            tool_name = getattr(tool_call, "name", "") or getattr(getattr(tool_call, "function", None), "name", "")
            tool_args = getattr(tool_call, "arguments", {}) or getattr(getattr(tool_call, "function", None), "arguments", {})
            if isinstance(tool_args, str):
                import json
                try:
                    tool_args = json.loads(tool_args)
                except Exception:
                    tool_args = {}

        if not isinstance(tool_args, dict):
            tool_args = {}

        self.event_stream.emit(EventType.TOOL_CALL_START, turn_id=turn_id, tool_name=tool_name, tool_args=tool_args)

        try:
            hook_result = self.hooks.run_hooks("pre_tool_use", tool_name, tool_args)
        except RuntimeError:
            hook_result = HookResult(decision=HookDecision.ALLOW)

        if hook_result.decision == HookDecision.DENY:
            self.event_stream.emit(EventType.TOOL_CALL_DENIED, turn_id=turn_id, tool_name=tool_name, reason=hook_result.reason)
            if hook_result.halt:
                return None
            return hook_result.reason or f"工具 {tool_name} 被拒绝"

        if hook_result.decision == HookDecision.MODIFY and hook_result.modified_input is not None:
            tool_args = hook_result.modified_input

        high_risk_tools = {"bash", "shell", "execute", "write_file"}
        risk_level = "high" if tool_name in high_risk_tools else "medium"

        approval_decision = self.approval.request_approval(
            tool_name=tool_name,
            tool_input=tool_args,
            reason=f"执行工具: {tool_name}",
            risk_level=risk_level,
        )

        if approval_decision == ApprovalDecision.DENY:
            self.event_stream.emit(EventType.TOOL_CALL_DENIED, turn_id=turn_id, tool_name=tool_name, reason="审批拒绝")
            return "审批拒绝"

        handler = self.tool_registry.get(tool_name)
        if handler is None:
            return f"未找到工具: {tool_name}"

        if callable(handler):
            result = handler(**tool_args) if isinstance(tool_args, dict) else handler(tool_args)
        else:
            result = handler

        result_str = str(result) if result is not None else ""

        self.event_stream.emit(EventType.TOOL_CALL_COMPLETE, turn_id=turn_id, tool_name=tool_name, result=result_str)

        return result_str
