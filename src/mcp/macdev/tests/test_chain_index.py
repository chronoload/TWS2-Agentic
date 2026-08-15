# -*- coding: utf-8 -*-
"""T1: calls+refs 双索引——collect_calls_refs 同一遍历产出调用图+引用索引，write_db 落库"""
import sys
from pathlib import Path
import sqlite3

# 独立路径引导（conftest 在部分 pytest 环境不生效时兜底）：mcp/ 为 macdev 包父目录
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from macdev.audit import chain, report


SAMPLE = '''\
GLOBAL_X = 10

def alpha():
    return 1

def beta():
    return alpha() + GLOBAL_X

class Gamma:
    def method(self):
        return beta()
'''


def _write_sample(tmp_path: Path) -> list:
    p = tmp_path / "sample.py"
    p.write_text(SAMPLE, encoding="utf-8")
    return [p]


def test_collect_calls_refs_produces_both_indexes(tmp_path):
    """同一遍历产出 calls(调用图) + refs(引用索引)"""
    files = _write_sample(tmp_path)
    calls, refs = chain.collect_calls_refs(files)
    assert len(calls) >= 2, f"应收集到至少 2 条调用关系，实际 {len(calls)}"
    assert ("beta", "alpha") in {(c[0], c[1]) for c in calls}
    assert ("Gamma.method", "beta") in {(c[0], c[1]) for c in calls}
    syms = {(r[0], r[3]) for r in refs}
    assert ("GLOBAL_X", "use") in syms, f"GLOBAL_X 应被标记为 use 引用，实际 refs={syms}"
    assert ("alpha", "def") in syms, "alpha 应有 def 定义记录"
    assert ("Gamma", "def") in syms, "Gamma 类应有 def 定义记录"


def test_write_db_creates_calls_refs_tables(tmp_path):
    """write_db 建 calls/refs 表并写入"""
    files = _write_sample(tmp_path)
    calls, refs = chain.collect_calls_refs(files)
    db = tmp_path / "out.db"
    report.write_db(db, [], [], calls=calls, refs=refs)
    conn = sqlite3.connect(str(db))
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        assert "calls" in tables, f"缺 calls 表：{tables}"
        assert "refs" in tables, f"缺 refs 表：{tables}"
        n_calls = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        n_refs = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        assert n_calls >= 2, f"calls 应有 >=2 行，实际 {n_calls}"
        assert n_refs >= 4, f"refs 应有 >=4 行，实际 {n_refs}"
    finally:
        conn.close()
