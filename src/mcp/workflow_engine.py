#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 工作流引擎 — 持久化多步骤编排
参考 DeerFlow 的子Agent编排 + Metaflow 的DAG流 + OpenCode的会话持久化

核心能力:
  持久化工作状态   — 不会因中断而丢失进度
  多步骤编排       — Agent/Tool/Condition/Parallel
  Checkpoint恢复   — 从任意断点恢复
  工作流DSL        — 声明式定义
  事件通知         — 与 Harness EventStream 集成
  协作式取消       — abort_event + threading.Event
"""
from __future__ import annotations

import json
import uuid
import sqlite3
import threading
import time
import traceback
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Union, Set
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

try:
    from .middleware import MiddlewareChain, MiddlewareContext, LoopDetectionMiddleware, ToolErrorMiddleware
    HAS_MIDDLEWARE = True
except ImportError:
    HAS_MIDDLEWARE = False

try:
    from .runtime import RunManager, RunStatus
    HAS_RUNTIME = True
except ImportError:
    HAS_RUNTIME = False


class StepType(Enum):
    AGENT = "agent"
    TOOL = "tool"
    CONDITION = "condition"
    PARALLEL = "parallel"
    LOOP = "loop"
    WAIT = "wait"
    NOTIFY = "notify"
    GT_PROVE = "gt_prove"
    LEAN_CHECK = "lean_check"
    MANIM_GEN = "manim_gen"
    MATHLENS = "mathlens"
    AUTORESEARCH = "autoresearch"


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowEventType(Enum):
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_PAUSED = "workflow_paused"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_RESUMED = "workflow_resumed"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_RETRYING = "step_retrying"
    PROGRESS_UPDATED = "progress_updated"
    CHECKPOINT_SAVED = "checkpoint_saved"


@dataclass
class WorkflowEvent:
    type: WorkflowEventType
    instance_id: str
    data: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class StepResult:
    step_id: str
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["output"] = self._serialize_output(self.output)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "StepResult":
        data = dict(data)
        data["status"] = StepStatus(data["status"])
        data["output"] = cls._deserialize_output(data.get("output"))
        return cls(**data)

    @staticmethod
    def _serialize_output(output: Any) -> Any:
        if output is None:
            return None
        try:
            if isinstance(output, (str, int, float, bool, list, dict)):
                return output
            return str(output)
        except Exception:
            return str(output)

    @staticmethod
    def _deserialize_output(data: Any) -> Any:
        return data


@dataclass
class WorkflowContext:
    instance_id: str
    workflow_id: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    current_step: Optional[str] = None
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    node_outputs: Dict[str, Any] = field(default_factory=dict)
    param_chains: Dict[str, dict] = field(default_factory=dict)
    started_at: Optional[str] = None
    updated_at: Optional[str] = None

    def get_var(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def set_var(self, key: str, value: Any):
        self.variables[key] = value

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "workflow_id": self.workflow_id,
            "input_data": self.input_data,
            "current_step": self.current_step,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "variables": self.variables,
            "node_outputs": self.node_outputs,
            "param_chains": self.param_chains,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowContext":
        ctx = cls(
            instance_id=data["instance_id"],
            workflow_id=data["workflow_id"],
            input_data=data.get("input_data", {}),
            current_step=data.get("current_step"),
            variables=data.get("variables", {}),
            node_outputs=data.get("node_outputs", {}),
            param_chains=data.get("param_chains", {}),
            started_at=data.get("started_at"),
            updated_at=data.get("updated_at"),
        )
        for sid, sr in data.get("step_results", {}).items():
            ctx.step_results[sid] = StepResult.from_dict(sr)
        return ctx

    def set_node_output(self, node_id: str, key: str, value: Any):
        if node_id not in self.node_outputs:
            self.node_outputs[node_id] = {}
        if not isinstance(self.node_outputs[node_id], dict):
            self.node_outputs[node_id] = {"_value": self.node_outputs[node_id]}
        self.node_outputs[node_id][key] = value

    def get_node_output(self, node_id: str, key: Optional[str] = None) -> Any:
        node = self.node_outputs.get(node_id)
        if node is None:
            return None
        if key is None:
            return node
        if isinstance(node, dict):
            return node.get(key)
        return node


@dataclass
class StepDefinition:
    step_id: str
    name: str
    step_type: StepType
    config: Dict[str, Any] = field(default_factory=dict)

    prompt_template: Optional[str] = None
    tools: Optional[List[str]] = None
    max_retries: int = 3

    condition_expr: Optional[str] = None
    true_steps: Optional[List[str]] = None
    false_steps: Optional[List[str]] = None

    parallel_steps: Optional[List[Dict]] = None

    loop_var: Optional[str] = None
    loop_items: Optional[str] = None
    max_iterations: int = 10

    param_inputs: Optional[List[Dict[str, Any]]] = None
    param_outputs: Optional[List[Dict[str, Any]]] = None
    param_transforms: Optional[Dict[str, str]] = None

    def to_dict(self) -> dict:
        d = {"step_id": self.step_id, "name": self.name,
             "step_type": self.step_type.value, "config": self.config}
        if self.prompt_template:
            d["prompt_template"] = self.prompt_template
        if self.tools:
            d["tools"] = self.tools
        if self.max_retries != 3:
            d["max_retries"] = self.max_retries
        if self.condition_expr:
            d["condition_expr"] = self.condition_expr
        if self.true_steps:
            d["true_steps"] = self.true_steps
        if self.false_steps:
            d["false_steps"] = self.false_steps
        if self.parallel_steps:
            d["parallel_steps"] = self.parallel_steps
        if self.loop_var:
            d["loop_var"] = self.loop_var
        if self.loop_items:
            d["loop_items"] = self.loop_items
        if self.param_inputs:
            d["param_inputs"] = self.param_inputs
        if self.param_outputs:
            d["param_outputs"] = self.param_outputs
        if self.param_transforms:
            d["param_transforms"] = self.param_transforms
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "StepDefinition":
        data = dict(data)
        data["step_type"] = StepType(data["step_type"])
        return cls(**data)


@dataclass
class WorkflowDefinition:
    workflow_id: str
    name: str
    description: str = ""
    version: str = "1.0"
    input_schema: Optional[Dict] = None
    output_schema: Optional[Dict] = None
    steps: List[StepDefinition] = field(default_factory=list)
    entry_step: Optional[str] = None
    checkpoint_after: Set[str] = field(default_factory=set)

    def get_step(self, step_id: str) -> Optional[StepDefinition]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def get_step_index(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.step_id == step_id:
                return i
        return -1

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "steps": [s.to_dict() for s in self.steps],
            "entry_step": self.entry_step,
            "checkpoint_after": list(self.checkpoint_after),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowDefinition":
        steps = [StepDefinition.from_dict(s) for s in data.get("steps", [])]
        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            input_schema=data.get("input_schema"),
            output_schema=data.get("output_schema"),
            steps=steps,
            entry_step=data.get("entry_step"),
            checkpoint_after=set(data.get("checkpoint_after", [])),
        )


class WorkflowPersistence:
    """工作流持久化存储"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._lock = threading.Lock()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # 先创建表
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS workflow_definitions (
                    workflow_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    version TEXT DEFAULT '1.0',
                    definition_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflow_instances (
                    instance_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    current_step_id TEXT,
                    current_step_name TEXT,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    progress REAL DEFAULT 0.0,
                    started_at TEXT,
                    paused_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(workflow_id)
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    context_snapshot TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (instance_id) REFERENCES workflow_instances(instance_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    step_id TEXT,
                    artifact_type TEXT NOT NULL DEFAULT 'data',
                    name TEXT NOT NULL,
                    content TEXT,
                    file_path TEXT,
                    size_bytes INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (instance_id) REFERENCES workflow_instances(instance_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_logs (
                    log_id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    step_id TEXT,
                    step_name TEXT,
                    log_level TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (instance_id) REFERENCES workflow_instances(instance_id)
                );

                CREATE INDEX IF NOT EXISTS idx_instances_status
                    ON workflow_instances(status);
                CREATE INDEX IF NOT EXISTS idx_instances_workflow
                    ON workflow_instances(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_checkpoints_instance
                    ON checkpoints(instance_id);
                CREATE INDEX IF NOT EXISTS idx_artifacts_instance
                    ON workflow_artifacts(instance_id);
                CREATE INDEX IF NOT EXISTS idx_logs_instance
                    ON workflow_logs(instance_id);
            """)
            
            # 数据库迁移：添加缺失的列
            self._migrate_db(conn)
    
    def _migrate_db(self, conn):
        """添加缺失的列"""
        # 表和需要添加的列
        tables = {
            "workflow_instances": {
                "current_step_name": "TEXT",
            },
            "workflow_logs": {
                "step_name": "TEXT",
            },
            "checkpoints": {
                # 已完整
            },
            "workflow_artifacts": {
                # 已完整
            },
        }
        
        for table_name, required_cols in tables.items():
            if not required_cols:
                continue
            # 获取现有列
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            existing_cols = {row[1] for row in cursor.fetchall()}
            
            for col_name, col_type in required_cols.items():
                if col_name not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
                        logger.info(f"数据库迁移：添加列 {table_name}.{col_name}")
                    except Exception as e:
                        logger.warning(f"添加列失败: {e}")

    def save_definition(self, wf_def: WorkflowDefinition):
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO workflow_definitions
                (workflow_id, name, description, version, definition_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                wf_def.workflow_id, wf_def.name, wf_def.description,
                wf_def.version, json.dumps(wf_def.to_dict(), ensure_ascii=False),
                datetime.now().isoformat(), datetime.now().isoformat(),
            ))

    def get_definition(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT definition_json FROM workflow_definitions WHERE workflow_id=?",
                (workflow_id,)
            ).fetchone()
            if row:
                return WorkflowDefinition.from_dict(json.loads(row["definition_json"]))
        return None

    def list_definitions(self) -> List[Dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT workflow_id, name, description, version, created_at "
                "FROM workflow_definitions ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_definition(self, workflow_id: str) -> bool:
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM workflow_definitions WHERE workflow_id=?",
                (workflow_id,)
            )
            return cursor.rowcount > 0

    def save_instance(self, instance_data: dict):
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO workflow_instances
                (instance_id, workflow_id, status, current_step_id,
                 current_step_name, context_json, progress, started_at, paused_at,
                 completed_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                instance_data["instance_id"],
                instance_data["workflow_id"],
                instance_data.get("status", "pending"),
                instance_data.get("current_step_id"),
                instance_data.get("current_step_name"),
                instance_data.get("context_json", "{}"),
                instance_data.get("progress", 0.0),
                instance_data.get("started_at"),
                instance_data.get("paused_at"),
                instance_data.get("completed_at"),
                instance_data.get("error_message"),
            ))

    def get_instance(self, instance_id: str) -> Optional[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_instances WHERE instance_id=?",
                (instance_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_instance(self, instance_id: str, **fields):
        if not fields:
            return
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [instance_id]
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                f"UPDATE workflow_instances SET {set_clause} WHERE instance_id=?",
                values
            )

    def list_instances(self, status: Optional[WorkflowStatus] = None,
                       limit: int = 50) -> List[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM workflow_instances WHERE status=? "
                    "ORDER BY started_at DESC LIMIT ?",
                    (status.value, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_instances "
                    "ORDER BY started_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def save_checkpoint(self, instance_id: str, step_id: str,
                        step_name: str, context: WorkflowContext):
        checkpoint_id = str(uuid.uuid4())
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO checkpoints
                (checkpoint_id, instance_id, step_id, step_name,
                 context_snapshot, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                checkpoint_id, instance_id, step_id, step_name,
                json.dumps(context.to_dict(), ensure_ascii=False),
                datetime.now().isoformat(),
            ))
        return checkpoint_id

    def get_last_checkpoint(self, instance_id: str) -> Optional[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE instance_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (instance_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_checkpoints(self, instance_id: str) -> List[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT checkpoint_id, instance_id, step_id, step_name, created_at "
                "FROM checkpoints WHERE instance_id=? ORDER BY created_at DESC",
                (instance_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def save_artifact(self, instance_id: str, artifact_type: str,
                      name: str, content: str = "",
                      file_path: str = "",
                      step_id: Optional[str] = None) -> str:
        artifact_id = str(uuid.uuid4())
        size = len(content.encode("utf-8")) if content else 0
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO workflow_artifacts
                (artifact_id, instance_id, step_id, artifact_type, name,
                 content, file_path, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                artifact_id, instance_id, step_id, artifact_type, name,
                content, file_path, size, datetime.now().isoformat(),
            ))
        return artifact_id

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_artifacts WHERE artifact_id=?",
                (artifact_id,)
            ).fetchone()
        return dict(row) if row else None

    def add_log(self, instance_id: str, message: str,
                level: str = "info", step_id: str = "",
                step_name: str = "",
                metadata: dict = None):
        log_id = str(uuid.uuid4())
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            # 确保迁移：添加缺失的 step_name 列
            cursor = conn.execute("PRAGMA table_info(workflow_logs)")
            cols = {row[1] for row in cursor.fetchall()}
            if "step_name" not in cols:
                try:
                    conn.execute("ALTER TABLE workflow_logs ADD COLUMN step_name TEXT")
                except:
                    pass
            
            # 插入日志
            if "step_name" in cols:
                conn.execute("""
                    INSERT INTO workflow_logs
                    (log_id, instance_id, step_id, step_name, log_level, message,
                     metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_id, instance_id, step_id, step_name, level, message,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    datetime.now().isoformat(),
                ))
            else:
                # 回退：不使用 step_name
                conn.execute("""
                    INSERT INTO workflow_logs
                    (log_id, instance_id, step_id, log_level, message,
                     metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_id, instance_id, step_id, level, message,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    datetime.now().isoformat(),
                ))

    def get_logs(self, instance_id: str, limit: int = 100,
                 level: Optional[str] = None) -> List[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if level:
                rows = conn.execute(
                    "SELECT * FROM workflow_logs WHERE instance_id=? AND log_level=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (instance_id, level, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_logs WHERE instance_id=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (instance_id, limit)
                ).fetchall()
        return [dict(r) for r in rows]


class WorkflowEngine:
    """工作流引擎 — 核心编排器"""

    _instance: Optional["WorkflowEngine"] = None
    _init_lock = threading.Lock()

    def __init__(self, db_path: Optional[Path] = None):
        db_path = Path(db_path) if db_path else Path("data/workflow.db")
        self.persistence = WorkflowPersistence(db_path)
        self._running: Dict[str, "WorkflowRunner"] = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="wf-")
        self._callbacks: Dict[str, List[Callable]] = {}
        self._event_listeners: List[Callable[[WorkflowEvent], None]] = []
        self._agent = None
        self._tools = None
        self._harness_runner = None
        self._middleware_chain = None
        if HAS_MIDDLEWARE:
            try:
                self._middleware_chain = MiddlewareChain()
                self._middleware_chain.add(ToolErrorMiddleware())
                self._middleware_chain.add(LoopDetectionMiddleware())
            except Exception:
                self._middleware_chain = None
        self._run_manager = RunManager() if HAS_RUNTIME else None

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> "WorkflowEngine":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance

    def set_agent(self, agent, tools):
        self._agent = agent
        self._tools = tools

    def set_harness_runner(self, runner):
        self._harness_runner = runner

    def on_event(self, listener: Callable[[WorkflowEvent], None]):
        self._event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[WorkflowEvent], None]):
        self._event_listeners = [l for l in self._event_listeners if l is not listener]

    def _emit_event(self, event_type: WorkflowEventType, instance_id: str, **data):
        event = WorkflowEvent(
            type=event_type,
            instance_id=instance_id,
            data=data,
        )
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception:
                traceback.print_exc()
        self._notify(instance_id, {"type": event_type.value, "instance_id": instance_id, **data})

    def register_builtin_workflows(self):
        try:
            from .predefined_workflows import WORKFLOW_REGISTRY
            for wf_id, wf_def in WORKFLOW_REGISTRY.items():
                existing = self.persistence.get_definition(wf_def.workflow_id)
                if not existing:
                    self.persistence.save_definition(wf_def)
        except Exception:
            pass

    def start_workflow(self, definition: WorkflowDefinition,
                       input_data: Dict[str, Any] = None,
                       callbacks: List[Callable] = None) -> str:
        input_data = input_data or {}
        instance_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        ctx = WorkflowContext(
            instance_id=instance_id,
            workflow_id=definition.workflow_id,
            input_data=input_data,
            started_at=now,
            updated_at=now,
        )

        self.persistence.save_instance({
            "instance_id": instance_id,
            "workflow_id": definition.workflow_id,
            "status": WorkflowStatus.RUNNING.value,
            "context_json": json.dumps(ctx.to_dict(), ensure_ascii=False),
            "started_at": now,
        })
        self.persistence.add_log(instance_id, f"工作流启动: {definition.name}")

        if callbacks:
            self._callbacks[instance_id] = callbacks

        runner = WorkflowRunner(self, definition, ctx)
        self._running[instance_id] = runner
        self._executor.submit(runner.run_sync)
        self._emit_event(WorkflowEventType.WORKFLOW_STARTED, instance_id,
                        workflow_id=definition.workflow_id, name=definition.name)
        return instance_id

    def pause_workflow(self, instance_id: str) -> bool:
        runner = self._running.get(instance_id)
        if runner:
            runner.pause()
            self._emit_event(WorkflowEventType.WORKFLOW_PAUSED, instance_id)
            return True
        return False

    def resume_workflow(self, instance_id: str) -> bool:
        instance = self.persistence.get_instance(instance_id)
        if not instance:
            return False
        status = instance.get("status", "")
        if status not in (WorkflowStatus.PAUSED.value, WorkflowStatus.FAILED.value):
            return False

        checkpoint = self.persistence.get_last_checkpoint(instance_id)
        if not checkpoint and instance.get("context_json"):
            context_data = json.loads(instance["context_json"])
            ctx = WorkflowContext.from_dict(context_data)
        elif checkpoint:
            ctx = WorkflowContext.from_dict(
                json.loads(checkpoint["context_snapshot"])
            )
        else:
            return False

        definition = self.persistence.get_definition(instance["workflow_id"])
        if not definition:
            return False

        self.persistence.update_instance(instance_id, status=WorkflowStatus.RUNNING.value)
        self.persistence.add_log(instance_id, "工作流恢复执行")

        from_step = checkpoint["step_id"] if checkpoint else (instance.get("current_step_id") or None)
        runner = WorkflowRunner(self, definition, ctx)
        self._running[instance_id] = runner
        self._executor.submit(runner.run_sync, from_step)
        self._emit_event(WorkflowEventType.WORKFLOW_RESUMED, instance_id)
        return True

    def cancel_workflow(self, instance_id: str) -> bool:
        runner = self._running.get(instance_id)
        if runner:
            runner.cancel()
            self._emit_event(WorkflowEventType.WORKFLOW_CANCELLED, instance_id)
            return True

        instance = self.persistence.get_instance(instance_id)
        if instance and instance.get("status") in (
            WorkflowStatus.RUNNING.value, WorkflowStatus.PAUSED.value
        ):
            self.persistence.update_instance(
                instance_id, status=WorkflowStatus.CANCELLED.value)
            self.persistence.add_log(instance_id, "工作流已取消")
            return True
        return False

    def get_status(self, instance_id: str) -> Optional[dict]:
        instance = self.persistence.get_instance(instance_id)
        if not instance:
            return None
        return {
            "instance_id": instance["instance_id"],
            "workflow_id": instance["workflow_id"],
            "status": instance["status"],
            "current_step": instance.get("current_step_id"),
            "current_step_name": instance.get("current_step_name"),
            "progress": instance.get("progress", 0.0),
            "started_at": instance.get("started_at"),
            "error_message": instance.get("error_message"),
        }

    def get_step_results(self, instance_id: str) -> Dict[str, dict]:
        instance = self.persistence.get_instance(instance_id)
        if not instance:
            return {}
        try:
            ctx = WorkflowContext.from_dict(json.loads(instance.get("context_json", "{}")))
        except Exception:
            return {}
        return {sid: sr.to_dict() for sid, sr in ctx.step_results.items()}

    def get_logs(self, instance_id: str, limit: int = 100, level: Optional[str] = None) -> List[dict]:
        return self.persistence.get_logs(instance_id, limit, level)

    def list_recoverable(self) -> List[dict]:
        instances = self.persistence.list_instances(WorkflowStatus.PAUSED)
        instances += self.persistence.list_instances(WorkflowStatus.RUNNING)
        result = []
        for inst in instances:
            cp = self.persistence.get_last_checkpoint(inst["instance_id"])
            result.append({
                "instance_id": inst["instance_id"],
                "workflow_id": inst["workflow_id"],
                "status": inst["status"],
                "last_checkpoint": cp["step_name"] if cp else None,
                "started_at": inst.get("started_at"),
            })
        return result

    def _notify(self, instance_id: str, data: dict):
        for cb in self._callbacks.get(instance_id, []):
            try:
                cb(data)
            except Exception:
                traceback.print_exc()


class WorkflowRunner:
    """单个工作流实例的运行器"""

    def __init__(self, engine: WorkflowEngine, definition: WorkflowDefinition,
                 context: WorkflowContext):
        self.engine = engine
        self.definition = definition
        self.context = context
        self._paused = False
        self._cancelled = False
        self._abort_event = threading.Event()
        self._current_step_def: Optional[StepDefinition] = None

    def run_sync(self, from_step: Optional[str] = None):
        try:
            self._run(from_step)
        except Exception as e:
            self._fail(str(e))

    def _run(self, from_step: Optional[str] = None):
        steps: List[StepDefinition]

        if from_step:
            idx = self.definition.get_step_index(from_step)
            if idx >= 0:
                steps = self.definition.steps[idx:]
            else:
                steps = list(self.definition.steps)
                self._snapshot_to_db()
        else:
            steps = list(self.definition.steps)
            self._snapshot_to_db()

        total = len(self.definition.steps)
        for i, step_def in enumerate(steps):
            if self._cancelled or self._abort_event.is_set():
                break
            self._wait_if_paused()
            if self._cancelled or self._abort_event.is_set():
                break

            self._current_step_def = step_def
            self.context.current_step = step_def.step_id
            progress = (i + 1) / max(total, 1)
            self._update_db_step(step_def.step_id, step_def.name, progress)
            self._log(f"执行步骤 [{i+1}/{total}]: {step_def.name}")
            self.engine._emit_event(
                WorkflowEventType.STEP_STARTED, self.context.instance_id,
                step_id=step_def.step_id, step_name=step_def.name,
                step_index=i+1, total_steps=total, progress=progress,
            )

            result = self._execute_step(step_def)
            self.context.step_results[step_def.step_id] = result

            if result.status == StepStatus.FAILED and step_def.max_retries > 0:
                for attempt in range(step_def.max_retries):
                    if self._cancelled or self._abort_event.is_set():
                        break
                    self._log(f"重试 {attempt+1}/{step_def.max_retries}")
                    self.engine._emit_event(
                        WorkflowEventType.STEP_RETRYING, self.context.instance_id,
                        step_id=step_def.step_id, attempt=attempt+1,
                    )
                    result = self._execute_step(step_def)
                    result.retry_count = attempt + 1
                    if result.status == StepStatus.COMPLETED:
                        break

            if result.status == StepStatus.FAILED:
                self.engine._emit_event(
                    WorkflowEventType.STEP_FAILED, self.context.instance_id,
                    step_id=step_def.step_id, error=result.error,
                )
                self._fail(f"步骤 {step_def.name} 失败: {result.error}")
                return

            self.engine._emit_event(
                WorkflowEventType.STEP_COMPLETED, self.context.instance_id,
                step_id=step_def.step_id, step_name=step_def.name,
                progress=progress,
            )

            if step_def.step_id in self.definition.checkpoint_after:
                self._save_checkpoint(step_def)
                self._snapshot_to_db()
                self.engine._emit_event(
                    WorkflowEventType.CHECKPOINT_SAVED, self.context.instance_id,
                    step_id=step_def.step_id,
                )

        if not self._cancelled and not self._abort_event.is_set():
            self._complete()
        elif self._cancelled:
            self.persistence_update_cancelled()

    def persistence_update_cancelled(self):
        self.engine.persistence.update_instance(
            self.context.instance_id,
            status=WorkflowStatus.CANCELLED.value,
            context_json=json.dumps(self.context.to_dict(), ensure_ascii=False),
        )
        self.engine.persistence.add_log(
            self.context.instance_id, "工作流已取消", "warn",
        )

    def _execute_step(self, step_def: StepDefinition) -> StepResult:
        result = StepResult(
            step_id=step_def.step_id,
            status=StepStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )

        try:
            self._apply_param_chain_inputs(step_def)
            st = step_def.step_type

            if st == StepType.AGENT:
                output = self._run_agent(step_def)
            elif st == StepType.TOOL:
                output = self._run_tool(step_def)
            elif st == StepType.PARALLEL:
                output = self._run_parallel(step_def)
            elif st == StepType.CONDITION:
                output = self._run_condition(step_def)
            elif st == StepType.LOOP:
                output = self._run_loop(step_def)
            elif st == StepType.WAIT:
                output = self._run_wait(step_def)
            elif st == StepType.NOTIFY:
                output = self._run_notify(step_def)
            elif st == StepType.GT_PROVE:
                output = self._run_gt_prove(step_def)
            elif st == StepType.LEAN_CHECK:
                output = self._run_lean_check(step_def)
            elif st == StepType.MANIM_GEN:
                output = self._run_manim_gen(step_def)
            elif st == StepType.MATHLENS:
                output = self._run_mathlens(step_def)
            elif st == StepType.AUTORESEARCH:
                output = self._run_autoresearch(step_def)
            else:
                output = None

            result.status = StepStatus.COMPLETED
            result.output = output
            self._apply_param_chain_outputs(step_def, output)

        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = f"{type(e).__name__}: {e}"
            traceback.print_exc()

        result.completed_at = datetime.now().isoformat()
        return result

    def _run_agent(self, step_def: StepDefinition) -> str:
        # 优先使用 HarnessRunner（如果可用）
        if self.engine._harness_runner:
            prompt = self._render(step_def.prompt_template or "")
            ctx = json.dumps(self.context.variables, ensure_ascii=False, indent=2)
            full_prompt = f"{prompt}\n\n上下文数据:\n```json\n{ctx}\n```"
            messages = [{"role": "user", "content": full_prompt}]
            turn_result = self.engine._harness_runner.run_turn(messages)
            return turn_result.final_response or turn_result.content or ""
        
        # 回退：使用 Agent
        agent = self.engine._agent
        if not agent:
            return f"警告：Agent 未初始化，无法执行步骤 '{step_def.name or step_def.step_id}'。请先初始化 Agent。"

        prompt = self._render(step_def.prompt_template or "")
        ctx = json.dumps(self.context.variables, ensure_ascii=False, indent=2)
        full_prompt = f"{prompt}\n\n上下文数据:\n```json\n{ctx}\n```"

        wf_messages = []
        if agent.messages and agent.messages[0].get("role") == "system":
            wf_messages.append(dict(agent.messages[0]))
        else:
            wf_messages.append({"role": "system", "content": "你是工作流执行助手。"})
        wf_messages.append({"role": "user", "content": full_prompt})

        llm = agent.llm
        if not llm:
            return "警告：Agent LLM 未初始化"

        tools = agent._get_tool_schemas() if hasattr(agent, '_get_tool_schemas') else None

        max_rounds = 5
        last_content = ""
        for _ in range(max_rounds):
            if self._cancelled or self._abort_event.is_set():
                return last_content or "(工作流步骤已取消)"

            response = llm.chat(wf_messages, tools=tools)

            if getattr(response, 'cancelled', False):
                return response.content or last_content or "(工作流步骤已取消)"

            if not response.tool_calls:
                return response.content or ""

            last_content = response.content or last_content
            wf_messages.append(response.message)
            for tc in response.tool_calls:
                if self._cancelled or self._abort_event.is_set():
                    return last_content or "(工作流步骤已取消)"
                result = agent._execute_tool(tc)
                wf_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return last_content or "(工作流Agent步骤达到最大轮次)"

    def _run_gt_prove(self, step_def: StepDefinition) -> Any:
        try:
            from .gt.gt_workflow import GTWorkflowStep
        except ImportError:
            return "GT Agent 模块不可用"

        source_code = self._render(step_def.prompt_template or "")
        context = json.dumps(self.context.variables, ensure_ascii=False, indent=2)
        mode = step_def.config.get("gt_mode", "basic") if step_def.config else "basic"
        allowed = step_def.config.get("allowed_references", []) if step_def.config else []
        forbidden = step_def.config.get("forbidden_assumptions", []) if step_def.config else []

        llm = None
        if self.engine._agent:
            llm = getattr(self.engine._agent, 'llm', None)

        step = GTWorkflowStep(
            mode=mode,
            llm=llm,
        )

        def abort_check():
            return self._cancelled or self._abort_event.is_set()

        result = step.execute(
            source_code=source_code,
            context=context,
            allowed_references=allowed,
            forbidden_assumptions=forbidden,
            abort_check=abort_check,
        )

        if result.get("status") == "PROVED":
            for key, value in result.items():
                if key != "final_code":
                    self.context.set_variable(f"gt_{key}", value)
        else:
            for key, value in result.items():
                self.context.set_variable(f"gt_{key}", value)

        return json.dumps(result, ensure_ascii=False)

    def _run_lean_check(self, step_def: StepDefinition) -> Any:
        try:
            from .research.lean4.lean4_tools import _run_lean, _run_lean4_mcp, _find_lean4_mcp
        except ImportError:
            return json.dumps({"error": "Lean4 模块不可用"}, ensure_ascii=False)

        code = self._render(step_def.prompt_template or "")
        if not code.strip():
            code = self.context.variables.get("source_code", "")
        timeout = step_def.config.get("timeout", 60) if step_def.config else 60

        if _find_lean4_mcp():
            result = _run_lean4_mcp("check", "--code", code, timeout=timeout)
        else:
            result = _run_lean(code, timeout=timeout)

        for key, value in result.items():
            self.context.set_variable(f"lean4_{key}", value)
        return json.dumps(result, ensure_ascii=False)

    def _run_manim_gen(self, step_def: StepDefinition) -> Any:
        try:
            from .research.manim.manim_tools import _run_manim_mcp, _run_manim, _find_manim_mcp
        except ImportError:
            return json.dumps({"error": "Manim 模块不可用"}, ensure_ascii=False)

        prompt = self._render(step_def.prompt_template or "")
        config = step_def.config or {}
        mode = config.get("mode", "simple")
        quality = config.get("quality", "h")
        audio = config.get("audio", False)

        if _find_manim_mcp():
            args = ["gen", prompt, "--mode", mode, "--quality", quality]
            if audio:
                args.append("--audio")
            result = _run_manim_mcp(*args, timeout=600)
        else:
            script_path = config.get("script_path", "")
            scene_name = config.get("scene_name", "")
            if script_path and scene_name:
                result = _run_manim(script_path, scene_name, quality)
            else:
                result = {"error": "manim-mcp 不可用且未提供 script_path/scene_name"}

        for key, value in result.items():
            self.context.set_variable(f"manim_{key}", value)
        return json.dumps(result, ensure_ascii=False)

    def _run_mathlens(self, step_def: StepDefinition) -> Any:
        try:
            from .research.mathlens.mathlens_tools import _run_script, SKILLS_DIR
        except ImportError:
            return json.dumps({"error": "MathLens 模块不可用"}, ensure_ascii=False)

        config = step_def.config or {}
        action = config.get("action", "render")
        project_dir = self._render(config.get("project_dir", ""))
        script_path = config.get("script_path", "script.py")
        scene_name = config.get("scene_name", "MathScene")
        quality = config.get("quality", "h")

        if action == "init":
            result = _run_script("init.py", project_dir or ".", timeout=30)
        elif action == "tts":
            csv_path = config.get("csv_path", "")
            voice = config.get("voice", "xiaoxiao")
            result = _run_script("generate_tts.py", csv_path, "./audio", "--voice", voice, timeout=300)
        elif action == "validate":
            storyboard_path = config.get("storyboard_path", "")
            result = _run_script("validate_audio.py", storyboard_path, "./audio", timeout=30)
        elif action == "check":
            result = _run_script("check.py", script_path, timeout=15)
        else:
            args = ["-f", script_path, "-s", scene_name, "-q", quality]
            result = _run_script("render.py", *args, timeout=600)

        for key, value in result.items():
            self.context.set_variable(f"mathlens_{key}", value)
        return json.dumps(result, ensure_ascii=False)

    def _run_autoresearch(self, step_def: StepDefinition) -> Any:
        config = step_def.config or {}
        topic = self._render(step_def.prompt_template or "")
        if not topic.strip():
            topic = self.context.variables.get("topic", "")
        if not topic.strip():
            topic = self.context.variables.get("research_topic", "")

        stages = config.get("stages", [
            "topic_init", "problem_decompose", "search_strategy",
            "literature_collect", "knowledge_extract", "synthesis",
            "hypothesis_gen", "experiment_design", "result_analysis",
        ])
        max_iterations = config.get("max_iterations", 1)

        stage_contracts = {
            "topic_init": {"outputs": ["research_scope.md"], "description": "研究范围界定"},
            "problem_decompose": {"outputs": ["sub_problems.md"], "description": "问题拆解"},
            "search_strategy": {"outputs": ["search_plan.md"], "description": "搜索策略"},
            "literature_collect": {"outputs": ["literature_list.md"], "description": "文献收集"},
            "literature_screen": {"outputs": ["screened_literature.md"], "description": "文献筛选"},
            "knowledge_extract": {"outputs": ["knowledge_notes.md"], "description": "知识提取"},
            "synthesis": {"outputs": ["synthesis_report.md"], "description": "知识综合"},
            "hypothesis_gen": {"outputs": ["hypotheses.md"], "description": "假设生成"},
            "experiment_design": {"outputs": ["experiment_plan.md"], "description": "实验设计"},
            "code_generation": {"outputs": ["experiment_code.py"], "description": "代码生成"},
            "resource_planning": {"outputs": ["resource_plan.md"], "description": "资源规划"},
            "experiment_run": {"outputs": ["experiment_log.txt"], "description": "实验执行"},
            "iterative_refine": {"outputs": ["refined_code.py"], "description": "迭代优化"},
            "result_analysis": {"outputs": ["analysis_report.md"], "description": "结果分析"},
            "research_decision": {"outputs": ["decision.md"], "description": "研究决策"},
            "paper_outline": {"outputs": ["paper_outline.md"], "description": "论文大纲"},
            "paper_draft": {"outputs": ["paper_draft.tex"], "description": "论文初稿"},
            "peer_review": {"outputs": ["review_comments.md"], "description": "同行评审"},
            "paper_revision": {"outputs": ["paper_revised.tex"], "description": "论文修改"},
            "quality_gate": {"outputs": ["quality_report.md"], "description": "质量门控"},
            "knowledge_archive": {"outputs": ["archive_summary.md"], "description": "知识归档"},
            "export_publish": {"outputs": ["final_paper.pdf"], "description": "导出发布"},
            "citation_verify": {"outputs": ["citation_report.md"], "description": "引用验证"},
        }

        try:
            from .research.autoresearch.autoresearch_tools import _inject_skills
        except ImportError:
            _inject_skills = None

        results = []
        for stage in stages:
            contract = stage_contracts.get(stage, {"outputs": [], "description": stage})
            skills_prompt = ""
            if _inject_skills:
                try:
                    skills_prompt = _inject_skills({"stage": stage, "topic": topic})
                except Exception:
                    pass

            stage_prompt = f"执行研究阶段 {stage}: {contract['description']}\n\n研究主题: {topic}\n预期输出: {', '.join(contract['outputs'])}"
            if skills_prompt:
                stage_prompt += f"\n\n## 匹配到的研究技能\n{skills_prompt[:3000]}"
            if results:
                last = results[-1]
                stage_prompt += f"\n\n前序阶段 ({last['stage']}) 结果摘要:\n{str(last.get('summary', last.get('output', '')))[:2000]}"

            try:
                output = self._run_agent(StepDefinition(
                    step_id=f"autoresearch_{stage}",
                    name=f"AutoResearch: {stage}",
                    step_type=StepType.AGENT,
                    prompt_template=stage_prompt,
                ))
                output_str = str(output)
            except Exception as e:
                output_str = f"[ERROR] {e}"

            results.append({
                "stage": stage,
                "description": contract["description"],
                "expected_outputs": contract["outputs"],
                "output": output_str[:5000],
                "summary": output_str[:500],
                "status": "error" if "[ERROR]" in output_str else "done",
            })

            self.context.set_variable(f"autoresearch_{stage}", output_str)
            self.context.set_variable("autoresearch_current_stage", stage)

        self.context.set_variable("autoresearch_results", results)
        self.context.set_variable("autoresearch_stages_completed", len(results))

        return json.dumps({
            "stages_completed": len(results),
            "topic": topic,
            "stages": [{"stage": r["stage"], "status": r["status"], "description": r["description"]} for r in results],
        }, ensure_ascii=False)

    def _run_tool(self, step_def: StepDefinition) -> Any:
        tools = self.engine._tools
        if not tools:
            raise RuntimeError("工具注册表未初始化")

        tool_name = step_def.config.get("tool_name") or step_def.config.get("tool")
        if not tool_name:
            raise ValueError("工具步骤缺少 tool_name 配置")

        args = self._render(step_def.config.get("args", {}))
        if isinstance(args, str):
            args = json.loads(args)
        if not isinstance(args, dict):
            args = {}

        if hasattr(tools, "execute"):
            return tools.execute(tool_name, **args)

        tool = tools.get(tool_name) if hasattr(tools, "get") else None
        if tool is None:
            raise ValueError(f"未找到工具: {tool_name}")

        if callable(tool):
            return tool(**args)

        return tool.execute(**args)

    def _run_parallel(self, step_def: StepDefinition) -> List[Any]:
        sub_steps = step_def.parallel_steps or []
        if not sub_steps:
            return []

        sub_defs = [StepDefinition.from_dict(s) for s in sub_steps]
        results = []

        with ThreadPoolExecutor(max_workers=min(len(sub_defs), 4)) as pool:
            futures = {}
            for sd in sub_defs:
                futures[pool.submit(self._execute_step, sd)] = sd.step_id
            for future in futures:
                try:
                    step_result = future.result(timeout=300)
                    results.append(step_result)
                except Exception as e:
                    results.append(StepResult(
                        step_id=futures[future],
                        status=StepStatus.FAILED,
                        error=str(e),
                    ))

        return [r.output if isinstance(r, StepResult) else r for r in results]

    def _run_condition(self, step_def: StepDefinition) -> bool:
        expr = step_def.condition_expr or "true"
        rendered = self._render_string(expr)
        return self._eval_condition(rendered, step_def)

    def _run_loop(self, step_def: StepDefinition) -> List[Any]:
        items_expr = step_def.loop_items or ""
        rendered_items = self._render(items_expr)
        try:
            items = json.loads(rendered_items) if isinstance(rendered_items, str) else rendered_items
        except Exception:
            items = [rendered_items] if rendered_items else []

        if not isinstance(items, list):
            items = [items]

        results = []
        for i, item in enumerate(items[:step_def.max_iterations]):
            if self._cancelled or self._abort_event.is_set():
                break
            if step_def.loop_var:
                self.context.set_var(step_def.loop_var, item)
            self._log(f"循环迭代 {i+1}/{min(len(items), step_def.max_iterations)}")
            result = self._execute_step(StepDefinition(
                step_id=f"{step_def.step_id}_iter_{i}",
                name=f"{step_def.name} [{i+1}]",
                step_type=StepType.AGENT if step_def.prompt_template else StepType.TOOL,
                prompt_template=step_def.prompt_template,
                config=step_def.config,
            ))
            results.append(result.output)
        return results

    def _run_wait(self, step_def: StepDefinition) -> str:
        self.pause()
        return "waiting_for_user"

    def _run_notify(self, step_def: StepDefinition) -> str:
        msg = self._render(step_def.config.get("message", "工作流步骤完成"))
        self._log(msg, "notify")
        return msg

    def _eval_condition(self, expr: str, step_def: StepDefinition) -> bool:
        expr = expr.strip()
        if expr.lower() in ("true", "yes", "1"):
            return True
        if expr.lower() in ("false", "no", "0"):
            return False
        try:
            safe_globals = {"__builtins__": {}, "context": self.context}
            return bool(eval(expr, safe_globals))
        except Exception:
            return bool(self._render(expr))

    def _apply_param_chain_inputs(self, step_def: StepDefinition):
        if not step_def.param_inputs:
            return
        try:
            from .param_chain import ParamBinding, resolve_step_params
        except ImportError:
            return
        args = step_def.config.setdefault("args", {})
        for binding in step_def.param_inputs:
            target = binding.get("target", "")
            source = binding.get("source", "")
            if not target or not source:
                continue
            transform = binding.get("transform")
            default = binding.get("default")
            try:
                value = self._resolve_param_source(source)
                if transform:
                    value = self._apply_param_transform(value, transform, source)
                if value is None and default is not None:
                    value = default
                args[target] = value
            except Exception as e:
                logger.warning(f"param_chain input failed for {step_def.step_id}.{target}: {e}")
                if "default" in binding:
                    args[target] = binding["default"]

    def _apply_param_chain_outputs(self, step_def: StepDefinition, output: Any):
        if not step_def.param_outputs:
            return
        if output is None:
            return
        try:
            output_data = json.loads(output) if isinstance(output, str) else output
        except (json.JSONDecodeError, TypeError):
            output_data = {"_raw": str(output)[:5000]}
        for binding in step_def.param_outputs:
            name = binding.get("name", "")
            path = binding.get("path", "")
            target_type = binding.get("type", "auto")
            if not name:
                continue
            if path:
                cur = output_data
                for part in path.split("."):
                    if isinstance(cur, dict):
                        cur = cur.get(part)
                    else:
                        cur = None
                        break
            elif isinstance(output_data, dict):
                cur = output_data.get(name, output_data)
            else:
                cur = output_data
            if target_type and target_type != "auto" and cur is not None:
                try:
                    if target_type in ("string", "str"):
                        cur = str(cur)
                    elif target_type in ("int", "integer"):
                        cur = int(cur)
                    elif target_type in ("float", "number"):
                        cur = float(cur)
                    elif target_type in ("bool", "boolean"):
                        cur = bool(cur)
                except (ValueError, TypeError):
                    pass
            self.context.set_node_output(step_def.step_id, name, cur)
            self.context.node_outputs[f"{step_def.step_id}.{name}"] = cur
            self.context.set_var(f"{step_def.step_id}.{name}", cur)

    def _resolve_param_source(self, source: str) -> Any:
        if not source:
            return None
        if source.startswith("$input."):
            path = source[len("$input."):]
            cur = self.context.input_data
            for part in path.split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
            return cur
        if source.startswith("$node."):
            path = source[len("$node."):]
            parts = path.split(".", 1)
            node_id = parts[0]
            key = parts[1] if len(parts) > 1 else None
            node = self.context.node_outputs.get(node_id)
            if isinstance(node, dict) and key:
                return node.get(key)
            return node
        if source.startswith("$step."):
            path = source[len("$step."):]
            parts = path.split(".", 1)
            step_id = parts[0]
            key = parts[1] if len(parts) > 1 else None
            step_result = self.context.step_results.get(step_id)
            if not step_result:
                return None
            if key is None:
                return step_result.output
            try:
                output_data = json.loads(step_result.output) if isinstance(step_result.output, str) else step_result.output
            except (json.JSONDecodeError, TypeError):
                output_data = {}
            if isinstance(output_data, dict):
                return output_data.get(key)
            return output_data
        if source.startswith("$var."):
            path = source[len("$var."):]
            cur = self.context.variables
            for part in path.split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
            return cur
        if source in self.context.variables:
            return self.context.variables[source]
        if source in self.context.input_data:
            return self.context.input_data[source]
        return None

    def _apply_param_transform(self, value: Any, transform: str, source: str) -> Any:
        try:
            from .param_chain import _apply_transform
        except ImportError:
            return value
        return _apply_transform(value, transform, {
            "context": self.context,
            "source": source,
        })

    def _render(self, template: Any, **extra) -> Any:
        if isinstance(template, str):
            return self._render_string(template)
        if isinstance(template, dict):
            return {k: self._render(v) for k, v in template.items()}
        if isinstance(template, list):
            return [self._render(v) for v in template]
        return template

    def _render_string(self, s: str) -> str:
        result = s
        for key, val in self.context.variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(val))
        result = result.replace("{query}", self.context.input_data.get("query", ""))
        result = result.replace("{task}", self.context.input_data.get("task", ""))
        result = result.replace("{input_json}",
            json.dumps(self.context.input_data, ensure_ascii=False, indent=2))
        result = result.replace("{step_results}",
            json.dumps({k: v.to_dict() for k, v in self.context.step_results.items()},
                       ensure_ascii=False, indent=2))
        result = result.replace("{node_outputs}",
            json.dumps(self.context.node_outputs, ensure_ascii=False, indent=2))
        return result

    def _snapshot_to_db(self):
        self.context.updated_at = datetime.now().isoformat()
        self.engine.persistence.update_instance(
            self.context.instance_id,
            context_json=json.dumps(self.context.to_dict(), ensure_ascii=False),
        )

    def _update_db_step(self, step_id: str, step_name: str, progress: float):
        self.context.updated_at = datetime.now().isoformat()
        self.engine.persistence.update_instance(
            self.context.instance_id,
            current_step_id=step_id,
            current_step_name=step_name,
            progress=progress,
            context_json=json.dumps(self.context.to_dict(), ensure_ascii=False),
        )
        self.engine._emit_event(
            WorkflowEventType.PROGRESS_UPDATED, self.context.instance_id,
            step_id=step_id, step_name=step_name, progress=progress,
        )

    def _save_checkpoint(self, step_def: StepDefinition):
        self.engine.persistence.save_checkpoint(
            self.context.instance_id,
            step_def.step_id,
            step_def.name,
            self.context,
        )

    def _log(self, message: str, level: str = "info"):
        self.engine.persistence.add_log(
            self.context.instance_id, message, level,
            step_id=self.context.current_step or "",
            step_name=getattr(self._current_step_def, "name", ""),
        )

    def _fail(self, error: str):
        self.engine.persistence.update_instance(
            self.context.instance_id,
            status=WorkflowStatus.FAILED.value,
            error_message=error,
            context_json=json.dumps(self.context.to_dict(), ensure_ascii=False),
        )
        self.engine.persistence.add_log(
            self.context.instance_id, f"工作流失败: {error}", "error",
        )
        self.engine._emit_event(
            WorkflowEventType.WORKFLOW_FAILED, self.context.instance_id,
            error=error,
        )

    def _complete(self):
        self.engine.persistence.update_instance(
            self.context.instance_id,
            status=WorkflowStatus.COMPLETED.value,
            progress=1.0,
            completed_at=datetime.now().isoformat(),
            context_json=json.dumps(self.context.to_dict(), ensure_ascii=False),
        )
        self.engine.persistence.add_log(
            self.context.instance_id, "工作流完成", "info",
        )
        self.engine._emit_event(
            WorkflowEventType.WORKFLOW_COMPLETED, self.context.instance_id,
        )
        self._running_cleanup()

    def _running_cleanup(self):
        self.engine._running.pop(self.context.instance_id, None)

    def pause(self):
        self._paused = True
        self._snapshot_to_db()
        self.engine.persistence.update_instance(
            self.context.instance_id,
            status=WorkflowStatus.PAUSED.value,
            paused_at=datetime.now().isoformat(),
            context_json=json.dumps(self.context.to_dict(), ensure_ascii=False),
        )

    def cancel(self):
        self._cancelled = True
        self._paused = False
        self._abort_event.set()

    def _wait_if_paused(self):
        while self._paused and not self._cancelled and not self._abort_event.is_set():
            self._abort_event.wait(0.5)


def get_workflow_engine(db_path: Optional[Path] = None) -> WorkflowEngine:
    return WorkflowEngine.get_instance(db_path)


__all__ = [
    "WorkflowEngine", "WorkflowRunner", "WorkflowPersistence",
    "WorkflowDefinition", "StepDefinition",
    "WorkflowContext", "StepResult",
    "StepType", "StepStatus", "WorkflowStatus",
    "WorkflowEventType", "WorkflowEvent",
    "get_workflow_engine",
]
