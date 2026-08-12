# 原子：_chain_connect（原 plan_cli.py 第 488 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _chain_connect(db: str) -> sqlite3.Connection | None:
    path = Path(db) if db else CHAIN_DB
    if not path.exists():
        print(f"[chain] 库不存在: {path}（先运行 python mcp/interface_chain_extractor.py）")
        return None
    conn = sqlite3.connect(str(path))
    conn.text_factory = str  # 避免编码问题
    return conn
