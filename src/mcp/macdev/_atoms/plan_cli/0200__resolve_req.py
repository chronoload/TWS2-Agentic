# 原子：_resolve_req（原 plan_cli.py 第 200 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _resolve_req(req_ref: str, req_map: dict) -> str:
    """解析任务关联需求的状态展示：path:/api/x → ✅ done / ⏳ open / ❌ missing"""
    if not req_ref:
        return "—"
    status = req_map.get(req_ref)
    if status is None:
        # 兼容仅写名称（缺 kind 前缀）
        for k, s in req_map.items():
            if k.split(":", 1)[-1] == req_ref:
                status = s
                break
    if status is None:
        return f"`{req_ref}`（需求库无此条目）"
    icon = {"done": "✅", "missing": "❌", "open": "⏳"}.get(status, "·")
    return f"{icon} `{req_ref}` ({status})"
