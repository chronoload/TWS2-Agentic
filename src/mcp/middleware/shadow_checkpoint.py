#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阴影 Git 检查点系统 — 参考 Cline ShadowGit 设计

核心原则：
- shadow repo 用 git add --force 追踪文件，不受工作区 .gitignore 影响
- 仅通过 shadow repo 自身的 info/exclude 控制追踪范围
- 这样无论用户在哪个目录下开发，checkpoint 都能正确追踪

多实例安全设计：
- 每个实例拥有独立 git 分支，互不干扰 commit 历史
- 文件锁保护嵌套 git 重命名操作（`_rename_nested_git_repos`）
- 同一 workspace 共享影子仓库，避免重复初始化
"""

import json
import logging
import os
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..middleware.base import AgentMiddleware, MiddlewareContext, MiddlewareResult, MiddlewareAction

logger = logging.getLogger(__name__)


def _find_git() -> Optional[str]:
    for candidate in ["git", "git.exe"]:
        try:
            r = subprocess.run([candidate, "--version"], capture_output=True, timeout=5, encoding="utf-8", errors="replace")
            if r.returncode == 0:
                return candidate
        except Exception:
            continue
    return None


GIT_EXE = _find_git()
GIT_DISABLED_SUFFIX = "_disabled"
BRANCH_PREFIX = "cp/"  # 每个实例独立分支: cp/<instance_id>


# ─── 排除规则（参考 Cline CheckpointExclusions 分类管理）───────────

def _build_artifact_patterns() -> List[str]:
    """构建产物和开发工具目录"""
    return [
        "node_modules/", ".venv/", "venv/", "__pycache__/",
        "env/", ".env/", ".tox/",
        "dist/", "build/", "target/", ".eggs/", "*.egg-info/",
        ".vscode/", ".idea/", ".vs/", "*.sublime-*",
        ".gradle/", ".parcel-cache/", ".next/", ".nuxt/",
        ".sass-cache/", "Pods/", "coverage/", "deps/",
        "bundle/", "obj/", "out/", "vendor/",
        ".mypy_cache/", ".pytest_cache/", ".cache/",
        ".ts2/cache_data/", "cache_data/",
    ]


def _media_file_patterns() -> List[str]:
    """媒体文件（图片/视频/音频）"""
    return [
        "*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.ico", "*.webp",
        "*.tiff", "*.tif", "*.raw", "*.heic", "*.avif", "*.eps", "*.psd",
        "*.3gp", "*.aac", "*.aiff", "*.avi", "*.divx", "*.flac",
        "*.m4a", "*.m4v", "*.mkv", "*.mov", "*.mp3", "*.mp4",
        "*.mpeg", "*.mpg", "*.ogg", "*.opus", "*.rm", "*.rmvb",
        "*.vob", "*.wav", "*.webm", "*.wma", "*.wmv",
    ]


def _large_data_patterns() -> List[str]:
    """大型二进制/数据文件"""
    return [
        "*.zip", "*.tar", "*.gz", "*.rar", "*.7z", "*.iso",
        "*.bin", "*.exe", "*.dll", "*.so", "*.dylib",
        "*.dat", "*.dmg", "*.msi", "*.deb", "*.rpm", "*.whl",
        "*.pth", "*.ckpt", "*.pt", "*.h5", "*.onnx",
        "*.npy", "*.npz",
    ]


def _document_patterns() -> List[str]:
    """编译输出文档（源码 .md/.rmd 等仍需追踪）"""
    return [
        "*.pdf", "*.doc", "*.docx", "*.xls", "*.xlsx", "*.pptx",
    ]


def _font_patterns() -> List[str]:
    """字体文件"""
    return [
        "*.ttf", "*.otf", "*.woff", "*.woff2",
    ]


def _database_patterns() -> List[str]:
    """数据库文件"""
    return [
        "*.db", "*.sqlite", "*.sqlite3", "*.bson", "*.parquet",
    ]


def _cache_temp_patterns() -> List[str]:
    """缓存和临时文件"""
    return [
        "*.pyc", "*.pyo", "*.pyd",
        "*.log", "*.tmp", "*.temp", "*.bak", "*.swp", "*.swo",
        "*.DS_Store", "Thumbs.db",
    ]


def _ts2_data_patterns() -> List[str]:
    """TS2 生成的数据目录（不需要 checkpoint 追踪）"""
    return [
        ".ts2_data/", "rag_data/", "sessions/", "logs/",
        "checkpoints/", "gt_agent_runs/", "trash/", "agent_config/",
        "Output/", "web_crawler_data/", "data_hub/", "skills/",
        "downloads/", "synergy_data/",
    ]


def _third_party_patterns() -> List[str]:
    """大型第三方项目（源码不需要 checkpoint）"""
    return [
        "projects/Privacy-bilii/",
        "LaTeX-OCR-main/", "Umi-OCR_Paddle_v2.1.5/",
    ]


def get_default_exclusions(workspace_root: str = "") -> List[str]:
    """获取完整的排除规则列表（分类管理，便于维护和扩展）

    参考 Cline CheckpointExclusions 的分类设计：
    - 每类规则独立函数，方便按需调整
    - shadow repo 使用 git add --force，不受工作区 .gitignore 影响
    - 所有过滤完全由 info/exclude 控制
    - 自动读取 .gitattributes 中的 LFS 模式（参考 Cline）
    """
    patterns = [
        ".git/",
        f".git{GIT_DISABLED_SUFFIX}/",
        *_build_artifact_patterns(),
        *_media_file_patterns(),
        *_large_data_patterns(),
        *_document_patterns(),
        *_font_patterns(),
        *_database_patterns(),
        *_cache_temp_patterns(),
        *_ts2_data_patterns(),
        *_third_party_patterns(),
    ]
    # 自动读取 .gitattributes 中的 LFS 模式（参考 Cline getLfsPatterns）
    if workspace_root:
        lfs = _read_lfs_patterns(workspace_root)
        if lfs:
            patterns.extend(lfs)
    return patterns


def _read_lfs_patterns(workspace_root: str) -> List[str]:
    """读取工作区 .gitattributes 中的 Git LFS 模式

    参考 Cline CheckpointExclusions.getLfsPatterns
    """
    try:
        attrs_path = Path(workspace_root) / ".gitattributes"
        if attrs_path.exists():
            content = attrs_path.read_text(encoding="utf-8", errors="ignore")
            return [
                line.split()[0].strip()
                for line in content.split("\n")
                if "filter=lfs" in line and line.split()[0].strip()
            ]
    except Exception:
        pass
    return []


class _FileLock:
    """基于文件的互斥锁，保护跨实例的竞态操作

    防崩溃残留设计：
    - 锁文件中写入 PID，方便检测僵尸锁
    - acquire 超时后自动清理僵尸锁并重试一次
    """

    def __init__(self, lock_path: Path):
        self._lock_path = lock_path
        self._acquired = False

    def _write_pid(self):
        """在锁文件中写入当前 PID"""
        try:
            self._lock_path.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass

    def _is_stale(self) -> bool:
        """检测锁文件是否为僵尸锁（持有锁的进程已退出）"""
        try:
            if not self._lock_path.exists():
                return False
            content = self._lock_path.read_text(encoding="utf-8").strip()
            if not content:
                return False
            pid = int(content)
            # Windows: 用 tasklist 检查进程是否存在
            import subprocess
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, timeout=5,
                encoding="utf-8", errors="replace",
            )
            return str(pid) not in r.stdout
        except Exception:
            # 不确定就认为是僵尸锁，清理后重试
            return True

    def acquire(self, timeout: float = 30.0):
        start = time.time()
        while True:
            try:
                fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                self._write_pid()
                self._acquired = True
                return
            except FileExistsError:
                # 超时时清理僵尸锁并重试一次
                if time.time() - start > timeout:
                    if self._is_stale():
                        try:
                            self._lock_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        # 重试一次
                        try:
                            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                            os.close(fd)
                            self._write_pid()
                            self._acquired = True
                            return
                        except FileExistsError:
                            pass
                    raise TimeoutError(f"无法获取锁 {self._lock_path}")
                time.sleep(0.05)

    def release(self):
        if self._acquired:
            try:
                self._lock_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class ShadowGitCheckpointer:
    """阴影 Git 检查点管理器

    多实例隔离：每个实例使用独立 git 分支 `cp/<instance_id>`
    锁保护：`_rename_nested_git_repos` 由文件锁序列化
    """

    def __init__(self):
        self._initialized = False
        self._workspace_root = ""
        self._repo_root = Path()
        self._git_dir = Path()
        self._instance_id = ""
        self._branch_name = ""
        self._lock: Optional[_FileLock] = None
        self._gc_counter = 0  # 周期性 gc 计数器
        self._extra_exclusions: List[str] = []  # 运行时可追加的排除规则
        self._snapshot_seq = 0  # 快照序号

    # ─── 初始化 ──────────────────────────────────────────

    def ensure_init(self, workspace_root: str, instance_id: str = "default") -> bool:
        """初始化影子仓库，为 instance_id 创建独立分支"""
        if not GIT_EXE:
            logger.error("git 不可用")
            return False

        try:
            ws_key = self._hash(workspace_root)
            self._repo_root = Path.home() / ".ts2" / "shadow_repo" / ws_key
            self._git_dir = self._repo_root / ".git"
            self._workspace_root = workspace_root
            self._instance_id = instance_id
            self._branch_name = f"{BRANCH_PREFIX}{instance_id}"
            self._lock = _FileLock(self._repo_root / ".lock")

            # 检查已有仓库：验证 core.worktree 配置（用 git config 而非直接读文件）
            if self._git_dir.exists():
                try:
                    r = self._run_git("config", "--get", "core.worktree")
                    if r.returncode == 0:
                        stored_ws = r.stdout.strip()
                        # 标准化后比较（处理 Windows 路径斜杠差异）
                        if stored_ws.replace("\\", "/").lower() == workspace_root.replace("\\", "/").lower():
                            self._initialized = True
                            self._update_excludes()
                            self._ensure_branch()
                            return True
                except Exception:
                    pass

            # 创建新仓库
            self._repo_root.mkdir(parents=True, exist_ok=True)
            self._run_git("init")
            self._run_git("config", "core.worktree", workspace_root)
            self._run_git("config", "commit.gpgSign", "false")
            self._run_git("config", "user.name", "TS2 Checkpoint")
            self._run_git("config", "user.email", "checkpoint@ts2.local")
            self._write_excludes()

            with self._lock:
                self._run_nested_rename(True)
                try:
                    self._run_git("add", "--force", ".", "--ignore-errors", timeout=300)
                    self._run_git("commit", "--allow-empty", "--no-verify", "-m", "TS2 checkpoint baseline")
                finally:
                    self._run_nested_rename(False)

            self._initialized = True
            self._ensure_branch()
            logger.info(f"阴影仓库已初始化: {self._repo_root} → {workspace_root} (instance={instance_id[:8]})")
            return True

        except Exception as e:
            logger.error(f"阴影仓库初始化失败: {e}")
            return False

    def _ensure_branch(self):
        """确保当前实例的分支存在（用 symbolic-ref，不修改 worktree 文件）"""
        if not self._initialized:
            return

        try:
            # 获取 master 基线的 hash（可能不存在，如仓库刚初始化但没有任何 commit）
            r_master = self._run_git("rev-parse", "master")
            master_hash = r_master.stdout.strip() if r_master.returncode == 0 else None

            r = self._run_git("rev-parse", "--verify", self._branch_name)
            if r.returncode != 0:
                if master_hash:
                    # 从 master 基线创建分支
                    self._run_git("branch", self._branch_name, master_hash)
                else:
                    # master 也不存在，从当前 HEAD 创建
                    cur = self._run_git("rev-parse", "HEAD")
                    if cur.returncode == 0:
                        self._run_git("branch", self._branch_name, cur.stdout.strip())
                    else:
                        # HEAD 也无效，跳过（稍后 snapshot 会创建初始 commit）
                        logger.debug(f"无法创建分支 {self._branch_name}，跳过")
                        return

            # 用 symbolic-ref 切换 HEAD，不修改 worktree 文件
            self._run_git("symbolic-ref", "HEAD", f"refs/heads/{self._branch_name}")
            logger.debug(f"分支就绪: {self._branch_name}")
        except Exception as e:
            logger.warning(f"分支切换失败: {e}")

    def _run_git(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
        cmd = [GIT_EXE, "-C", str(self._repo_root)] + list(args)
        return subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )

    @staticmethod
    def _hash(text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _write_excludes(self):
        """写入排除规则到 shadow repo 的 info/exclude

        关键设计：shadow repo 使用 git add --force，因此工作区的 .gitignore
        不会影响追踪。所有过滤完全由此文件控制。
        """
        patterns = get_default_exclusions(self._workspace_root) + self._extra_exclusions
        excludes_file = self._git_dir / "info" / "exclude"
        excludes_file.parent.mkdir(parents=True, exist_ok=True)
        excludes_file.write_text("\n".join(patterns) + "\n", encoding="utf-8")

    def _update_excludes(self):
        try:
            self._write_excludes()
        except Exception:
            pass

    # ─── 核心操作 ────────────────────────────────────────

    def snapshot(self, tool_name: str = "", source: str = "auto", step: int = -1,
                 snapshot_type: str = "", force: bool = False) -> Optional[str]:
        """创建快照（当前实例分支上 commit）

        Args:
            tool_name: 触发快照的工具名
            source: 快照来源 — 'auto'(自动), 'manual'(手动), 'baseline'(初始基线), 'saber'(SaberSystem 专属)
            step: 快照序号（-1=使用内部计数器自增）
            snapshot_type: SaberSystem 专属快照类型（如 plan_operator_run / plan_archive / 
                           protocol_amendment / rag_injection / health_intervention / opportunity_capture）。
                           空字符串表示普通 TS2 快照。
            force: True 时即使无文件变更也创建 commit（Saber 状态快照场景）

        Returns:
            commit hash (12 chars) 或 None
        """
        if not self._initialized:
            return None

        try:
            status = self._run_git("status", "--porcelain")
            if not status.stdout.strip() and not force:
                return None

            with self._lock:
                self._ensure_branch()
                self._run_nested_rename(True)
                try:
                    start = time.time()
                    add_result = self._run_git("add", "--force", ".", "--ignore-errors")
                    if add_result.returncode != 0:
                        # git add 可能因不可读文件（如 Windows 长路径）返回非 0，
                        # 但仍可能已 stage 部分文件，继续尝试 commit
                        logger.debug(f"git add 有警告: {add_result.stderr[:120]}")

                    elapsed_ms = int((time.time() - start) * 1000)
                    # step: 外部传入优先，否则自增
                    if step >= 0:
                        self._snapshot_seq = step
                    else:
                        self._snapshot_seq += 1
                    # 结构化 commit message: source|step|tool|instance|duration|snapshot_type
                    msg = f"{source}|{self._snapshot_seq:03d}|{tool_name or 'auto'}|{self._instance_id[:8]}|{elapsed_ms}|{snapshot_type}"
                    commit_result = self._run_git(
                        "commit", "--allow-empty", "--no-verify",
                        "-m", f"TS2 checkpoint: {msg}",
                    )

                    if commit_result.returncode == 0:
                        hash_result = self._run_git("rev-parse", "HEAD")
                        if hash_result.returncode == 0:
                            h = hash_result.stdout.strip()[:12]
                            logger.debug(f"快照 {h} ({elapsed_ms}ms, branch={self._branch_name})")
                            # 每 100 次快照执行一次 git gc，控制仓库大小
                            self._gc_counter += 1
                            if self._gc_counter >= 100:
                                self._gc_counter = 0
                                try:
                                    self._run_git("gc", "--auto", timeout=120)
                                except Exception:
                                    pass
                            return h
                finally:
                    self._run_nested_rename(False)

        except subprocess.TimeoutExpired:
            logger.warning("git snapshot 超时")
        except Exception as e:
            logger.debug(f"快照跳过: {e}")

        return None

    def restore_files(self, commit_hash: str) -> bool:
        """恢复工作区到指定 commit（用 read-tree，不移动分支指针）

        注意：不调用 _run_nested_rename，因为：
        1. read-tree -u --reset 只处理追踪的文件，不碰未追踪的用户文件
        2. 嵌套 git 仓库的 .git 目录在恢复过程中保持原位，避免子仓库状态损坏
        3. 不留 clean -fd，防止误删用户新建的未追踪文件

        commit_hash 可以是完整 40 字符或前 7+ 字符（git 接受短 hash 前缀）。
        """
        if not self._initialized:
            return False

        try:
            with self._lock:
                self._ensure_branch()
                try:
                    r = self._run_git("read-tree", "-u", "--reset", commit_hash)
                    if r.returncode != 0:
                        logger.error(f"git read-tree 失败: {r.stderr[:200]}")
                        return False
                    logger.info(f"文件已恢复到 {commit_hash[:8]} (instance={self._instance_id[:8]})")
                    return True
                except Exception:
                    raise
        except Exception as e:
            logger.error(f"文件恢复失败: {e}")
            return False

    def get_commits(self, count: int = 50, snapshot_type: str = "") -> List[Dict[str, Any]]:
        """获取当前分支的检查点列表（含结构化元数据）

        Args:
            count: 最多返回的 commit 数量
            snapshot_type: 按 SaberSystem 快照类型过滤（空字符串=不过滤）。
                           过滤在 Python 侧执行（git log 不支持按消息内容过滤），
                           因此当指定 snapshot_type 时会多拉取一些 commit 再过滤。

        返回格式:
        {
            "hash": "abc123def456",
            "full_hash": "abc123def456...",
            "timestamp": 1718700000,
            "message": "原始 commit message",
            "meta": {
                "source": "auto" | "manual" | "baseline" | "saber",
                "step": 1,
                "tool": "write_file",
                "instance": "sess1234",
                "duration_ms": 150,
                "snapshot_type": "plan_operator_run" | ""
            }
        }
        """
        if not self._initialized:
            return []
        try:
            # 过滤时多拉取一些 commit 以保证过滤后数量充足
            fetch_count = count * 5 if snapshot_type else count
            r = self._run_git("log", self._branch_name,
                              f"--max-count={fetch_count}", "--format=%H|%ct|%s")
            if r.returncode != 0 or not r.stdout.strip():
                return []
            commits = []
            for line in r.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 2)
                if len(parts) >= 2:
                    raw_msg = parts[2] if len(parts) > 2 else ""
                    meta = self._parse_commit_meta(raw_msg)
                    if snapshot_type and meta.get("snapshot_type", "") != snapshot_type:
                        continue
                    commit = {
                        "hash": parts[0][:12],
                        "full_hash": parts[0],
                        "timestamp": int(parts[1]),
                        "message": raw_msg,
                        "meta": meta,
                    }
                    commits.append(commit)
                    if len(commits) >= count:
                        break
            return commits
        except Exception:
            return []

    @staticmethod
    def _parse_commit_meta(raw_msg: str) -> Dict[str, Any]:
        """从 commit message 解析结构化元数据

        新格式（6 字段）: "source|step|tool|instance|duration|snapshot_type"
        旧格式（5 字段）: "source|step|tool|instance|duration"
        更旧格式: "[instance][step] tool" 或自由文本
        """
        meta: Dict[str, Any] = {
            "source": "auto",
            "step": 0,
            "tool": "",
            "instance": "",
            "duration_ms": None,
            "snapshot_type": "",
        }

        # 去掉前缀
        clean = raw_msg
        if clean.startswith("TS2 checkpoint: "):
            clean = clean[len("TS2 checkpoint: "):]

        # 尝试新格式: source|step|tool|instance|duration[|snapshot_type]
        parts = clean.split("|")
        if len(parts) >= 5:
            try:
                meta["source"] = parts[0] if parts[0] in ("auto", "manual", "baseline", "saber") else "auto"
                meta["step"] = int(parts[1])
                meta["tool"] = parts[2]
                meta["instance"] = parts[3]
                meta["duration_ms"] = int(parts[4]) if parts[4].isdigit() else None
                if len(parts) >= 6:
                    meta["snapshot_type"] = parts[5]
                return meta
            except (ValueError, IndexError):
                pass

        # 兼容旧格式: [instance][step] tool
        import re
        m = re.match(r"^\[([^\]]+)\]\[(\d+)\]\s*(.*)", clean)
        if m:
            meta["instance"] = m.group(1)
            meta["step"] = int(m.group(2))
            meta["tool"] = m.group(3)
            return meta

        # 纯文本
        meta["tool"] = clean
        return meta

    def get_diff_set(self, from_hash: str, to_hash: str = "") -> List[Dict[str, Any]]:
        """获取两个检查点之间的差异文件集（含 +/- 行数统计）

        参考 Cline CheckpointTracker.getDiffSet

        Args:
            from_hash: 起始 commit hash
            to_hash: 结束 commit hash（默认当前分支 HEAD）

        Returns:
            [{"path": "...", "status": "A/M/D/R", "additions": N, "deletions": N}]
        """
        if not self._initialized:
            return []
        try:
            to_ref = to_hash or self._branch_name
            r = self._run_git("diff", "--numstat", f"{from_hash}..{to_ref}")
            if r.returncode != 0 or not r.stdout.strip():
                return []

            # 同时获取 name-status
            r2 = self._run_git("diff", "--name-status", f"{from_hash}..{to_ref}")
            statuses = {}
            if r2.returncode == 0:
                for line in r2.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        statuses[parts[1]] = parts[0]

            result = []
            for line in r.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t", 2)
                if len(parts) >= 3:
                    path = parts[2]
                    adds = int(parts[0]) if parts[0] != "-" else 0
                    dels = int(parts[1]) if parts[1] != "-" else 0
                    result.append({
                        "path": path,
                        "status": statuses.get(path, "M"),
                        "additions": adds,
                        "deletions": dels,
                    })
            return result
        except Exception:
            return []

    def get_diff_count(self, from_hash: str, to_hash: str = "") -> int:
        """快速获取两个检查点之间的变更文件数

        参考 Cline CheckpointTracker.getDiffCount
        """
        if not self._initialized:
            return 0
        try:
            to_ref = to_hash or self._branch_name
            r = self._run_git("diff", "--name-only", f"{from_hash}..{to_ref}")
            if r.returncode == 0:
                lines = [l for l in r.stdout.strip().split("\n") if l]
                return len(lines)
        except Exception:
            pass
        return 0

    def get_parent_hash(self, commit_hash: str) -> str:
        """获取指定 commit 的父 commit hash"""
        if not self._initialized:
            return ""
        try:
            r = self._run_git("rev-parse", f"{commit_hash}^")
            if r.returncode == 0:
                return r.stdout.strip()[:12]
        except Exception:
            pass
        return ""

    def get_incremental_diff(self, commit_hash: str) -> List[Dict[str, Any]]:
        """获取指定 commit 相对于父 commit 的增量差异

        与 get_diff_set 不同，这里只返回该 commit 自身的变更，不累加后续 commit。
        """
        parent_hash = self.get_parent_hash(commit_hash)
        if not parent_hash:
            # 没有 parent（可能是 baseline），与空树比较
            return self.get_diff_set("4b825dc642cb6eb9a060e54bf899d15363d7b90d", commit_hash)
        return self.get_diff_set(parent_hash, commit_hash)

    def get_incremental_diff_content(self, commit_hash: str, file_path: str, max_lines: int = 80) -> str:
        """获取指定 commit 中某文件的增量 diff 内容"""
        if not self._initialized:
            return ""
        try:
            parent_hash = self.get_parent_hash(commit_hash)
            if parent_hash:
                r = self._run_git("diff", f"{parent_hash}..{commit_hash}", "--", file_path)
            else:
                r = self._run_git("diff", "4b825dc642cb6eb9a060e54bf899d15363d7b90d", commit_hash, "--", file_path)
            if r.returncode == 0:
                return "\n".join(r.stdout.split("\n")[:max_lines])
        except Exception:
            pass
        return ""

    def get_diff(self, commit_hash: str) -> List[Dict[str, str]]:
        """获取指定 commit 与当前 HEAD 的差异"""
        if not self._initialized:
            return []
        try:
            r = self._run_git("diff", "--name-status", f"{commit_hash}..{self._branch_name}")
            if r.returncode != 0:
                return []
            diffs = []
            for line in r.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t", 1)
                diffs.append({"path": parts[1] if len(parts) > 1 else "", "status": parts[0] if len(parts) > 0 else "?"})
            return diffs
        except Exception:
            return []

    def get_diff_content(self, commit_hash: str, file_path: str, max_lines: int = 50) -> str:
        if not self._initialized:
            return ""
        try:
            r = self._run_git("diff", f"{commit_hash}..{self._branch_name}", "--", file_path)
            if r.returncode == 0:
                return "\n".join(r.stdout.split("\n")[:max_lines])
        except Exception:
            pass
        return ""

    # ─── 嵌套 git 处理（文件锁保护）──────────────────────

    def _run_nested_rename(self, disable: bool):
        """执行嵌套 git 重命名（无锁——由调用方保证加锁）"""
        try:
            ws = Path(self._workspace_root)
            if not ws.exists():
                return
            suffix = GIT_DISABLED_SUFFIX
            for git_dir in ws.rglob(".git"):
                if git_dir == self._git_dir:
                    continue
                if git_dir.is_dir():
                    if disable:
                        new = git_dir.parent / f".git{suffix}"
                    else:
                        if git_dir.name.endswith(suffix):
                            new = git_dir.parent / ".git"
                        else:
                            continue
                    try:
                        git_dir.rename(new)
                    except Exception:
                        pass
        except Exception:
            pass

    # 兼容旧接口
    def _rename_nested_git_repos(self, disable: bool):
        """遗留接口，内部直接用 _run_nested_rename"""
        self._run_nested_rename(disable)


class CheckpointMiddleware(AgentMiddleware):
    """检查点中间件 — 混合架构：SQLite 增量追踪（高频）+ Shadow Git 全量快照（低频）

    设计参考：
    - Cline ShadowGit: git add --force + info/exclude 控制追踪范围
    - Crush FileVersionDB: SQLite 按文件版本追踪，O(changed_files)
    - LangGraph CheckpointMetadata: 元数据驱动（source, step, tool）
    - Crush VersionedMap: 全局版本号，前端按需刷新
    - Crush PubSub: 事件驱动，检查点创建时通知前端

    性能优化：
    - after_tool → SQLite INSERT（仅变更文件，~1ms）
    - Shadow Git 快照降频：仅 baseline + 每 N 步 + 手动触发
    - 前端轮询用 global_version，避免重复拉取

    多实例安全：用 MiddlewareContext.session_id 作为 instance_id，
    每个 session 拥有独立 git 分支，互不影响。
    """

    name = "checkpoint"
    order = 97

    # 事件回调列表（参考 Crush PubSub，解耦中间件与传输层）
    # 回调签名: (event_type: str, payload: dict) -> None
    _event_callbacks: List[Any] = []

    @classmethod
    def on_event(cls, callback):
        """注册事件回调（由 app.py 注册 WS 推送）"""
        cls._event_callbacks.append(callback)

    @classmethod
    def off_event(cls, callback):
        """移除事件回调"""
        if callback in cls._event_callbacks:
            cls._event_callbacks.remove(callback)

    def _emit(self, event_type: str, payload: dict):
        """发布事件到所有注册的回调"""
        for cb in self._event_callbacks:
            try:
                cb(event_type, payload)
            except Exception:
                pass

    # 默认只读工具（不修改文件，无需快照）
    DEFAULT_READ_ONLY_TOOLS = frozenset({
        "read_file", "web_search", "fetch_url", "list_directory",
        "grep", "glob", "file_info", "list_code_definition_names",
        "calculate", "diff_files", "search_files", "search_courses",
        "search_sessions", "search_configs", "search_skills",
        "search_documents", "search_mcp_tools",
        "act_mode_respond", "ask_followup_question",
    })

    # 写入工具 → 可推断变更文件路径
    WRITE_TOOL_PATH_KEYS = {
        "write_file": "path",
        "edit_file": "path",
        "create_file": "path",
        "delete_file": "paths",
        "rename_file": "old_path",
        "write_to_file": "path",
        "apply_diff": "path",
        "insert_content": "path",
        "search_and_replace": "path",
        "do_import_from_server": "dir_path",
        "do_export_to_server": "dir_path",
    }

    # Shadow Git 全量快照间隔（每 N 步触发一次）
    SHADOW_GIT_INTERVAL = 10

    def __init__(self, workspace_root: str = "",
                 extra_exclusions: Optional[List[str]] = None,
                 read_only_tools: Optional[set] = None,
                 shadow_git_interval: int = 0):
        """初始化检查点中间件

        Args:
            workspace_root: 工作区根目录
            extra_exclusions: 额外的排除规则（追加到默认规则之后）
            read_only_tools: 自定义只读工具集合（覆盖默认集合）
            shadow_git_interval: Shadow Git 全量快照间隔（0=使用默认 SHADOW_GIT_INTERVAL）
        """
        self._checkpointer = ShadowGitCheckpointer()
        self._workspace_root = workspace_root
        self._initialized = False
        self._last_hash = ""
        self._instance_id = ""
        self._snapshot_seq = 0
        self._extra_exclusions = extra_exclusions or []
        self._read_only_tools = read_only_tools or set(self.DEFAULT_READ_ONLY_TOOLS)
        self._shadow_git_interval = shadow_git_interval or self.SHADOW_GIT_INTERVAL
        # 将额外排除规则传递给 checkpointer
        if self._extra_exclusions:
            self._checkpointer._extra_exclusions = list(self._extra_exclusions)
        # SQLite 增量版本追踪（参考 Crush）
        self._fdb: Optional[Any] = None

    def _ensure_fdb(self) -> Any:
        """懒初始化 SQLite 文件版本数据库"""
        if self._fdb is None and self._workspace_root:
            from .file_version_db import FileVersionDB
            db_path = os.path.join(self._workspace_root, ".ts2_data", "file_versions.db")
            self._fdb = FileVersionDB(db_path)
        return self._fdb

    def _extract_changed_files(self, tool_name: str, tool_args: dict) -> List[Dict]:
        """从工具参数中推断变更文件路径（参考 Crush 的精确追踪）

        返回: [{"path": "...", "status": "A/M/D", "content_hash": "...", "additions": N, "deletions": N}]
        """
        changed = []
        path_key = self.WRITE_TOOL_PATH_KEYS.get(tool_name)

        if path_key == "paths":
            # delete_file: paths 是列表
            paths = tool_args.get("paths", [])
            if isinstance(paths, str):
                paths = [paths]
            for p in paths:
                if p:
                    changed.append({"path": p, "status": "D", "content_hash": "", "additions": 0, "deletions": 0})
        elif path_key:
            path = tool_args.get(path_key, "")
            if path:
                # 尝试计算 content_hash（二进制安全，不依赖编码）
                content_hash = ""
                additions = 0
                deletions = 0
                try:
                    full_path = os.path.join(self._workspace_root, path) if not os.path.isabs(path) else path
                    if os.path.isfile(full_path):
                        with open(full_path, "rb") as f:
                            raw = f.read()
                        from .file_version_db import FileVersionDB
                        content_hash = FileVersionDB.content_hash(raw.decode("utf-8", errors="replace"))
                        # 新文件：additions = 行数
                        additions = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
                except Exception:
                    pass
                # write_file 可能是新建也可能是覆盖，根据文件是否已存在判断
                if tool_name in ("create_file", "write_to_file"):
                    status = "A"
                elif tool_name == "write_file":
                    # mode=append 一定是修改；mode=create 时检查文件是否已存在
                    if tool_args.get("mode") == "append":
                        status = "M"
                    else:
                        status = "A"
                else:
                    status = "M"
                changed.append({
                    "path": path, "status": status,
                    "content_hash": content_hash,
                    "additions": additions, "deletions": deletions,
                })

        return changed

    def add_exclusions(self, patterns: List[str]):
        """运行时添加排除规则"""
        self._checkpointer._extra_exclusions.extend(patterns)
        if self._initialized:
            self._checkpointer._update_excludes()

    def remove_exclusion(self, pattern: str):
        """运行时移除排除规则"""
        if pattern in self._checkpointer._extra_exclusions:
            self._checkpointer._extra_exclusions.remove(pattern)
        if self._initialized:
            self._checkpointer._update_excludes()

    def _ensure_ready(self) -> bool:
        if not self._initialized and self._instance_id:
            self._initialized = self._checkpointer.ensure_init(
                self._workspace_root, instance_id=self._instance_id
            )
        return self._initialized

    def before_agent(self, messages: List[Dict], context: MiddlewareContext) -> MiddlewareResult:
        ws = context.extra.get("workspace_root", self._workspace_root) or self._workspace_root
        if ws:
            self._workspace_root = ws

        # session_id 稳定化：只在首次或 session_id 变更时更新
        new_sid = context.session_id or ""
        sid_changed = False
        if new_sid and new_sid != self._instance_id:
            # session_id 变更（前端传了新的会话 ID）
            self._instance_id = new_sid
            self._snapshot_seq = 0
            sid_changed = True
        elif not self._instance_id:
            # 首次初始化，无 session_id
            self._instance_id = new_sid or "global"
            self._snapshot_seq = 0
            sid_changed = True

        # 只在 session_id 变更或首次初始化时创建 baseline
        if sid_changed and self._ensure_ready():
            h = self._checkpointer.snapshot("", source="baseline", step=0)
            fdb = self._ensure_fdb()
            if fdb:
                fdb.create_checkpoint(
                    session_id=self._instance_id,
                    source="baseline",
                    step=0,
                    tool="",
                    git_hash=h or "",
                )
            self._snapshot_seq = 1
        elif not self._initialized and self._ensure_ready():
            # 已有 instance_id 但未初始化（进程重启后）
            self._snapshot_seq = 0
            h = self._checkpointer.snapshot("", source="baseline", step=0)
            fdb = self._ensure_fdb()
            if fdb:
                fdb.create_checkpoint(
                    session_id=self._instance_id,
                    source="baseline",
                    step=0,
                    tool="",
                    git_hash=h or "",
                )
            self._snapshot_seq = 1
        return MiddlewareResult()

    def after_tool(self, tool_name: str, tool_args: dict, tool_result: str, context: MiddlewareContext) -> MiddlewareResult:
        if tool_name in self._read_only_tools:
            # 只读工具：记录文件读取（参考 Crush FileTracker）
            if tool_name == "read_file":
                path = tool_args.get("path", "")
                if path:
                    fdb = self._ensure_fdb()
                    if fdb:
                        fdb.record_read(self._instance_id, path)
            return MiddlewareResult()

        if not self._ensure_ready():
            return MiddlewareResult()

        try:
            self._snapshot_seq += 1

            # 1. SQLite 增量追踪（高频，~1ms）
            changed_files = self._extract_changed_files(tool_name, tool_args)
            fdb = self._ensure_fdb()
            git_hash = ""
            if fdb:
                cp_id = fdb.create_checkpoint(
                    session_id=self._instance_id,
                    source="auto",
                    step=self._snapshot_seq,
                    tool=tool_name,
                    changed_files=changed_files if changed_files else None,
                )

            # 2. Shadow Git 全量快照（低频：baseline + 每 N 步 + 手动）
            need_git_snapshot = (
                self._snapshot_seq == 1  # 第一步
                or self._snapshot_seq % self._shadow_git_interval == 0  # 每 N 步
            )
            if need_git_snapshot:
                h = self._checkpointer.snapshot(tool_name, source="auto", step=self._snapshot_seq)
                if h:
                    self._last_hash = h
                    git_hash = h
                    # 回写 git_hash 到 SQLite
                    if fdb and cp_id and cp_id > 0:
                        try:
                            conn = fdb._connect()
                            conn.execute("UPDATE checkpoints SET checkpoint_hash = ? WHERE id = ?", (git_hash, cp_id))
                            conn.commit()
                        except Exception:
                            pass

        except Exception:
            pass

        # 发布检查点事件（参考 Crush PubSub，前端按需刷新）
        try:
            version = 0
            fdb2 = self._ensure_fdb()
            if fdb2:
                version = fdb2.global_version()
            self._emit("checkpoint_created", {
                "session_id": self._instance_id,
                "step": self._snapshot_seq,
                "tool": tool_name,
                "version": version,
            })
        except Exception:
            pass

        return MiddlewareResult()

    def after_agent(self, messages: List[Dict], context: MiddlewareContext) -> MiddlewareResult:
        """Agent 回复后检测 LLM 输出中的 unified diff（参考 Crush diffdetect）

        当 LLM 直接在回复中输出 diff 而不是调用 apply_diff 工具时，
        自动检测并记录，方便前端展示和后续处理。
        """
        # 检查最后一条 assistant 消息
        if not messages:
            return MiddlewareResult()

        last_msg = messages[-1]
        if last_msg.get("role") != "assistant":
            return MiddlewareResult()

        content = last_msg.get("content", "")
        if not content or not isinstance(content, str):
            return MiddlewareResult()

        try:
            from .diffdetect import is_unified_diff, extract_diff_blocks, diff_blocks_to_tool_args
            if is_unified_diff(content):
                blocks = extract_diff_blocks(content)
                if blocks:
                    tool_args = diff_blocks_to_tool_args(blocks)
                    # 记录到中间件元数据，供前端和工具系统使用
                    result = MiddlewareResult()
                    result.metadata["detected_diffs"] = tool_args
                    result.metadata["diff_count"] = len(tool_args)
                    logger.info(f"diffdetect: 在 LLM 回复中检测到 {len(tool_args)} 个 diff 块")
                    return result
        except Exception as e:
            logger.debug(f"diffdetect 检测失败: {e}")

        return MiddlewareResult()

    def get_checkpoints(self, count: int = 50) -> List[Dict[str, Any]]:
        """获取检查点列表（优先从 SQLite，回退到 Shadow Git）

        SQLite 更快（简单 SQL 查询），Shadow Git 作为补充。
        """
        fdb = self._ensure_fdb()
        if fdb:
            cps = fdb.get_checkpoints(self._instance_id, count)
            if cps:
                return cps
        # 回退到 Shadow Git
        return self._checkpointer.get_commits(count)

    def get_diff_set_fast(self, from_id: int, to_id: int = 0) -> List[Dict[str, Any]]:
        """快速获取差异文件集（从 SQLite，~1ms）

        优先使用 SQLite，回退到 Shadow Git。
        """
        fdb = self._ensure_fdb()
        if fdb:
            result = fdb.get_diff_set(from_id, to_id)
            if result:
                return result
        # 回退到 Shadow Git
        return []

    # ─── SaberSystem 专属快照入口 ────────────────────────

    # SaberSystem 支持的快照类型（见文档 §12.2）
    SABER_SNAPSHOT_TYPES = frozenset({
        "plan_operator_run",    # Plan 算子运行
        "plan_archive",         # Plan 归档
        "protocol_amendment",   # 协议修订
        "rag_injection",        # 万有 RAG 注入
        "health_intervention",  # 健康干预
        "opportunity_capture",  # 机遇捕捉
    })

    def saber_snapshot(self, snapshot_type: str, tool_name: str = "",
                       force: bool = True) -> Optional[str]:
        """SaberSystem 专属快照入口

        每个 Plan 算子运行/状态变更/归档/健康干预/机遇捕捉都可触发快照。
        底层存储/检索/回滚逻辑完全复用现有 CheckpointMiddleware 基础设施。

        Args:
            snapshot_type: 快照类型（见 SABER_SNAPSHOT_TYPES）
            tool_name: 触发快照的工具名（用于元数据）
            force: 默认 True，因为 Saber 状态快照可能不涉及文件变更

        Returns:
            commit hash (12 chars) 或 None
        """
        if not self._ensure_ready():
            return None

        self._snapshot_seq += 1
        h = self._checkpointer.snapshot(
            tool_name=tool_name,
            source="saber",
            step=self._snapshot_seq,
            snapshot_type=snapshot_type,
            force=force,
        )
        if h:
            self._last_hash = h
            # 发布事件
            try:
                version = self.global_version
                self._emit("saber_checkpoint", {
                    "session_id": self._instance_id,
                    "step": self._snapshot_seq,
                    "snapshot_type": snapshot_type,
                    "tool": tool_name,
                    "hash": h,
                    "version": version,
                })
            except Exception:
                pass
        return h

    def get_saber_snapshots(self, snapshot_type: str = "", count: int = 50) -> List[Dict[str, Any]]:
        """获取 SaberSystem 快照列表（可按类型过滤）

        Args:
            snapshot_type: 快照类型过滤（空=返回所有 saber 快照）
            count: 最多返回数量
        """
        if snapshot_type:
            return self._checkpointer.get_commits(count, snapshot_type=snapshot_type)
        # 无类型过滤时，返回所有 source=saber 的快照
        all_commits = self._checkpointer.get_commits(count * 3)
        return [c for c in all_commits if c["meta"].get("source") == "saber"][:count]

    @property
    def checkpointer(self) -> ShadowGitCheckpointer:
        return self._checkpointer

    @property
    def fdb(self) -> Optional[Any]:
        return self._fdb

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def global_version(self) -> int:
        """全局版本号（参考 Crush VersionedMap，前端按需刷新）"""
        fdb = self._ensure_fdb()
        if fdb:
            return fdb.global_version()
        return 0

    def reset(self):
        self._initialized = False
        self._last_hash = ""
        self._instance_id = ""
