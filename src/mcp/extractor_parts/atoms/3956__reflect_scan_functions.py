# 原子：_reflect_scan_functions（原 interface_chain_extractor.py 第 3956 行）
# 逻辑组：doc_reflect · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _reflect_scan_functions() -> list:
    """反射暴露模块所有顶层函数的签名/行数/说明，用于 --doc 自举文档（全量，不白名单）。"""
    import inspect as _inspect
    module = sys.modules[__name__]
    results = []
    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue  # 内部辅助/_reflect_* 工具不列
        if not _inspect.isfunction(obj) or getattr(obj, "__module__", None) != __name__:
            continue  # 仅本模块 def，import 进来的不列
        try:
            sig = _inspect.signature(obj)
            src = _inspect.getsource(obj)
            results.append({
                "name": name,
                "signature": str(sig),
                "doc": (obj.__doc__ or "").strip(),
                "lines": len(src.splitlines()),
            })
        except Exception:
            continue
    results.sort(key=lambda r: r["name"])
    return results
