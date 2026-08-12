# 原子：_migrate（原 plan_cli.py 第 90 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _migrate(conn: sqlite3.Connection) -> None:
    """旧库补列（新列在 CREATE TABLE 中已定义，旧库用 ALTER 追加）。"""
    plan_cols = {r[1] for r in conn.execute("PRAGMA table_info(plans)").fetchall()}
    for col in ("arch", "stack", "global_constraints"):
        if col not in plan_cols:
            conn.execute(f"ALTER TABLE plans ADD COLUMN {col} TEXT DEFAULT ''")
    task_cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "files" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN files TEXT DEFAULT ''")
    if "defect_ref" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN defect_ref TEXT DEFAULT ''")
    if "interfaces" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN interfaces TEXT DEFAULT ''")
    if "review_status" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN review_status TEXT DEFAULT 'pending'")
    if "review_findings" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN review_findings TEXT DEFAULT ''")
