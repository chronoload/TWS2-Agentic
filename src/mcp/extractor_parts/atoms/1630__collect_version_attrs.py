# 原子：_collect_version_attrs（原 interface_chain_extractor.py 第 1630 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _collect_version_attrs(fn) -> set:
    """收集函数内引用的「版本/时间戳仲裁字段」：updated_at/version/hash/seq 等"""
    VERSION_HINTS = ("updated_at", "updated", "version", "revision",
                     "_last_hash", "checkpoint_hash", "seq", "_snapshot_seq",
                     "created_at", "mtime", "timestamp")
    attrs = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Attribute):
            if sub.attr in VERSION_HINTS or any(
                    h in sub.attr.lower() for h in ("version", "_hash", "_seq")):
                attrs.add(sub.attr)
        elif isinstance(sub, ast.Str):
            if sub.s in VERSION_HINTS:
                attrs.add(sub.s)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if sub.value in VERSION_HINTS:
                attrs.add(sub.value)
    return attrs
