# 原子：cmd_create（原 plan_cli.py 第 228 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_create(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    cur.execute("INSERT INTO plans(title, goal, arch, stack, global_constraints, status) VALUES (?,?,?,?,?,?)",
                (args.title, args.goal, args.arch, args.stack, _unescape(args.global_constraints) or "", "open"))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    print(f"[create] plan id={pid} title={args.title}")
    return 0
