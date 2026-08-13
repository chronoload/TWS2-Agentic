# 原子：_call_repr（原 interface_chain_extractor.py 第 1300 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _call_repr(node: ast.AST) -> str:
    """把 ast.Call 的 func 转成可读字符串：store.update / _sync_agent_from_store"""
    f = getattr(node, "func", None)
    if f is None:
        return ""
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        base = _call_repr(f.value) if isinstance(f.value, (ast.Name, ast.Attribute)) else "*"
        return f"{base}.{f.attr}"
    return ""
