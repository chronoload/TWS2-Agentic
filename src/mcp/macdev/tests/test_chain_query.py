# -*- coding: utf-8 -*-
"""T2: chain callers/kw 查询——chain_callers 上游/下游 + chain_kw def/use 引用列表"""
import sys
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from macdev.audit import chain_query


def _make_db(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE calls(caller TEXT, callee TEXT, file TEXT, line INT)")
    conn.executemany("INSERT INTO calls VALUES (?,?,?,?)", [
        ("beta", "alpha", "a.py", 5),
        ("Gamma.method", "beta", "a.py", 10),
        ("delta", "alpha", "b.py", 3),
    ])
    conn.execute("CREATE TABLE refs(symbol TEXT, file TEXT, line INT, kind TEXT)")
    conn.executemany("INSERT INTO refs VALUES (?,?,?,?)", [
        ("alpha", "a.py", 2, "def"),
        ("beta", "a.py", 4, "def"),
        ("GLOBAL_X", "a.py", 6, "use"),
        ("alpha", "a.py", 6, "use"),
        ("Gamma", "a.py", 8, "def"),
    ])
    conn.commit()
    conn.close()
    return db


def test_chain_callers_upstream_downstream(tmp_path):
    """chain_callers 输出上游(谁调 X) + 下游(X 调谁)，file:line 定位"""
    db = _make_db(tmp_path)
    out = chain_query.chain_callers(db, func="alpha")
    text = "\n".join(out)
    assert "beta" in text and "a.py:5" in text, f"上游 beta 未命中：\n{text}"
    assert "delta" in text and "b.py:3" in text, f"上游 delta 未命中：\n{text}"
    assert "下游" in text or "callee" in text, "应输出下游分区"


def test_chain_callers_downstream_only(tmp_path):
    """X 有下游（X 调用了谁）时输出下游列表"""
    db = _make_db(tmp_path)
    out = chain_query.chain_callers(db, func="beta")
    text = "\n".join(out)
    assert "alpha" in text, f"beta 调用了 alpha 未命中：\n{text}"


def test_chain_kw_def_use(tmp_path):
    """chain_kw 输出引用位置列表，def/use 标注"""
    db = _make_db(tmp_path)
    out = chain_query.chain_kw(db, keyword="alpha")
    text = "\n".join(out)
    assert "a.py:2" in text and "def" in text, f"alpha 定义(def) 未命中：\n{text}"
    assert "a.py:6" in text and "use" in text, f"alpha 引用(use) 未命中：\n{text}"


def test_chain_callers_missing_table_graceful(tmp_path):
    """旧 db 无 calls/refs 表 → 友好提示刷新，不崩溃"""
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE stats(key TEXT, value TEXT)")
    conn.commit()
    conn.close()
    out = chain_query.chain_callers(db, func="alpha")
    assert any("audit" in line or "刷新" in line for line in out), f"应提示刷新：{out}"
