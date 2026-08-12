# 原子：_reflect_constants（原 plan_cli.py 第 1756 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _reflect_constants() -> list:
    """反射提取模块级常量（PLANS_DB/REQ_DB/DOCS_DIR 等）。"""
    import inspect as _inspect
    module = sys.modules[__name__]
    consts = []
    for name, val in sorted(module.__dict__.items()):
        if name.isupper() and not name.startswith('_') and isinstance(val, (str, Path, int, float)):
            consts.append((name, repr(val)))
    return consts
