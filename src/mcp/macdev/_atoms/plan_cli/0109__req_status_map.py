# 原子：_req_status_map（原 plan_cli.py 第 109 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _req_status_map() -> dict:
    """从 requirements.db 构建 {kind:name: status} 查询映射（缺失则返回空）"""
    if not Path(REQ_DB).exists():
        return {}
    try:
        conn = sqlite3.connect(str(REQ_DB))
        rows = conn.execute("SELECT kind, name, status FROM requirements").fetchall()
        conn.close()
        return {f"{k}:{n}": s for k, n, s in rows}
    except Exception:
        return {}
