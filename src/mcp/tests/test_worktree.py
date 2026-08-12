import os
import shutil
import subprocess

import pytest

from mcp import worktree
from mcp.runtime import RunManager

HAVE_GIT = shutil.which("git") is not None

pytestmark = pytest.mark.skipif(not HAVE_GIT, reason="git is not installed")


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(repo), check=True)
    (repo / "f.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=str(repo), check=True)
    return str(repo)


def _patch_home(tmp_path, monkeypatch):
    home = tmp_path / "worktrees"
    monkeypatch.setattr(worktree, "get_worktrees_home_path", lambda: str(home))
    return str(home)


def test_not_git_directory_returns_error(tmp_path, monkeypatch):
    _patch_home(tmp_path, monkeypatch)
    result = worktree.create_task_worktree(str(tmp_path / "not_a_repo"))
    assert result.success is False
    assert "git" in result.message.lower()


@pytest.mark.parametrize("bad_id", ["../evil", "a/b", "a\\b", "a\x00b", "a..b"])
def test_invalid_task_id_rejected(tmp_path, monkeypatch, bad_id):
    repo = _make_repo(tmp_path)
    _patch_home(tmp_path, monkeypatch)
    result = worktree.create_task_worktree(repo, task_id=bad_id)
    assert result.success is False
    assert "invalid" in result.message.lower()


def test_validate_task_id():
    assert worktree.validate_task_id("abc12")
    assert not worktree.validate_task_id("../evil")
    assert not worktree.validate_task_id("a/b")
    assert not worktree.validate_task_id("a\\b")
    assert not worktree.validate_task_id("a\x00b")
    assert not worktree.validate_task_id("")
    assert not worktree.validate_task_id("..")


def test_create_success(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    _patch_home(tmp_path, monkeypatch)
    result = worktree.create_task_worktree(repo)
    assert result.success
    assert result.repo_root == repo
    assert result.path and os.path.isdir(result.path)
    assert os.path.exists(os.path.join(result.path, "f.txt"))
    assert result.task_id and len(result.task_id) == worktree.TASK_ID_LENGTH
    assert worktree.remove_worktree(result.path)


def test_duplicate_task_id_retries(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    _patch_home(tmp_path, monkeypatch)
    first = worktree.create_task_worktree(repo, task_id="abcde")
    assert first.success
    second = worktree.create_task_worktree(repo, task_id="abcde")
    assert second.success
    assert second.task_id != "abcde"
    assert second.path != first.path
    assert worktree.remove_worktree(first.path)
    assert worktree.remove_worktree(second.path)


def test_remove_success(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    _patch_home(tmp_path, monkeypatch)
    result = worktree.create_task_worktree(repo, task_id="abcde")
    assert result.success
    assert worktree.remove_worktree(result.path)
    assert not os.path.exists(result.path)


def test_list_worktrees(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    _patch_home(tmp_path, monkeypatch)
    entries = worktree.list_worktrees(cwd=repo)
    assert any(entry["path"] == repo for entry in entries)
    result = worktree.create_task_worktree(repo, task_id="abcde")
    assert result.success
    entries = worktree.list_worktrees(cwd=repo)
    assert any(entry["path"] == result.path for entry in entries)
    assert worktree.remove_worktree(result.path)


def test_run_manager_attach_and_cleanup(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    _patch_home(tmp_path, monkeypatch)
    manager = RunManager()
    record = manager.create_or_reject(thread_id="t1")
    result = worktree.create_task_worktree(repo, task_id="abcde")
    assert result.success
    manager.attach_worktree(record.run_id, result.path)
    assert manager.get(record.run_id).worktree_path == result.path
    manager.mark_success(record.run_id)
    assert manager.get(record.run_id).worktree_path is None
    assert not os.path.exists(result.path)


def test_run_manager_keep_worktree(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    _patch_home(tmp_path, monkeypatch)
    manager = RunManager()
    record = manager.create_or_reject(thread_id="t2")
    result = worktree.create_task_worktree(repo, task_id="abcde")
    assert result.success
    manager.attach_worktree(record.run_id, result.path)
    assert manager.cleanup_worktree(record.run_id, keep=True)
    assert manager.get(record.run_id).worktree_path == result.path
    assert manager.get(record.run_id).keep_worktree is True
    assert os.path.exists(result.path)
    assert manager.cleanup_worktree(record.run_id)
    assert not os.path.exists(result.path)
