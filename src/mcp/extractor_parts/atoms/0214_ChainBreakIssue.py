# 原子：ChainBreakIssue（原 interface_chain_extractor.py 第 214 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class ChainBreakIssue:
    entry: str          # 入口函数名
    fallback: str       # 被检测到的兜底源调用（如 _build_messages_from_checkpoints）
    file: str
    line: int
    detail: str
