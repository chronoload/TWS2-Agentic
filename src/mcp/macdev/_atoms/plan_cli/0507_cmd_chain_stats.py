# 原子：cmd_chain_stats（原 plan_cli.py 第 507 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_chain_stats(args) -> int:
    conn = _chain_connect(args.db)
    if conn is None:
        return 1
    try:
        rows = conn.execute("SELECT key, value FROM stats").fetchall()
        if not rows:
            print("[chain] stats 为空")
            return 0
        for k, v in rows:
            print(f"  {k} = {v}")
        _chain_product_hint()
    finally:
        conn.close()
    return 0
