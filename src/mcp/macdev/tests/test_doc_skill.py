import subprocess, sys
from pathlib import Path

def test_doc_generates_skill_docs(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "macdev", "doc", "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))
    assert r.returncode == 0, r.stderr
    for name in ("AUDIT_DOC.md", "PLAN.md"):
        assert (tmp_path / name).exists(), name

def test_skill_dir_present():
    assert (Path(__file__).resolve().parents[2] / "macdev-skill" / "SKILL.md").exists()

def test_skill_examples_present():
    root = Path(__file__).resolve().parents[2]
    assert (root / "macdev-skill" / "examples" / "sample_project" / "task.json").exists()
    assert (root / "macdev-skill" / "examples" / "sample_out" / "INTERFACE_CHAIN.md").exists()
    assert (root / "macdev-skill" / "examples" / "sample_out" / "PLAN_1.md").exists()
