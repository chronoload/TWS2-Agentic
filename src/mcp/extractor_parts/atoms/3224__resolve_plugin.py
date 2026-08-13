# 原子：_resolve_plugin（原 interface_chain_extractor.py 第 3224 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _resolve_plugin(spec: str) -> tuple[str, str, Path] | None:
    """解析 --plugin lang:path 为 (lang, 执行器, 脚本)；裸路径视为可执行文件（rust 二进制等）。"""
    import shutil
    lang, p = (spec.split(":", 1) if ":" in spec else ("", spec))
    path = Path(p)
    if not path.exists():
        print(f"[plugin] 路径不存在: {p}")
        return None
    if lang == "node":
        if not shutil.which("node"):
            print(f"[plugin] 未找到 node，跳过 {p}")
            return None
        return "node", "node", path
    if lang in ("python", "py"):
        return "python", sys.executable, path
    # 其他 lang / 裸路径：直接执行（rust 二进制等可执行文件）
    return lang, "", path
