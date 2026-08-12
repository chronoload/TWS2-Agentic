# 原子：_has_content_arbitration（原 interface_chain_extractor.py 第 1650 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _has_content_arbitration(fn) -> bool:
    """检测「内容级仲裁」手段（等效于版本仲裁，可替代数量仲裁）：
      - 对消息列表/切片的内容相等比较：agent.messages == store_msgs、
        full[:len(prefix)] == prefix
      - 前缀判定：调用 _is_prefix / startswith / endswith
    有内容级比较即说明同步函数能区分"分叉/相等"，不再只是纯数量仲裁。
    """
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Compare):
            # == / != 内容比较（两侧含 Attribute 或 Slice）
            if any(isinstance(op, (ast.Eq, ast.NotEq)) for op in sub.ops):
                sides = [sub.left] + list(sub.comparators)
                if any(isinstance(s, (ast.Attribute, ast.Subscript, ast.Slice))
                       for s in sides):
                    return True
        elif isinstance(sub, ast.Call) and isinstance(sub.func, (ast.Name, ast.Attribute)):
            name = sub.func.id if isinstance(sub.func, ast.Name) else sub.func.attr
            if name in ("_is_prefix", "startswith", "endswith",
                        "reconcile", "diverged"):
                return True
    return False
