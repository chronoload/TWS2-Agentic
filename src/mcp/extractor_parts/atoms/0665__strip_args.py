# 原子：_strip_args（原 interface_chain_extractor.py 第 665 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _strip_args(s: str, limit: int = 60) -> str:
    return s if len(s) <= limit else s[:limit] + "..."
