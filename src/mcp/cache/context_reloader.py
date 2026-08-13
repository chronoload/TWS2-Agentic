#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上下文重载器 — 参考 Cline ContextManager 设计
会话检查点、增量恢复、上下文历史追踪
"""

import time
import json
import logging
import random
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from .disk import get_disk_store

logger = logging.getLogger(__name__)


@dataclass
class ContextUpdate:
    timestamp: float
    update_type: str  # "text", "tool_call", "tool_result", "reasoning"
    data: Any
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "update_type": self.update_type,
            "data": self.data,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ContextUpdate":
        return cls(
            timestamp=d.get("timestamp", 0),
            update_type=d.get("update_type", "text"),
            data=d.get("data", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass
class FileSnapshot:
    """文件快照 — 记录单个文件在检查点时的状态"""
    path: str              # 相对于 workspace_root 的路径
    content_hash: str      # 内容哈希（快速比对）
    content: str = ""      # 文件内容（小文件内联存储）
    stored_externally: bool = False  # 大文件存储在外部

    def to_dict(self) -> Dict:
        d = {
            "path": self.path,
            "content_hash": self.content_hash,
            "stored_externally": self.stored_externally,
        }
        if not self.stored_externally:
            d["content"] = self.content
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "FileSnapshot":
        return cls(
            path=d.get("path", ""),
            content_hash=d.get("content_hash", ""),
            content=d.get("content", ""),
            stored_externally=d.get("stored_externally", False),
        )


@dataclass
class ContextCheckpoint:
    checkpoint_id: str
    timestamp: float
    message_index: int
    total_messages: int
    total_tokens: int
    summary: str = ""
    messages_snapshot: List[Dict] = field(default_factory=list)
    context_updates: List[ContextUpdate] = field(default_factory=list)
    # ─── 新增：文件级快照（参考 Cline CheckpointTracker）───
    git_commit_hash: str = ""                    # git commit hash（如果可用）
    file_snapshots: List[FileSnapshot] = field(default_factory=list)  # 文件快照列表
    workspace_root: str = ""                     # 工作区根目录

    def to_dict(self) -> Dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "message_index": self.message_index,
            "total_messages": self.total_messages,
            "total_tokens": self.total_tokens,
            "summary": self.summary,
            "messages_snapshot": self.messages_snapshot,
            "context_updates": [u.to_dict() for u in self.context_updates],
            "git_commit_hash": self.git_commit_hash,
            "file_snapshots": [f.to_dict() for f in self.file_snapshots],
            "workspace_root": self.workspace_root,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ContextCheckpoint":
        return cls(
            checkpoint_id=d.get("checkpoint_id", ""),
            timestamp=d.get("timestamp", 0),
            message_index=d.get("message_index", 0),
            total_messages=d.get("total_messages", 0),
            total_tokens=d.get("total_tokens", 0),
            summary=d.get("summary", ""),
            messages_snapshot=d.get("messages_snapshot", []),
            context_updates=[
                ContextUpdate.from_dict(u) for u in d.get("context_updates", [])
            ],
            git_commit_hash=d.get("git_commit_hash", ""),
            file_snapshots=[
                FileSnapshot.from_dict(f) for f in d.get("file_snapshots", [])
            ],
            workspace_root=d.get("workspace_root", ""),
        )


@dataclass
class ConversationSnapshot:
    conversation_id: str
    title: str
    created_at: str
    last_checkpoint_id: str = ""
    total_rounds: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "created_at": self.created_at,
            "last_checkpoint_id": self.last_checkpoint_id,
            "total_rounds": self.total_rounds,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_cost": self.total_cost,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ConversationSnapshot":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ContextReloader:
    """
    上下文重载器 — 类似 Cline ContextManager

    功能：
    - 创建/恢复检查点
    - 增量上下文更新
    - 会话快照管理
    - checkpoint 持久化
    """

    def __init__(self):
        self._disk = get_disk_store()
        self._active_checkpoints: Dict[str, ContextCheckpoint] = {}
        self._pending_updates: Dict[int, Dict[int, List[ContextUpdate]]] = {}
        self._conversation_snapshots: Dict[str, ConversationSnapshot] = {}
        self._lock = __import__("threading").RLock()

    def create_checkpoint(
        self,
        messages: List[Dict],
        message_index: int = 0,
        total_tokens: int = 0,
        summary: str = "",
        workspace_root: str = "",
        snapshot_files: bool = False,
        file_patterns: Optional[List[str]] = None,
    ) -> ContextCheckpoint:
        with self._lock:
            cid = f"cp-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
            
            # 按需收集文件快照（默认不快照，避免性能问题）
            file_snapshots = []
            git_hash = ""
            if snapshot_files and workspace_root:
                file_snapshots = self._snapshot_files(workspace_root, file_patterns)
                git_hash = self._git_commit(workspace_root)
            
            checkpoint = ContextCheckpoint(
                checkpoint_id=cid,
                timestamp=time.time(),
                message_index=message_index,
                total_messages=len(messages),
                total_tokens=total_tokens,
                summary=summary,
                messages_snapshot=deepcopy(messages),
                git_commit_hash=git_hash,
                file_snapshots=file_snapshots,
                workspace_root=workspace_root,
            )
            self._active_checkpoints[cid] = checkpoint
            return checkpoint

    def restore_checkpoint(
        self, checkpoint_id: str
    ) -> Optional[ContextCheckpoint]:
        # 命名空间守卫：检查点 key 必须为 cp-* 格式。会话 ID（sess_*）等其它命名空间
        # 标识符不应进入本系统（历史 bug：曾把 session_id 传入导致「检查点不存在」假警报）
        if not checkpoint_id or not str(checkpoint_id).startswith("cp-"):
            logger.warning(f"检查点 key 命名空间不符（应为 cp-*）: {checkpoint_id}")
            return None
        with self._lock:
            checkpoint = self._active_checkpoints.get(checkpoint_id)
            if checkpoint:
                logger.info(f"恢复检查点: {checkpoint_id} (消息索引={checkpoint.message_index})")
                return checkpoint

        # 磁盘读取不需要锁（disk store 自带锁）
        data = self._disk.checkpoint_store.get(checkpoint_id)
        if data:
            checkpoint = ContextCheckpoint.from_dict(data)
            with self._lock:
                self._active_checkpoints[checkpoint_id] = checkpoint
            logger.info(f"从磁盘恢复检查点: {checkpoint_id}")
            return checkpoint

        logger.warning(f"检查点不存在: {checkpoint_id}")
        return None

    def save_checkpoint(self, checkpoint: ContextCheckpoint):
        with self._lock:
            self._active_checkpoints[checkpoint.checkpoint_id] = checkpoint
        self._disk.checkpoint_store.set(
            checkpoint.checkpoint_id, checkpoint.to_dict()
        )

    def delete_checkpoint(self, checkpoint_id: str):
        # 命名空间守卫：与 restore_checkpoint 一致，拒绝非 cp-* 的 key（防误删）
        if not checkpoint_id or not str(checkpoint_id).startswith("cp-"):
            logger.warning(f"检查点 key 命名空间不符（应为 cp-*）: {checkpoint_id}")
            return
        with self._lock:
            self._active_checkpoints.pop(checkpoint_id, None)
        self._disk.checkpoint_store.delete(checkpoint_id)

    def list_checkpoints(self) -> List[str]:
        disk_keys = self._disk.checkpoint_store.list_keys()
        with self._lock:
            active_keys = list(self._active_checkpoints.keys())
        all_keys = set(disk_keys) | set(active_keys)
        return sorted(all_keys, reverse=True)

    def add_context_update(
        self,
        message_index: int,
        block_index: int,
        update: ContextUpdate,
    ):
        if message_index not in self._pending_updates:
            self._pending_updates[message_index] = {}
        if block_index not in self._pending_updates[message_index]:
            self._pending_updates[message_index][block_index] = []
        self._pending_updates[message_index][block_index].append(update)

    def get_context_updates(
        self, message_index: int, block_index: int
    ) -> List[ContextUpdate]:
        return self._pending_updates.get(message_index, {}).get(block_index, [])

    def get_latest_update(
        self, message_index: int, block_index: int
    ) -> Optional[ContextUpdate]:
        updates = self.get_context_updates(message_index, block_index)
        return updates[-1] if updates else None

    def truncate_updates(self, max_timestamp: float):
        for msg_idx, blocks in list(self._pending_updates.items()):
            for blk_idx, updates in list(blocks.items()):
                cutoff = 0
                while cutoff < len(updates) and updates[cutoff].timestamp <= max_timestamp:
                    cutoff += 1
                if cutoff < len(updates):
                    updates[:] = updates[:cutoff]
                if not updates:
                    del blocks[blk_idx]
            if not blocks:
                del self._pending_updates[msg_idx]

    def create_conversation_snapshot(
        self,
        conversation_id: str,
        title: str = "",
        checkpoint_id: str = "",
    ) -> ConversationSnapshot:
        snapshot = ConversationSnapshot(
            conversation_id=conversation_id,
            title=title,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            last_checkpoint_id=checkpoint_id,
        )
        self._conversation_snapshots[conversation_id] = snapshot
        return snapshot

    def update_conversation_snapshot(
        self, conversation_id: str, **kwargs
    ):
        if conversation_id in self._conversation_snapshots:
            for key, value in kwargs.items():
                if hasattr(self._conversation_snapshots[conversation_id], key):
                    setattr(self._conversation_snapshots[conversation_id], key, value)

    def get_conversation_snapshot(
        self, conversation_id: str
    ) -> Optional[ConversationSnapshot]:
        return self._conversation_snapshots.get(conversation_id)

    def rollback_to_checkpoint(
        self, checkpoint_id: str
    ) -> Optional[List[Dict]]:
        checkpoint = self.restore_checkpoint(checkpoint_id)
        if checkpoint is None:
            return None

        with self._lock:
            max_ts = checkpoint.timestamp
            self.truncate_updates(max_ts)
            return deepcopy(checkpoint.messages_snapshot)

    def restore_workspace(self, checkpoint_id: str) -> bool:
        """恢复工作区文件到检查点状态（参考 Cline 的 workspace 恢复模式）"""
        checkpoint = self.restore_checkpoint(checkpoint_id)
        if not checkpoint or not checkpoint.file_snapshots:
            return False

        workspace = checkpoint.workspace_root
        if not workspace:
            return False

        restored = 0
        for snap in checkpoint.file_snapshots:
            try:
                target = Path(workspace) / snap.path
                if snap.stored_externally:
                    # 大文件从外部存储读取
                    data = self._disk.file_store.get(f"file:{checkpoint_id}:{snap.path}")
                    if data:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(data, encoding="utf-8")
                        restored += 1
                elif snap.content is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(snap.content, encoding="utf-8")
                    restored += 1
            except Exception as e:
                logger.warning(f"恢复文件 {snap.path} 失败: {e}")

        # git reset（如果有 commit hash）
        if checkpoint.git_commit_hash:
            self._git_reset(workspace, checkpoint.git_commit_hash)

        logger.info(f"工作区恢复完成: {restored}/{len(checkpoint.file_snapshots)} 个文件")
        return restored > 0

    def get_file_diffs(self, checkpoint_id: str) -> List[Dict[str, str]]:
        """获取检查点与当前工作区的文件差异（参考 Cline 的 presentMultifileDiff）"""
        checkpoint = self.restore_checkpoint(checkpoint_id)
        if not checkpoint or not checkpoint.file_snapshots:
            return []

        workspace = checkpoint.workspace_root
        diffs = []
        for snap in checkpoint.file_snapshots:
            try:
                current_path = Path(workspace) / snap.path
                if current_path.exists():
                    current_content = current_path.read_text(encoding="utf-8")
                    current_hash = self._hash_content(current_content)
                    if current_hash != snap.content_hash:
                        diffs.append({
                            "path": snap.path,
                            "before": snap.content,
                            "after": current_content,
                            "status": "modified",
                        })
                else:
                    diffs.append({
                        "path": snap.path,
                        "before": snap.content,
                        "after": "",
                        "status": "deleted",
                    })
            except Exception:
                pass

        return diffs

    # ─── 文件快照辅助方法 ──────────────────────────────────

    def _snapshot_files(
        self,
        workspace_root: str,
        patterns: Optional[List[str]] = None,
        max_file_size: int = 100_000,
    ) -> List[FileSnapshot]:
        """快照工作区文件"""
        root = Path(workspace_root)
        if not root.exists():
            return []

        # 默认快照的文件模式
        if patterns is None:
            patterns = ["*.py", "*.md", "*.json", "*.yaml", "*.yml", "*.toml", "*.txt", "*.rmd"]

        # 排除的目录
        excluded_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
            ".ts2", "cache_data", "logs",
        }

        snapshots = []
        for pattern in patterns:
            for filepath in root.rglob(pattern):
                # 跳过排除目录
                if any(part in excluded_dirs for part in filepath.parts):
                    continue
                # 跳过隐藏文件
                if any(part.startswith(".") for part in filepath.parts):
                    continue

                try:
                    stat = filepath.stat()
                    if stat.st_size > max_file_size:
                        continue  # 跳过过大文件

                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    rel_path = str(filepath.relative_to(root))
                    snapshots.append(FileSnapshot(
                        path=rel_path,
                        content_hash=self._hash_content(content),
                        content=content,
                    ))
                except Exception:
                    pass

        return snapshots

    @staticmethod
    def _hash_content(content: str) -> str:
        """计算内容哈希"""
        import hashlib
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _git_commit(workspace_root: str) -> str:
        """尝试 git commit 并返回 hash"""
        try:
            import subprocess
            _kw = {"capture_output": True, "cwd": workspace_root,
                   "encoding": "utf-8", "errors": "replace"}
            # 检查是否是 git 仓库
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                **_kw, timeout=5,
            )
            if result.returncode != 0:
                return ""

            # stage 所有变更
            subprocess.run(
                ["git", "add", "-A"],
                **_kw, timeout=10,
            )
            # commit
            result = subprocess.run(
                ["git", "commit", "--allow-empty", "-m", f"TS2 checkpoint {time.strftime('%Y-%m-%d %H:%M:%S')}"],
                **_kw, timeout=10,
            )
            # 获取 hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                **_kw, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:12]
        except Exception:
            pass
        return ""

    @staticmethod
    def _git_reset(workspace_root: str, commit_hash: str) -> bool:
        """git reset 到指定 commit"""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "reset", "--hard", commit_hash],
                capture_output=True, cwd=workspace_root, timeout=10,
                encoding="utf-8", errors="replace",
            )
            return result.returncode == 0
        except Exception:
            return False

    def clear(self):
        with self._lock:
            self._active_checkpoints.clear()
            self._pending_updates.clear()
            self._conversation_snapshots.clear()


_reloader: Optional["ContextReloader"] = None


def get_context_reloader() -> "ContextReloader":
    """获取全局单例 ContextReloader，避免每次创建新实例导致内存缓存丢失"""
    global _reloader
    if _reloader is None:
        _reloader = ContextReloader()
    return _reloader