import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolRegistration:
    name: str
    toolset: str
    schema: Dict[str, Any]
    handler: Callable
    check_fn: Optional[Callable] = None
    emoji: str = ""
    risk_level: str = "medium"


@dataclass
class CommandRegistration:
    name: str
    handler: Callable
    description: str = ""
    usage: str = ""


class PluginContext:
    def __init__(self, plugin_name: str, plugin_dir: str = "", trust_gate: Optional[Any] = None):
        self.plugin_name = plugin_name
        self.plugin_dir = plugin_dir
        self._trust_gate = trust_gate
        self._tools: List[ToolRegistration] = []
        self._hooks: Dict[str, List[Callable]] = {}
        self._commands: List[CommandRegistration] = []
        self._platforms: List[Dict[str, Any]] = []
        self._context_engines: List[Any] = []
        self._skills: List[Dict[str, Any]] = []
        self._llm: Optional[Any] = None

    @property
    def llm(self) -> Optional[Any]:
        return self._llm

    def register_tool(
        self,
        name: str,
        toolset: str,
        schema: Dict[str, Any],
        handler: Callable,
        check_fn: Optional[Callable] = None,
        emoji: str = "",
        risk_level: str = "medium",
    ):
        self._tools.append(ToolRegistration(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            emoji=emoji,
            risk_level=risk_level,
        ))

    def register_hook(self, hook_name: str, callback: Callable):
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(callback)

    def register_platform(self, name: str, label: str, adapter_factory: Callable, check_fn: Optional[Callable] = None):
        self._platforms.append({
            "name": name,
            "label": label,
            "adapter_factory": adapter_factory,
            "check_fn": check_fn,
        })

    def register_command(self, name: str, handler: Callable, description: str = "", usage: str = ""):
        self._commands.append(CommandRegistration(
            name=name,
            handler=handler,
            description=description,
            usage=usage,
        ))

    def register_skill(self, name: str, path: str, description: str = ""):
        self._skills.append({
            "name": name,
            "path": path,
            "description": description,
        })

    def register_context_engine(self, engine: Any):
        self._context_engines.append(engine)

    def inject_message(self, content: str, role: str = "user"):
        hooks = self._hooks.get("inject_message", [])
        for hook in hooks:
            try:
                hook(content, role)
            except Exception as e:
                logger.error(f"Plugin {self.plugin_name} inject_message error: {e}")

    def dispatch_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        for tool_reg in self._tools:
            if tool_reg.name == tool_name:
                return tool_reg.handler(**args)
        return None

    def get_registered_tools(self) -> List[ToolRegistration]:
        return list(self._tools)

    def get_registered_hooks(self) -> Dict[str, List[Callable]]:
        return dict(self._hooks)

    def get_registered_commands(self) -> List[CommandRegistration]:
        return list(self._commands)

    def get_registered_platforms(self) -> List[Dict[str, Any]]:
        return list(self._platforms)

    def get_registered_skills(self) -> List[Dict[str, Any]]:
        return list(self._skills)
