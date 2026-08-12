# 原子：cmd_step_delete（原 plan_cli.py 第 390 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_step_delete(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    cur.execute("DELETE FROM steps WHERE id = ?", (args.id,))
    conn.commit()
    print(f"[step] id={args.id} 删除 {cur.rowcount} 行")
    conn.close()
    return 0
