# 原子：cmd_task_update（原 plan_cli.py 第 307 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_task_update(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    sets, params = [], []
    for field in ("status", "title", "detail", "files", "req", "defect", "interfaces"):
        val = getattr(args, field, None)
        if val is not None:
            col = "req_ref" if field == "req" else ("defect_ref" if field == "defect" else field)
            val = _unescape(val) if field in ("files", "detail", "interfaces") else val
            sets.append(f"{col} = ?")
            params.append(val)
    if not sets:
        print("[task] 至少提供 --status/--title/--detail/--files/--req/--defect/--interfaces 之一")
        return 1
    params.append(args.id)
    cur.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    print(f"[task] id={args.id} 更新 {cur.rowcount} 行")
    conn.close()
    return 0
