# 原子：_connect（原 plan_cli.py 第 47 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _connect(db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS plans(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        goal TEXT DEFAULT '',
        arch TEXT DEFAULT '',
        stack TEXT DEFAULT '',
        global_constraints TEXT DEFAULT '',
        status TEXT DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id INT NOT NULL,
        title TEXT NOT NULL,
        detail TEXT DEFAULT '',
        files TEXT DEFAULT '',
        req_ref TEXT DEFAULT '',
        defect_ref TEXT DEFAULT '',
        interfaces TEXT DEFAULT '',
        status TEXT DEFAULT 'open',
        review_status TEXT DEFAULT 'pending',
        review_findings TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS steps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INT NOT NULL,
        ord INT DEFAULT 0,
        text TEXT DEFAULT '',
        action TEXT DEFAULT 'other',
        code TEXT DEFAULT '',
        lang TEXT DEFAULT '',
        run TEXT DEFAULT '',
        expected TEXT DEFAULT '',
        status TEXT DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    _migrate(conn)
    return conn
