# 原子：cmd_task_list（原 plan_cli.py 第 289 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_task_list(args) -> int:
    conn = _connect(args.db)
    rows = conn.execute(
        "SELECT id, title, detail, files, req_ref, defect_ref, interfaces, status, review_status FROM tasks WHERE plan_id = ? ORDER BY id",
        (args.plan,)).fetchall()
    conn.close()
    if not rows:
        print("[task] (empty)")
        return 0
    for r in rows:
        extra = f"  (defect: {r[5]})" if r[5] else ""
        ifr = f"  (interfaces: {r[6][:60]})" if r[6] else ""
        rev = {"approved": "review✅", "review_requested": "review🔄",
               "needs_fix": "review❌", "pending": "review-"}.get(r[8], r[8])
        print(f"id={r[0]} [{r[7]}] {r[1]}  — {r[2][:60]}  (files: {r[3] or '—'}, req: {r[4] or '—'}, {rev}){extra}{ifr}")
    return 0
