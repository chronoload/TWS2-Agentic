# 原子：_key_arg_expr（原 interface_chain_extractor.py 第 1775 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _key_arg_expr(call):
    """取消费者的 key 实参：第一位置参数，或命名的 key/id/checkpoint_id 关键字"""
    if call.args:
        return call.args[0]
    for kw in call.keywords:
        if kw.arg in ("key", "id", "session_id", "checkpoint_id", "checkpoint", "conversation_id"):
            return kw.value
    return None
