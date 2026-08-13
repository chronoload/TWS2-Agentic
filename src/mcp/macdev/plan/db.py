"""plan.db：SQLite 存储层（plans/tasks/steps 三表，兼容 plan_cli 表结构）。
路径全部可配，macdev 不硬编码任何项目路径。
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path


class PlanStore:
    def __init__(self, db: Path | str = "plans.db",
                 index_json: Path | str = "", req_db: Path | str = "",
                 out_dir: Path | str = "") -> None:
        self.db = Path(db)
        self.index_json = Path(index_json) if index_json else None
        self.req_db = Path(req_db) if req_db else None
        # 双轨产物目录：变更自动刷新 PLAN_<id>.md/.json + plans.csv（缺省 db 同目录）
        self.out_dir = Path(out_dir) if out_dir else self.db.parent
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db))
        conn.text_factory = str
        conn.execute("""CREATE TABLE IF NOT EXISTS plans(
            id TEXT PRIMARY KEY,
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
            plan_id TEXT NOT NULL,
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
        self._migrate(conn)
        return conn

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """旧库迁移：
        1. 补列（新列在 CREATE TABLE 中已定义，旧库用 ALTER 追加）。
        2. id 机制升级（日期+计划名）：旧库 plans.id / tasks.plan_id 为 INTEGER，
           重建为 TEXT 并原样拷贝旧数据（id 转文本），否则文本 id 无法插入。
        """
        plan_cols = {r[1] for r in conn.execute("PRAGMA table_info(plans)").fetchall()}
        for col in ("arch", "stack", "global_constraints"):
            if col not in plan_cols:
                conn.execute(f"ALTER TABLE plans ADD COLUMN {col} TEXT DEFAULT ''")
        task_cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        for col in ("files", "defect_ref", "interfaces", "review_status", "review_findings"):
            if col not in task_cols:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT DEFAULT ''")

        # id 机制升级：plans.id 若为 INTEGER（旧库）→ 重建为 TEXT 并迁移数据
        plan_type = [r[2] for r in conn.execute("PRAGMA table_info(plans)").fetchall()
                     if r[1] == "id"]
        if plan_type and plan_type[0].upper() != "TEXT":
            _migrate_plan_id_text(conn)

    def load_defects(self) -> list:
        """读取 audit 产出的静态缺陷 index，归一为 {id, dim, kind, file, line, attr, detail, severity}。"""
        if not self.index_json or not Path(self.index_json).exists():
            return []
        try:
            idx = json.loads(Path(self.index_json).read_text(encoding="utf-8"))
        except Exception:
            return []
        out: list = []
        sev = {"no_assignment": "red", "missing_behavior": "red", "clear_without_set": "red",
               "stale_cache": "red", "count_only_arbitration": "red",
               "cross_namespace_key": "red", "unguarded_key_consumer": "orange",
               "external_contract": "orange", "loose_match": "yellow"}
        for b in idx.get("behavior", []) or []:
            if not (b.get("missing") or []):
                continue
            out.append({"id": f"behavior:{b.get('file','')}:{b.get('entry','')}",
                        "dim": "behavior", "kind": "missing_behavior",
                        "file": b.get("file", ""), "line": 0, "attr": b.get("entry", ""),
                        "detail": "缺失副作用: " + ", ".join(b["missing"]),
                        "severity": "red"})
        for i in idx.get("flag_lifecycle", []) or []:
            out.append({"id": f"flag:{i.get('file','')}:{i.get('line',0)}:{i.get('kind','')}",
                        "dim": "flag", "kind": i.get("kind", ""),
                        "file": i.get("file", ""), "line": i.get("line", 0),
                        "attr": i.get("attr", ""), "detail": i.get("detail", ""),
                        "severity": sev.get(i.get("kind", ""), "yellow")})
        for i in idx.get("merge_direction", []) or []:
            out.append({"id": f"merge:{i.get('file','')}:{i.get('line',0)}",
                        "dim": "merge", "kind": i.get("kind", ""),
                        "file": i.get("file", ""), "line": i.get("line", 0),
                        "attr": i.get("fn", ""), "detail": i.get("detail", ""),
                        "severity": sev.get(i.get("kind", ""), "yellow")})
        for i in (idx.get("defuse") or {}).get("issues", []) or []:
            out.append({"id": f"defuse:{i.get('file','')}:{i.get('line',0)}:{i.get('attr','')}",
                        "dim": "defuse", "kind": i.get("kind", ""),
                        "file": i.get("file", ""), "line": i.get("line", 0),
                        "attr": i.get("attr", ""), "detail": i.get("detail", ""),
                        "severity": sev.get(i.get("kind", ""), "yellow")})
        for i in idx.get("id_source", []) or []:
            out.append({"id": f"id_source:{i.get('file','')}:{i.get('line',0)}:{i.get('kind','')}",
                        "dim": "id_source", "kind": i.get("kind", ""),
                        "file": i.get("file", ""), "line": i.get("line", 0),
                        "attr": i.get("consumer", ""), "detail": i.get("detail", ""),
                        "severity": sev.get(i.get("kind", ""), "yellow")})
        return out

    def req_status_map(self) -> dict:
        """从 requirements.db 构建 {kind:name: status} 查询映射（缺失则返回空）"""
        if not self.req_db or not Path(self.req_db).exists():
            return {}
        try:
            conn = sqlite3.connect(str(self.req_db))
            rows = conn.execute("SELECT kind, name, status FROM requirements").fetchall()
            conn.close()
            return {f"{k}:{n}": s for k, n, s in rows}
        except Exception:
            return {}


def _migrate_plan_id_text(conn: sqlite3.Connection) -> None:
    """把 plans.id / tasks.plan_id 从 INTEGER 迁移为 TEXT（保留旧数据）。"""
    conn.execute("ALTER TABLE plans RENAME TO plans_legacy")
    conn.execute("""CREATE TABLE plans(
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        goal TEXT DEFAULT '',
        arch TEXT DEFAULT '',
        stack TEXT DEFAULT '',
        global_constraints TEXT DEFAULT '',
        status TEXT DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    cols = ["title", "goal", "arch", "stack", "global_constraints", "status", "created_at"]
    conn.execute(
        "INSERT INTO plans(id, title, goal, arch, stack, global_constraints, status, created_at) "
        f"SELECT CAST(id AS TEXT), {','.join(cols)} FROM plans_legacy")
    conn.execute("DROP TABLE plans_legacy")

    conn.execute("ALTER TABLE tasks RENAME TO tasks_legacy")
    conn.execute("""CREATE TABLE tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id TEXT NOT NULL,
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
    task_cols = ["title", "detail", "files", "req_ref", "defect_ref", "interfaces",
                 "status", "review_status", "review_findings", "created_at"]
    conn.execute(
        "INSERT INTO tasks(id, plan_id, title, detail, files, req_ref, defect_ref, "
        "interfaces, status, review_status, review_findings, created_at) "
        f"SELECT id, CAST(plan_id AS TEXT), {','.join(task_cols)} FROM tasks_legacy")
    conn.execute("DROP TABLE tasks_legacy")
    conn.commit()
