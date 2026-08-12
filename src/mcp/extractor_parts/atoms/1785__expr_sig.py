# 原子：_expr_sig（原 interface_chain_extractor.py 第 1785 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _expr_sig(e) -> str:
    """实参表达式 → 签名：req.session_id → session_id；变量 → 变量名；字符串字面量 → str:<值>"""
    if isinstance(e, ast.Attribute):
        return e.attr
    if isinstance(e, ast.Name):
        return e.id
    if isinstance(e, ast.Constant) and isinstance(e.value, str):
        return "str:" + e.value
    if isinstance(e, ast.Starred) and isinstance(e.value, (ast.Name, ast.Attribute)):
        return _expr_sig(e.value)
    return ""
