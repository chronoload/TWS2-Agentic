# 原子：CallEdge（原 interface_chain_extractor.py 第 2381 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class CallEdge:
    src_file: str
    src_func: str
    dst: str           # 调用目标表达式
    dst_kind: str      # self_method | same_module | cross_module | external | builtin | unknown
    dst_module: str    # cross_module 时解析到的包路径
    line: int
