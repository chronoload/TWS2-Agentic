# 原子：cmd_step_list（原 plan_cli.py 第 355 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_step_list(args) -> int:
    conn = _connect(args.db)
    rows = conn.execute(
        "SELECT id, ord, text, action, run, expected, status FROM steps WHERE task_id = ? ORDER BY ord",
        (args.task,)).fetchall()
    conn.close()
    if not rows:
        print("[step] (empty)")
        return 0
    for r in rows:
        print(f"id={r[0]} [#{r[1]}] [{r[6]}] ({r[3]}) {r[2]}  — run: {r[4] or '—'}, expected: {r[5] or '—'}")
    return 0
