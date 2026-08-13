from enum import Enum
from dataclasses import dataclass, field
from typing import Set, List, Optional


class Permission(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


DEFAULT_ALLOWED_COMMANDS = {
    "python", "python3", "pip", "node", "npm", "npx", "git",
    "ls", "cat", "head", "tail", "grep", "find", "echo",
    "wc", "sort", "uniq", "diff", "curl", "wget",
}

DEFAULT_DENIED_COMMANDS = {
    "rm", "rmdir", "del", "format", "mkfs", "dd",
    "sudo", "su", "runas", "shutdown", "reboot",
    "reg", "regedit", "powershell", "cmd",
}


@dataclass
class SandboxPolicy:
    max_execution_time: int = 30
    max_output_bytes: int = 65536
    max_processes: int = 5
    allow_network: bool = False
    allow_file_write: bool = False
    allow_file_read: bool = True
    allowed_commands: Set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED_COMMANDS))
    denied_commands: Set[str] = field(default_factory=lambda: set(DEFAULT_DENIED_COMMANDS))
    allowed_paths: List[str] = field(default_factory=list)
    denied_paths: List[str] = field(default_factory=lambda: [
        "C:\\Windows\\System32", "/etc", "/root",
    ])
    env_vars: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, base: Optional["SandboxPolicy"] = None) -> "SandboxPolicy":
        """从全局配置加载命令策略（与统一审批联动）

        合并规则：默认列表 + 配置追加列表；配置清空列表不覆盖默认（安全兜底）。
        黑名单优先级最高：即使同时出现在白名单也直接拒绝。
        """
        policy = base if base is not None else cls()
        try:
            from ..config import get_config_manager
            cm = get_config_manager()
            extra_allowed = cm.get_sandbox_allowed_commands() or []
            extra_denied = cm.get_sandbox_denied_commands() or []
            if extra_allowed:
                policy.allowed_commands = set(DEFAULT_ALLOWED_COMMANDS) | set(extra_allowed)
            if extra_denied:
                policy.denied_commands = set(DEFAULT_DENIED_COMMANDS) | set(extra_denied)
        except Exception:
            pass
        return policy

    def check_command(self, command: str) -> Permission:
        base = command.strip().split()[0] if command.strip() else ""
        base = base.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        base = base.lower()
        if base in self.denied_commands:
            return Permission.DENY
        if base in self.allowed_commands:
            return Permission.ALLOW
        return Permission.ASK

    def check_path(self, path: str) -> Permission:
        for dp in self.denied_paths:
            if path.startswith(dp):
                return Permission.DENY
        if self.allowed_paths:
            for ap in self.allowed_paths:
                if path.startswith(ap):
                    return Permission.ALLOW
            return Permission.ASK
        if self.allow_file_read:
            return Permission.ALLOW
        return Permission.ASK

    @classmethod
    def strict(cls) -> "SandboxPolicy":
        return cls(
            max_execution_time=10,
            max_output_bytes=16384,
            max_processes=1,
            allow_network=False,
            allow_file_write=False,
            allow_file_read=True,
            allowed_commands={"python", "python3", "node"},
        )

    @classmethod
    def permissive(cls) -> "SandboxPolicy":
        return cls(
            max_execution_time=120,
            max_output_bytes=262144,
            max_processes=10,
            allow_network=True,
            allow_file_write=True,
            allow_file_read=True,
            denied_commands=set(),
        )
