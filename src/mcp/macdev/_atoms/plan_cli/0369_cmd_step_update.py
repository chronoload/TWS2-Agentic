# 原子：cmd_step_update（原 plan_cli.py 第 369 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_step_update(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    sets, params = [], []
    for field in ("status", "text", "action", "code", "lang", "run", "expected"):
        val = getattr(args, field, None)
        if val is not None:
            val = _unescape(val) if field == "code" else val
            sets.append(f"{field} = ?")
            params.append(val)
    if not sets:
        print("[step] 至少提供 --status/--text/--action/--code/--lang/--run/--expected 之一")
        return 1
    params.append(args.id)
    cur.execute(f"UPDATE steps SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    print(f"[step] id={args.id} 更新 {cur.rowcount} 行")
    conn.close()
    return 0
