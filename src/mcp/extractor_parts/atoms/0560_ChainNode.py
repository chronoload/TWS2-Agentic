# 原子：ChainNode（原 interface_chain_extractor.py 第 560 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class ChainNode:
    name: str                      # 调用目标（函数名 / 类.方法）
    kind: str                      # helper | class_method | module | builtin | unknown
    file: str = ""
    line: int = 0
    detail: str = ""
    children: list = field(default_factory=list)
