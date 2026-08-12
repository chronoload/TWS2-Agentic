# 原子：_reflect_data_pool_kinds（原 interface_chain_extractor.py 第 3997 行）
# 逻辑组：doc_reflect · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _reflect_data_pool_kinds() -> list:
    """反射提取数据池 kind 映射表。"""
    import inspect as _inspect
    module = sys.modules[__name__]
    kinds = getattr(module, "_DATA_POOL_KINDS", {})
    return [(k, v.pattern if isinstance(v, re.Pattern) else str(v)) for k, v in kinds.items()]
