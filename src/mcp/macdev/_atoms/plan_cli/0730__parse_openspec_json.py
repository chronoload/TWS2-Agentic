# 原子：_parse_openspec_json（原 plan_cli.py 第 730 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _parse_openspec_json(out: str) -> dict:
    try:
        return json.loads(out)
    except Exception:
        return {}
