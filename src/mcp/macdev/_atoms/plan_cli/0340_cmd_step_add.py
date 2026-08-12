# 原子：cmd_step_add（原 plan_cli.py 第 340 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_step_add(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    last = cur.execute("SELECT MAX(ord) FROM steps WHERE task_id = ?", (args.task,)).fetchone()[0]
    cur.execute("""INSERT INTO steps(task_id, ord, text, action, code, lang, run, expected, status)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (args.task, (last or 0) + 1, args.text, args.action, _unescape(args.code) or "",
                 args.lang or "", args.run or "", args.expected or "", "open"))
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    print(f"[step] id={sid} task={args.task} action={args.action} text={args.text}")
    return 0
