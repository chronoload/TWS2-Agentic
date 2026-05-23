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
"""
from __future__ import annotations

import json
import uuid
import sqlite3
import asyncio
import threading
import traceback
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Union, Set
from concurrent.futures import ThreadPoolExecutor


class StepType(Enum):
    AGENT = "agent"
    TOOL = "tool"
    CONDITION = "condition"
    PARALLEL = "parallel"
    LOOP = "loop"
    WAIT = "wait"
    NOTIFY = "notify"


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
            started_at=data.get("started_at"),
            updated_at=data.get("updated_at"),
        )
        for sid, sr in data.get("step_results", {}).items():
            ctx.step_results[sid] = StepResult.from_dict(sr)
        return ctx


# ============================================================
# 工作流 DSL 定义
# ============================================================

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


# ============================================================
# Persistence Layer — SQLite
# ============================================================

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

    # ---- Definition CRUD ----

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

    # ---- Instance CRUD ----

    def save_instance(self, instance_data: dict):
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO workflow_instances
                (instance_id, workflow_id, status, current_step_id,
                 context_json, progress, started_at, paused_at,
                 completed_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                instance_data["instance_id"],
                instance_data["workflow_id"],
                instance_data.get("status", "pending"),
                instance_data.get("current_step_id"),
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

    # ---- Checkpoints ----

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

    # ---- Artifacts ----

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

    # ---- Logs ----

    def add_log(self, instance_id: str, message: str,
                level: str = "info", step_id: str = "",
                metadata: dict = None):
        log_id = str(uuid.uuid4())
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
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


# ============================================================
# Workflow Engine
# ============================================================

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
        self._agent = None
        self._tools = None

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

    # ---- Workflow Lifecycle ----

    def start_workflow(self, definition: WorkflowDefinition,
                       input_data: Dict[str, Any] = None,
                       callbacks: List[Callable] = None) -> str:
        """同步启动工作流，后台执行"""
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
        return instance_id

    def pause_workflow(self, instance_id: str) -> bool:
        runner = self._running.get(instance_id)
        if runner:
            runner.pause()
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

        from_step = checkpoint["step_id"] if checkpoint else None
        runner = WorkflowRunner(self, definition, ctx)
        self._running[instance_id] = runner
        self._executor.submit(runner.run_sync, from_step)
        return True

    def cancel_workflow(self, instance_id: str) -> bool:
        runner = self._running.get(instance_id)
        if runner:
            runner.cancel()
            self._notify(instance_id, {"type": "cancelled", "message": "工作流已取消"})
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
            "progress": instance.get("progress", 0.0),
            "started_at": instance.get("started_at"),
        }

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


# ============================================================
# Workflow Runner
# ============================================================

class WorkflowRunner:
    """单个工作流实例的运行器"""
    import re as _re

    def __init__(self, engine: WorkflowEngine, definition: WorkflowDefinition,
                 context: WorkflowContext):
        self.engine = engine
        self.definition = definition
        self.context = context
        self._paused = False
        self._cancelled = False
        self._current_step_def: Optional[StepDefinition] = None

    def run_sync(self, from_step: Optional[str] = None):
        """同步执行——由线程池调用"""
        try:
            self._run(from_step)
        except Exception as e:
            self._fail(str(e))

    def _run(self, from_step: Optional[str] = None):
        steps: List[StepDefinition]

        if from_step:
            idx = self.definition.get_step_index(from_step)
            steps = self.definition.steps[idx + 1:]
        else:
            steps = list(self.definition.steps)
            self._snapshot_to_db()

        total = len(self.definition.steps)
        for i, step_def in enumerate(steps):
            if self._cancelled:
                break
            self._wait_if_paused()
            if self._cancelled:
                break

            self._current_step_def = step_def
            self.context.current_step = step_def.step_id
            self._update_db_step(step_def.step_id, (i + 1) / max(total, 1))
            self._log(f"执行步骤 [{i+1}/{total}]: {step_def.name}")

            result = self._execute_step(step_def)
            self.context.step_results[step_def.step_id] = result

            if result.status == StepStatus.FAILED and step_def.max_retries > 0:
                for attempt in range(step_def.max_retries):
                    self._log(f"重试 {attempt+1}/{step_def.max_retries}")
                    result = self._execute_step(step_def)
                    result.retry_count = attempt + 1
                    if result.status == StepStatus.COMPLETED:
                        break

            if result.status == StepStatus.FAILED:
                self._fail(f"步骤 {step_def.name} 失败: {result.error}")
                return

            if step_def.step_id in self.definition.checkpoint_after:
                self._save_checkpoint(step_def)
                self._snapshot_to_db()

        if not self._cancelled:
            self._complete()

    def _execute_step(self, step_def: StepDefinition) -> StepResult:
        result = StepResult(
            step_id=step_def.step_id,
            status=StepStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )

        try:
            st = step_def.step_type

            if st == StepType.AGENT:
                output = self._run_agent(step_def)
            elif st == StepType.TOOL:
                output = self._run_tool(step_def)
            elif st == StepType.PARALLEL:
                output = self._run_parallel(step_def)
            elif st == StepType.CONDITION:
                output = self._run_condition(step_def)
            elif st == StepType.WAIT:
                output = self._run_wait(step_def)
            elif st == StepType.NOTIFY:
                output = self._run_notify(step_def)
            else:
                output = None

            result.status = StepStatus.COMPLETED
            result.output = output

        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = f"{type(e).__name__}: {e}"
            traceback.print_exc()

        result.completed_at = datetime.now().isoformat()
        return result

    def _run_agent(self, step_def: StepDefinition) -> str:
        agent = self.engine._agent
        if not agent:
            raise RuntimeError("Agent 未初始化")

        prompt = self._render(step_def.prompt_template or "")
        # 确保 context 作为 JSON 注入
        ctx = json.dumps(self.context.variables, ensure_ascii=False, indent=2)
        full_prompt = f"{prompt}\n\n上下文数据:\n```json\n{ctx}\n```"

        try:
            return agent.chat_sync(full_prompt)
        except AttributeError:
            return agent.chat(full_prompt)

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
                    results.append(future.result(timeout=300))
                except Exception as e:
                    results.append(StepResult(
                        step_id=futures[future],
                        status=StepStatus.FAILED,
                        error=str(e),
                    ))

        return [r.output for r in results]

    def _run_condition(self, step_def: StepDefinition) -> bool:
        expr = step_def.condition_expr or "true"
        rendered = self._render(f"${{{expr}}}")
        return self._eval_condition(rendered, step_def)

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
        import re
        for key, val in self.context.variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(val))
        result = result.replace("{query}", self.context.input_data.get("query", ""))
        result = result.replace("{task}", self.context.input_data.get("task", ""))
        result = result.replace("{input_json}",
            json.dumps(self.context.input_data, ensure_ascii=False, indent=2))
        result = result.replace("{step_results}",
            json.dumps({k: v.to_dict() for k, v in self.context.step_results.items()},
                       ensure_ascii=False, indent=2))
        return result

    # ---- State management ----

    def _snapshot_to_db(self):
        self.context.updated_at = datetime.now().isoformat()
        self.engine.persistence.update_instance(
            self.context.instance_id,
            context_json=json.dumps(self.context.to_dict(), ensure_ascii=False),
        )

    def _update_db_step(self, step_id: str, progress: float):
        self.engine.persistence.update_instance(
            self.context.instance_id,
            current_step_id=step_id,
            progress=progress,
            context_json=json.dumps(self.context.to_dict(), ensure_ascii=False),
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
        self.engine._notify(self.context.instance_id,
                           {"type": "failed", "error": error})

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
        self.engine._notify(self.context.instance_id,
                           {"type": "completed", "instance_id": self.context.instance_id})

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

    def _wait_if_paused(self):
        import time
        while self._paused and not self._cancelled:
            time.sleep(0.5)


# ============================================================
# Convenience Functions
# ============================================================

def get_workflow_engine(db_path: Optional[Path] = None) -> WorkflowEngine:
    return WorkflowEngine.get_instance(db_path)


__all__ = [
    "WorkflowEngine", "WorkflowRunner", "WorkflowPersistence",
    "WorkflowDefinition", "StepDefinition",
    "WorkflowContext", "StepResult",
    "StepType", "StepStatus", "WorkflowStatus",
    "get_workflow_engine",
]