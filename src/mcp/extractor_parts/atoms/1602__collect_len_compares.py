# 原子：_collect_len_compares（原 interface_chain_extractor.py 第 1602 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _collect_len_compares(fn) -> list:
    """收集函数内所有基于 len() 或 *_count 的数量比较节点（用于覆盖方向仲裁）。
    匹配两种形式：
      - len(a) > len(b) / store_msg_count > agent_msg_count
      - 比较两侧变量名含 count（_count / _cnt）或为 len 调用
    """
    found = []
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Compare):
            continue
        op = sub.ops[0] if sub.ops else None
        if not isinstance(op, (ast.Gt, ast.Lt, ast.GtE, ast.LtE)):
            continue
        left, right = sub.left, sub.comparators[0]
        def _is_count_expr(e) -> bool:
            if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == "len":
                return True
            if isinstance(e, ast.Name) and ("count" in e.id.lower() or e.id.lower().endswith("_cnt")):
                return True
            if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Sub) \
                    and _is_count_expr(e.left):
                return True
            return False
        if _is_count_expr(left) or _is_count_expr(right):
            found.append(sub)
    return found
