"""requirement.db：需求 SQLite 存储层 + 双轨产物同步。

约定（语言环境无关、人类/机器双轨）：
- 机器权威：requirements.db（主库，requirements 表）
- 机器快照：requirements.json / requirements.csv（每次变更自动刷新）
- 人类可读：REQUIREMENTS.md（每次变更自动刷新）
- 对齐产物：REQUIREMENT_ALIGNMENT.md + requirement_alignment.json/csv/db
时间戳统一 UTC（datetime('now')），编码统一 utf-8，不依赖宿主时区/locale。
"""
from __future__ import annotations
import csv
import json
import sqlite3
from pathlib import Path

VALID_KINDS = ("interface", "path", "file", "spec")
VALID_STATUS = ("open", "done", "missing")


class RequirementStore:
    def __init__(self, db: Path | str = "requirements.db",
                 out_dir: Path | str = "", index_json: Path | str = "") -> None:
        self.db = Path(db)
        self.out_dir = Path(out_dir) if out_dir else self.db.parent
        self.index_json = Path(index_json) if index_json else ""
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db))
        conn.text_factory = str
        conn.execute("""CREATE TABLE IF NOT EXISTS requirements(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            detail TEXT DEFAULT '',
            source TEXT DEFAULT 'cli',
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        return conn

    # ─── CRUD（变更后自动 refresh 双轨产物）───

    def add(self, kind: str, name: str, detail: str = "", source: str = "cli") -> int:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO requirements(kind, name, detail, source, status) VALUES (?,?,?,?,?)",
            (kind, name, detail, source, "open"))
        conn.commit()
        rid = cur.lastrowid
        conn.close()
        self.refresh()
        return rid

    def list(self, kind: str = "", status: str = "") -> list:
        conn = self.connect()
        sql = "SELECT id, kind, name, detail, source, status, created_at FROM requirements"
        conds, params = [], []
        if kind:
            conds.append("kind = ?")
            params.append(kind)
        if status:
            conds.append("status = ?")
            params.append(status)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
        conn.close()
        return rows

    def update(self, rid: int, **fields) -> int:
        sets, params = [], []
        for k in ("kind", "name", "detail", "source", "status"):
            if k in fields and fields[k] is not None:
                sets.append(f"{k} = ?")
                params.append(fields[k])
        if not sets:
            return 0
        params.append(rid)
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(f"UPDATE requirements SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        n = cur.rowcount
        conn.close()
        if n:
            self.refresh()
        return n

    def delete(self, rid: int) -> int:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM requirements WHERE id = ?", (rid,))
        conn.commit()
        n = cur.rowcount
        conn.close()
        if n:
            self.refresh()
        return n

    def all_items(self) -> list:
        """DB 行 → 对齐器输入结构（带 req_id/status）。"""
        return [{"kind": r[1], "name": r[2], "detail": r[3], "source": r[4],
                 "line": 0, "req_id": r[0], "status": r[5]} for r in self.list()]

    # ─── 双轨同步（db 权威 → json/csv/md 统一刷新）───

    def refresh(self) -> list:
        """主库 requirements.db → requirements.json / requirements.csv / REQUIREMENTS.md。"""
        rows = self.list()
        artifacts = [self._write_json(rows), self._write_csv(rows), self._write_md(rows)]
        return artifacts

    def _write_json(self, rows: list) -> Path:
        target = self.out_dir / "requirements.json"
        data = [{"id": r[0], "kind": r[1], "name": r[2], "detail": r[3],
                 "source": r[4], "status": r[5], "created_at": r[6]} for r in rows]
        target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return target

    def _write_csv(self, rows: list) -> Path:
        target = self.out_dir / "requirements.csv"
        with open(target, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "kind", "name", "detail", "source", "status", "created_at"])
            for r in rows:
                w.writerow(list(r))
        return target

    def _write_md(self, rows: list) -> Path:
        target = self.out_dir / "REQUIREMENTS.md"
        lines = ["# 需求清单（结构化，由 `macdev requirement` 维护）\n",
                 f"> 数据源: `{self.db}` · 共 {len(rows)} 条 · 本文件自动同步，勿手改\n"]
        by_status = {}
        for r in rows:
            by_status.setdefault(r[5], []).append(r)
        for st in VALID_STATUS:
            if st not in by_status:
                continue
            lines.append(f"\n## {st} ({len(by_status[st])})\n")
            lines.append("| id | 类型 | 名称 | 状态 | 来源 | 说明 |")
            lines.append("|----|------|------|------|------|------|")
            for r in by_status[st]:
                detail_txt = r[3][:100].replace("|", "\\|")
                lines.append(f"| {r[0]} | {r[1]} | `{r[2]}` | {r[5]} | {r[4]} | {detail_txt} |")
        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    # ─── 对齐产物落盘（md + json + csv + db 四件套）───

    def write_alignment(self, res: dict, req_dirs: list) -> list:
        from . import align
        artifacts = []
        md = self.out_dir / "REQUIREMENT_ALIGNMENT.md"
        md.write_text(align.gen_markdown(res, req_dirs, {}), encoding="utf-8")
        artifacts.append(md)

        json_p = self.out_dir / "requirement_alignment.json"
        json_p.write_text(json.dumps({"scanned_dirs": [str(d) for d in req_dirs],
                                      "items": res["alignment"],
                                      "missing_paths": res["missing_paths"],
                                      "prefix_matches": res["prefix_matches"],
                                      "extra_paths": res["extra_paths"]},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        artifacts.append(json_p)

        csv_p = self.out_dir / "requirement_alignment.csv"
        with open(csv_p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["source", "line", "kind", "name", "found", "found_in", "detail"])
            for a in res["alignment"]:
                w.writerow([a["source"], a["line"], a["kind"], a["name"],
                            int(a["found"]), a.get("found_in", ""), a["detail"]])
        artifacts.append(csv_p)

        db = self.out_dir / "requirement_alignment.db"
        conn = sqlite3.connect(str(db))
        try:
            c = conn.cursor()
            c.execute("DROP TABLE IF EXISTS requirements")
            c.execute("""CREATE TABLE requirements(
                source TEXT, line INT, kind TEXT, name TEXT,
                found INT, found_in TEXT, detail TEXT)""")
            c.executemany("INSERT INTO requirements VALUES (?,?,?,?,?,?,?)",
                          [(a["source"], a["line"], a["kind"], a["name"],
                            int(a["found"]), a.get("found_in", ""), a["detail"])
                           for a in res["alignment"]])
            c.execute("DROP TABLE IF EXISTS path_alignment")
            c.execute("CREATE TABLE path_alignment(status TEXT, path TEXT)")
            actual = set(res["actual_paths"])
            c.executemany("INSERT INTO path_alignment VALUES (?,?)",
                          [("missing", p) for p in res["missing_paths"]] +
                          [("prefix", p) for p in res["prefix_matches"]] +
                          [("extra", p) for p in res["extra_paths"]] +
                          [("matched", p) for p in res["declared_paths"] if p in actual])
            conn.commit()
        finally:
            conn.close()
        artifacts.append(db)
        return artifacts
