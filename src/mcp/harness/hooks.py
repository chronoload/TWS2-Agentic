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
                encoding='utf-8', errors='replace',
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


class CommandGuardHook:
    """把 command_guard 的静态分析接入 Hook 管线的适配器。

    设计意图
    --------
    与 CommandGuardMiddleware 功能等价，但面向 hook 管线（对应 Cline 的
    command-guard.ts 在 Plan 模式下拦截 run_commands 的行为）：通过 spec()
    返回一个注册在 pre_tool_use 事件的 HookSpec，由 HookPipeline 调用
    handle()。命中黑名单时返回 DENY 阻止工具执行，未命中返回 ALLOW；
    仅在 Plan 模式下生效。

    模式判定优先级（高到低）：set_mode 显式设置 > tool_input 里的 mode 字段 >
    构造时注入的 mode_getter 回调。
    """

    def __init__(self, mode_getter: Optional[Callable[[], str]] = None):
        """初始化命令守卫钩子。

        参数
        ----
        mode_getter: 可选回调，返回当前模式字符串；在 set_mode 与输入均
        未提供模式时兜底使用。
        """
        self._mode_getter = mode_getter
        self._mode: Optional[str] = None

    def set_mode(self, mode: str) -> None:
        """显式设定模式（最高优先级）。

        参数
        ----
        mode: 模式名，统一转为小写后与 "plan" 比较。
        """
        self._mode = str(mode).lower()

    def spec(self) -> HookSpec:
        """生成注册到 HookPipeline 的 HookSpec。

        返回
        ----
        名为 "command_guard"、事件为 pre_tool_use、以 self.handle 为处理器的
        HookSpec。
        """
        return HookSpec(name="command_guard", event="pre_tool_use", handler=self.handle)

    def _is_plan_mode(self, tool_input: Dict) -> bool:
        """按优先级判定当前是否处于 Plan 模式。

        判定顺序（命中即返回）：set_mode 显式设置 > tool_input 里的 mode
        字段 > mode_getter 回调（抛异常时按非 Plan 处理）。

        参数
        ----
        tool_input: 本次工具调用的输入字典。

        返回
        ----
        处于 Plan 模式返回 True，否则 False。
        """
        # 1. set_mode 显式设置优先。
        if self._mode is not None:
            return self._mode == "plan"
        # 2. 工具输入里的 mode 字段。
        if isinstance(tool_input, dict):
            mode = tool_input.get("mode")
            if mode:
                return str(mode).lower() == "plan"
        # 3. 外部回调兜底；回调抛异常时按"非 Plan"放行，避免误伤。
        if self._mode_getter is not None:
            try:
                return str(self._mode_getter()).lower() == "plan"
            except Exception:
                return False
        return False

    def handle(self, tool_name: str, tool_input: Dict) -> HookResult:
        """pre_tool_use 事件的处理函数（由 HookPipeline 调用）。

        逻辑：非 Plan 模式直接 ALLOW → 非终端工具直接 ALLOW → 取不到命令
        文本直接 ALLOW → analyze_command 分析，命中黑名单返回 DENY 并附上
        中文原因，否则 ALLOW。对 command_guard 采用函数内延迟导入，避免在
        hook 定义处形成模块级循环依赖。

        参数
        ----
        tool_name: 即将执行的工具名。
        tool_input: 工具输入字典。

        返回
        ----
        HookResult：拦截时 decision 为 DENY；否则 ALLOW。
        """
        if not self._is_plan_mode(tool_input):
            return HookResult(decision=HookDecision.ALLOW)
        from ..middleware.command_guard import TERMINAL_TOOLS, COMMAND_KEYS, analyze_command
        if tool_name not in TERMINAL_TOOLS:
            return HookResult(decision=HookDecision.ALLOW)
        command = None
        if isinstance(tool_input, dict):
            for key in COMMAND_KEYS:
                value = tool_input.get(key)
                if isinstance(value, str):
                    command = value
                    break
        if not command or not command.strip():
            return HookResult(decision=HookDecision.ALLOW)
        result = analyze_command(command)
        if result.blocked:
            return HookResult(
                decision=HookDecision.DENY,
                reason=f"Plan 模式禁止：{result.reason}",
            )
        return HookResult(decision=HookDecision.ALLOW)
