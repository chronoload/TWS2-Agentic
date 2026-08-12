# 原子：_write_sqlite（原 interface_chain_extractor.py 第 3784 行）
# 逻辑组：output · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _write_sqlite(db_path: Path, defuse_result, endpoints, models,
                  drifts, client_methods, behavior_issues, flag_issues,
                  merge_issues, id_source_issues,
                  hardcoded=None, env_vars=None, data_pools=None, static_resources=None) -> None:
    """写 SQLite 数据库：端/模型/客户端/漂移/def-use 表 + 统计 + 新增 4 维度表"""
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

        c.execute("DROP TABLE IF EXISTS client_methods")
        c.execute("""CREATE TABLE client_methods(
            name TEXT, line INT, endpoint TEXT, http_method TEXT, payload_keys TEXT)""")
        c.executemany(
            "INSERT INTO client_methods VALUES (?,?,?,?,?)",
            [(cm.name, cm.line, cm.endpoint, cm.http_method,
              "|".join(cm.payload_keys)) for cm in client_methods])

        c.execute("DROP TABLE IF EXISTS drifts")
        c.execute("""CREATE TABLE drifts(
            kind TEXT, client TEXT, endpoint TEXT, detail TEXT)""")
        c.executemany(
            "INSERT INTO drifts VALUES (?,?,?,?)",
            [(d.kind, d.client, d.endpoint, d.detail) for d in drifts])

        c.execute("DROP TABLE IF EXISTS defuse_issues")
        c.execute("""CREATE TABLE defuse_issues(
            kind TEXT, attr TEXT, file TEXT, line INT, obj TEXT,
            default_value TEXT, detail TEXT)""")
        c.execute("DROP TABLE IF EXISTS defuse_reads")
        c.execute("""CREATE TABLE defuse_reads(
            file TEXT, line INT, obj TEXT, attr TEXT, default_value TEXT)""")
        c.execute("DROP TABLE IF EXISTS behavior_issues")
        c.execute("""CREATE TABLE behavior_issues(
            entry TEXT, missing TEXT, file TEXT, detail TEXT)""")
        c.executemany(
            "INSERT INTO behavior_issues VALUES (?,?,?,?)",
            [(b.entry, "|".join(b.missing), b.file, b.detail)
             for b in behavior_issues if _is_behavior_defect(b)])
        c.execute("DROP TABLE IF EXISTS flag_lifecycle")
        c.execute("""CREATE TABLE flag_lifecycle(
            kind TEXT, attr TEXT, file TEXT, line INT, detail TEXT)""")
        c.executemany(
            "INSERT INTO flag_lifecycle VALUES (?,?,?,?,?)",
            [(i.kind, i.attr, i.file, i.line, i.detail) for i in flag_issues])
        c.execute("DROP TABLE IF EXISTS merge_direction")
        c.execute("""CREATE TABLE merge_direction(
            kind TEXT, fn TEXT, file TEXT, line INT, detail TEXT)""")
        c.executemany(
            "INSERT INTO merge_direction VALUES (?,?,?,?,?)",
            [(i.kind, i.fn, i.file, i.line, i.detail) for i in merge_issues])
        c.execute("DROP TABLE IF EXISTS id_source")
        c.execute("""CREATE TABLE id_source(
            kind TEXT, consumer TEXT, key_arg TEXT, file TEXT, line INT, detail TEXT)""")
        c.executemany(
            "INSERT INTO id_source VALUES (?,?,?,?,?,?)",
            [(i.kind, i.consumer, i.key_arg, i.file, i.line, i.detail) for i in id_source_issues])

        # 新增 4 维度表
        c.execute("DROP TABLE IF EXISTS hardcoded")
        c.execute("""CREATE TABLE hardcoded(
            file TEXT, line INT, kind TEXT, value TEXT, context TEXT)""")
        if hardcoded:
            c.executemany(
                "INSERT INTO hardcoded VALUES (?,?,?,?,?)",
                [(i.file, i.line, i.kind, i.value, i.context) for i in hardcoded])

        c.execute("DROP TABLE IF EXISTS env_vars")
        c.execute("""CREATE TABLE env_vars(
            file TEXT, line INT, name TEXT, default_value TEXT, context TEXT)""")
        if env_vars:
            c.executemany(
                "INSERT INTO env_vars VALUES (?,?,?,?,?)",
                [(i.file, i.line, i.name, i.default, i.context) for i in env_vars])

        c.execute("DROP TABLE IF EXISTS data_pools")
        c.execute("""CREATE TABLE data_pools(
            file TEXT, line INT, name TEXT, kind TEXT, size_hint TEXT, context TEXT)""")
        if data_pools:
            c.executemany(
                "INSERT INTO data_pools VALUES (?,?,?,?,?,?)",
                [(i.file, i.line, i.name, i.kind, i.size_hint, i.context) for i in data_pools])

        c.execute("DROP TABLE IF EXISTS static_resources")
        c.execute("""CREATE TABLE static_resources(
            file TEXT, line INT, path TEXT, kind TEXT, context TEXT)""")
        if static_resources:
            c.executemany(
                "INSERT INTO static_resources VALUES (?,?,?,?,?)",
                [(i.file, i.line, i.path, i.kind, i.context) for i in static_resources])

        if defuse_result:
            reads, _w, issues, _closed = defuse_result
            c.executemany(
                "INSERT INTO defuse_issues VALUES (?,?,?,?,?,?,?)",
                [(i.kind, i.attr, i.file, i.line, i.obj, i.default, i.detail)
                 for i in issues])
            c.executemany(
                "INSERT INTO defuse_reads VALUES (?,?,?,?,?)",
                [(r.file, r.line, r.obj, r.attr, r.default) for r in reads])

        c.execute("DROP TABLE IF EXISTS stats")
        c.execute("CREATE TABLE stats(key TEXT, value TEXT)")
        stats = {"endpoints": len(endpoints), "models": len(models),
                 "client_methods": len(client_methods), "drifts": len(drifts),
                 "defuse_issues": len(defuse_result[2]) if defuse_result else 0,
                 "behavior_issues": len([b for b in behavior_issues if _is_behavior_defect(b)]),
                 "flag_lifecycle": len(flag_issues),
                 "merge_direction": len(merge_issues),
                 "id_source": len(id_source_issues),
                 "hardcoded": len(hardcoded) if hardcoded else 0,
                 "env_vars": len(env_vars) if env_vars else 0,
                 "data_pools": len(data_pools) if data_pools else 0,
                 "static_resources": len(static_resources) if static_resources else 0}
        c.executemany("INSERT INTO stats VALUES (?,?)",
                      [(k, str(v)) for k, v in stats.items()])
        conn.commit()
    finally:
        conn.close()
