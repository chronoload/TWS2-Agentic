# 原子：cmd_task_delete（原 plan_cli.py 第 329 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_task_delete(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    cur.execute("DELETE FROM steps WHERE task_id IN (SELECT id FROM tasks WHERE id = ?)", (args.id,))
    cur.execute("DELETE FROM tasks WHERE id = ?", (args.id,))
    conn.commit()
    print(f"[task] id={args.id} 删除 {cur.rowcount} 行（含 steps）")
    conn.close()
    return 0
