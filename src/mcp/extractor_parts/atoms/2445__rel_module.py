# 原子：_rel_module（原 interface_chain_extractor.py 第 2445 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _rel_module(file: Path, root: Path) -> str:
    """文件 → 包路径；剥离 src/lib（含中间层，兼容 monorepo packages/*/src）"""
    rel = file.relative_to(root).with_suffix("")
    parts = [p for p in rel.parts if p not in ("src", "lib")]
    return ".".join(parts)
