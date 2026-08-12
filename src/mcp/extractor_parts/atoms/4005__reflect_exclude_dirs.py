# 原子：_reflect_exclude_dirs（原 interface_chain_extractor.py 第 4005 行）
# 逻辑组：doc_reflect · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _reflect_exclude_dirs() -> list:
    """反射提取默认排除目录列表。"""
    import inspect as _inspect
    module = sys.modules[__name__]
    return list(getattr(module, "_SCAN_DEFAULT_EXCLUDE", ()))
