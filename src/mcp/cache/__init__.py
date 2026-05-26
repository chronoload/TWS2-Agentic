#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 缓存基础设施 — 参考 Cline StateManager + OpenCode Session 设计

分层缓存架构：
  Layer 1: LRU Cache (热数据，纳秒级)
  Layer 2: StateManager (会话级缓存，内存)
  Layer 3: Disk Store (持久化，文件/JSON)

核心模块：
  - LRUCache:     线程安全 LRU，带 TTL 过期
  - StateManager: 类似 Cline 的全局状态+防抖持久化
  - ModelCache:   类似 Cline modelInfoCache + OpenCode models
  - ContextReloader: 类似 Cline ContextManager 的会话恢复
  - UIState:      UI 状态持久化
"""

from .lru_cache import LRUCache, TTLCache, CacheEntry
from .state_manager import (
    StateManager,
    GlobalState,
    WorkspaceState,
    SessionState,
    get_state_manager,
)
from .model_cache import (
    ModelCache,
    ModelInfo,
    ProviderModelCache,
    get_model_cache,
)
from .context_reloader import (
    ContextReloader,
    ContextCheckpoint,
    ConversationSnapshot,
)
from .ui_state import (
    UIStateManager,
    WindowGeometry,
    UIState,
    get_ui_state_manager,
)
from .disk import (
    DiskStore,
    KeyValueStore,
    JSONFileStore,
    get_disk_store,
)

__all__ = [
    "LRUCache",
    "TTLCache",
    "CacheEntry",
    "StateManager",
    "GlobalState",
    "WorkspaceState",
    "SessionState",
    "get_state_manager",
    "ModelCache",
    "ModelInfo",
    "ProviderModelCache",
    "get_model_cache",
    "ContextReloader",
    "ContextCheckpoint",
    "ConversationSnapshot",
    "UIStateManager",
    "WindowGeometry",
    "UIState",
    "get_ui_state_manager",
    "DiskStore",
    "KeyValueStore",
    "JSONFileStore",
    "get_disk_store",
]