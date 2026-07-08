"""
SaberSystem 版本归档测试
扩展 CheckpointMiddleware 支持 snapshot_type 字段（见文档 §12.2）

TDD 红绿重构：先写失败测试，再实现最小代码通过。
"""
import os
import tempfile
from pathlib import Path

import pytest

from mcp.middleware.shadow_checkpoint import (
    ShadowGitCheckpointer,
    CheckpointMiddleware,
)


# ─── 单元测试：commit message 解析（无需 git）───


class TestParseCommitMetaWithSnapshotType:
    """_parse_commit_meta 解析 snapshot_type 字段"""

    def test_parses_6_field_format_with_snapshot_type(self):
        """新格式 6 字段: source|step|tool|instance|duration|snapshot_type"""
        raw = "saber|005|plan_operator|sess1234|150|plan_operator_run"
        meta = ShadowGitCheckpointer._parse_commit_meta(raw)
        assert meta["source"] == "saber"
        assert meta["step"] == 5
        assert meta["tool"] == "plan_operator"
        assert meta["instance"] == "sess1234"
        assert meta["duration_ms"] == 150
        assert meta["snapshot_type"] == "plan_operator_run"

    def test_parses_6_field_with_empty_snapshot_type(self):
        """空 snapshot_type 也应正确解析（兼容无类型快照）"""
        raw = "auto|003|write_file|sess1234|120|"
        meta = ShadowGitCheckpointer._parse_commit_meta(raw)
        assert meta["snapshot_type"] == ""

    def test_backward_compat_5_field_format(self):
        """旧格式 5 字段（无 snapshot_type）仍能解析，snapshot_type 默认空"""
        raw = "auto|003|write_file|sess1234|120"
        meta = ShadowGitCheckpointer._parse_commit_meta(raw)
        assert meta["source"] == "auto"
        assert meta["step"] == 3
        assert meta["tool"] == "write_file"
        assert meta["instance"] == "sess1234"
        assert meta["duration_ms"] == 120
        assert meta["snapshot_type"] == ""

    def test_backward_compat_old_bracket_format(self):
        """更旧的 [instance][step] tool 格式仍能解析"""
        raw = "[sess1234][3] write_file"
        meta = ShadowGitCheckpointer._parse_commit_meta(raw)
        assert meta["instance"] == "sess1234"
        assert meta["step"] == 3
        assert meta["tool"] == "write_file"
        assert meta["snapshot_type"] == ""

    def test_full_commit_message_with_prefix(self):
        """完整 commit message 含 'TS2 checkpoint: ' 前缀"""
        raw = "TS2 checkpoint: saber|007|plan_archive|sess1234|200|plan_archive"
        meta = ShadowGitCheckpointer._parse_commit_meta(raw)
        assert meta["snapshot_type"] == "plan_archive"
        assert meta["source"] == "saber"


# ─── 集成测试：git 仓库操作（需要 git 可用）───


def _git_available() -> bool:
    """检查 git 是否可用"""
    try:
        import subprocess
        r = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


pytestmark_git = pytest.mark.skipif(
    not _git_available(), reason="git 不可用"
)


class TestSnapshotWithSnapshotType:
    """snapshot() 方法支持 snapshot_type 参数"""

    @pytestmark_git
    def test_snapshot_with_type_creates_commit(self, tmp_path):
        """带 snapshot_type 的快照在 commit message 中包含类型"""
        cp = ShadowGitCheckpointer()
        ws = str(tmp_path)
        assert cp.ensure_init(ws, instance_id="test-saber")

        # 创建一个文件让 git 有变更可追踪
        (tmp_path / "plan.md").write_text("# Plan", encoding="utf-8")

        h = cp.snapshot(
            tool_name="plan_operator",
            source="saber",
            step=1,
            snapshot_type="plan_operator_run",
        )
        assert h is not None

        commits = cp.get_commits(5)
        assert len(commits) >= 1
        # 找到刚创建的 commit
        latest = commits[0]
        assert latest["meta"]["snapshot_type"] == "plan_operator_run"
        assert latest["meta"]["source"] == "saber"

    @pytestmark_git
    def test_snapshot_force_creates_empty_commit(self, tmp_path):
        """force=True 时即使无文件变更也创建 commit（Saber 状态快照）"""
        cp = ShadowGitCheckpointer()
        ws = str(tmp_path)
        assert cp.ensure_init(ws, instance_id="test-force")

        # 先创建一个初始 commit
        (tmp_path / "init.txt").write_text("init", encoding="utf-8")
        cp.snapshot(source="baseline", step=0)

        # 不修改任何文件，用 force=True 创建空 commit
        h = cp.snapshot(
            source="saber",
            step=1,
            snapshot_type="plan_archive",
            force=True,
        )
        assert h is not None  # force 模式下应返回 hash

        commits = cp.get_commits(5)
        latest = commits[0]
        assert latest["meta"]["snapshot_type"] == "plan_archive"

    @pytestmark_git
    def test_snapshot_without_force_returns_none_when_no_changes(self, tmp_path):
        """无 force 时，无文件变更返回 None（保持原有行为）"""
        cp = ShadowGitCheckpointer()
        ws = str(tmp_path)
        assert cp.ensure_init(ws, instance_id="test-noforce")

        # 初始 commit
        (tmp_path / "init.txt").write_text("init", encoding="utf-8")
        cp.snapshot(source="baseline", step=0)

        # 不修改文件，无 force
        h = cp.snapshot(source="auto", step=1, snapshot_type="plan_operator_run")
        assert h is None  # 原有行为：无变更不创建快照

    @pytestmark_git
    def test_get_commits_filters_by_snapshot_type(self, tmp_path):
        """get_commits 支持按 snapshot_type 过滤"""
        cp = ShadowGitCheckpointer()
        ws = str(tmp_path)
        assert cp.ensure_init(ws, instance_id="test-filter")

        # 创建不同类型的快照
        (tmp_path / "f1.txt").write_text("1", encoding="utf-8")
        cp.snapshot(source="saber", step=1, snapshot_type="plan_operator_run", force=True)

        (tmp_path / "f2.txt").write_text("2", encoding="utf-8")
        cp.snapshot(source="saber", step=2, snapshot_type="plan_archive", force=True)

        (tmp_path / "f3.txt").write_text("3", encoding="utf-8")
        cp.snapshot(source="auto", step=3)  # 无 snapshot_type

        # 过滤 plan_archive 类型
        archived = cp.get_commits(50, snapshot_type="plan_archive")
        assert len(archived) >= 1
        assert all(c["meta"]["snapshot_type"] == "plan_archive" for c in archived)

        # 过滤 plan_operator_run 类型
        operator_runs = cp.get_commits(50, snapshot_type="plan_operator_run")
        assert len(operator_runs) >= 1
        assert all(c["meta"]["snapshot_type"] == "plan_operator_run" for c in operator_runs)

        # 无过滤返回全部
        all_commits = cp.get_commits(50)
        assert len(all_commits) >= 3


class TestSaberSnapshotMethod:
    """CheckpointMiddleware.saber_snapshot() 方法"""

    @pytestmark_git
    def test_saber_snapshot_creates_typed_checkpoint(self, tmp_path):
        """saber_snapshot 创建带类型的快照"""
        mw = CheckpointMiddleware(workspace_root=str(tmp_path))
        mw._instance_id = "test-saber-mw"
        mw._ensure_ready()

        h = mw.saber_snapshot("plan_operator_run", tool_name="plan_operator")
        assert h is not None

        commits = mw.get_checkpoints(5)
        latest = commits[0]
        assert latest["meta"]["snapshot_type"] == "plan_operator_run"
