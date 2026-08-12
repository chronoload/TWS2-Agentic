# 原子：_iter_ancestor_ifs（原 interface_chain_extractor.py 第 1328 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _iter_ancestor_ifs(node, tree) -> list:
    """收集 node 的所有祖先 if 条件（ast.If 的 test），按从近到远。"""
    conds = []
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.If):
            continue
        # 判断 node 是否位于该 if 分支体内
        if any(n is node for n in ast.walk(parent)):
            # 排除自身即为 if.test 的情况（条件表达式里的调用，如 while 条件）
            conds.append(_unparse(parent.test))
    return conds
