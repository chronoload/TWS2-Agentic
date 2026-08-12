# 原子：_openspec_change_root（原 plan_cli.py 第 737 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _openspec_change_root(change: str, cwd: str = "") -> str:
    """从 `openspec status --json` 提取 changeRoot。"""
    code, out = _run_openspec("status", "--change", change, "--json", cwd=cwd)
    if code != 0:
        return ""
    return _parse_openspec_json(out).get("changeRoot", "")
