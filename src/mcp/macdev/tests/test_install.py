import subprocess
import sys
from pathlib import Path


def _run(*args):
    return subprocess.run(
        [sys.executable, str(Path("macdev/scripts/install.py")), *args],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))


def test_install_target_copies_package(tmp_path):
    """--target 将 macdev 包整体复制进目标目录（物理副本，非 .pth 指针）。"""
    r = _run("--target", str(tmp_path))
    assert r.returncode == 0, r.stderr
    dst = tmp_path / "macdev"
    assert (dst / "__init__.py").exists()
    assert (dst / "__main__.py").exists()
    # 关键：不得再写 .pth 指针（语义漂移修复点）
    assert not (tmp_path / "macdev.pth").exists()


def test_install_idempotent_refresh(tmp_path):
    """重复安装 = 覆盖刷新快照（可一键重刷）。"""
    _run("--target", str(tmp_path))
    r = _run("--target", str(tmp_path))
    assert r.returncode == 0
    assert "已复制" in r.stdout
    assert (tmp_path / "macdev" / "__init__.py").exists()


def test_install_excludes_caches(tmp_path):
    """副本不携带 __pycache__/.pytest_cache。"""
    _run("--target", str(tmp_path))
    dst = tmp_path / "macdev"
    caches = [p for p in dst.rglob("*") if p.name in ("__pycache__", ".pytest_cache")]
    assert not caches, [str(p) for p in caches]


def test_uninstall(tmp_path):
    _run("--target", str(tmp_path))
    r = _run("--uninstall", "--target", str(tmp_path))
    assert r.returncode == 0
    assert "已移除" in r.stdout
    assert not (tmp_path / "macdev").exists()


def test_install_list_ok():
    r = _run("--list")
    assert r.returncode == 0
    assert "macdev 包:" in r.stdout