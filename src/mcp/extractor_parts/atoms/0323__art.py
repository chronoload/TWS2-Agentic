# 原子：_art（原 interface_chain_extractor.py 第 323 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _art(out_dir: Path, name: str) -> Path:
    """产物输出路径：name 必须登记在 EXTRACTOR_ARTIFACTS（自文档反射守卫）。"""
    if name not in ART_NAMES:
        raise KeyError(f"产物 '{name}' 未登记在 EXTRACTOR_ARTIFACTS，请补登记（否则 --doc 清单缺失）")
    return out_dir / name
