# 原子：_resolve_ts_module（原 interface_chain_extractor.py 第 2514 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _resolve_ts_module(mod_str: str, file_path: Path, root: Path) -> str:
    """相对 import 路径 → 模块路径；第三方包/绝对路径返回 ''"""
    if not mod_str.startswith("."):
        return ""
    base = file_path.parent
    p = Path(mod_str)
    parts = list(p.parts)
    # 去掉 ./ 与 ../ 前缀段
    while parts and parts[0] in ("..", "."):
        parts.pop(0)
    cand = base.joinpath(*parts).with_suffix("")
    if not cand.is_dir() and not cand.with_suffix(".ts").exists() \
            and not cand.with_suffix(".tsx").exists() and not cand.with_suffix(".js").exists():
        return ""
    try:
        rel = cand.relative_to(root)
    except ValueError:
        return ""
    parts2 = [x for x in rel.parts if x not in ("src", "lib")]
    return ".".join(parts2)
