#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一会话管理器 - 唯一的会话管理入口
桥接持久化层（ConversationHistory/SQLite）和运行时层（SessionInstanceManager）
确保 UI、Agent 助手窗口、缓存和工具系统完全同步
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from collections import OrderedDict

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """会话摘要信息 - 用于列表展示"""
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    turn_count: int = 0
    is_active: bool = False
    has_running_tasks: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


class UnifiedSessionManager:
    """
    统一会话管理器 - 唯一的会话管理入口
    
    架构:
    ┌─────────────────────────────────────┐
    │       UnifiedSessionManager         │  ← 唯一入口
    │  (桥接持久化层和运行时层)            │
    ├─────────────┬───────────────────────┤
    │ 持久化层     │ 运行时层              │
    │ ConvHistory │ SessionInstanceMgr    │
    │ (SQLite)    │ (内存+后台任务)       │
    └─────────────┴───────────────────────┘
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.RLock()
        self._callbacks: List[Callable] = []
        self._active_session_id: Optional[str] = None
        
        # 持久化层：延迟导入，避免循环依赖
        self._conversation_history = None
        self._db_path = db_path
        
        # 运行时层：延迟导入
        self._instance_manager = None
        
        # 内存缓存：会话摘要
        self._session_cache: OrderedDict[str, SessionInfo] = OrderedDict()
    
    def _get_conversation_history(self):
        """延迟获取 ConversationHistory"""
        if self._conversation_history is None:
            try:
                from ..agent_assistant import ConversationHistory
                self._conversation_history = ConversationHistory(self._db_path or "ws2_agent_history.db")
                self._rebuild_cache()
            except Exception as e:
                logger.error(f"ConversationHistory 初始化失败: {e}")
        return self._conversation_history
    
    def _get_instance_manager(self):
        """延迟获取 SessionInstanceManager"""
        if self._instance_manager is None:
            try:
                from .session_instances import get_session_instance_manager
                self._instance_manager = get_session_instance_manager()
            except Exception as e:
                logger.error(f"SessionInstanceManager 初始化失败: {e}")
        return self._instance_manager
    
    def _rebuild_cache(self):
        """从持久化层重建内存缓存"""
        history = self._get_conversation_history()
        if not history:
            return
        
        try:
            conversations = history.list_conversations()
            self._session_cache.clear()
            for conv in conversations:
                info = SessionInfo(
                    session_id=conv["id"],
                    title=conv["title"],
                    created_at=conv["created_at"],
                    updated_at=conv["updated_at"],
                    message_count=0,
                    turn_count=0,
                    is_active=(conv["id"] == self._active_session_id)
                )
                self._session_cache[conv["id"]] = info
        except Exception as e:
            logger.error(f"重建缓存失败: {e}")
    
    def _notify_callbacks(self, event_type: str, session_id: str, **kwargs):
        """通知所有订阅者"""
        for callback in self._callbacks:
            try:
                callback(event_type, session_id, **kwargs)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")
    
    def register_callback(self, callback: Callable):
        """注册会话变更回调 callback(event_type, session_id, **kwargs)"""
        self._callbacks.append(callback)
    
    # ==================== 会话 CRUD ====================
    
    def create_session(self, title: str = "新对话") -> str:
        """创建新会话，返回 session_id"""
        with self._lock:
            history = self._get_conversation_history()
            if not history:
                return None
            
            session_id = history.create_conversation(title)
            
            # 更新缓存
            now = datetime.now().isoformat()
            info = SessionInfo(
                session_id=session_id,
                title=title,
                created_at=now,
                updated_at=now,
                is_active=True
            )
            
            # 取消其他会话的活动状态
            for sid in self._session_cache:
                self._session_cache[sid].is_active = False
            
            self._session_cache[session_id] = info
            self._active_session_id = session_id
            
            # 创建运行时实例
            inst_mgr = self._get_instance_manager()
            if inst_mgr:
                inst_mgr.create_instance(session_id, title)
                inst_mgr.set_active_instance(session_id)
            
            self._notify_callbacks("created", session_id, title=title)
            logger.info(f"创建会话: {title} ({session_id[:8]})")
            return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话详情（从持久化层读取）"""
        history = self._get_conversation_history()
        if not history:
            return None
        
        conversation = history.get_conversation(session_id)
        if not conversation:
            return None
        
        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": conversation.messages,
            "metadata": conversation.metadata
        }
    
    def get_active_session_id(self) -> Optional[str]:
        """获取当前活动会话 ID"""
        return self._active_session_id
    
    def get_active_session(self) -> Optional[Dict]:
        """获取当前活动会话详情"""
        if self._active_session_id:
            return self.get_session(self._active_session_id)
        return None
    
    def set_active_session(self, session_id: str) -> bool:
        """切换活动会话（后台任务继续运行）"""
        with self._lock:
            if session_id not in self._session_cache:
                # 尝试从持久化层加载
                history = self._get_conversation_history()
                if history:
                    conv = history.get_conversation(session_id)
                    if conv:
                        self._session_cache[session_id] = SessionInfo(
                            session_id=conv.id,
                            title=conv.title,
                            created_at=conv.created_at,
                            updated_at=conv.updated_at,
                            is_active=False
                        )
                    else:
                        return False
                else:
                    return False
            
            # 更新活动状态
            for sid in self._session_cache:
                self._session_cache[sid].is_active = (sid == session_id)
            
            self._active_session_id = session_id
            
            # 同步运行时实例
            inst_mgr = self._get_instance_manager()
            if inst_mgr:
                title = self._session_cache[session_id].title
                inst_mgr.get_or_create_instance(session_id, title)
                inst_mgr.set_active_instance(session_id)
            
            self._notify_callbacks("switched", session_id)
            logger.info(f"切换到会话: {self._session_cache[session_id].title}")
            return True
    
    def rename_session(self, session_id: str, new_title: str) -> bool:
        """重命名会话"""
        with self._lock:
            history = self._get_conversation_history()
            if not history:
                return False
            
            history.update_conversation_title(session_id, new_title)
            
            if session_id in self._session_cache:
                self._session_cache[session_id].title = new_title
            
            self._notify_callbacks("renamed", session_id, title=new_title)
            return True
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        with self._lock:
            history = self._get_conversation_history()
            if not history:
                return False
            
            history.delete_conversation(session_id)
            self._session_cache.pop(session_id, None)
            
            # 清理运行时实例
            inst_mgr = self._get_instance_manager()
            if inst_mgr:
                inst_mgr.delete_instance(session_id)
            
            # 如果删除的是活动会话，选择新的
            if self._active_session_id == session_id:
                if self._session_cache:
                    self._active_session_id = next(iter(self._session_cache.keys()))
                    self._session_cache[self._active_session_id].is_active = True
                else:
                    self._active_session_id = None
            
            self._notify_callbacks("deleted", session_id)
            logger.info(f"删除会话: {session_id[:8]}")
            return True
    
    def list_sessions(self, limit: int = 50) -> List[SessionInfo]:
        """列出所有会话（从缓存读取，按更新时间倒序）"""
        with self._lock:
            sessions = list(self._session_cache.values())
            
            # 补充运行时信息
            inst_mgr = self._get_instance_manager()
            if inst_mgr:
                for info in sessions:
                    instance = inst_mgr.get_instance(info.session_id)
                    if instance:
                        info.has_running_tasks = len(instance.get_active_tasks()) > 0
            
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            return sessions[:limit]
    
    # ==================== 消息管理 ====================
    
    def add_message(self, session_id: str, role: str, content: str, **kwargs) -> bool:
        """添加消息到会话"""
        history = self._get_conversation_history()
        if not history:
            return False
        
        from ..agent_assistant import ConversationMessage
        msg = ConversationMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            **{k: v for k, v in kwargs.items() if k in 
               ('reasoning_content', 'tool_call_id', 'tool_name', 'tool_args', 'tool_result', 'tool_calls')}
        )
        history.save_message(session_id, msg)
        
        # 更新缓存
        if session_id in self._session_cache:
            self._session_cache[session_id].message_count += 1
            if role == "user":
                self._session_cache[session_id].turn_count += 1
            self._session_cache[session_id].updated_at = datetime.now().isoformat()
        
        return True
    
    # ==================== Agent 实例管理 ====================
    
    def associate_agent(self, session_id: str, agent: Any) -> bool:
        """为会话关联 Agent 实例"""
        inst_mgr = self._get_instance_manager()
        if inst_mgr:
            return inst_mgr.associate_agent(session_id, agent)
        return False
    
    def get_agent(self, session_id: str) -> Optional[Any]:
        """获取会话关联的 Agent 实例"""
        inst_mgr = self._get_instance_manager()
        if inst_mgr:
            instance = inst_mgr.get_instance(session_id)
            if instance:
                return instance.agent_instance
        return None
    
    # ==================== 后台任务管理 ====================
    
    def create_background_task(self, session_id: str, task_type: str,
                               target_func: Callable, *args, **kwargs) -> Optional[Any]:
        """创建后台任务"""
        inst_mgr = self._get_instance_manager()
        if inst_mgr:
            return inst_mgr.create_background_task(session_id, task_type, target_func, *args, **kwargs)
        return None
    
    def get_running_tasks(self, session_id: Optional[str] = None) -> List[Dict]:
        """获取运行中的任务"""
        inst_mgr = self._get_instance_manager()
        if not inst_mgr:
            return []
        
        tasks = inst_mgr.get_all_tasks(session_id)
        return [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "conversation_id": t.conversation_id,
                "status": t.status,
                "progress": t.progress,
                "error": t.error
            }
            for t in tasks
            if t.status == "running"
        ]
    
    def cancel_task(self, task_id: str) -> bool:
        """取消后台任务"""
        inst_mgr = self._get_instance_manager()
        if inst_mgr:
            return inst_mgr.cancel_task(task_id)
        return False
    
    # ==================== 兼容性接口 ====================
    
    def get_conversation_history(self):
        """获取底层 ConversationHistory（兼容旧代码）"""
        return self._get_conversation_history()
    
    def get_instance_manager(self):
        """获取底层 SessionInstanceManager（兼容旧代码）"""
        return self._get_instance_manager()


# 全局单例
_unified_manager: Optional[UnifiedSessionManager] = None


def get_unified_session_manager(db_path: Optional[str] = None) -> UnifiedSessionManager:
    """获取统一会话管理器（单例模式）"""
    global _unified_manager
    if _unified_manager is None:
        _unified_manager = UnifiedSessionManager(db_path)
    return _unified_manager
