# 原子：_call_target（原 interface_chain_extractor.py 第 2468 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _call_target(call) -> tuple:
    """调用表达式 → (dst 名称, dst_kind, base) 
    base：Attribute 的接收者（模块别名 / self / 普通对象）"""
    f = call.func
    if isinstance(f, ast.Name):
        return f.id, "name", None
    if isinstance(f, ast.Attribute):
        base = f.value
        if isinstance(base, ast.Name) and base.id in ("self", "cls"):
            return f.attr, "self_method", None
        if isinstance(base, ast.Name):
            return f.attr, "attr", base.id
        if isinstance(base, ast.Attribute):
            # a.b.c() → 取最底层名字 a
            node = base
            while isinstance(node, ast.Attribute):
                node = node.value
            bottom = node.id if isinstance(node, ast.Name) else ""
            return f.attr, "attr_chain", bottom
    return "", "unknown", None
