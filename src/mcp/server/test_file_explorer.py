"""文件树/源码浏览器后端测试：目录 mtime 填充 + search_files 目录枚举。

运行：cd src/mcp/server && python -m mcp.server.test_file_explorer
"""
import tempfile
import pathlib

from mcp.server.sync import FileSyncEngine


def _make_ws():
    d = tempfile.mkdtemp()
    ws = pathlib.Path(d)
    for name, kind, content in [
        ("Notes", "dir", None),
        ("docs", "dir", None),
        ("Notes/a.md", "file", "a"),
        ("Notes/b.py", "file", "b"),
        ("Notes/sub", "dir", None),
        ("Notes/sub/c.md", "file", "c"),
    ]:
        p = ws / name
        if kind == "dir":
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    return ws


def test_read_dir_dir_has_modified():
    ws = _make_ws()
    engine = FileSyncEngine(str(ws))
    entries = engine.read_dir("Notes")
    by_name = {e.name: e for e in entries}
    assert "sub" in by_name, "目录应在 read_dir 结果中"
    sub = by_name["sub"]
    assert sub.is_dir
    assert sub.modified > 0, "目录必须填充 modified（mtime）"
    assert by_name["a.md"].modified > 0
    assert by_name["b.py"].modified > 0


def test_search_dir_type_filter():
    ws = _make_ws()
    engine = FileSyncEngine(str(ws))
    dirs = engine.search_files(query="", type_filter="dir")
    names = {e.name for e in dirs}
    assert "Notes" in names, "全局搜索 dir 应返回 Notes"
    assert "docs" in names, "全局搜索 dir 应返回 docs"
    assert "sub" in names, "全局搜索 dir 应返回嵌套 sub"
    assert all(e.is_dir for e in dirs), "dir 筛选结果应全为目录"
    for e in dirs:
        assert e.modified > 0, "dir 筛选结果应带 modified"


def test_search_file_ext_filter_unchanged():
    ws = _make_ws()
    engine = FileSyncEngine(str(ws))
    files = engine.search_files(query="", type_filter=".md")
    assert files, "应有 .md 文件"
    assert all(not e.is_dir and e.ext == ".md" for e in files)


def test_search_subdir_dir_filter():
    ws = _make_ws()
    engine = FileSyncEngine(str(ws))
    dirs = engine.search_files(query="", subdir="Notes", type_filter="dir")
    names = {e.name for e in dirs}
    assert "sub" in names, "子目录搜索 dir 应返回 sub"


def test_search_desc_dirs_first():
    """显式 mtime desc：文件组内按 modified 降序（无 type_filter 时搜索仅返回文件）。"""
    ws = _make_ws()
    engine = FileSyncEngine(str(ws))
    entries = engine.search_files(query="", subdir="Notes", sort_by="mtime", order="desc")
    assert entries, "应有结果"
    assert all(not e.is_dir for e in entries), "无 type_filter 时结果应全为文件"
    mtimes = [e.modified for e in entries]
    assert mtimes == sorted(mtimes, reverse=True), "mtime desc 应降序排列"


def test_search_default_sort_mtime_desc():
    """无参调用默认 mtime desc：目录优先，文件组内按 modified 降序。"""
    ws = _make_ws()
    engine = FileSyncEngine(str(ws))
    entries = engine.search_files(query="", subdir="Notes")
    files = [e for e in entries if not e.is_dir]
    mtimes = [e.modified for e in files]
    assert mtimes == sorted(mtimes, reverse=True), "默认应按 mtime 降序（文件组内）"
    # 目录仍应在最前
    first_file_idx = next(i for i, e in enumerate(entries) if not e.is_dir)
    assert all(e.is_dir for e in entries[:first_file_idx])


if __name__ == "__main__":
    test_read_dir_dir_has_modified()
    test_search_dir_type_filter()
    test_search_file_ext_filter_unchanged()
    test_search_subdir_dir_filter()
    test_search_desc_dirs_first()
    test_search_default_sort_mtime_desc()
    print("test_file_explorer passed")
