# 原子：cmd_update（原 plan_cli.py 第 254 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_update(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    sets, params = [], []
    for field in ("status", "title", "goal", "arch", "stack", "global_constraints"):
        val = getattr(args, field, None)
        if val is not None:
            val = _unescape(val) if field == "global_constraints" else val
            sets.append(f"{field} = ?")
            params.append(val)
    if not sets:
        print("[update] 至少提供 --status/--title/--goal/--arch/--stack/--global-constraints")
        return 1
    params.append(args.id)
    cur.execute(f"UPDATE plans SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    print(f"[update] plan id={args.id} 更新 {cur.rowcount} 行")
    conn.close()
    return 0
