import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .plugin_context import PluginContext

logger = logging.getLogger(__name__)


class PluginKind(Enum):
    STANDALONE = "standalone"
    BACKEND = "backend"
    EXCLUSIVE = "exclusive"
    PLATFORM = "platform"
    MODEL_PROVIDER = "model-provider"


@dataclass
class PluginEntry:
    name: str
    kind: PluginKind = PluginKind.STANDALONE
    plugin_dir: Path = field(default_factory=Path)
    provides_tools: List[str] = field(default_factory=list)
    requires_env: List[str] = field(default_factory=list)
    enabled: bool = True
    ctx: Optional[PluginContext] = None
    register_fn: Optional[Callable] = None


class PluginManager:
    def __init__(self, plugins_dirs: Optional[List[Path]] = None):
        self._entries: Dict[str, PluginEntry] = {}
        # 路径回退链：显式传入目录 → 本包 mcp/plugins（历史死代码修复）
        resolved_dirs: List[Path] = []
        if plugins_dirs:
            resolved_dirs.extend(Path(d) for d in plugins_dirs)
        package_plugins = Path(__file__).resolve().parent
        has_effective = any(d.exists() for d in resolved_dirs)
        if not has_effective and package_plugins.exists():
            resolved_dirs.append(package_plugins)
            logger.info(f"PluginManager: 回退到内置插件目录 {package_plugins}")
        self._plugins_dirs = resolved_dirs
        self._global_tools: Dict[str, Any] = {}
        self._global_hooks: Dict[str, List[Callable]] = {}

    def discover_plugins(self) -> List[PluginEntry]:
        discovered = []
        for plugins_dir in self._plugins_dirs:
            if not plugins_dir.exists():
                continue
            self._scan_dir(plugins_dir, discovered, depth=0)
        logger.info(f"PluginManager: discovered {len(discovered)} plugins")
        return discovered

    def _scan_dir(self, base_dir: Path, discovered: list, depth: int, max_depth: int = 2) -> None:
        for plugin_dir in sorted(base_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            if plugin_dir.name.startswith("_") or plugin_dir.name.startswith("."):
                continue

            manifest = plugin_dir / "plugin.yaml"

            if manifest.exists():
                entry = self._parse_manifest(plugin_dir, manifest)
                if entry:
                    discovered.append(entry)
                    self._entries[entry.name] = entry
            elif depth < max_depth:
                sub_dirs_with_yaml = [
                    sub for sub in plugin_dir.iterdir()
                    if sub.is_dir() and not sub.name.startswith(("_", "."))
                    and (sub / "plugin.yaml").exists()
                ]
                if sub_dirs_with_yaml:
                    for sub in sub_dirs_with_yaml:
                        entry = self._parse_manifest(sub, sub / "plugin.yaml")
                        if entry:
                            discovered.append(entry)
                            self._entries[entry.name] = entry

    def load_plugin(self, name: str) -> Optional[PluginContext]:
        entry = self._entries.get(name)
        if not entry:
            logger.warning(f"Plugin not found: {name}")
            return None

        if not entry.enabled:
            logger.info(f"Plugin disabled: {name}")
            return None

        ctx = PluginContext(
            plugin_name=name,
            plugin_dir=str(entry.plugin_dir),
        )

        if entry.register_fn:
            try:
                entry.register_fn(ctx)
            except Exception as e:
                logger.error(f"Plugin {name} register() error: {e}")
                return None
        else:
            init_file = entry.plugin_dir / "__init__.py"
            if init_file.exists():
                try:
                    module = self._load_module(init_file, f"plugin_{name}")
                    if hasattr(module, "register"):
                        module.register(ctx)
                    else:
                        logger.warning(f"Plugin {name} has no register() function")
                        return None
                except Exception as e:
                    logger.error(f"Plugin {name} load error: {e}")
                    return None

        entry.ctx = ctx
        self._merge_to_global(ctx)
        logger.info(f"Plugin loaded: {name} ({len(ctx.get_registered_tools())} tools)")
        return ctx

    def load_all(self, enabled_only: bool = True) -> List[PluginContext]:
        loaded = []
        for name, entry in self._entries.items():
            if enabled_only and not entry.enabled:
                continue
            ctx = self.load_plugin(name)
            if ctx:
                loaded.append(ctx)
        return loaded

    def get_tool(self, tool_name: str) -> Optional[Any]:
        return self._global_tools.get(tool_name)

    def get_all_tools(self) -> Dict[str, Any]:
        return dict(self._global_tools)

    def run_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        results = []
        for callback in self._global_hooks.get(hook_name, []):
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {hook_name} error: {e}")
        return results

    def enable_plugin(self, name: str):
        entry = self._entries.get(name)
        if entry:
            entry.enabled = True

    def disable_plugin(self, name: str):
        entry = self._entries.get(name)
        if entry:
            entry.enabled = False

    def list_plugins(self) -> List[PluginEntry]:
        return list(self._entries.values())

    def _parse_manifest(self, plugin_dir: Path, manifest_path: Path) -> Optional[PluginEntry]:
        entry = PluginEntry(
            name=plugin_dir.name,
            plugin_dir=plugin_dir,
        )

        if not manifest_path.exists():
            return entry

        try:
            import yaml
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return entry
        except ImportError:
            return entry
        except Exception as e:
            logger.error(f"Plugin manifest parse error {manifest_path}: {e}")
            return entry

        entry.name = data.get("name", plugin_dir.name)
        kind_str = data.get("kind", "standalone")
        try:
            entry.kind = PluginKind(kind_str)
        except ValueError:
            entry.kind = PluginKind.STANDALONE

        entry.provides_tools = data.get("provides_tools", [])
        entry.requires_env = data.get("requires_env", [])

        return entry

    def _load_module(self, file_path: Path, module_name: str):
        if module_name in sys.modules:
            return sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
        return None

    def _merge_to_global(self, ctx: PluginContext):
        for tool_reg in ctx.get_registered_tools():
            self._global_tools[tool_reg.name] = tool_reg

        for hook_name, callbacks in ctx.get_registered_hooks().items():
            if hook_name not in self._global_hooks:
                self._global_hooks[hook_name] = []
            self._global_hooks[hook_name].extend(callbacks)
