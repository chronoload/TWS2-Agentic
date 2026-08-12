# 原子：load_task（原 interface_chain_extractor.py 第 48 行）
# 逻辑组：cli · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def load_task(path) -> dict:
    """加载外置任务配置 JSON（特化参数单一事实源）。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"任务配置文件不存在: {p}")
    return json.loads(p.read_text(encoding="utf-8"))
