"""EnvPlugin 基类和注册表"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DetectionResult:
    name: str
    detected: bool
    version: str = ""
    path: str = ""
    details: str = ""


@dataclass
class LockFile:
    plugin_name: str
    entries: dict = field(default_factory=dict)


class EnvPlugin:
    """环境插件基类——所有插件实现此接口"""

    name: str = "base"

    def detect(self) -> DetectionResult:
        """检测环境是否可用"""
        raise NotImplementedError

    def install(self, confirm: bool = True) -> bool:
        """安装依赖（需用户确认）"""
        raise NotImplementedError

    def lock(self) -> LockFile:
        """锁定版本到文件"""
        raise NotImplementedError

    def verify(self) -> bool:
        """验证环境完好"""
        raise NotImplementedError

    def _run(self, cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
        """运行系统命令"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return -1, "", f"Command not found: {cmd[0]}"
        except subprocess.TimeoutExpired:
            return -2, "", f"Timeout after {timeout}s"


class PluginRegistry:
    """插件注册表"""

    def __init__(self):
        self._plugins: dict[str, EnvPlugin] = {}

    def register(self, plugin: EnvPlugin) -> None:
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> EnvPlugin | None:
        return self._plugins.get(name)

    def detect_all(self) -> list[DetectionResult]:
        return [p.detect() for p in self._plugins.values()]

    @property
    def plugins(self) -> dict[str, EnvPlugin]:
        return self._plugins.copy()
