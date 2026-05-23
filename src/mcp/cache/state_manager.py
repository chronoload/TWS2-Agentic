#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
状态管理器 — 参考 Cline StateManager 设计
内存缓存 + 延迟防抖持久化 (500ms)
优先级: remote_config > session_override > task > global
"""

import time
import logging
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from .disk import get_disk_store, DiskStore

logger = logging.getLogger(__name__)


@dataclass
class GlobalState:
    api_provider: str = ""
    api_model_id: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    max_rounds: int = 20
    auto_approve_tools: bool = False
    theme: str = "light"
    language: str = "zh-CN"
    plan_mode: bool = False
    task_history: List[Dict] = field(default_factory=list)
    custom_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceState:
    last_opened_tab: str = ""
    last_search_query: str = ""
    selected_domain: str = ""
    selected_course: str = ""
    view_mode: str = "list"
    sort_by: str = "title"
    sort_order: str = "asc"
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionState:
    session_id: str = ""
    session_override_auto_approve: Optional[bool] = None
    session_override_temperature: Optional[float] = None
    session_override_max_tokens: Optional[int] = None


class StateManager:
    """
    内存缓存 + 防抖持久化 — 类似 Cline StateManager

    优先级链: remote_config > session_override > task_state > global_state > workspace_state
    """

    _instance: Optional["StateManager"] = None

    PERSISTENCE_DELAY_MS = 500

    def __init__(self, disk_store: Optional[DiskStore] = None):
        self._disk = disk_store or get_disk_store()
        self._lock = threading.RLock()

        # 内存缓存层
        self._global_state_cache: Dict[str, Any] = {}
        self._workspace_state_cache: Dict[str, Any] = {}
        self._session_override_cache: Dict[str, Any] = {}
        self._remote_config_cache: Dict[str, Any] = {}
        self._task_state_cache: Dict[str, Any] = {}
        self._secrets_cache: Dict[str, str] = {}

        # 防抖持久化
        self._pending_global: Set[str] = set()
        self._pending_workspace: Set[str] = set()
        self._pending_secrets: Set[str] = set()
        self._persistence_timer: Optional[threading.Timer] = None

        self._initialized = False

    @classmethod
    def initialize(cls, disk_store: Optional[DiskStore] = None) -> "StateManager":
        if cls._instance is None:
            cls._instance = cls(disk_store)
        if cls._instance._initialized:
            return cls._instance

        cls._instance._load_from_disk()
        cls._instance._initialized = True
        logger.info("StateManager 初始化完成")
        return cls._instance

    @classmethod
    def get(cls) -> "StateManager":
        if cls._instance is None:
            raise RuntimeError("StateManager 尚未初始化，请先调用 StateManager.initialize()")
        return cls._instance

    @classmethod
    def get_or_create(cls) -> "StateManager":
        if cls._instance is None:
            return cls.initialize()
        return cls._instance

    def _load_from_disk(self):
        with self._lock:
            self._global_state_cache = self._disk.global_state.all()
            self._workspace_state_cache = self._disk.workspace_state.all()
            self._secrets_cache = self._disk.secrets.all()

    def _schedule_persistence(self):
        if self._persistence_timer:
            self._persistence_timer.cancel()
        self._persistence_timer = threading.Timer(
            self.PERSISTENCE_DELAY_MS / 1000.0,
            self._persist_pending
        )
        self._persistence_timer.daemon = True
        self._persistence_timer.start()

    def _persist_pending(self):
        with self._lock:
            if self._pending_global:
                updates = {k: self._global_state_cache[k]
                          for k in self._pending_global if k in self._global_state_cache}
                self._disk.global_state.set_batch(updates)
                self._pending_global.clear()

            if self._pending_workspace:
                updates = {k: self._workspace_state_cache[k]
                          for k in self._pending_workspace if k in self._workspace_state_cache}
                self._disk.workspace_state.set_batch(updates)
                self._pending_workspace.clear()

            if self._pending_secrets:
                updates = {k: self._secrets_cache[k]
                          for k in self._pending_secrets if k in self._secrets_cache}
                self._disk.secrets.set_batch(updates)
                self._pending_secrets.clear()

    def flush(self):
        if self._persistence_timer:
            self._persistence_timer.cancel()
            self._persistence_timer = None
        self._persist_pending()

    # === Global State ===

    def set_global(self, key: str, value: Any):
        with self._lock:
            self._global_state_cache[key] = value
            self._pending_global.add(key)
            self._schedule_persistence()

    def set_global_batch(self, updates: Dict[str, Any]):
        with self._lock:
            self._global_state_cache.update(updates)
            self._pending_global.update(updates.keys())
            self._schedule_persistence()

    def get_global(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._global_state_cache.get(key, default)

    # === Workspace State ===

    def set_workspace(self, key: str, value: Any):
        with self._lock:
            self._workspace_state_cache[key] = value
            self._pending_workspace.add(key)
            self._schedule_persistence()

    def set_workspace_batch(self, updates: Dict[str, Any]):
        with self._lock:
            self._workspace_state_cache.update(updates)
            self._pending_workspace.update(updates.keys())
            self._schedule_persistence()

    def get_workspace(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._workspace_state_cache.get(key, default)

    # === Secrets ===

    def set_secret(self, key: str, value: str):
        with self._lock:
            self._secrets_cache[key] = value
            self._pending_secrets.add(key)
            self._schedule_persistence()

    def get_secret(self, key: str) -> Optional[str]:
        with self._lock:
            return self._secrets_cache.get(key)

    # === Session Override (内存隔离，不持久化) ===

    def set_session_override(self, key: str, value: Any):
        with self._lock:
            self._session_override_cache[key] = value

    def get_session_override(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._session_override_cache.get(key)

    def clear_session_overrides(self):
        with self._lock:
            self._session_override_cache.clear()

    # === Remote Config ===

    def set_remote_config(self, key: str, value: Any):
        with self._lock:
            self._remote_config_cache[key] = value

    def replace_remote_config(self, config: Dict[str, Any]):
        with self._lock:
            self._remote_config_cache = dict(config)

    def get_remote_config(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._remote_config_cache.get(key)

    # === Task State ===

    def set_task_state(self, key: str, value: Any):
        with self._lock:
            self._task_state_cache[key] = value

    def get_task_state(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._task_state_cache.get(key)

    def clear_task_state(self):
        with self._lock:
            self._task_state_cache.clear()

    # === 优先级获取 ===

    def get_with_precedence(self, key: str, default: Any = None) -> Any:
        """优先级: remote > session_override > task > global > workspace"""
        with self._lock:
            if key in self._remote_config_cache:
                return self._remote_config_cache[key]
            if key in self._session_override_cache:
                return self._session_override_cache[key]
            if key in self._task_state_cache:
                return self._task_state_cache[key]
            if key in self._global_state_cache:
                return self._global_state_cache[key]
            if key in self._workspace_state_cache:
                return self._workspace_state_cache[key]
            return default

    # === 导出 ===

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "global": deepcopy(self._global_state_cache),
                "workspace": deepcopy(self._workspace_state_cache),
                "task": deepcopy(self._task_state_cache),
                "session_overrides": deepcopy(self._session_override_cache),
                "remote_config": deepcopy(self._remote_config_cache),
            }

    def reinitialize(self):
        self.flush()
        self._load_from_disk()


_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    return StateManager.get_or_create()