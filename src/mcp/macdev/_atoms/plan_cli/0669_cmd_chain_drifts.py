# 原子：cmd_chain_drifts（原 plan_cli.py 第 669 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_chain_drifts(args) -> int:
    conn = _chain_connect(args.db)
    if conn is None:
        return 1
    try:
        rows = conn.execute("SELECT kind, client, endpoint, detail FROM drifts ORDER BY kind").fetchall()
        if not rows:
            print("[chain] 无漂移记录")
            return 0
        for kind, client, endpoint, detail in rows:
            print(f"  [{kind}] {client} → {endpoint}")
            if detail:
                print(f"      {detail[:180]}")
        print(f"\n[chain] 共 {len(rows)} 条漂移")
    finally:
        conn.close()
    return 0
