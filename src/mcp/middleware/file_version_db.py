#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量文件版本追踪 — 参考 Crush 的 files 表设计

与 Shadow Git 互补：
- Shadow Git: 全量快照（低频，baseline/手动），O(workspace_size)
- FileVersionDB: 增量文件版本（高频，每次工具调用），O(changed_files)

性能优势：
- after_tool 只 INSERT 变更的文件，不扫描整个工作区
- diff 查询是简单 SQL，不需要 git diff
- 前端轮询用 version 号，避免重复拉取

数据模型（参考 Crush）：
- checkpoints: 检查点元数据（hash, source, step, tool, duration）
- file_versions: 文件版本（checkpoint_id, path, content, status, version）
- read_files: 文件读取追踪（session_id, path, read_at）
"""

import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 当前 schema 版本，用于迁移
SCHEMA_VERSION = 1

_SCHEMA_SQL = """
-- 检查点元数据
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_hash TEXT NOT NULL,       -- Shadow Git commit hash（可为空，纯 SQLite 检查点）
    session_id TEXT NOT NULL DEFAULT '', -- 实例/会话标识
    parent_session_id TEXT NOT NULL DEFAULT '', -- 父会话 ID（参考 Crush Session 树）
    source TEXT NOT NULL DEFAULT 'auto', -- auto/manual/baseline
    step INTEGER NOT NULL DEFAULT 0,    -- 快照序号
    tool TEXT NOT NULL DEFAULT '',       -- 触发工具名
    duration_ms INTEGER,                -- 快照耗时
    created_at REAL NOT NULL            -- Unix timestamp
);

-- 文件版本（参考 Crush files 表）
CREATE TABLE IF NOT EXISTS file_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id INTEGER NOT NULL,
    path TEXT NOT NULL,                 -- 相对路径
    content_hash TEXT NOT NULL DEFAULT '', -- 内容 SHA256 前 16 字符（避免存大文本）
    status TEXT NOT NULL DEFAULT 'M',   -- A/M/D/R
    additions INTEGER NOT NULL DEFAULT 0,
    deletions INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 0, -- 该文件的版本号（递增）
    created_at REAL NOT NULL,
    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(id) ON DELETE CASCADE
);

-- 文件读取追踪（参考 Crush read_files 表）
CREATE TABLE IF NOT EXISTS read_files (
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    read_at REAL NOT NULL,
    PRIMARY KEY (session_id, path)
);

-- 全局版本号（参考 Crush VersionedMap）
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fv_checkpoint ON file_versions(checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_fv_path ON file_versions(path);
CREATE INDEX IF NOT EXISTS idx_fv_path_version ON file_versions(path, version);
CREATE INDEX IF NOT EXISTS idx_cp_session ON checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_cp_created ON checkpoints(created_at);

-- 初始版本号
INSERT OR IGNORE INTO meta (key, value) VALUES ('version', '1');
INSERT OR IGNORE INTO meta (key, value) VALUES ('global_version', '0');
"""


class FileVersionDB:
    """SQLite 增量文件版本追踪

    核心设计：
    - 每次工具调用只记录变更的文件（不是整个工作区）
    - content_hash 避免存储大文本（实际内容在 Shadow Git 中）
    - global_version 递增，前端按需刷新
    """

    def __init__(self, db_path: str = ""):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA_SQL)
            # 迁移：为旧表添加 parent_session_id 列
            self._migrate()
        return self._conn

    def _migrate(self):
        """数据库迁移：确保 schema 版本一致

        迁移策略（参考 Crush 惰性迁移）：
        - __init__ 中 executescript 运行 _SCHEMA_SQL（CREATE TABLE IF NOT EXISTS + v1 索引）
        - 此处按版本号递增执行 ALTER TABLE / CREATE INDEX
        - 每次迁移完成立即更新 meta version，避免重复执行
        """
        try:
            row = self._conn.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
            version = int(row["value"]) if row else 0
            if version < 2:
                # v1 → v2: 添加 parent_session_id 列 + 索引
                # 必须先 ADD COLUMN，再 CREATE INDEX（否则索引创建会因列不存在而失败）
                try:
                    self._conn.execute("ALTER TABLE checkpoints ADD COLUMN parent_session_id TEXT NOT NULL DEFAULT ''")
                except Exception:
                    pass
                try:
                    self._conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_parent ON checkpoints(parent_session_id)")
                except Exception:
                    pass
                self._conn.execute("UPDATE meta SET value = '2' WHERE key = 'version'")
                self._conn.commit()
            else:
                # 兜底：即使 version>=2，也尝试补列（防止之前迁移不完整）
                try:
                    self._conn.execute("ALTER TABLE checkpoints ADD COLUMN parent_session_id TEXT NOT NULL DEFAULT ''")
                except Exception:
                    pass
                try:
                    self._conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_parent ON checkpoints(parent_session_id)")
                except Exception:
                    pass
        except Exception:
            pass

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ─── 检查点操作 ────────────────────────────────────────

    def create_checkpoint(self, session_id: str, source: str = "auto",
                          step: int = 0, tool: str = "",
                          git_hash: str = "", duration_ms: int = 0,
                          changed_files: Optional[List[Dict]] = None,
                          parent_session_id: str = "") -> int:
        """创建检查点并记录变更文件

        Args:
            changed_files: [{"path": "...", "status": "A/M/D", "content_hash": "...", "additions": N, "deletions": N}]
            parent_session_id: 父会话 ID（参考 Crush Session 树，工具子会话时使用）

        Returns:
            checkpoint_id
        """
        conn = self._connect()
        now = time.time()
        try:
            cur = conn.execute(
                "INSERT INTO checkpoints (checkpoint_hash, session_id, parent_session_id, source, step, tool, duration_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (git_hash, session_id, parent_session_id, source, step, tool, duration_ms, now),
            )
            cp_id = cur.lastrowid

            if changed_files:
                for f in changed_files:
                    path = f["path"]
                    # 获取当前最大版本号
                    row = conn.execute(
                        "SELECT MAX(version) as v FROM file_versions WHERE path = ?",
                        (path,),
                    ).fetchone()
                    version = (row["v"] or 0) + 1

                    conn.execute(
                        "INSERT INTO file_versions (checkpoint_id, path, content_hash, status, additions, deletions, version, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (cp_id, path, f.get("content_hash", ""), f.get("status", "M"),
                         f.get("additions", 0), f.get("deletions", 0), version, now),
                    )

            # 递增全局版本号
            conn.execute("UPDATE meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'global_version'")
            conn.commit()
            return cp_id
        except Exception as e:
            conn.rollback()
            logger.warning(f"创建检查点失败: {e}")
            return -1

    def get_checkpoints(self, session_id: str, count: int = 50) -> List[Dict[str, Any]]:
        """获取检查点列表（含文件变更统计）"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT c.*, COUNT(fv.id) as file_count "
            "FROM checkpoints c LEFT JOIN file_versions fv ON c.id = fv.checkpoint_id "
            "WHERE c.session_id = ? "
            "GROUP BY c.id ORDER BY c.created_at DESC LIMIT ?",
            (session_id, count),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_child_checkpoints(self, parent_session_id: str, count: int = 50) -> List[Dict[str, Any]]:
        """获取子会话的检查点列表（参考 Crush Session 树）

        用于查询工具子会话的检查点，支持树形展示。
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT c.*, COUNT(fv.id) as file_count "
            "FROM checkpoints c LEFT JOIN file_versions fv ON c.id = fv.checkpoint_id "
            "WHERE c.parent_session_id = ? "
            "GROUP BY c.id ORDER BY c.created_at DESC LIMIT ?",
            (parent_session_id, count),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session_tree(self, session_id: str) -> Dict[str, Any]:
        """获取会话树结构（参考 Crush Session 树）

        Returns:
            {"session_id": "...", "checkpoints": [...], "children": [{"session_id": "...", ...}]}
        """
        conn = self._connect()
        # 主会话检查点
        main_cps = self.get_checkpoints(session_id)
        # 子会话
        child_rows = conn.execute(
            "SELECT DISTINCT session_id FROM checkpoints WHERE parent_session_id = ?",
            (session_id,),
        ).fetchall()
        children = []
        for row in child_rows:
            child_sid = row["session_id"]
            children.append({
                "session_id": child_sid,
                "checkpoints": self.get_checkpoints(child_sid),
            })
        return {
            "session_id": session_id,
            "checkpoints": main_cps,
            "children": children,
        }

    def get_checkpoint(self, checkpoint_id: int) -> Optional[Dict[str, Any]]:
        """获取单个检查点"""
        conn = self._connect()
        row = conn.execute("SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)).fetchone()
        return dict(row) if row else None

    # ─── 文件版本操作 ──────────────────────────────────────

    def get_file_versions(self, path: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取指定文件的版本历史"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT fv.*, c.tool, c.source, c.created_at as cp_created_at "
            "FROM file_versions fv JOIN checkpoints c ON fv.checkpoint_id = c.id "
            "WHERE fv.path = ? ORDER BY fv.version DESC LIMIT ?",
            (path, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_diff_set(self, from_checkpoint_id: int, to_checkpoint_id: int = 0) -> List[Dict[str, Any]]:
        """获取两个检查点之间的差异文件集

        参考 Cline getDiffSet / Crush ListLatestSessionFiles
        """
        conn = self._connect()
        if to_checkpoint_id == 0:
            # 与最新检查点比较
            row = conn.execute(
                "SELECT MAX(id) as max_id FROM checkpoints"
            ).fetchone()
            to_checkpoint_id = row["max_id"] if row else 0

        if from_checkpoint_id == 0 or to_checkpoint_id == 0:
            return []

        # 获取两个检查点之间的所有文件变更
        rows = conn.execute(
            "SELECT fv.path, fv.status, fv.additions, fv.deletions, fv.version "
            "FROM file_versions fv "
            "WHERE fv.checkpoint_id > ? AND fv.checkpoint_id <= ? "
            "GROUP BY fv.path "
            "HAVING fv.version = MAX(fv.version)",
            (from_checkpoint_id, to_checkpoint_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_checkpoint_diff_files(self, checkpoint_id: int) -> List[Dict[str, Any]]:
        """获取指定检查点自身的变更文件（增量 diff）

        只返回该检查点记录的 file_versions，即该工具调用实际修改的文件。
        与 get_diff_set 不同，这里不累加后续检查点的变更。
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT fv.path, fv.status, fv.additions, fv.deletions, fv.version "
            "FROM file_versions fv "
            "WHERE fv.checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_prev_checkpoint_id(self, checkpoint_id: int, session_id: str = "") -> int:
        """获取同一会话中指定检查点的前一个检查点 ID"""
        conn = self._connect()
        if session_id:
            row = conn.execute(
                "SELECT MAX(id) as prev_id FROM checkpoints "
                "WHERE id < ? AND session_id = ?",
                (checkpoint_id, session_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(id) as prev_id FROM checkpoints WHERE id < ?",
                (checkpoint_id,),
            ).fetchone()
        return row["prev_id"] if row and row["prev_id"] else 0

    def get_diff_count(self, from_checkpoint_id: int, to_checkpoint_id: int = 0) -> int:
        """快速获取变更文件数"""
        conn = self._connect()
        if to_checkpoint_id == 0:
            row = conn.execute("SELECT MAX(id) as max_id FROM checkpoints").fetchone()
            to_checkpoint_id = row["max_id"] if row else 0
        if from_checkpoint_id == 0 or to_checkpoint_id == 0:
            return 0
        row = conn.execute(
            "SELECT COUNT(DISTINCT path) as cnt FROM file_versions "
            "WHERE checkpoint_id > ? AND checkpoint_id <= ?",
            (from_checkpoint_id, to_checkpoint_id),
        ).fetchone()
        return row["cnt"] if row else 0

    # ─── 文件读取追踪 ──────────────────────────────────────

    def record_read(self, session_id: str, path: str):
        """记录文件读取（参考 Crush FileTracker）"""
        conn = self._connect()
        conn.execute(
            "INSERT OR REPLACE INTO read_files (session_id, path, read_at) VALUES (?, ?, ?)",
            (session_id, path, time.time()),
        )
        conn.commit()

    def get_read_files(self, session_id: str) -> List[str]:
        """获取会话中读取过的文件列表"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT path FROM read_files WHERE session_id = ? ORDER BY read_at DESC",
            (session_id,),
        ).fetchall()
        return [r["path"] for r in rows]

    def is_file_read(self, session_id: str, path: str) -> bool:
        """检查文件是否在当前会话中被读取过"""
        conn = self._connect()
        row = conn.execute(
            "SELECT 1 FROM read_files WHERE session_id = ? AND path = ?",
            (session_id, path),
        ).fetchone()
        return row is not None

    # ─── 版本号 ────────────────────────────────────────────

    def global_version(self) -> int:
        """获取全局版本号（参考 Crush VersionedMap）"""
        conn = self._connect()
        row = conn.execute("SELECT value FROM meta WHERE key = 'global_version'").fetchone()
        return int(row["value"]) if row else 0

    # ─── 工具方法 ──────────────────────────────────────────

    @staticmethod
    def content_hash(content: str) -> str:
        """计算内容哈希（SHA256 前 16 字符）"""
        return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]

    @staticmethod
    def detect_changes(old_content: str, new_content: str) -> Tuple[str, int, int]:
        """检测两个版本之间的变更类型和行数差异

        Returns:
            (status, additions, deletions)
        """
        if old_content == "" and new_content != "":
            return "A", new_content.count("\n") + 1, 0
        if old_content != "" and new_content == "":
            return "D", 0, old_content.count("\n") + 1

        old_lines = set(old_content.splitlines())
        new_lines = set(new_content.splitlines())
        additions = len(new_lines - old_lines)
        deletions = len(old_lines - new_lines)
        return "M", additions, deletions
