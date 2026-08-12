# 原子：_falsy_literal_text（原 interface_chain_extractor.py 第 1115 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _falsy_literal_text(s: str) -> bool:
    """判断默认值源码文本是否为假值常量（False/None/0/''/[]/{} 等）"""
    s = s.strip()
    if s in ("False", "None", "0", "0.0", "''", '""', "[]", "{}", "()"):
        return True
    try:
        v = ast.literal_eval(s)
        return v is None or v is False or v == 0 or v == 0.0 or v == ""
    except Exception:
        return False
