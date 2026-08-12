import subprocess
import sys
from pathlib import Path


def test_install_target(tmp_path):
    """--target 写入 .pth，文件内容指向 macdev 父目录。"""
    r = subprocess.run(
        [sys.executable, str(Path("macdev/scripts/install.py")), "--target", str(tmp_path)],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))
    assert r.returncode == 0, r.stderr
    pth = tmp_path / "macdev.pth"
    assert pth.exists()
    content = pth.read_text(encoding="utf-8").strip()
    assert content and Path(content).is_dir()  # .pth 指向 macdev 父目录

def test_install_list_ok():
    r = subprocess.run(
        [sys.executable, str(Path("macdev/scripts/install.py")), "--list"],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))
    assert r.returncode == 0
    assert "macdev 包:" in r.stdout
