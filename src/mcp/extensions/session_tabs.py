#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话 Tab 管理器
- 支持多会话在独立 Tab 中并行运行
- 每个 Tab 有独立的 Agent 实例和 UI 状态
- 保留右侧对话导航功能
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TabState:
    """Tab 状态"""
    tab_id: str
    conversation_id: str
    title: str
    is_active: bool = False
    is_processing: bool = False
    has_running_tasks: bool = False
    agent_instance: Optional[Any] = None
    last_updated: float = field(default_factory=lambda: datetime.now().timestamp())
    should_stop: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)
    chat_html: str = ""
    nav_blocks: List[Dict] = field(default_factory=list)
    nav_current_idx: int = -1
    scroll_position: float = 1.0


class SessionTabManager:
    """
    会话 Tab 管理器
    
    架构:
    ┌────────────────────────────────────────────────────────┐
    │                    SessionTabManager                     │
    │  (管理多个 Tab 的生命周期和状态)                         │
    ├────────────────────────────────────────────────────────┤
    │  tabs: Dict[str, TabState]                             │
    │    - 每个 tab_id 对应一个 TabState                      │
    │    - TabState 包含 agent_instance 和 UI 状态            │
    └────────────────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self.tabs: Dict[str, TabState] = {}
        self.active_tab_id: Optional[str] = None
        self._callbacks: List[Callable] = []
        self._tab_counter = 0
    
    def register_callback(self, callback: Callable):
        """注册 Tab 变更回调 callback(event_type, tab_id, tab_state)"""
        self._callbacks.append(callback)
    
    def _notify_callbacks(self, event_type: str, tab_id: str, **kwargs):
        """通知所有订阅者"""
        for callback in self._callbacks:
            try:
                callback(event_type, tab_id, **kwargs)
            except Exception as e:
                logger.error(f"Tab 回调执行失败: {e}")
    
    def create_tab(self, conversation_id: str, title: str = "新对话", 
                   agent_instance: Any = None) -> str:
        """创建新 Tab"""
        with self._lock:
            self._tab_counter += 1
            tab_id = f"tab_{self._tab_counter}_{conversation_id[:8]}"
            
            tab_state = TabState(
                tab_id=tab_id,
                conversation_id=conversation_id,
                title=title,
                agent_instance=agent_instance
            )
            
            self.tabs[tab_id] = tab_state
            self._notify_callbacks("created", tab_id, tab_state=tab_state)
            
            logger.info(f"创建 Tab: {title} ({tab_id})")
            return tab_id
    
    def get_tab(self, tab_id: str) -> Optional[TabState]:
        """获取指定 Tab"""
        return self.tabs.get(tab_id)
    
    def get_active_tab(self) -> Optional[TabState]:
        """获取当前活动 Tab"""
        if self.active_tab_id:
            return self.tabs.get(self.active_tab_id)
        return None
    
    def set_active_tab(self, tab_id: str) -> bool:
        """设置活动 Tab"""
        with self._lock:
            if tab_id not in self.tabs:
                return False
            
            for tid, state in self.tabs.items():
                state.is_active = (tid == tab_id)
            
            self.active_tab_id = tab_id
            self._notify_callbacks("activated", tab_id)
            
            logger.info(f"激活 Tab: {self.tabs[tab_id].title} ({tab_id})")
            return True
    
    def close_tab(self, tab_id: str) -> bool:
        """关闭 Tab"""
        with self._lock:
            if tab_id not in self.tabs:
                return False
            
            tab_state = self.tabs[tab_id]
            
            if tab_state.is_processing:
                if tab_state.agent_instance and hasattr(tab_state.agent_instance, 'cancel'):
                    tab_state.agent_instance.cancel()
                logger.info(f"关闭 Tab 时取消运行中的任务: {tab_id}")
            
            del self.tabs[tab_id]
            
            if self.active_tab_id == tab_id:
                if self.tabs:
                    self.active_tab_id = next(iter(self.tabs.keys()))
                    self.tabs[self.active_tab_id].is_active = True
                else:
                    self.active_tab_id = None
            
            self._notify_callbacks("closed", tab_id)
            logger.info(f"关闭 Tab: {tab_id}")
            return True
    
    def set_processing(self, tab_id: str, is_processing: bool):
        """设置 Tab 的处理状态"""
        if tab_id in self.tabs:
            self.tabs[tab_id].is_processing = is_processing
            self._notify_callbacks("processing_changed", tab_id, is_processing=is_processing)
    
    def update_agent(self, tab_id: str, agent_instance: Any):
        """更新 Tab 的 Agent 实例"""
        if tab_id in self.tabs:
            self.tabs[tab_id].agent_instance = agent_instance
    
    def update_title(self, tab_id: str, title: str):
        """更新 Tab 标题"""
        if tab_id in self.tabs:
            self.tabs[tab_id].title = title
            self._notify_callbacks("title_changed", tab_id, title=title)
    
    def get_all_tabs(self) -> List[TabState]:
        """获取所有 Tab"""
        return list(self.tabs.values())
    
    def get_running_tabs(self) -> List[TabState]:
        """获取正在运行（后台有任务）的 Tab"""
        return [t for t in self.tabs.values() if t.has_running_tasks or t.is_processing]
    
    def has_running_tasks(self, tab_id: str) -> bool:
        """检查指定 Tab 是否有运行中的任务"""
        if tab_id in self.tabs:
            return self.tabs[tab_id].has_running_tasks or self.tabs[tab_id].is_processing
        return False
    
    def cancel_tab(self, tab_id: str) -> bool:
        """取消指定 Tab 的运行"""
        if tab_id in self.tabs:
            tab_state = self.tabs[tab_id]
            tab_state.should_stop = True
            if tab_state.cancel_event:
                tab_state.cancel_event.set()
            if tab_state.agent_instance and hasattr(tab_state.agent_instance, 'cancel'):
                tab_state.agent_instance.cancel()
                logger.info(f"取消 Tab 任务: {tab_id}")
                return True
        return False
    
    def set_should_stop(self, tab_id: str, value: bool):
        """设置指定 Tab 的 should_stop 标志"""
        if tab_id in self.tabs:
            self.tabs[tab_id].should_stop = value
            if value and self.tabs[tab_id].cancel_event:
                self.tabs[tab_id].cancel_event.set()
            elif not value and self.tabs[tab_id].cancel_event:
                self.tabs[tab_id].cancel_event.clear()
    
    def get_should_stop(self, tab_id: str) -> bool:
        """获取指定 Tab 的 should_stop 标志"""
        if tab_id in self.tabs:
            return self.tabs[tab_id].should_stop
        return False
    
    def save_tab_ui_state(self, tab_id: str, chat_html: str = "",
                          nav_blocks: List[Dict] = None, nav_current_idx: int = -1,
                          scroll_position: float = 1.0):
        """保存指定 Tab 的 UI 状态"""
        if tab_id in self.tabs:
            tab = self.tabs[tab_id]
            tab.chat_html = chat_html
            if nav_blocks is not None:
                tab.nav_blocks = nav_blocks
            tab.nav_current_idx = nav_current_idx
            tab.scroll_position = scroll_position
            tab.last_updated = datetime.now().timestamp()
    
    def get_tab_ui_state(self, tab_id: str) -> Optional[Dict]:
        """获取指定 Tab 的 UI 状态"""
        if tab_id in self.tabs:
            tab = self.tabs[tab_id]
            return {
                "chat_html": tab.chat_html,
                "nav_blocks": tab.nav_blocks,
                "nav_current_idx": tab.nav_current_idx,
                "scroll_position": tab.scroll_position,
            }
        return None


_global_tab_manager: Optional[SessionTabManager] = None


def get_session_tab_manager() -> SessionTabManager:
    """获取全局 Tab 管理器（单例模式）"""
    global _global_tab_manager
    if _global_tab_manager is None:
        _global_tab_manager = SessionTabManager()
    return _global_tab_manager


def reset_session_tab_manager():
    """重置全局 Tab 管理器（用于测试）"""
    global _global_tab_manager
    _global_tab_manager = None
