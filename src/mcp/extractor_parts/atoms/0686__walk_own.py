# 原子：_walk_own（原 interface_chain_extractor.py 第 686 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _walk_own(node):
    """遍历节点自身 body，跳过嵌套函数/类定义（避免闭包内部调用混入父函数）"""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield from _walk_own(child)
