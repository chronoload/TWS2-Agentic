"""patch.model：自演化补丁数据模型（缺陷 → 可固化补丁脚本）。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PatchScript:
    """一条审计缺陷 → 可执行补丁脚本（落盘 .py，可审查/应用/回滚）。"""
    id: str                       # flag:app.py:23:clear_without_set
    kind: str                     # 缺陷类型（clear_without_set / hardcoded_secret / ...）
    file: str                     # 相对项目根的源码文件
    strategy: str                 # 生成器名（注册于 patch.generator）
    title: str
    detail: str = ""
    operations: list = field(default_factory=list)  # [{op, line, text, ...}]

    def to_py(self, root: str = ".") -> str:
        """固化为可独立执行的补丁脚本（元数据 + operations，供 apply 读取）。"""
        import json
        payload = {
            "id": self.id, "kind": self.kind, "file": self.file,
            "strategy": self.strategy, "title": self.title,
            "detail": self.detail, "operations": self.operations,
        }
        return ("# macdev 自演化补丁脚本（自动生成，可审查/可回滚，勿手改 operations）\n"
                "# 重新生成：python -m macdev patch gen --db <interface_chain.db>\n"
                "# 应用：python -m macdev patch apply --patch <本文件>\n"
                f"PATCH = {json.dumps(payload, ensure_ascii=False, indent=2)}\n")


def load_patch(path) -> PatchScript:
    """从固化脚本读取 PATCH 常量。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_macdev_patch", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = mod.PATCH
    return PatchScript(**p)
