# 原子：_normalize_path（原 interface_chain_extractor.py 第 1070 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _normalize_path(p: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", p)
