#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话实例管理系统
- 支持会话在后台运行
- 每个对话有独立的 Agent 实例
- 支持任务状态跟踪
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BackgroundTask:
    """后台任务信息"""
    task_id: str
    task_type: str
    conversation_id: str
    status: str = "pending"  # pending, running, completed, failed
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress: float = 0.0
    result: Any = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None
    cancel_event: Optional[threading.Event] = None


@dataclass
class ConversationInstance:
    """对话会话实例"""
    conversation_id: str
    title: str
    created_at: float
    updated_at: float
    is_active: bool = False
    agent_instance: Optional[Any] = None
    background_tasks: List[BackgroundTask] = field(default_factory=list)
    messages: List[Dict] = field(default_factory=list)
    context: Dict = field(default_factory=dict)
    is_running: bool = False
    
    def get_active_tasks(self) -> List[BackgroundTask]:
        """获取正在运行的任务"""
        return [t for t in self.background_tasks if t.status == "running"]
    
    def get_pending_tasks(self) -> List[BackgroundTask]:
        """获取待处理的任务"""
        return [t for t in self.background_tasks if t.status == "pending"]


class SessionInstanceManager:
    """会话实例管理器 - 管理所有对话的独立实例"""
    
    def __init__(self):
        self.instances: Dict[str, ConversationInstance] = {}
        self.active_conversation_id: Optional[str] = None
        self._lock = threading.RLock()
        self._task_callbacks: Dict[str, List[Callable]] = {}
    
    def create_instance(self, conversation_id: str, title: str) -> ConversationInstance:
        """创建新的会话实例"""
        with self._lock:
            if conversation_id in self.instances:
                logger.warning(f"会话 {conversation_id} 已存在")
                return self.instances[conversation_id]
            
            instance = ConversationInstance(
                conversation_id=conversation_id,
                title=title,
                created_at=datetime.now().timestamp(),
                updated_at=datetime.now().timestamp()
            )
            
            self.instances[conversation_id] = instance
            logger.info(f"创建会话实例: {title} ({conversation_id[:8]})")
            return instance
    
    def get_instance(self, conversation_id: str) -> Optional[ConversationInstance]:
        """获取指定会话实例"""
        return self.instances.get(conversation_id)
    
    def get_or_create_instance(self, conversation_id: str, title: str) -> ConversationInstance:
        """获取或创建会话实例"""
        instance = self.get_instance(conversation_id)
        if not instance:
            instance = self.create_instance(conversation_id, title)
        return instance
    
    def set_active_instance(self, conversation_id: str) -> bool:
        """设置活动会话"""
        with self._lock:
            if conversation_id not in self.instances:
                logger.error(f"会话 {conversation_id} 不存在")
                return False
            
            # 更新激活状态
            for conv_id, inst in self.instances.items():
                inst.is_active = (conv_id == conversation_id)
            
            self.active_conversation_id = conversation_id
            logger.info(f"切换到会话: {self.instances[conversation_id].title}")
            return True
    
    def get_active_instance(self) -> Optional[ConversationInstance]:
        """获取当前活动的会话"""
        if self.active_conversation_id:
            return self.instances.get(self.active_conversation_id)
        return None
    
    def list_instances(self) -> List[ConversationInstance]:
        """列出所有会话实例"""
        return list(self.instances.values())
    
    def update_instance(self, conversation_id: str, **kwargs) -> bool:
        """更新会话实例"""
        with self._lock:
            instance = self.instances.get(conversation_id)
            if not instance:
                return False
            
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            instance.updated_at = datetime.now().timestamp()
            return True
    
    def associate_agent(self, conversation_id: str, agent: Any) -> bool:
        """为会话关联 Agent 实例"""
        with self._lock:
            instance = self.instances.get(conversation_id)
            if not instance:
                return False
            
            instance.agent_instance = agent
            logger.debug(f"关联 Agent 到会话: {instance.title}")
            return True
    
    def add_message(self, conversation_id: str, message: Dict) -> bool:
        """添加消息到会话"""
        with self._lock:
            instance = self.instances.get(conversation_id)
            if not instance:
                return False
            
            message["timestamp"] = datetime.now().isoformat()
            instance.messages.append(message)
            instance.updated_at = datetime.now().timestamp()
            return True
    
    def create_background_task(self, conversation_id: str, task_type: str, 
                             target_func: Callable, *args, **kwargs) -> Optional[BackgroundTask]:
        """创建后台任务"""
        with self._lock:
            instance = self.instances.get(conversation_id)
            if not instance:
                logger.error(f"会话 {conversation_id} 不存在")
                return None
            
            task_id = str(uuid.uuid4())
            task = BackgroundTask(
                task_id=task_id,
                task_type=task_type,
                conversation_id=conversation_id
            )
            
            cancel_event = threading.Event()
            task.cancel_event = cancel_event
            
            def wrapped_task():
                try:
                    task.status = "running"
                    task.started_at = datetime.now().timestamp()
                    task.result = target_func(*args, **kwargs)
                    task.status = "completed"
                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)
                    logger.error(f"后台任务失败: {e}")
                finally:
                    task.completed_at = datetime.now().timestamp()
                    self._notify_task_callbacks(task)
            
            thread = threading.Thread(target=wrapped_task, daemon=True)
            task.thread = thread
            instance.background_tasks.append(task)
            
            thread.start()
            logger.info(f"启动后台任务: {task_type} ({task_id[:8]})")
            
            return task
    
    def cancel_task(self, task_id: str) -> bool:
        """取消后台任务"""
        with self._lock:
            for instance in self.instances.values():
                for task in instance.background_tasks:
                    if task.task_id == task_id:
                        if task.cancel_event:
                            task.cancel_event.set()
                        task.status = "failed"
                        task.error = "用户取消"
                        logger.info(f"取消任务: {task_id[:8]}")
                        return True
            return False
    
    def get_all_tasks(self, conversation_id: Optional[str] = None) -> List[BackgroundTask]:
        """获取所有任务（可选按会话过滤）"""
        with self._lock:
            tasks = []
            if conversation_id:
                instance = self.instances.get(conversation_id)
                if instance:
                    tasks.extend(instance.background_tasks)
            else:
                for instance in self.instances.values():
                    tasks.extend(instance.background_tasks)
            return tasks
    
    def _notify_task_callbacks(self, task: BackgroundTask):
        """通知任务回调"""
        if task.task_id in self._task_callbacks:
            for callback in self._task_callbacks[task.task_id]:
                try:
                    callback(task)
                except Exception as e:
                    logger.error(f"任务回调失败: {e}")
    
    def register_task_callback(self, task_id: str, callback: Callable):
        """注册任务回调"""
        if task_id not in self._task_callbacks:
            self._task_callbacks[task_id] = []
        self._task_callbacks[task_id].append(callback)
    
    def delete_instance(self, conversation_id: str) -> bool:
        """删除会话实例"""
        with self._lock:
            if conversation_id not in self.instances:
                return False
            
            # 取消所有任务
            instance = self.instances[conversation_id]
            for task in instance.background_tasks:
                if task.cancel_event:
                    task.cancel_event.set()
            
            del self.instances[conversation_id]
            
            # 如果删除的是活动会话，选择一个新的
            if self.active_conversation_id == conversation_id and self.instances:
                self.active_conversation_id = next(iter(self.instances.keys()))
                self.instances[self.active_conversation_id].is_active = True
            
            logger.info(f"删除会话实例: {conversation_id[:8]}")
            return True


# 全局单例
_session_instance_manager: Optional[SessionInstanceManager] = None


def get_session_instance_manager() -> SessionInstanceManager:
    """获取会话实例管理器（单例模式）"""
    global _session_instance_manager
    if _session_instance_manager is None:
        _session_instance_manager = SessionInstanceManager()
    return _session_instance_manager
