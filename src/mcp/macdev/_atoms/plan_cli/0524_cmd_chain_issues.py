# 原子：cmd_chain_issues（原 plan_cli.py 第 524 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_chain_issues(args) -> int:
    """跨表聚合查询缺陷（defuse + behavior + flag + merge + id_source），
    支持 --kind/--file/--attr 过滤与 --count 分布，替代 grep。"""
    conn = _chain_connect(args.db)
    if conn is None:
        return 1
    try:
        if args.count:
            # 缺陷类型计数分布（8 维中 5 维可入库，行为契约统一记 missing_behavior）
            rows = (conn.execute(
                "SELECT 'defuse', kind, count(*) FROM defuse_issues GROUP BY kind "
                "UNION ALL SELECT 'flag', kind, count(*) FROM flag_lifecycle GROUP BY kind "
                "UNION ALL SELECT 'merge', kind, count(*) FROM merge_direction GROUP BY kind "
                "UNION ALL SELECT 'id_source', kind, count(*) FROM id_source GROUP BY kind "
                "UNION ALL SELECT 'behavior', 'missing_behavior', count(*) FROM behavior_issues"
            ).fetchall())
            if not rows:
                print("[chain] 无缺陷记录")
                return 0
            for table, kind, c in rows:
                if c:
                    print(f"  [{table}:{kind}]  {c}")
            print(f"\n[chain] 缺陷总计 {sum(c for _, _, c in rows)} 条")
            print("[chain] 提示: 缺陷清单只是附加值；宏观优先看 stats / endpoints --by-file / PROJECT_CHAIN.md §关键端点依赖链")
            return 0

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

        kinds = [k for k in args.kind.split(",") if k]
        hits = []
        for table, r in results:
            kind, attr, file, line, obj, dv, detail = r
            if kinds and kind not in kinds:
                continue
            if args.file and args.file.lower() not in file.lower():
                continue
            if args.attr and args.attr.lower() not in (attr or "").lower():
                continue
            hits.append((table, kind, attr, file, line, obj, dv, detail))
        if not hits:
            print(f"[chain] 无匹配缺陷（db={args.db}）")
            return 0
        for table, kind, attr, file, line, obj, dv, detail in hits:
            loc = f"{file}:{line}" if line else file
            print(f"  [{table}:{kind}] {loc}  attr={attr or '—'}  obj={obj or '—'}  default={dv or '—'}")
            if detail:
                print(f"      {detail[:180]}")
        print(f"\n[chain] 共 {len(hits)} 条（过滤: kind={args.kind or '—'} file={args.file or '—'} attr={args.attr or '—'}）")
    finally:
        conn.close()
    return 0
