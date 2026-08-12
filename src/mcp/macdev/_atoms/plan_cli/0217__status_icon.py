# 原子：_status_icon（原 plan_cli.py 第 217 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _status_icon(status: str) -> str:
    return {"done": "✅", "open": "⏳", "cancelled": "⏹️"}.get(status, "·")
