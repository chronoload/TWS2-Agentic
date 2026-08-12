# 原子：IdSourceIssue（原 interface_chain_extractor.py 第 1757 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class IdSourceIssue:
    kind: str        # cross_namespace_key | unguarded_key_consumer
    consumer: str    # 消费者函数名
    key_arg: str     # 违规实参 / key 形参名
    file: str
    line: int
    detail: str
