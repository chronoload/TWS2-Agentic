# 原子：cmd_task_add（原 plan_cli.py 第 275 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_task_add(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    cur.execute("INSERT INTO tasks(plan_id, title, detail, files, req_ref, defect_ref, interfaces, status) VALUES (?,?,?,?,?,?,?,?)",
                (args.plan, args.title, args.detail, _unescape(args.files) or "",
                 args.req or "", args.defect or "", _unescape(args.interfaces) or "", "open"))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    print(f"[task] id={tid} plan={args.plan} title={args.title}"
          + (f" defect={args.defect}" if args.defect else ""))
    return 0
