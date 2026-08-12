# 原子：_task_dir_files（原 interface_chain_extractor.py 第 79 行）
# 逻辑组：cli · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _task_dir_files(dirs: list, names: set) -> list:
    """任务扫描目录中按目录名取 *.py（排除 __init__）。"""
    out = []
    for d in dirs:
        if d.name in names and d.is_dir():
            out += [f for f in sorted(d.glob("*.py")) if f.name != "__init__.py"]
    return out
