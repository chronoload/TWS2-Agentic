from __future__ import annotations

import logging
import threading
import time
import uuid
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

from .persistence import AutomationPersistence, AutomationTask, AutomationRun, MIN_INTERVAL_SECONDS
from .triggers import TriggerType, create_trigger, EventTrigger
from .event_bus import EventBus, Event

try:
    from ..runtime import RunManager, RunRecord, RunStatus, RunJournal, JournalEventType
    HAS_RUNTIME = True
except ImportError:
    HAS_RUNTIME = False

logger = logging.getLogger(__name__)


class AutomationType(Enum):
    MODEL = "model"
    NON_MODEL = "non_model"
    WORKFLOW = "workflow"
    POPUP = "popup"


@dataclass
class TaskStatus:
    task_id: str
    name: str
    automation_type: str
    trigger_type: str
    enabled: bool
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    is_running: bool = False
    last_error: Optional[str] = None


class AutomationEngine:
    _instance: Optional["AutomationEngine"] = None
    _init_lock = threading.Lock()

    SCHEDULE_INTERVAL = 30

    def __init__(self, db_path: Optional[Path] = None):
        db_path = Path(db_path) if db_path else Path("data/automation.db")
        self.persistence = AutomationPersistence(db_path)
        self.event_bus = EventBus.get_instance()
        self.popup_manager = None
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="auto-")
        self._triggers: Dict[str, Any] = {}
        self._running_tasks: Dict[str, str] = {}
        self._running = False
        self._schedule_thread: Optional[threading.Thread] = None
        self._event_sub_id: Optional[str] = None
        self._model_provider = None
        self._workflow_engine = None
        self._run_manager = RunManager() if HAS_RUNTIME else None
        self._run_journal = RunJournal(
            journal_dir=str(db_path.parent / "journal")
        ) if HAS_RUNTIME else None
        self._load_triggers()

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> "AutomationEngine":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance

    def set_model_provider(self, provider):
        self._model_provider = provider

    def set_workflow_engine(self, engine):
        self._workflow_engine = engine

    def set_popup_manager(self, manager):
        self.popup_manager = manager

    def _load_triggers(self):
        tasks = self.persistence.list_tasks()
        with self._lock:
            for task in tasks:
                if task.enabled:
                    self._create_trigger_for_task(task)

    def _create_trigger_for_task(self, task: AutomationTask):
        try:
            trigger_type = TriggerType(task.trigger_type)
            trigger = create_trigger(trigger_type, task.trigger_config)
            self._triggers[task.task_id] = trigger
        except Exception:
            logger.exception("Failed to create trigger for task %s", task.task_id)

    def start(self):
        if self._running:
            return
        self._running = True
        self._event_sub_id = self.event_bus.subscribe(
            "automation.*", self._on_event
        )
        self._schedule_thread = threading.Thread(
            target=self._schedule_loop, daemon=True, name="auto-scheduler"
        )
        self._schedule_thread.start()
        logger.info("AutomationEngine started")

    def stop(self):
        self._running = False
        if self._event_sub_id:
            self.event_bus.unsubscribe(self._event_sub_id)
            self._event_sub_id = None
        if self._schedule_thread:
            self._schedule_thread.join(timeout=5)
            self._schedule_thread = None
        logger.info("AutomationEngine stopped")

    def _schedule_loop(self):
        while self._running:
            try:
                self._check_triggers()
            except Exception:
                logger.exception("Error in schedule loop")
            time.sleep(self.SCHEDULE_INTERVAL)

    def _check_triggers(self):
        tasks = self.persistence.list_tasks(enabled_only=True)
        for task in tasks:
            with self._lock:
                if task.task_id in self._running_tasks:
                    continue
                trigger = self._triggers.get(task.task_id)
                if trigger is None:
                    continue

            result = trigger.check(task.last_run_at)
            if result.should_fire:
                self._executor.submit(self._execute_task, task.task_id)
            if result.next_run_at:
                self.persistence.update_task_last_run(
                    task.task_id, task.last_run_at, result.next_run_at
                )

    def _on_event(self, event: Event):
        with self._lock:
            for task_id, trigger in self._triggers.items():
                if isinstance(trigger, EventTrigger):
                    trigger.notify_event(event.event_type)

    def register_task(self, name: str, automation_type: str,
                      trigger_type: str, trigger_config: Dict[str, Any],
                      action_config: Dict[str, Any] = None,
                      metadata: Dict[str, Any] = None) -> str:
        task_id = uuid.uuid4().hex[:12]
        try:
            AutomationType(automation_type)
        except ValueError:
            raise ValueError(f"Invalid automation_type: {automation_type}")
        try:
            TriggerType(trigger_type)
        except ValueError:
            raise ValueError(f"Invalid trigger_type: {trigger_type}")

        if trigger_type == TriggerType.INTERVAL.value:
            interval = trigger_config.get("interval_seconds", 0)
            if interval < MIN_INTERVAL_SECONDS:
                trigger_config["interval_seconds"] = MIN_INTERVAL_SECONDS

        task = AutomationTask(
            task_id=task_id,
            name=name,
            automation_type=automation_type,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            action_config=action_config or {},
            metadata=metadata or {},
            enabled=True,
        )
        self.persistence.save_task(task)
        with self._lock:
            self._create_trigger_for_task(task)
        self.persistence.add_log(task_id, f"Task registered: {name}")
        self.event_bus.publish("automation.task_registered", {"task_id": task_id, "name": name})
        return task_id

    def unregister_task(self, task_id: str) -> bool:
        with self._lock:
            self._triggers.pop(task_id, None)
            self._running_tasks.pop(task_id, None)
        result = self.persistence.delete_task(task_id)
        if result:
            self.persistence.add_log(task_id, "Task unregistered")
            self.event_bus.publish("automation.task_unregistered", {"task_id": task_id})
        return result

    def enable_task(self, task_id: str) -> bool:
        result = self.persistence.update_task_enabled(task_id, True)
        if result:
            task = self.persistence.get_task(task_id)
            if task:
                with self._lock:
                    self._create_trigger_for_task(task)
            self.persistence.add_log(task_id, "Task enabled")
            self.event_bus.publish("automation.task_enabled", {"task_id": task_id})
        return result

    def disable_task(self, task_id: str) -> bool:
        with self._lock:
            self._triggers.pop(task_id, None)
        result = self.persistence.update_task_enabled(task_id, False)
        if result:
            self.persistence.add_log(task_id, "Task disabled")
            self.event_bus.publish("automation.task_disabled", {"task_id": task_id})
        return result

    def trigger_task(self, task_id: str) -> Optional[str]:
        task = self.persistence.get_task(task_id)
        if task is None:
            return None
        with self._lock:
            if task_id in self._running_tasks:
                return self._running_tasks[task_id]
        run_id = uuid.uuid4().hex[:12]
        self._executor.submit(self._execute_task, task_id, run_id)
        return run_id

    def list_tasks(self, enabled_only: bool = False) -> List[AutomationTask]:
        return self.persistence.list_tasks(enabled_only=enabled_only)

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        task = self.persistence.get_task(task_id)
        if task is None:
            return None
        with self._lock:
            is_running = task_id in self._running_tasks
        last_run = self.persistence.get_last_run(task_id)
        last_error = None
        if last_run and last_run.error:
            last_error = last_run.error
        return TaskStatus(
            task_id=task.task_id,
            name=task.name,
            automation_type=task.automation_type,
            trigger_type=task.trigger_type,
            enabled=task.enabled,
            last_run_at=task.last_run_at,
            next_run_at=task.next_run_at,
            is_running=is_running,
            last_error=last_error,
        )

    def _execute_task(self, task_id: str, run_id: str = None):
        task = self.persistence.get_task(task_id)
        if task is None:
            return

        run_id = run_id or uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()

        with self._lock:
            self._running_tasks[task_id] = run_id

        run = AutomationRun(
            run_id=run_id,
            task_id=task_id,
            status="running",
            started_at=now,
        )
        self.persistence.save_run(run)
        self.persistence.add_log(task_id, f"Task execution started: {task.name}", run_id=run_id)
        self.event_bus.publish("automation.task_started", {"task_id": task_id, "run_id": run_id})

        start_time = time.time()
        try:
            result = self._dispatch_action(task)
            elapsed = int((time.time() - start_time) * 1000)
            self.persistence.update_run(
                run_id,
                status="completed",
                completed_at=datetime.now().isoformat(),
                duration_ms=elapsed,
                result=str(result) if result else None,
            )
            self.persistence.update_task_last_run(task_id, now)
            self.persistence.add_log(
                task_id, f"Task completed in {elapsed}ms", run_id=run_id, log_level="info"
            )
            self.event_bus.publish("automation.task_completed", {
                "task_id": task_id, "run_id": run_id, "duration_ms": elapsed,
            })
        except Exception as e:
            elapsed = int((time.time() - start_time) * 1000)
            error_msg = f"{type(e).__name__}: {e}"
            self.persistence.update_run(
                run_id,
                status="failed",
                completed_at=datetime.now().isoformat(),
                duration_ms=elapsed,
                error=error_msg,
            )
            self.persistence.add_log(
                task_id, f"Task failed: {error_msg}", run_id=run_id, log_level="error"
            )
            self.event_bus.publish("automation.task_failed", {
                "task_id": task_id, "run_id": run_id, "error": error_msg,
            })
            logger.exception("Task %s execution failed", task_id)
        finally:
            with self._lock:
                self._running_tasks.pop(task_id, None)

    def _dispatch_action(self, task: AutomationTask) -> Any:
        auto_type = AutomationType(task.automation_type)

        if auto_type == AutomationType.MODEL:
            return self._execute_model_task(task)
        elif auto_type == AutomationType.NON_MODEL:
            return self._execute_non_model_task(task)
        elif auto_type == AutomationType.WORKFLOW:
            return self._execute_workflow_task(task)
        elif auto_type == AutomationType.POPUP:
            return self._execute_popup_task(task)
        else:
            raise ValueError(f"Unknown automation type: {auto_type}")

    def _execute_model_task(self, task: AutomationTask) -> Any:
        if self._model_provider is None:
            try:
                from ..llm import get_model_provider
                self._model_provider = get_model_provider()
            except (ImportError, AttributeError):
                raise RuntimeError("Model provider not available")

        prompt = task.action_config.get("prompt", "")
        model = task.action_config.get("model", "")
        if not prompt:
            raise ValueError("Model task requires 'prompt' in action_config")

        if hasattr(self._model_provider, "generate"):
            return self._model_provider.generate(prompt)
        elif hasattr(self._model_provider, "chat"):
            messages = [{"role": "user", "content": prompt}]
            return self._model_provider.chat(messages)
        elif callable(self._model_provider):
            return self._model_provider(prompt=prompt, model=model)
        else:
            raise RuntimeError("Model provider has no callable interface")

    def _execute_non_model_task(self, task: AutomationTask) -> Any:
        action = task.action_config.get("action", "")
        params = task.action_config.get("params", {})

        if action == "log":
            message = params.get("message", "")
            logger.info("Non-model task log: %s", message)
            return message

        handler = task.action_config.get("handler")
        if handler and callable(handler):
            return handler(**params)

        raise ValueError(f"Unknown non-model action: {action}")

    def _execute_workflow_task(self, task: AutomationTask) -> Any:
        if self._workflow_engine is None:
            try:
                from ..workflow_engine import get_workflow_engine
                self._workflow_engine = get_workflow_engine()
            except (ImportError, AttributeError):
                raise RuntimeError("Workflow engine not available")

        workflow_id = task.action_config.get("workflow_id", "")
        input_data = task.action_config.get("input_data", {})
        if not workflow_id:
            raise ValueError("Workflow task requires 'workflow_id' in action_config")

        definition = self._workflow_engine.persistence.get_definition(workflow_id)
        if definition is None:
            raise ValueError(f"Workflow not found: {workflow_id}")

        instance_id = self._workflow_engine.start_workflow(definition, input_data)
        return {"instance_id": instance_id}

    def _execute_popup_task(self, task: AutomationTask) -> Any:
        if self.popup_manager is None:
            from .popup_manager import PopupManager
            self.popup_manager = PopupManager.get_instance()

        popup_id = task.action_config.get("popup_id", task.task_id)
        title = task.action_config.get("title", "学习提醒")
        content = task.action_config.get("content", "")
        show_popup = task.action_config.get("show_popup", True)

        if show_popup:
            assistant = self.popup_manager.create_assistant(
                popup_id, task.action_config.get("popup_config")
            )
            assistant.show()
            if content:
                assistant.push_notification(title, content)
            return {"popup_id": popup_id, "shown": True}
        else:
            pushed = self.popup_manager.push_to_assistant(popup_id, title, content)
            return {"popup_id": popup_id, "pushed": pushed}


def get_automation_engine(db_path: Optional[Path] = None) -> AutomationEngine:
    return AutomationEngine.get_instance(db_path)


__all__ = [
    "AutomationEngine", "AutomationType", "TaskStatus",
    "get_automation_engine",
]
