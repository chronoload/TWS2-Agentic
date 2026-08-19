"""skill_types from_skill_md 无 frontmatter 回退解码"""
import sys
from pathlib import Path

from mcp.skill_system.skill_types import Skill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_from_skill_md_without_frontmatter_fallback(tmp_path):
    """SKILL.md 无 frontmatter → 回退：name=目录名，description=首行标题"""
    d = tmp_path / "systematic-debugging"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "# systematic-debugging\n\nUse when debugging, test failures.\n", encoding="utf-8")
    skill = Skill.from_skill_md(d)
    assert skill is not None
    assert skill.name == "systematic-debugging"
    assert "systematic-debugging" in skill.description


def test_from_skill_md_with_frontmatter_unchanged(tmp_path):
    """有 frontmatter 的行为不变"""
    d = tmp_path / "brainstorming"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: brainstorming\n---\n# Brainstorming\n", encoding="utf-8")
    skill = Skill.from_skill_md(d)
    assert skill is not None
    assert skill.name == "brainstorming"


def test_from_skill_md_missing_returns_none(tmp_path):
    """无 SKILL.md → None"""
    d = tmp_path / "empty"
    d.mkdir()
    assert Skill.from_skill_md(d) is None
