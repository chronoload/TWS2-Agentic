# 原子：DataclassDef（原 interface_chain_extractor.py 第 143 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class DataclassDef:
    name: str
    file: str
    line: int
    kind: str  # dataclass | enum
    fields: list[ModelField] = field(default_factory=list)
