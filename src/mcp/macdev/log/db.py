"""logs.db：log 插件 SQLite 存储层（经验沉淀）。

经验分双轨：
- scope=project（随项目，最主要）：写入 <name>-project/logs.db，条目归属当前项目
- scope=pkg（随包）：写入随包经验库（macdev-skill/logs.db），通用方法论随 skill 分发

路径全部可配，macdev 不硬编码任何项目路径（与 plan 一致）。
表 logs：id/category/title/body/tags/refs/scope/created_at。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# 允许的分类（经验沉淀的类型）
CATEGORIES = ("lessons", "pitfalls", "patterns", "decisions")

CATEGORY_LABELS = {
    "lessons": "经验教训",
    "pitfalls": "陷阱",
    "patterns": "模式",
    "decisions": "决策",
}

# 经验归属：随项目（默认，最主要） / 随包（通用方法论随 skill 分发）
SCOPES = ("project", "pkg")
SCOPE_LABELS = {"project": "随项目", "pkg": "随包"}


class LogStore:
    def __init__(self, db: Path | str = "logs.db") -> None:
        self.db = Path(db)
        self.db.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db))
        conn.text_factory = str
        conn.row_factory = sqlite3.Row  # 按列名取值：旧库 ALTER 补列会改变列序，位置索引不可靠
        conn.execute("""CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            refs TEXT DEFAULT '',
            scope TEXT DEFAULT 'project',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )""")
        self._migrate(conn)
        return conn

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """旧库迁移：补 scope 列（旧条目归属随包库时由调用方/命令按库定位标注）。"""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(logs)").fetchall()}
        if "scope" not in cols:
            conn.execute("ALTER TABLE logs ADD COLUMN scope TEXT DEFAULT 'project'")
            conn.commit()

    def add(self, category: str, title: str, body: str = "",
            tags: str = "", refs: str = "", scope: str = "project") -> int:
        conn = self.connect()
        cur = conn.execute(
            "INSERT INTO logs(category, title, body, tags, refs, scope) VALUES (?,?,?,?,?,?)",
            (category, title, body, tags, refs, scope))
        conn.commit()
        lid = cur.lastrowid
        conn.close()
        return lid

    def update(self, lid: int, **fields) -> bool:
        allowed = {"category", "title", "body", "tags", "refs", "scope"}
        sets, params = [], []
        for k, v in fields.items():
            if v is not None and k in allowed:
                sets.append(f"{k}=?")
                params.append(v)
        if not sets:
            return False
        conn = self.connect()
        cur = conn.execute(f"UPDATE logs SET {','.join(sets)} WHERE id=?", params + [lid])
        conn.commit()
        ok = cur.rowcount > 0
        conn.close()
        return ok

    def delete(self, lid: int) -> bool:
        conn = self.connect()
        cur = conn.execute("DELETE FROM logs WHERE id=?", (lid,))
        conn.commit()
        ok = cur.rowcount > 0
        conn.close()
        return ok

    def get(self, lid: int) -> dict | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM logs WHERE id=?", (lid,)).fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_dict(row)

    def list(self, category: str = "", tag: str = "", scope: str = "") -> list:
        q = "SELECT * FROM logs"
        params = []
        conds = []
        if category:
            conds.append("category=?")
            params.append(category)
        if tag:
            conds.append("tags LIKE ?")
            params.append(f"%{tag}%")
        if scope:
            conds.append("scope=?")
            params.append(scope)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id DESC"
        conn = self.connect()
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def query(self, keyword: str, category: str = "", scope: str = "") -> list:
        """全文模糊查询 title/body/tags/refs。"""
        q = ("SELECT * FROM logs WHERE (title LIKE ? OR body LIKE ? "
             "OR tags LIKE ? OR refs LIKE ?)")
        params = [f"%{keyword}%"] * 4
        if category:
            q += " AND category=?"
            params.append(category)
        if scope:
            q += " AND scope=?"
            params.append(scope)
        q += " ORDER BY id DESC"
        conn = self.connect()
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {k: row[k] for k in (
            "id", "category", "title", "body", "tags", "refs", "scope", "created_at")}

    def export_md(self, out: Path, scope: str = "") -> str:
        """导出 LOGS.md（按 scope 分组、按分类分组的人类可读文档），返回写出的路径。"""
        entries = self.list(scope=scope)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        scopes = [scope] if scope else list(SCOPES)
        lines = [
            "# macdev LOG — 经验沉淀库",
            "",
            f"> 由 `python -m macdev log` 生成；机器可查入口：`logs.db`（表 logs）。",
            f"> 共 {len(entries)} 条。",
            "",
        ]
        for sc in scopes:
            sc_entries = [e for e in entries if e["scope"] == sc]
            if not sc_entries:
                continue
            lines.append(f"## {SCOPE_LABELS.get(sc, sc)}经验（{sc}）— {len(sc_entries)} 条")
            lines.append("")
            for cat in CATEGORIES:
                group = [e for e in sc_entries if e["category"] == cat]
                if not group:
                    continue
                lines.append(f"### {CATEGORY_LABELS.get(cat, cat)}（{cat}）— {len(group)} 条")
                lines.append("")
                for e in group:
                    lines.append(f"#### [{e['id']}] {e['title']}")
                    lines.append("")
                    lines.append(f"- 分类: {cat} ｜ 标签: {e['tags'] or '—'} ｜ 时间: {e['created_at']}")
                    if e["refs"]:
                        lines.append(f"- 引用: {e['refs']}")
                    lines.append("")
                    if e["body"]:
                        lines.append(e["body"])
                        lines.append("")
                lines.append("")
        out.write_text("\n".join(lines), encoding="utf-8")
        return str(out)
