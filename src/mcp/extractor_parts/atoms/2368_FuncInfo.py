# 原子：FuncInfo（原 interface_chain_extractor.py 第 2368 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class FuncInfo:
    name: str
    file: str
    line: int
    end_line: int
    size: int          # 行数（粗略代码规模）
    is_method: bool
    class_name: str
    params: list
    is_entry: bool
