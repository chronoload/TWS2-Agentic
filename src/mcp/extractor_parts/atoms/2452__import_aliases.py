# 原子：_import_aliases（原 interface_chain_extractor.py 第 2452 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _import_aliases(tree) -> dict:
    """模块别名表：{'np': 'numpy', 'reloader': 'x.cache.reloader', ...}"""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                key = a.asname or a.name.split(".")[0]
                aliases[key] = a.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                key = a.asname or a.name
                aliases[key] = f"{mod}.{a.name}" if mod else a.name
    return aliases
