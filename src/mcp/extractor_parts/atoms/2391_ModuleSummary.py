# 原子：ModuleSummary（原 interface_chain_extractor.py 第 2391 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class ModuleSummary:
    file: str
    module: str        # 包路径（kimi_cli.soul.agent）
    classes: int
    funcs: int
    lines: int
    entry_points: list
    out_degree: int    # 调用其它模块函数次数
    in_degree: int
