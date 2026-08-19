"""workspace.py 递归扫描：发现 skills/ 深层 SKILL.md 与 *.md（macdev 子技能）"""
import sys
from pathlib import Path

from mcp.prompt.workspace import load_workspace_files

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _mk_root(tmp_path):
    root = tmp_path / "ws"
    (root / "skills").mkdir(parents=True)
    (root / "skills" / "macdev-skill").mkdir()
    (root / "skills" / "macdev-skill" / "SKILL.md").write_text(
        "---\nname: macdev\n---\n# macdev\n", encoding="utf-8")
    (root / "skills" / "macdev-skill" / "skills").mkdir()
    (root / "skills" / "macdev-skill" / "skills" / "brainstorming.md").write_text(
        "# brainstorming\n\nUse when designing features.\n", encoding="utf-8")
    (root / "skills" / "macdev-skill" / "skills" / "systematic-debugging.md").write_text(
        "# systematic-debugging\n\nUse when debugging.\n", encoding="utf-8")
    return root


def test_load_workspace_files_recursive_skill_discovery(tmp_path):
    """递归发现 skills/**/SKILL.md 与深层 *.md（macdev-skill/skills/*.md）"""
    root = _mk_root(tmp_path)
    ws = load_workspace_files(str(root))
    joined = "\n".join(ws.skills)
    assert "macdev" in joined  # SKILL.md
    assert "brainstorming" in joined  # 深层子技能 *.md
    assert "systematic-debugging" in joined
    assert len(ws.skills) >= 3


def test_load_workspace_files_no_skills_dir(tmp_path):
    """无 skills/ 目录 → 不崩溃，skills 空"""
    root = tmp_path / "empty"
    root.mkdir()
    ws = load_workspace_files(str(root))
    assert ws.skills == []
