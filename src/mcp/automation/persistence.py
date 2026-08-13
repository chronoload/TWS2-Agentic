from __future__ import annotations

import json
import sqlite3
import threading
import uuid
import time
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 1800


@dataclass
class AutomationTask:
    task_id: str
    name: str
    automation_type: str
    trigger_type: str
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    action_config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger_config"] = json.dumps(d["trigger_config"], ensure_ascii=False)
        d["action_config"] = json.dumps(d["action_config"], ensure_ascii=False)
        d["metadata"] = json.dumps(d["metadata"], ensure_ascii=False)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationTask":
        data = dict(data)
        for key in ("trigger_config", "action_config", "metadata"):
            val = data.get(key)
            if isinstance(val, str):
                try:
                    data[key] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    data[key] = {}
        return cls(**data)


@dataclass
class AutomationRun:
    run_id: str
    task_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    result: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationRun":
        return cls(**data)


class AutomationPersistence:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS automation_tasks (
                    task_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    automation_type TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_config TEXT NOT NULL DEFAULT '{}',
                    action_config TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at TEXT,
                    next_run_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS automation_runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms INTEGER,
                    result TEXT,
                    error TEXT,
                    FOREIGN KEY (task_id) REFERENCES automation_tasks(task_id)
                );

                CREATE TABLE IF NOT EXISTS automation_logs (
                    log_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    run_id TEXT,
                    log_level TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_enabled
                    ON automation_tasks(enabled);
                CREATE INDEX IF NOT EXISTS idx_runs_task
                    ON automation_runs(task_id);
                CREATE INDEX IF NOT EXISTS idx_runs_status
                    ON automation_runs(status);
                CREATE INDEX IF NOT EXISTS idx_logs_task
                    ON automation_logs(task_id);
                CREATE INDEX IF NOT EXISTS idx_logs_created
                    ON automation_logs(created_at);
            """)
            
            # 数据库迁移
            self._migrate_db(conn)
    
    def _migrate_db(self, conn):
        """添加缺失的列"""
        # 目前 automation_tasks 和 automation_runs 的列已经完整
        # 这里预留用于未来扩展
        pass

    def save_task(self, task: AutomationTask):
        now = datetime.now().isoformat()
        if task.created_at is None:
            task.created_at = now
        task.updated_at = now
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO automation_tasks
                (task_id, name, automation_type, trigger_type, trigger_config,
                 action_config, enabled, last_run_at, next_run_at,
                 created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_id, task.name, task.automation_type, task.trigger_type,
                json.dumps(task.trigger_config, ensure_ascii=False),
                json.dumps(task.action_config, ensure_ascii=False),
                1 if task.enabled else 0,
                task.last_run_at, task.next_run_at,
                task.created_at, task.updated_at,
                json.dumps(task.metadata, ensure_ascii=False),
            ))

    def get_task(self, task_id: str) -> Optional[AutomationTask]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM automation_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row:
                return AutomationTask.from_dict(dict(row))
        return None

    def list_tasks(self, enabled_only: bool = False) -> List[AutomationTask]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM automation_tasks"
            if enabled_only:
                query += " WHERE enabled=1"
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query).fetchall()
        return [AutomationTask.from_dict(dict(r)) for r in rows]

    def delete_task(self, task_id: str) -> bool:
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM automation_tasks WHERE task_id=?", (task_id,)
            )
            return cursor.rowcount > 0

    def update_task_enabled(self, task_id: str, enabled: bool) -> bool:
        now = datetime.now().isoformat()
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "UPDATE automation_tasks SET enabled=?, updated_at=? WHERE task_id=?",
                (1 if enabled else 0, now, task_id),
            )
            return cursor.rowcount > 0

    def update_task_last_run(self, task_id: str, last_run_at: str, next_run_at: str = None):
        now = datetime.now().isoformat()
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            if next_run_at:
                conn.execute(
                    "UPDATE automation_tasks SET last_run_at=?, next_run_at=?, updated_at=? WHERE task_id=?",
                    (last_run_at, next_run_at, now, task_id),
                )
            else:
                conn.execute(
                    "UPDATE automation_tasks SET last_run_at=?, updated_at=? WHERE task_id=?",
                    (last_run_at, now, task_id),
                )

    def save_run(self, run: AutomationRun):
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO automation_runs
                (run_id, task_id, status, started_at, completed_at,
                 duration_ms, result, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run.run_id, run.task_id, run.status, run.started_at,
                run.completed_at, run.duration_ms, run.result, run.error,
            ))

    def update_run(self, run_id: str, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [run_id]
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                f"UPDATE automation_runs SET {sets} WHERE run_id=?", values
            )

    def list_runs(self, task_id: str = None, limit: int = 50) -> List[AutomationRun]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if task_id:
                rows = conn.execute(
                    "SELECT * FROM automation_runs WHERE task_id=? ORDER BY started_at DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM automation_runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [AutomationRun.from_dict(dict(r)) for r in rows]

    def get_last_run(self, task_id: str) -> Optional[AutomationRun]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM automation_runs WHERE task_id=? ORDER BY started_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if row:
                return AutomationRun.from_dict(dict(row))
        return None

    def add_log(self, task_id: str, message: str, run_id: str = None,
                log_level: str = "info", metadata: Dict[str, Any] = None):
        log_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO automation_logs
                (log_id, task_id, run_id, log_level, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                log_id, task_id, run_id, log_level, message,
                json.dumps(metadata or {}, ensure_ascii=False), now,
            ))

    def get_logs(self, task_id: str = None, limit: int = 100,
                 log_level: str = None) -> List[Dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conditions = []
            params = []
            if task_id:
                conditions.append("task_id=?")
                params.append(task_id)
            if log_level:
                conditions.append("log_level=?")
                params.append(log_level)
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            query = f"SELECT * FROM automation_logs{where} ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


__all__ = [
    "AutomationPersistence", "AutomationTask", "AutomationRun",
    "MIN_INTERVAL_SECONDS",
]
