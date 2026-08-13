# 原子：_reflect_dataclass_fields（原 interface_chain_extractor.py 第 3939 行）
# 逻辑组：doc_reflect · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _reflect_dataclass_fields(cls) -> list:
    """反射提取 dataclass 字段名与默认值，用于 --doc 自举文档。"""
    import dataclasses as _dc
    fields = []
    try:
        for f in _dc.fields(cls):
            default = "REQUIRED"
            if f.default is not _dc.MISSING:
                default = repr(f.default)
            elif f.default_factory is not _dc.MISSING:
                default = f"<factory: {f.default_factory.__name__}>"
            fields.append((f.name, str(f.type), default))
    except Exception:
        pass
    return fields
