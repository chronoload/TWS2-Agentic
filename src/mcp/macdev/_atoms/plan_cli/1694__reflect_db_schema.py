# 原子：_reflect_db_schema（原 plan_cli.py 第 1694 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _reflect_db_schema() -> list:
    """反射提取 SQLite 表结构（从 _connect 的 CREATE TABLE 语句解析）。"""
    import inspect as _inspect
    schema = []
    try:
        src = _inspect.getsource(_connect)
        for m in re.finditer(r'CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\(([^)]+)\)', src, re.DOTALL):
            table = m.group(1)
            cols_raw = m.group(2).strip()
            cols = []
            for line in cols_raw.split('\n'):
                line = line.strip().rstrip(',')
                if not line or line.startswith('--'):
                    continue
                cm = re.match(r'(\w+)\s+(\w+)(?:\s+DEFAULT\s+([^,]+))?', line)
                if cm:
                    cols.append((cm.group(1), cm.group(2), (cm.group(3) or '').strip()))
            schema.append((table, cols))
    except Exception:
        pass
    return schema
