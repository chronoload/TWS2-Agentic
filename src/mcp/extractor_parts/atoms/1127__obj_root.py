# 原子：_obj_root（原 interface_chain_extractor.py 第 1127 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _obj_root(node) -> str:
    """取属性读写对象的最左侧名字：agent.state.x → agent；self → self；Name → id"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _obj_root(node.value)
    return "?"
