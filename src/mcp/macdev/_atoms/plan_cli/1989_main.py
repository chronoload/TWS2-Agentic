# 原子：main（原 plan_cli.py 第 1989 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def main():
    ap = _build_parser()
    args = ap.parse_args()
    rc = _dispatch(args)
    _auto_refresh_docs()
    return rc
