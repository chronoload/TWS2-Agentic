# -*- coding: utf-8 -*-
"""T3: 增量编译——文件指纹缓存 + 变更检测 + calls/refs 增量合并（改 1 文件只重扫该文件）"""
import sys
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from macdev.audit import chain, report


SAMPLE_A = '''\
GLOBAL_X = 10

def alpha():
    return 1

def beta():
    return alpha() + GLOBAL_X
'''

SAMPLE_B = '''\
def delta():
    return alpha() * 2
'''

SAMPLE_B2 = '''\
def delta():
    return alpha() * 3

def epsilon():
    return delta()
'''


def _setup(tmp_path: Path):
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text(SAMPLE_A, encoding="utf-8")
    b.write_text(SAMPLE_B, encoding="utf-8")
    return [a, b]


def test_changed_files_detects_only_modified(tmp_path):
    """指纹缓存：改 1 文件后重跑，changed 只含该文件"""
    files = _setup(tmp_path)
    db = tmp_path / "t.db"
    report.write_db(db, [], [], calls=[], refs=[])
    fps0 = {str(p): chain.file_fingerprint(p) for p in files}
    chain.save_fingerprints(db, fps0)
    # 修改 b.py
    files[1].write_text(SAMPLE_B2, encoding="utf-8")
    changed, removed, fps = chain.changed_file_paths(files, db)
    changed_strs = {str(p) for p in changed}
    assert str(files[1]) in changed_strs, f"b.py 变更应被检测：{changed_strs}"
    assert str(files[0]) not in changed_strs, f"a.py 未变更不应重扫：{changed_strs}"
    assert not removed, "无删除文件"


def test_incremental_merge_equals_full(tmp_path):
    """增量合并结果 == 全量重扫结果（正确性）"""
    files = _setup(tmp_path)
    db = tmp_path / "t.db"
    # 首次全量
    calls_full, refs_full = chain.collect_calls_refs(files)
    report.write_db(db, [], [], calls=calls_full, refs=refs_full)
    fps0 = {str(p): chain.file_fingerprint(p) for p in files}
    chain.save_fingerprints(db, fps0)
    # 修改 b.py → 增量
    files[1].write_text(SAMPLE_B2, encoding="utf-8")
    changed, _removed, _fps = chain.changed_file_paths(files, db)
    old_calls, old_refs = report.read_db_calls_refs(db)
    dirty = set(changed) | set()
    keep_calls = [c for c in old_calls if c[2] not in dirty]
    keep_refs = [r for r in old_refs if r[1] not in dirty]
    new_calls, new_refs = chain.collect_calls_refs([files[1]])
    calls_inc = keep_calls + new_calls
    refs_inc = keep_refs + new_refs
    # 全量重扫参照
    calls_ref, refs_ref = chain.collect_calls_refs(files)
    assert set(calls_inc) == set(calls_ref), f"增量 calls 与全量不一致"
    assert set(refs_inc) == set(refs_ref), "增量 refs 与全量不一致"


def test_fingerprint_change_detected(tmp_path):
    """mtime+size 指纹在内容变化时能检出（即使大小相同也需检出）"""
    files = _setup(tmp_path)
    db = tmp_path / "t.db"
    report.write_db(db, [], [], calls=[], refs=[])
    fps0 = {str(p): chain.file_fingerprint(p) for p in files}
    chain.save_fingerprints(db, fps0)
    # 同大小内容变更（+3 变 +2 → 长度不同；再试同长度）
    files[0].write_text(SAMPLE_A.replace("return 1", "return 9"), encoding="utf-8")
    changed, _, _ = chain.changed_file_paths(files, db)
    changed_strs = {str(p) for p in changed}
    assert str(files[0]) in changed_strs, f"内容变更应被检出：{changed_strs}"
