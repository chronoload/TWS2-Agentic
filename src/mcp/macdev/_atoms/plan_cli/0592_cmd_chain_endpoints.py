# 原子：cmd_chain_endpoints（原 plan_cli.py 第 592 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_chain_endpoints(args) -> int:
    conn = _chain_connect(args.db)
    if conn is None:
        return 1
    try:
        if args.by_file:
            # 端点按文件分组统计
            rows = conn.execute(
                "SELECT file, count(*) FROM endpoints GROUP BY file ORDER BY 2 DESC").fetchall()
            if not rows:
                print("[chain] 无端点")
                return 0
            for file, c in rows:
                print(f"  {c:4}  {file}")
            print(f"\n[chain] 共 {sum(c for _, c in rows)} 个端点 / {len(rows)} 个文件")
            return 0

        sql = "SELECT method, path, func, request_model, file, line, doc FROM endpoints WHERE 1=1"
        params: list = []
        if args.path:
            sql += " AND path LIKE ?"
            params.append(f"%{args.path}%")
        if args.func:
            sql += " AND func LIKE ?"
            params.append(f"%{args.func}%")
        if args.no_model:
            # 无请求模型的端点：POST 类入参未走 Pydantic 校验（结构异常候选）
            sql += " AND (request_model IS NULL OR request_model = '')"
        rows = conn.execute(sql + " ORDER BY path, method", params).fetchall()
        if not rows:
            print("[chain] 无匹配端点")
            return 0
        for method, path, func, req_model, file, line, doc in rows:
            print(f"  {method:6} {path}  → {func}()  req={req_model or '—'}  ({file}:{line})")
            if doc:
                print(f"        {doc[:100]}")
        print(f"\n[chain] 共 {len(rows)} 个端点")
    finally:
        conn.close()
    return 0
