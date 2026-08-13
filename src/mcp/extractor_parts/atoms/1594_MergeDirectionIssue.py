# 原子：MergeDirectionIssue（原 interface_chain_extractor.py 第 1594 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class MergeDirectionIssue:
    kind: str          # count_only_arbitration | arbiter_without_source
    fn: str
    file: str
    line: int
    detail: str
