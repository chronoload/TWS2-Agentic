# 原子：HardcodedItem（原 interface_chain_extractor.py 第 253 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class HardcodedItem:
    file: str
    line: int
    kind: str       # url | port | path | key | secret | token | password | db_host | db_port | other
    value: str
    context: str = ""
