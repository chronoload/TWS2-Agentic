import json
import subprocess
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class HookDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"


@dataclass
class HookResult:
    decision: HookDecision = HookDecision.ALLOW
    reason: str = ""
    modified_input: Optional[Dict] = None
    context: Dict = field(default_factory=dict)
    halt: bool = False


@dataclass
class HookSpec:
    name: str
    event: str = "pre_tool_use"
    command: Optional[str] = None
    handler: Optional[Callable] = None
    enabled: bool = True


class HookPipeline:
    def __init__(self):
        self._hooks: Dict[str, List[HookSpec]] = {}

    def register(self, hook: HookSpec):
        if hook.event not in self._hooks:
            self._hooks[hook.event] = []
        self._hooks[hook.event].append(hook)

    def unregister(self, name: str):
        for event_type in self._hooks:
            self._hooks[event_type] = [h for h in self._hooks[event_type] if h.name != name]

    def run_hooks(self, event: str, tool_name: str, tool_input: Dict) -> HookResult:
        hooks = self._hooks.get(event, [])
        current_input = tool_input
        for hook in hooks:
            if not hook.enabled:
                continue
            result = self._execute_hook(hook, tool_name, current_input)
            if result.decision == HookDecision.DENY:
                return result
            if result.decision == HookDecision.MODIFY and result.modified_input is not None:
                current_input = result.modified_input
            if result.halt:
                break
        return HookResult(decision=HookDecision.ALLOW, modified_input=current_input if current_input != tool_input else None)

    def _execute_hook(self, hook: HookSpec, tool_name: str, tool_input: Dict) -> HookResult:
        if hook.handler:
            try:
                return hook.handler(tool_name, tool_input)
            except Exception as e:
                return HookResult(decision=HookDecision.DENY, reason=str(e))
        if hook.command:
            return self._run_command_hook(hook, tool_name, tool_input)
        return HookResult(decision=HookDecision.ALLOW)

    def _run_command_hook(self, hook: HookSpec, tool_name: str, tool_input: Dict) -> HookResult:
        payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
        try:
            proc = subprocess.run(
                hook.command,
                input=payload,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                output = json.loads(proc.stdout)
                decision = HookDecision(output.get("decision", "allow"))
                return HookResult(
                    decision=decision,
                    reason=output.get("reason", ""),
                    modified_input=output.get("modified_input"),
                    context=output.get("context", {}),
                )
            return HookResult(decision=HookDecision.DENY, reason=proc.stderr or f"exit code {proc.returncode}")
        except subprocess.TimeoutExpired:
            return HookResult(decision=HookDecision.DENY, reason="hook command timed out")
        except Exception as e:
            return HookResult(decision=HookDecision.DENY, reason=str(e))
