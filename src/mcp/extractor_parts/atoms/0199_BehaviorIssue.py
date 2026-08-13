# 原子：BehaviorIssue（原 interface_chain_extractor.py 第 199 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class BehaviorIssue:
    entry: str          # 入口函数名
    missing: list       # 未在正常完成路径上触发的 must-call 目标
    file: str
    detail: str
