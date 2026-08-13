"""audit.chain_query：定向查询 interface_chain.db（stats/issues/endpoints/models/
drifts/tables），从 plan_cli chain 系列原子重组，替代 grep-read。
"""
from __future__ import annotations
import sqlite3
from pathlib import Path


def chain_connect(db: Path | str | None = None) -> sqlite3.Connection | None:
    path = Path(db) if db else None
    if path is not None and not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.text_factory = str
    return conn


def chain_stats(db: Path | str | None = None) -> list:
    conn = chain_connect(db)
    if conn is None:
        return ["[chain] 库不存在（先运行 python -m macdev audit）"]
    try:
        rows = conn.execute("SELECT key, value FROM stats").fetchall()
        if not rows:
            return ["[chain] stats 为空"]
        return [f"  {k} = {v}" for k, v in rows]
    finally:
        conn.close()


def chain_endpoints(db: Path | str | None = None, by_file: bool = False,
                    path: str = "", func: str = "", no_model: bool = False) -> list:
    conn = chain_connect(db)
    if conn is None:
        return ["[chain] 库不存在（先运行 python -m macdev audit）"]
    try:
        if by_file:
            rows = conn.execute(
                "SELECT file, count(*) FROM endpoints GROUP BY file ORDER BY 2 DESC").fetchall()
            if not rows:
                return ["[chain] 无端点"]
            out = [f"  {c:4}  {file}" for file, c in rows]
            out.append(f"\n[chain] 共 {sum(c for _, c in rows)} 个端点 / {len(rows)} 个文件")
            return out
        sql = "SELECT method, path, func, request_model, file, line, doc FROM endpoints WHERE 1=1"
        params: list = []
        if path:
            sql += " AND path LIKE ?"
            params.append(f"%{path}%")
        if func:
            sql += " AND func LIKE ?"
            params.append(f"%{func}%")
        if no_model:
            sql += " AND (request_model IS NULL OR request_model = '')"
        rows = conn.execute(sql + " ORDER BY path, method", params).fetchall()
        if not rows:
            return ["[chain] 无匹配端点"]
        out = []
        for method, p, f, req_model, file, line, doc in rows:
            out.append(f"  {method:6} {p}  → {f}()  req={req_model or '—'}  ({file}:{line})")
            if doc:
                out.append(f"        {doc[:100]}")
        out.append(f"\n[chain] 共 {len(rows)} 个端点")
        return out
    finally:
        conn.close()


def chain_models(db: Path | str | None = None, dup: bool = False, name: str = "") -> list:
    conn = chain_connect(db)
    if conn is None:
        return ["[chain] 库不存在（先运行 python -m macdev audit）"]
    try:
        if dup:
            rows = conn.execute(
                "SELECT name, group_concat(DISTINCT file) FROM models "
                "GROUP BY name HAVING count(DISTINCT file) > 1 ORDER BY name").fetchall()
            if not rows:
                return ["[chain] 无跨文件重复模型定义"]
            out = [f"  {n} -> {files}" for n, files in rows]
            out.append(f"\n[chain] 共 {len(rows)} 个模型存在跨文件重复定义（后定义覆盖先定义风险）")
            return out
        sql = "SELECT name, field, type, required, default_value, file, line FROM models WHERE 1=1"
        params: list = []
        if name:
            sql += " AND name LIKE ?"
            params.append(f"%{name}%")
        rows = conn.execute(sql + " ORDER BY name, line", params).fetchall()
        if not rows:
            return ["[chain] 无匹配模型"]
        out = [f"  {n}.{field} : {typ}  required={bool(req)}  default={dv or '—'}  ({file}:{line})"
               for n, field, typ, req, dv, file, line in rows]
        out.append(f"\n[chain] 共 {len(rows)} 个字段")
        return out
    finally:
        conn.close()


def chain_drifts(db: Path | str | None = None) -> list:
    conn = chain_connect(db)
    if conn is None:
        return ["[chain] 库不存在（先运行 python -m macdev audit）"]
    try:
        rows = conn.execute("SELECT kind, client, endpoint, detail FROM drifts ORDER BY kind").fetchall()
        if not rows:
            return ["[chain] 无漂移记录"]
        out = []
        for kind, client, endpoint, detail in rows:
            out.append(f"  [{kind}] {client} → {endpoint}")
            if detail:
                out.append(f"      {detail[:180]}")
        out.append(f"\n[chain] 共 {len(rows)} 条漂移")
        return out
    finally:
        conn.close()


def chain_issues(db: Path | str | None = None, count: bool = False,
                 kind: str = "", file: str = "", attr: str = "") -> list:
    conn = chain_connect(db)
    if conn is None:
        return ["[chain] 库不存在（先运行 python -m macdev audit）"]
    try:
        if count:
            rows = (conn.execute(
                "SELECT 'defuse', kind, count(*) FROM defuse_issues GROUP BY kind "
                "UNION ALL SELECT 'flag', kind, count(*) FROM flag_lifecycle GROUP BY kind "
                "UNION ALL SELECT 'merge', kind, count(*) FROM merge_direction GROUP BY kind "
                "UNION ALL SELECT 'id_source', kind, count(*) FROM id_source GROUP BY kind "
                "UNION ALL SELECT 'behavior', 'missing_behavior', count(*) FROM behavior_issues"
            ).fetchall())
            if not rows:
                return ["[chain] 无缺陷记录"]
            out = [f"  [{table}:{k}]  {c}" for table, k, c in rows if c]
            out.append(f"\n[chain] 缺陷总计 {sum(c for _, _, c in rows)} 条")
            out.append("[chain] 提示: 缺陷清单只是附加值；宏观优先看 stats / endpoints --by-file / INTERFACE_CHAIN.md §8 依赖链")
            return out

        results = []
        for row in conn.execute(
                "SELECT kind, attr, file, line, obj, default_value, detail FROM defuse_issues"):
            results.append(("defuse", row))
        for row in conn.execute(
                "SELECT kind, attr, file, line, NULL, NULL, detail FROM flag_lifecycle"):
            results.append(("flag", row))
        for row in conn.execute(
                "SELECT kind, fn, file, line, NULL, NULL, detail FROM merge_direction"):
            results.append(("merge", row))
        for row in conn.execute(
                "SELECT kind, consumer, file, line, NULL, NULL, detail FROM id_source"):
            results.append(("id_source", row))
        for row in conn.execute(
                "SELECT 'missing_behavior', entry, file, 0, NULL, NULL, detail FROM behavior_issues"):
            results.append(("behavior", row))

        kinds = [k for k in kind.split(",") if k]
        hits = []
        for table, r in results:
            k, attr_v, f, ln, obj, dv, detail = r
            if kinds and k not in kinds:
                continue
            if file and file.lower() not in (f or "").lower():
                continue
            if attr and attr.lower() not in (attr_v or "").lower():
                continue
            hits.append((table, k, attr_v, f, ln, obj, dv, detail))
        if not hits:
            return [f"[chain] 无匹配缺陷"]
        out = []
        for table, k, attr_v, f, ln, obj, dv, detail in hits:
            loc = f"{f}:{ln}" if ln else f
            out.append(f"  [{table}:{k}] {loc}  attr={attr_v or '—'}  obj={obj or '—'}  default={dv or '—'}")
            if detail:
                out.append(f"      {detail[:180]}")
        out.append(f"\n[chain] 共 {len(hits)} 条（过滤: kind={kind or '—'} file={file or '—'} attr={attr or '—'}）")
        return out
    finally:
        conn.close()


def chain_tables(db: Path | str | None = None) -> list:
    conn = chain_connect(db)
    if conn is None:
        return ["[chain] 库不存在（先运行 python -m macdev audit）"]
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        out = [f"=== 表列表 ({len(tables)} 个) ==="]
        for t in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{t}])")]
                out.append(f"\n  {t}（行数: {count}）: {', '.join(cols)}")
            except Exception as e:
                out.append(f"\n  {t}（查询失败: {e}）")
        return out
    finally:
        conn.close()
