from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AuditTask:
    """AuditTask：外置任务模型（入口/规则/目录/排除/策略），项目语义不进内核。"""
    root: Path
    endpoints: list = field(default_factory=list)
    files: dict = field(default_factory=dict)      # {key: 相对路径}
    agent_methods: list = field(default_factory=list)
    chains: dict = field(default_factory=dict)     # {max_depth, entries, preset}
    behavior_rules: dict = field(default_factory=dict)
    id_source_rules: list = field(default_factory=list)
    scan_dirs: list = field(default_factory=list)
    exclude: tuple = ("test", "tests", "node_modules", ".git", ".venv",
                      "venv", "build", "dist", "docs", "__pycache__")
    strategy: str = "base"
    progress: bool = True          # 扫描进度打印
    scan_timeout: int = 0          # 扫描超时秒数（0=不限）；超时截断为已处理子集

    @classmethod
    def from_json(cls, path: Path, root: Path) -> "AuditTask":
        import json
        cfg = json.loads(path.read_text(encoding="utf-8"))
        return cls(root=root, **{k: v for k, v in cfg.items() if k != "name"})
