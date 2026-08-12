# 原子：_resolve_defect（原 plan_cli.py 第 1337 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _resolve_defect(defect_ref: str, defect_map: dict) -> str:
    """展示任务绑定缺陷的状态：缺陷仍在 index.json → 🔴 未修复；已消失 → ✅ 已修复"""
    if not defect_ref:
        return "—"
    d = defect_map.get(defect_ref)
    if d is None:
        return f"✅ `{defect_ref}`（静态报告中已消失）"
    icon = {"red": "🔴", "orange": "🟠", "yellow": "🟡"}[d["severity"]]
    return f"{icon} `{defect_ref}`"
