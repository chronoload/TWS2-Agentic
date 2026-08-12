#!/usr/bin/env python3
"""需求文档结构化 CLI — Agent 通过 API 写需求，不再用 WriteFile 手写 md。

设计：
  - 需求以结构化条目存 SQLite（mcp/data/requirements.db），文档由数据渲染。
  - Agent / 用户通过本 CLI 增删改查需求（interface / path / file 三类）。
  - align 子命令复用 requirement_align 的代码/端点对齐逻辑，输出对齐报告。

用法：
  python mcp/requirement_cli.py add   --kind interface --name createX --detail "签名说明"
  python mcp/requirement_cli.py add   --kind path --name /api/agent/chat/stream --detail "流式聊天"
  python mcp/requirement_cli.py list  [--kind interface] [--status open|done|missing]
  python mcp/requirement_cli.py update --id 3 --status done [--name ...] [--detail ...]
  python mcp/requirement_cli.py delete --id 3
  python mcp/requirement_cli.py export --format md|json|csv
  python mcp/requirement_cli.py align [--index mcp/docs/interface_chain_index.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = MCP_ROOT.parent
DB_PATH = MCP_ROOT / "data" / "requirements.db"
DOCS_DIR = MCP_ROOT / "docs"

VALID_KINDS = ("interface", "path", "file", "spec")
VALID_STATUS = ("open", "done", "missing")


def _connect(db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS requirements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        detail TEXT DEFAULT '',
        source TEXT DEFAULT 'cli',
        status TEXT DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    return conn


def _parse_extra(extra: list) -> dict:
    out = {}
    for pair in extra or []:
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k] = v
    return out


def cmd_add(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO requirements(kind, name, detail, source, status) VALUES (?,?,?,?,?)",
        (args.kind, args.name, args.detail, args.source, "open"))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    print(f"[add] id={rid} kind={args.kind} name={args.name}")
    return 0


def cmd_list(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    sql = "SELECT id, kind, name, detail, source, status, created_at FROM requirements"
    conds, params = [], []
    if args.kind:
        conds.append("kind = ?")
        params.append(args.kind)
    if args.status:
        conds.append("status = ?")
        params.append(args.status)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id"
    rows = cur.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        print("[list] (empty)")
        return 0
    print(f"{'id':<4} {'kind':<10} {'status':<8} name / detail")
    for r in rows:
        print(f"{r[0]:<4} {r[1]:<10} {r[5]:<8} {r[2]}  — {r[3][:80]}")
    return 0


def cmd_update(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    sets, params = [], []
    if args.status:
        sets.append("status = ?")
        params.append(args.status)
    if args.name:
        sets.append("name = ?")
        params.append(args.name)
    if args.detail is not None:
        sets.append("detail = ?")
        params.append(args.detail)
    if not sets:
        print("[update] 至少提供 --status/--name/--detail 之一")
        return 1
    params.append(args.id)
    cur.execute(f"UPDATE requirements SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    n = cur.rowcount
    conn.close()
    print(f"[update] id={args.id} 更新 {n} 行")
    return 0


def cmd_delete(args) -> int:
    conn = _connect(args.db)
    cur = conn.cursor()
    cur.execute("DELETE FROM requirements WHERE id = ?", (args.id,))
    conn.commit()
    n = cur.rowcount
    conn.close()
    print(f"[delete] id={args.id} 删除 {n} 行")
    return 0


def cmd_export(args) -> int:
    conn = _connect(args.db)
    rows = conn.execute("SELECT id, kind, name, detail, source, status, created_at FROM requirements ORDER BY id").fetchall()
    conn.close()
    if args.format == "json":
        data = [{"id": r[0], "kind": r[1], "name": r[2], "detail": r[3],
                 "source": r[4], "status": r[5], "created_at": r[6]} for r in rows]
        (DOCS_DIR / "requirements.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[export] json → {DOCS_DIR / 'requirements.json'} ({len(data)} 条)")
    elif args.format == "csv":
        with open(DOCS_DIR / "requirements.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "kind", "name", "detail", "source", "status", "created_at"])
            for r in rows:
                w.writerow(list(r))
        print(f"[export] csv → {DOCS_DIR / 'requirements.csv'} ({len(rows)} 条)")
    else:  # md
        lines = ["# 需求清单（结构化，由 requirement_cli 维护）\n",
                 f"> 数据源: `{args.db}` · 共 {len(rows)} 条\n"]
        by_status = {}
        for r in rows:
            by_status.setdefault(r[5], []).append(r)
        for st in ("open", "done", "missing"):
            if st not in by_status:
                continue
            lines.append(f"\n## {st} ({len(by_status[st])})\n")
            lines.append("| id | 类型 | 名称 | 状态 | 来源 | 说明 |")
            lines.append("|----|------|------|------|------|------|")
            for r in by_status[st]:
                detail_txt = r[3][:100].replace("|", "\\|")
                lines.append(f"| {r[0]} | {r[1]} | `{r[2]}` | {r[5]} | {r[4]} | {detail_txt} |")
        (DOCS_DIR / "REQUIREMENTS.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"[export] md → {DOCS_DIR / 'REQUIREMENTS.md'} ({len(rows)} 条)")
    return 0


def cmd_align(args) -> int:
    """结构化需求 → 代码/端点对齐（复用 requirement_align 逻辑）"""
    sys.path.insert(0, str(MCP_ROOT))
    try:
        import requirement_align as ra
    except ImportError as e:
        print(f"[align] 无法导入 requirement_align: {e}")
        return 1

    # 1. 从 DB 读需求
    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT id, kind, name, detail, source, status FROM requirements").fetchall()
    conn.close()
    items = [{"kind": r[1], "name": r[2], "detail": r[3], "source": r[4],
              "line": 0, "req_id": r[0], "status": r[5]} for r in rows]

    # 2. 端点索引 + 代码索引
    endpoints = []
    try:
        idx = json.loads(Path(args.index).read_text(encoding="utf-8"))
        endpoints = idx.get("endpoints", [])
    except Exception as e:
        print(f"[warn] 读取接口索引失败: {e}")

    res = ra.align(items, ra.build_code_index(), endpoints)

    # 3. 回写对齐状态到 DB（未找到/缺失标记 missing）
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    for a in res["alignment"]:
        if a["kind"] == "path":
            if not a["found"]:
                cur.execute("UPDATE requirements SET status='missing' WHERE id=? AND status!='done'",
                            (a.get("req_id", -1),))
        else:
            if not a["found"]:
                cur.execute("UPDATE requirements SET status='missing' WHERE id=? AND status!='done'",
                            (a.get("req_id", -1),))
    conn.commit()
    conn.close()

    # 4. 输出报告（md + json + csv + sqlite）
    (DOCS_DIR / "REQUIREMENT_ALIGNMENT.md").write_text(
        ra.gen_markdown(res, [f"db:{args.db}"], {}), encoding="utf-8")
    with open(DOCS_DIR / "requirement_alignment.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["req_id", "kind", "name", "found", "found_in", "status", "detail"])
        for a in res["alignment"]:
            w.writerow([a.get("req_id", ""), a["kind"], a["name"], a["found"],
                        a.get("found_in", ""), a.get("status", ""), a["detail"]])
    aconn = sqlite3.connect(str(DOCS_DIR / "requirement_alignment.db"))
    try:
        c = aconn.cursor()
        c.execute("DROP TABLE IF EXISTS requirements")
        c.execute("""CREATE TABLE requirements(
            req_id INT, kind TEXT, name TEXT, found INT,
            found_in TEXT, status TEXT, detail TEXT)""")
        c.executemany("INSERT INTO requirements VALUES (?,?,?,?,?,?,?)",
                      [(a.get("req_id", 0), a["kind"], a["name"], int(a["found"]),
                        a.get("found_in", ""), a.get("status", ""), a["detail"])
                       for a in res["alignment"]])
        aconn.commit()
    finally:
        aconn.close()

    print(f"[align] 需求={len(res['alignment'])} 未找到={len(res['not_found'])} "
          f"端点缺失={len(res['missing_paths'])} 前缀={len(res['prefix_matches'])}")
    print(f"  报告 → {DOCS_DIR / 'REQUIREMENT_ALIGNMENT.md'}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="需求文档结构化 CLI（Agent 直接填 API）")
    ap.add_argument("--db", default=str(DB_PATH), help=f"SQLite 路径（默认 {DB_PATH}）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="新增需求条目")
    p_add.add_argument("--kind", required=True, choices=VALID_KINDS)
    p_add.add_argument("--name", required=True, help="接口/路径/文件名")
    p_add.add_argument("--detail", default="", help="说明")
    p_add.add_argument("--source", default="cli", help="来源（如 brief-1）")

    p_list = sub.add_parser("list", help="列出需求")
    p_list.add_argument("--kind", choices=VALID_KINDS)
    p_list.add_argument("--status", choices=VALID_STATUS)

    p_upd = sub.add_parser("update", help="更新需求")
    p_upd.add_argument("--id", type=int, required=True)
    p_upd.add_argument("--status", choices=VALID_STATUS)
    p_upd.add_argument("--name")
    p_upd.add_argument("--detail")

    p_del = sub.add_parser("delete", help="删除需求")
    p_del.add_argument("--id", type=int, required=True)

    p_exp = sub.add_parser("export", help="导出文档")
    p_exp.add_argument("--format", choices=("md", "json", "csv"), default="md")

    p_alg = sub.add_parser("align", help="与代码/端点对齐")
    p_alg.add_argument("--index", default=str(DOCS_DIR / "interface_chain_index.json"))

    args = ap.parse_args()
    db = os.environ.get("TS2_REQ_DB", args.db) if not hasattr(args, "db") else args.db
    args.db = db

    handlers = {"add": cmd_add, "list": cmd_list, "update": cmd_update,
                "delete": cmd_delete, "export": cmd_export, "align": cmd_align}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
