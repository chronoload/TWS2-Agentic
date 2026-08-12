# 原子：cmd_delete（原 plan_cli.py 第 400 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_delete(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    cur.execute("DELETE FROM steps WHERE task_id IN (SELECT id FROM tasks WHERE plan_id = ?)", (args.id,))
    cur.execute("DELETE FROM tasks WHERE plan_id = ?", (args.id,))
    cur.execute("DELETE FROM plans WHERE id = ?", (args.id,))
    conn.commit()
    n = cur.rowcount
    conn.close()
    print(f"[delete] plan id={args.id} 删除 {n} 行（含任务/步骤）")
    return 0
