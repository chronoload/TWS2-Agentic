# 原子：cmd_chain_tables（原 plan_cli.py 第 688 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_chain_tables(args) -> int:
    """列出库表结构与行数（复用 _query_interface_db.py 逻辑）。"""
    conn = _chain_connect(args.db)
    if conn is None:
        return 1
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        print(f"=== 表列表 ({len(tables)} 个) ===")
        for t in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{t}])")]
                print(f"\n  {t}（行数: {count}）: {', '.join(cols)}")
            except Exception as e:
                print(f"\n  {t}（查询失败: {e}）")
    finally:
        conn.close()
    return 0
