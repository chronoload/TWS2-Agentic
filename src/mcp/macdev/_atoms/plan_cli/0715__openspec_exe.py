# 原子：_openspec_exe（原 plan_cli.py 第 715 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _openspec_exe() -> str:
    """定位 openspec CLI（优先 PATH，找不到时用裸名让 subprocess 报错）。"""
    return shutil.which("openspec") or "openspec"
