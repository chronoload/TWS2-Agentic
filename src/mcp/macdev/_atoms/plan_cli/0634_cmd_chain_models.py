# 原子：cmd_chain_models（原 plan_cli.py 第 634 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_chain_models(args) -> int:
    conn = _chain_connect(args.db)
    if conn is None:
        return 1
    try:
        if args.dup:
            # 跨文件重复模型定义：后定义覆盖先定义 → 语义偏移风险
            rows = conn.execute(
                "SELECT name, group_concat(DISTINCT file) FROM models "
                "GROUP BY name HAVING count(DISTINCT file) > 1 ORDER BY name").fetchall()
            if not rows:
                print("[chain] 无跨文件重复模型定义")
                return 0
            for name, files in rows:
                print(f"  {name} -> {files}")
            print(f"\n[chain] 共 {len(rows)} 个模型存在跨文件重复定义（后定义覆盖先定义风险）")
            return 0

        sql = "SELECT name, field, type, required, default_value, file, line FROM models WHERE 1=1"
        params: list = []
        if args.name:
            sql += " AND name LIKE ?"
            params.append(f"%{args.name}%")
        rows = conn.execute(sql + " ORDER BY name, line", params).fetchall()
        if not rows:
            print("[chain] 无匹配模型")
            return 0
        for name, field, typ, req, dv, file, line in rows:
            print(f"  {name}.{field} : {typ}  required={bool(req)}  default={dv or '—'}  ({file}:{line})")
        print(f"\n[chain] 共 {len(rows)} 个字段")
    finally:
        conn.close()
    return 0
