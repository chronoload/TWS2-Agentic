"""audit.report：双轨产物生成（Markdown 报告 / CSV / SQLite 全表）。
从 extractor 原子重组：报告通用化（无 TS2 特化小节），SQLite 全维度建表。
"""
from __future__ import annotations
import csv
import sqlite3
from pathlib import Path
from .parse import _type_short
from .analyze import _is_behavior_defect


def gen_markdown(endpoints, models, dep_sections: str = "",
                 defuse=None, behavior=None, flag=None, merge=None, id_source=None,
                 hardcoded=None, env_vars=None, data_pools=None, static_resources=None) -> str:
    """通用审计报告：端点/模型/语义偏移 + 依赖链（§8）+ 6 维分析 + 4 维扫描。"""
    L: list[str] = []

    # 1. 端点
    L.append("## 1. 后端端点一览\n")
    L.append("| 方法 | 路径 | 函数 | 请求模型 | 返回字段 | 说明 |")
    L.append("|------|------|------|----------|----------|------|")
    for ep in sorted(endpoints, key=lambda e: e.path):
        rm = f"`{ep.request_model}`" if ep.request_model else "—"
        resp = ", ".join(f"`{k}`" for k in ep.response_keys[:8]) if ep.response_keys else "—"
        L.append(f"| {ep.method} | `{ep.path}` | `{ep.func}` | {rm} | {resp} | {ep.doc or ''} |")

    # 2. 请求模型
    L.append("\n## 2. Pydantic 请求模型\n")
    if models:
        for m in sorted(models, key=lambda x: x.name):
            L.append(f"### `{m.name}` — {m.file}:{m.line}\n")
            if m.doc:
                L.append(f"_{m.doc}_\n")
            L.append("| 字段 | 类型 | 必填 | 默认值 |")
            L.append("|------|------|------|--------|")
            for f in m.fields:
                L.append(f"| `{f.name}` | `{_type_short(f.type)}` | {'✅' if f.required else '—'} | `{f.default}` |")
            L.append("")
    else:
        L.append("未检测到 Pydantic 模型。\n")

    # 3. 语义偏移（重复模型名）
    L.append("\n## 3. 语义偏移检测（后端内部）\n")
    dup_models = {}
    for m in models:
        dup_models.setdefault(m.name, []).append(f"{m.file}:{m.line}")
    dups = {k: v for k, v in dup_models.items() if len(v) > 1}
    if dups:
        L.append("⚠️ **重复定义的模型名**（后定义会覆盖先定义，极易引发语义偏移）：\n")
        L.append("| 模型名 | 定义位置 |")
        L.append("|--------|----------|")
        for k, v in dups.items():
            L.append(f"| `{k}` | {'; '.join(v)} |")
    else:
        L.append("后端模型无重名。\n")

    # 8. 依赖链（亲属追逐，build_dep_sections 输出 §8 标题，编号自洽）
    if dep_sections:
        L.append(dep_sections)

    # 9. def-use
    L.append("\n## 9. def-use 属性一致性检查（跨文件）\n")
    L.append("> 扫描 `getattr(obj, 'attr', default)` 读取点，交叉验证全库是否存在 `obj.attr` 赋值点。\n")
    if defuse:
        _reads, _writes, issues, closed = defuse
        hard = [i for i in issues if i.kind == "no_assignment"]
        loose = [i for i in issues if i.kind == "loose_match"]
        external = [i for i in issues if i.kind == "external_contract"]
        L.append(f"**读取点 {len(_reads)} · 赋值点 {len(_writes)} · 恒值风险 {len(issues)}"
                 f"（无赋值 {len(hard)} / 对象不匹配 {len(loose)} / 外部契约 {len(external)}）**\n")
        if hard:
            L.append("\n### 🔴 恒值风险：读取点无任何赋值\n")
            L.append("| 属性 | 读取位置 | 对象 | 默认值 | 风险说明 |")
            L.append("|------|----------|------|--------|----------|")
            for i in hard:
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | `{i.obj}` | `{i.default}` | {i.detail} |")
        if loose:
            L.append("\n### 🟡 对象名不匹配（跨对象同名属性，需人工确认）\n")
            L.append("| 属性 | 读取位置 | 对象 | 默认值 | 可能的赋值位置 |")
            L.append("|------|----------|------|--------|----------------|")
            for i in loose:
                wl = "; ".join(f"{f}:{ln}" for f, ln, *_ in i.writes[:4]) or "—"
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | `{i.obj}` | `{i.default}` | {wl} |")
        if not hard and not loose:
            L.append("\n✅ 核心业务代码中所有假值默认的 `getattr` 读取均有赋值点闭合。\n")
        if external:
            L.append("\n### 🟠 外部/库对象属性读取（项目内无赋值，需人工核查）\n")
            L.append("| 属性 | 读取位置 | 对象 | 默认值 | 核查结论 |")
            L.append("|------|----------|------|--------|----------|")
            for i in external[:40]:
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | `{i.obj}` | `{i.default}` | {i.detail} |")
        if closed:
            L.append("\n### 已闭合读取（赋值链）\n")
            L.append("| 属性 | 读取位置 | 对象 | 赋值位置 |")
            L.append("|------|----------|------|----------|")
            for r, wl in closed[:40]:
                ws = "; ".join(f"{f}:{ln}" for f, ln, *_ in wl) or "—"
                L.append(f"| `{r.attr}` | {r.file}:{r.line} | `{r.obj}` | {ws} |")
    else:
        L.append("（未启用）\n")

    # 10. 行为契约
    L.append("\n## 10. 行为契约检查（must-call 路径覆盖）\n")
    L.append("> 依赖链只验证「被调用的函数存在」，无法验证「入口的正常完成路径必须触发某副作用」。\n")
    if behavior:
        hard = [b for b in behavior if b.missing and "未找到" not in b.detail]
        missing_entry = [b for b in behavior if "未找到" in b.detail]
        L.append(f"**入口 {len(behavior)} · 命中问题 {len(hard)} · 规则失效 {len(missing_entry)}**\n")
        if hard:
            L.append("\n### 🔴 缺少必须的副作用调用\n")
            L.append("| 入口 | 缺失目标 | 说明 |")
            L.append("|------|----------|------|")
            for b in hard:
                L.append(f"| `{b.entry}` | {', '.join(f'`{m}`' for m in b.missing)} | {b.detail} |")
        if missing_entry:
            L.append("\n### 🟠 规则失效（入口函数未找到，规则需更新）\n")
            for b in missing_entry:
                L.append(f"- `{b.entry}`：{b.detail}")
        if not hard and not missing_entry:
            L.append("\n✅ 所有入口的正常完成路径均触发了声明的副作用。\n")
    else:
        L.append("（未启用）\n")

    # 11. 状态标志生命周期
    L.append("\n## 11. 状态标志生命周期检查（clear/set 配对 · 跨会话缓存重置）\n")
    if flag:
        cw = [i for i in flag if i.kind == "clear_without_set"]
        sc = [i for i in flag if i.kind == "stale_cache"]
        L.append(f"**clear_without_set {len(cw)} · stale_cache {len(sc)}**\n")
        if cw:
            L.append("\n### 🔴 clear 后无 set 恢复\n")
            L.append("| 标志 | 位置 | 说明 |")
            L.append("|------|------|------|")
            for i in cw:
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | {i.detail} |")
        if sc:
            L.append("\n### 🟠 跨会话缓存未重置\n")
            L.append("| 字段 | 位置 | 说明 |")
            L.append("|------|------|------|")
            for i in sc:
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | {i.detail} |")
        if not cw and not sc:
            L.append("\n✅ 状态标志生命周期正常。\n")
    else:
        L.append("（未启用）\n")

    # 12. 合并方向仲裁
    L.append("\n## 12. 状态机合并方向仲裁（数量仲裁 vs 版本仲裁）\n")
    if merge:
        cma = [i for i in merge if i.kind == "count_only_arbitration"]
        L.append(f"**count_only_arbitration {len(cma)}**\n")
        if cma:
            L.append("\n### 🔴 数量仲裁无版本字段\n")
            L.append("| 函数 | 位置 | 说明 |")
            L.append("|------|------|------|")
            for i in cma:
                L.append(f"| `{i.fn}` | {i.file}:{i.line} | {i.detail} |")
        else:
            L.append("\n✅ 合并方向均携带版本仲裁或无需合并。\n")
    else:
        L.append("（未启用）\n")

    # 13. 标识符命名空间
    L.append("\n## 13. 标识符命名空间来源契约（跨命名空间 key 误用 · 无守卫消费者）\n")
    if id_source:
        ck = [i for i in id_source if i.kind == "cross_namespace_key"]
        ug = [i for i in id_source if i.kind == "unguarded_key_consumer"]
        L.append(f"**cross_namespace_key {len(ck)} · unguarded_key_consumer {len(ug)}**\n")
        if ck:
            L.append("\n### 🔴 跨命名空间 key 误用\n")
            L.append("| 消费点 | key 实参 | 位置 | 说明 |")
            L.append("|--------|----------|------|------|")
            for i in ck:
                L.append(f"| `{i.consumer}()` | `{i.key_arg}` | {i.file}:{i.line} | {i.detail} |")
        if ug:
            L.append("\n### 🟠 消费者无命名空间守卫\n")
            L.append("| 消费者 | key 形参 | 位置 | 说明 |")
            L.append("|--------|----------|------|------|")
            for i in ug:
                L.append(f"| `{i.consumer}()` | `{i.key_arg}` | {i.file}:{i.line} | {i.detail} |")
        if not ck and not ug:
            L.append("\n✅ 所有存储消费点的 key 均来自同命名空间创建点，且有前缀守卫。\n")
    else:
        L.append("（未启用）\n")

    # 14-17. 4 维扫描
    L.append(f"\n## 14. 硬编码常量（{len(hardcoded) if hardcoded else 0}）\n")
    if hardcoded:
        L.append("| 文件 | 行 | 类型 | 值 | 上下文 |")
        L.append("|------|----|------|----|--------|")
        for i in hardcoded[:30]:
            L.append(f"| {i.file} | {i.line} | `{i.kind}` | `{i.value[:60]}` | {i.context[:30]} |")
        if len(hardcoded) > 30:
            L.append(f"| ... | ... | ... | 共 {len(hardcoded)} 条，详见 hardcoded.csv |")
    else:
        L.append("未检测到硬编码常量。\n")

    L.append(f"\n## 15. 环境变量读取（{len(env_vars) if env_vars else 0}）\n")
    if env_vars:
        L.append("| 文件 | 行 | 变量名 | 默认值 | 上下文 |")
        L.append("|------|----|--------|--------|--------|")
        for i in env_vars[:30]:
            L.append(f"| {i.file} | {i.line} | `{i.name}` | `{i.default or '—'}` | {i.context[:30]} |")
        if len(env_vars) > 30:
            L.append(f"| ... | ... | ... | 共 {len(env_vars)} 条，详见 env_vars.csv |")
    else:
        L.append("未检测到环境变量读取。\n")

    L.append(f"\n## 16. 数据池/状态（{len(data_pools) if data_pools else 0}）\n")
    if data_pools:
        L.append("| 文件 | 行 | 名称 | 类型 | 规模 | 上下文 |")
        L.append("|------|----|------|------|------|--------|")
        for i in data_pools[:30]:
            L.append(f"| {i.file} | {i.line} | `{i.name}` | `{i.kind}` | {i.size_hint[:30]} | {i.context[:20]} |")
        if len(data_pools) > 30:
            L.append(f"| ... | ... | ... | 共 {len(data_pools)} 条，详见 data_pools.csv |")
    else:
        L.append("未检测到数据池/状态。\n")

    L.append(f"\n## 17. 静态资源路径（{len(static_resources) if static_resources else 0}）\n")
    if static_resources:
        L.append("| 文件 | 行 | 路径 | 类型 | 上下文 |")
        L.append("|------|----|------|------|--------|")
        for i in static_resources[:30]:
            L.append(f"| {i.file} | {i.line} | `{i.path[:60]}` | `{i.kind}` | {i.context[:30]} |")
        if len(static_resources) > 30:
            L.append(f"| ... | ... | ... | 共 {len(static_resources)} 条，详见 static_resources.csv |")
    else:
        L.append("未检测到静态资源路径。\n")

    return "\n".join(L)


def _write_csv(path: Path, headers: list, rows: list) -> None:
    """写 CSV（utf-8-sig 便于 Excel 直接打开）"""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow(["" if v is None else str(v) for v in r])


def write_csvs(out_dir: Path, endpoints, models, drifts, defuse,
               behavior, flag, merge, id_source, scan_items) -> None:
    """四类 CSV 明细产物。"""
    _write_csv(out_dir / "endpoints.csv",
               ["method", "path", "func", "request_model", "response_keys", "file", "line", "doc"],
               [(e.method, e.path, e.func, e.request_model, "|".join(e.response_keys),
                 e.file, e.line, e.doc) for e in endpoints])
    _write_csv(out_dir / "models.csv",
               ["name", "file", "line", "field", "type", "required", "default_value"],
               [(m.name, m.file, m.line, f.name, _type_short(f.type), int(f.required), f.default)
                for m in models for f in m.fields])
    _write_csv(out_dir / "drifts.csv",
               ["kind", "client", "endpoint", "detail"],
               [(d.kind, d.client, d.endpoint, d.detail) for d in drifts])
    if defuse:
        _reads, _writes, issues, closed = defuse
        _write_csv(out_dir / "defuse_issues.csv",
                   ["kind", "attr", "file", "line", "obj", "default_value", "detail"],
                   [(i.kind, i.attr, i.file, i.line, i.obj, i.default, i.detail) for i in issues])
        _write_csv(out_dir / "defuse_reads.csv",
                   ["file", "line", "obj", "attr", "default_value"],
                   [(r.file, r.line, r.obj, r.attr, r.default) for r in _reads])
    _write_csv(out_dir / "behavior_issues.csv",
               ["entry", "missing", "file", "detail"],
               [(b.entry, "|".join(b.missing), b.file, b.detail)
                for b in behavior if _is_behavior_defect(b)])
    _write_csv(out_dir / "flag_lifecycle.csv",
               ["kind", "attr", "file", "line", "detail"],
               [(i.kind, i.attr, i.file, i.line, i.detail) for i in flag])
    _write_csv(out_dir / "merge_direction.csv",
               ["kind", "fn", "file", "line", "detail"],
               [(i.kind, i.fn, i.file, i.line, i.detail) for i in merge])
    _write_csv(out_dir / "id_source.csv",
               ["kind", "consumer", "key_arg", "file", "line", "detail"],
               [(i.kind, i.consumer, i.key_arg, i.file, i.line, i.detail) for i in id_source])
    _write_csv(out_dir / "hardcoded.csv",
               ["file", "line", "kind", "value", "context"],
               [(i.file, i.line, i.kind, i.value, i.context) for i in scan_items["hardcoded"]])
    _write_csv(out_dir / "env_vars.csv",
               ["file", "line", "name", "default_value", "context"],
               [(i.file, i.line, i.name, i.default, i.context) for i in scan_items["env_vars"]])
    _write_csv(out_dir / "data_pools.csv",
               ["file", "line", "name", "kind", "size_hint", "context"],
               [(i.file, i.line, i.name, i.kind, i.size_hint, i.context)
                for i in scan_items["data_pools"]])
    _write_csv(out_dir / "static_resources.csv",
               ["file", "line", "path", "kind", "context"],
               [(i.file, i.line, i.path, i.kind, i.context)
                for i in scan_items["static_resources"]])


def write_db(db_path: Path, endpoints, models, drifts=None, defuse=None,
             behavior=None, flag=None, merge=None, id_source=None, scan_items=None) -> None:
    """写 SQLite 全维度表：endpoints/models/drifts/defuse/behavior/flag/merge/id_source/扫描/stats。"""
    conn = sqlite3.connect(str(db_path))
    try:
        c = conn.cursor()
        c.execute("DROP TABLE IF EXISTS endpoints")
        c.execute("""CREATE TABLE endpoints(
            method TEXT, path TEXT, func TEXT, request_model TEXT,
            response_keys TEXT, file TEXT, line INT, doc TEXT)""")
        c.executemany(
            "INSERT INTO endpoints VALUES (?,?,?,?,?,?,?,?)",
            [(e.method, e.path, e.func, e.request_model,
              "|".join(e.response_keys), e.file, e.line, e.doc) for e in endpoints])

        c.execute("DROP TABLE IF EXISTS models")
        c.execute("""CREATE TABLE models(
            name TEXT, file TEXT, line INT, field TEXT,
            type TEXT, required INT, default_value TEXT)""")
        c.executemany(
            "INSERT INTO models VALUES (?,?,?,?,?,?,?)",
            [(m.name, m.file, m.line, f.name, _type_short(f.type),
              int(f.required), f.default) for m in models for f in m.fields])

        c.execute("DROP TABLE IF EXISTS drifts")
        c.execute("""CREATE TABLE drifts(
            kind TEXT, client TEXT, endpoint TEXT, detail TEXT)""")
        if drifts:
            c.executemany("INSERT INTO drifts VALUES (?,?,?,?)",
                          [(d.kind, d.client, d.endpoint, d.detail) for d in drifts])

        c.execute("DROP TABLE IF EXISTS defuse_issues")
        c.execute("""CREATE TABLE defuse_issues(
            kind TEXT, attr TEXT, file TEXT, line INT, obj TEXT,
            default_value TEXT, detail TEXT)""")
        c.execute("DROP TABLE IF EXISTS defuse_reads")
        c.execute("""CREATE TABLE defuse_reads(
            file TEXT, line INT, obj TEXT, attr TEXT, default_value TEXT)""")
        if defuse:
            reads, _w, issues, _closed = defuse
            c.executemany("INSERT INTO defuse_issues VALUES (?,?,?,?,?,?,?)",
                          [(i.kind, i.attr, i.file, i.line, i.obj, i.default, i.detail)
                           for i in issues])
            c.executemany("INSERT INTO defuse_reads VALUES (?,?,?,?,?)",
                          [(r.file, r.line, r.obj, r.attr, r.default) for r in reads])

        c.execute("DROP TABLE IF EXISTS behavior_issues")
        c.execute("""CREATE TABLE behavior_issues(
            entry TEXT, missing TEXT, file TEXT, detail TEXT)""")
        if behavior:
            c.executemany("INSERT INTO behavior_issues VALUES (?,?,?,?)",
                          [(b.entry, "|".join(b.missing), b.file, b.detail)
                           for b in behavior if _is_behavior_defect(b)])

        c.execute("DROP TABLE IF EXISTS flag_lifecycle")
        c.execute("""CREATE TABLE flag_lifecycle(
            kind TEXT, attr TEXT, file TEXT, line INT, detail TEXT)""")
        if flag:
            c.executemany("INSERT INTO flag_lifecycle VALUES (?,?,?,?,?)",
                          [(i.kind, i.attr, i.file, i.line, i.detail) for i in flag])

        c.execute("DROP TABLE IF EXISTS merge_direction")
        c.execute("""CREATE TABLE merge_direction(
            kind TEXT, fn TEXT, file TEXT, line INT, detail TEXT)""")
        if merge:
            c.executemany("INSERT INTO merge_direction VALUES (?,?,?,?,?)",
                          [(i.kind, i.fn, i.file, i.line, i.detail) for i in merge])

        c.execute("DROP TABLE IF EXISTS id_source")
        c.execute("""CREATE TABLE id_source(
            kind TEXT, consumer TEXT, key_arg TEXT, file TEXT, line INT, detail TEXT)""")
        if id_source:
            c.executemany("INSERT INTO id_source VALUES (?,?,?,?,?,?)",
                          [(i.kind, i.consumer, i.key_arg, i.file, i.line, i.detail)
                           for i in id_source])

        scan_items = scan_items or {}
        for tbl, cols, rows in [
            ("hardcoded", "(file TEXT, line INT, kind TEXT, value TEXT, context TEXT)",
             [(i.file, i.line, i.kind, i.value, i.context) for i in scan_items.get("hardcoded", [])]),
            ("env_vars", "(file TEXT, line INT, name TEXT, default_value TEXT, context TEXT)",
             [(i.file, i.line, i.name, i.default, i.context) for i in scan_items.get("env_vars", [])]),
            ("data_pools", "(file TEXT, line INT, name TEXT, kind TEXT, size_hint TEXT, context TEXT)",
             [(i.file, i.line, i.name, i.kind, i.size_hint, i.context)
              for i in scan_items.get("data_pools", [])]),
            ("static_resources", "(file TEXT, line INT, path TEXT, kind TEXT, context TEXT)",
             [(i.file, i.line, i.path, i.kind, i.context)
              for i in scan_items.get("static_resources", [])]),
        ]:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")
            c.execute(f"CREATE TABLE {tbl}{cols}")
            if rows:
                c.executemany(f"INSERT INTO {tbl} VALUES ({','.join('?' * len(cols.split(',')))})", rows)

        c.execute("DROP TABLE IF EXISTS stats")
        c.execute("CREATE TABLE stats(key TEXT, value TEXT)")
        stats = {"endpoints": len(endpoints), "models": len(models),
                 "drifts": len(drifts) if drifts else 0,
                 "defuse_issues": len(defuse[2]) if defuse else 0,
                 "behavior_issues": len([b for b in behavior if _is_behavior_defect(b)]) if behavior else 0,
                 "flag_lifecycle": len(flag) if flag else 0,
                 "merge_direction": len(merge) if merge else 0,
                 "id_source": len(id_source) if id_source else 0,
                 "hardcoded": len(scan_items.get("hardcoded", [])) if scan_items else 0,
                 "env_vars": len(scan_items.get("env_vars", [])) if scan_items else 0,
                 "data_pools": len(scan_items.get("data_pools", [])) if scan_items else 0,
                 "static_resources": len(scan_items.get("static_resources", [])) if scan_items else 0}
        c.executemany("INSERT INTO stats VALUES (?,?)",
                      [(k, str(v)) for k, v in stats.items()])
        conn.commit()
    finally:
        conn.close()
