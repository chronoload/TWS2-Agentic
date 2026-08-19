"""skill-dynamic-inject TDD：catalog 纯函数核心单测（scan/parse/route）"""
from pathlib import Path

from macdev.skill.catalog import SkillDoc, scan, route


def _mk_skill_dir(tmp_path):
    d = tmp_path / "skills"
    d.mkdir()
    (d / "brainstorming.md").write_text(
        "# brainstorming\n\n探索用户意图、需求与设计。Use when designing new features.",
        encoding="utf-8",
    )
    (d / "systematic-debugging.md").write_text(
        "# systematic-debugging\n\n任何 bug/测试失败/意外行为，先系统排查再修。Use when debugging.",
        encoding="utf-8",
    )
    return d


def test_scan_discovers_markdown_skills(tmp_path):
    """scan(目录) 返回每个 *.md 的 SkillDoc，含推断字段"""
    d = _mk_skill_dir(tmp_path)
    docs = scan(d)
    assert len(docs) == 2
    names = {x.name for x in docs}
    assert names == {"brainstorming", "systematic-debugging"}


def test_scan_parses_title_from_first_h1(tmp_path):
    """无 frontmatter 纯 md：name=文件名，description=首行 # 标题"""
    d = _mk_skill_dir(tmp_path)
    doc = scan(d)[0]
    assert doc.name in ("brainstorming", "systematic-debugging")
    assert doc.description in ("brainstorming", "systematic-debugging")


def test_parse_pure_md_without_frontmatter():
    """parse 解码无 frontmatter 纯 md：name=文件名 desc=首行标题 content=全文"""
    from macdev.skill.catalog import parse

    doc = parse("brainstorming", "brainstorming.md", "# 探索设计\n\n正文内容")
    assert doc.name == "brainstorming"
    assert doc.description == "探索设计"
    assert doc.content == "# 探索设计\n\n正文内容"


def test_route_debugging_to_systematic(tmp_path):
    """route(修bug) → systematic-debugging"""
    d = _mk_skill_dir(tmp_path)
    docs = scan(d)
    hit = route("帮我修复这个 bug", docs)
    assert hit is not None
    assert hit.name == "systematic-debugging"


def test_route_design_to_brainstorming(tmp_path):
    """route(新功能设计) → brainstorming"""
    d = _mk_skill_dir(tmp_path)
    docs = scan(d)
    hit = route("新功能设计需求", docs)
    assert hit is not None
    assert hit.name == "brainstorming"


def test_route_returns_none_on_no_match(tmp_path):
    """route 无匹配 → None（fallback 全量注入）"""
    d = _mk_skill_dir(tmp_path)
    docs = scan(d)
    assert route("随机闲聊话题", docs) is None


def test_scan_missing_dir_returns_empty():
    """目录不存在 → 空列表，不崩溃"""
    assert scan(Path("nope_missing_dir_xyz")) == []


def test_route_empty_catalog_returns_none():
    """空目录 route → None"""
    assert route("任意", []) is None
