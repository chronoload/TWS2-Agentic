# 原子：extract_func_map（原 interface_chain_extractor.py 第 593 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def extract_func_map(path: Path) -> dict:
    """提取模块内所有函数定义（含嵌套），返回 {函数名: FunctionDef}"""
    if not path.exists():
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return {}
    fmap: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fmap.setdefault(node.name, node)
    return fmap
