# 原子：cmd_list（原 plan_cli.py 第 240 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_list(args) -> int:
    conn = _connect(args.db)
    rows = conn.execute(
        "SELECT p.id, p.title, p.status, COUNT(t.id) FROM plans p "
        "LEFT JOIN tasks t ON t.plan_id = p.id GROUP BY p.id ORDER BY p.id").fetchall()
    conn.close()
    if not rows:
        print("[list] (empty)")
        return 0
    for r in rows:
        print(f"id={r[0]} [{r[2]}] 任务={r[3]}  {r[1]}")
    return 0
