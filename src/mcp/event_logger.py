#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户事件日志系统
- 记录各种用户操作事件
- 增量同步到 Agent
- 自动载入到对话上下文
- 封装完整 API
"""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import threading
import hashlib


@dataclass
class UserEvent:
    """用户事件定义"""
    event_id: str
    event_type: str  # 事件类型: file, tab, input, tool, navigation, action
    event_subtype: Optional[str] = None  # 子类型
    timestamp: str = ""
    event_data: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_operation: Optional[str] = None  # read, write, delete, modify, rename
    ui_element: Optional[str] = None  # UI元素类型
    context_info: Optional[str] = None  # 上下文信息
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None
    duration_ms: Optional[int] = None  # 操作耗时
    session_id: Optional[str] = None
    user_session_id: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @staticmethod
    def _safe_summary_text(value: Any, max_len: int = 60) -> str:
        """安全格式化文本用于摘要"""
        if value is None:
            return ""
        text = str(value)
        if len(text) > max_len:
            text = text[:max_len - 3] + "..."
        # 清理 Markdown 特殊字符
        return text.replace('\\', '\\\\').replace('`', '\\`').replace('*', '\\*').replace('_', '\\_')
    
    def to_summary(self) -> str:
        """返回事件摘要用于Agent理解的简要（安全版本）"""
        time_part = self.timestamp[:19] if self.timestamp else ""
        parts = [f"[{time_part}] [{self.event_type or 'unknown'}"]
        if self.event_subtype:
            parts.append(f":{self.event_subtype}")
        
        parts.append("]")
        
        if self.file_path:
            parts.append(f" 文件: {self._safe_summary_text(self.file_path, 80)}")
        elif self.file_name:
            parts.append(f" 文件: {self._safe_summary_text(self.file_name, 50)}")
        
        if self.file_operation:
            parts.append(f" 操作: {self._safe_summary_text(self.file_operation, 20)}")
        
        if self.ui_element:
            parts.append(f" UI: {self._safe_summary_text(self.ui_element, 30)}")
        
        if self.context_info:
            parts.append(f" 上下文: {self._safe_summary_text(self.context_info, 50)}")
        
        if self.new_value:
            str_val = str(self.new_value)
            # 跳过 JSON、过长内容、包含特殊格式的内容
            if ('{' not in str_val and '}' not in str_val and
                '\n' not in str_val and str_val.strip()):
                parts.append(f" 值: {self._safe_summary_text(str_val, 40)}")
        
        result = " ".join(parts)
        if len(result) > 200:
            result = result[:197] + "..."
        
        return result
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventLogger:
    """事件记录器"""
    
    _instance: Optional['EventLogger'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __init__(self, storage_path: Optional[Path]):
        self.storage_path = storage_path
        self.session_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:12]
        self.db_path = storage_path / "user_events.db"
        self._init_db()
        self._current_events: List[UserEvent] = []
        self._dirty_events_lock = threading.Lock()
        
        # 最大事件保留数量
        self._max_recent_events = 100
        self._event_callbacks: List[Any] = []
    
    @classmethod
    def get_instance(cls, storage_path: Optional[Path] = None) -> 'EventLogger':
        if not cls._instance:
            with cls._lock:
                if not cls._instance and storage_path:
                    cls._instance = cls(storage_path)
        return cls._instance
    
    def _init_db(self):
        """初始化数据库"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_subtype TEXT,
                timestamp TEXT NOT NULL,
                event_data TEXT,
                file_path TEXT,
                file_name TEXT,
                file_operation TEXT,
                ui_element TEXT,
                context_info TEXT,
                previous_value TEXT,
                new_value TEXT,
                duration_ms INTEGER,
                session_id TEXT,
                is_synced INTEGER DEFAULT 0
            )
        ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_events_synced ON events(is_synced)
            ''')
    
    def _add_event(self, event: UserEvent):
        """添加事件"""
        if not event.event_id:
            import uuid
            event.event_id = str(uuid.uuid4())
        if not event.timestamp:
            event.timestamp = datetime.now().isoformat()
        event.session_id = self.session_id
        
        with self._dirty_events_lock:
            self._current_events.append(event)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO events (
                        event_id, event_type, event_subtype, timestamp, event_data,
                        file_path, file_name, file_operation, ui_element, context_info,
                        previous_value, new_value, duration_ms, session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event.event_id,
                    event.event_type,
                    event.event_subtype,
                    event.timestamp,
                    json.dumps(event.event_data, ensure_ascii=False),
                    event.file_path,
                    event.file_name,
                    event.file_operation,
                    event.ui_element,
                    event.context_info,
                    json.dumps(event.previous_value, ensure_ascii=False) if event.previous_value else None,
                    json.dumps(event.new_value, ensure_ascii=False) if event.new_value else None,
                    event.duration_ms,
                    event.session_id
                ))
        
        # 保留最近N个事件
        if len(self._current_events) > self._max_recent_events:
            self._current_events = self._current_events[-self._max_recent_events:]
    
    # === 工具方法 - 封装好的API ===
    
    def log_file_operation(self, file_path: Union[str, Path], operation: str, 
                       previous_value: Any = None, new_value: Any = None,
                       context_info: Optional[str] = None, 
                       duration_ms: Optional[int] = None):
        """记录文件操作
        operation: read, write, delete, rename, open, close
        """
        path = Path(file_path)
        self._add_event(UserEvent(
            event_id="",
            event_type="file",
            event_subtype="operation",
            timestamp="",
            file_path=str(path),
            file_name=path.name,
            file_operation=operation,
            context_info=context_info,
            previous_value=previous_value,
            new_value=new_value,
            duration_ms=duration_ms,
            event_data={
                "file_size": path.stat().st_size if path.exists() else None,
                "file_ext": path.suffix
            }
        ))
    
    def log_tab_change(self, tab_name: str, previous_tab: Optional[str] = None, 
                      context_info: Optional[str] = None):
        """记录标签页切换"""
        self._add_event(UserEvent(
            event_id="",
            event_type="navigation",
            event_subtype="tab_switch",
            timestamp="",
            ui_element="tab_bar",
            context_info=context_info,
            previous_value=previous_tab,
            new_value=tab_name
        ))
    
    def log_input(self, input_type: str, content: str, element: str = "text_input", 
                 context_info: Optional[str] = None):
        """记录用户输入"""
        self._add_event(UserEvent(
            event_id="",
            event_type="input",
            event_subtype=input_type,
            timestamp="",
            ui_element=element,
            context_info=context_info,
            new_value=content
        ))
    
    def log_tool_call(self, tool_name: str, tool_args: Dict, tool_result: Any = None, 
                    duration_ms: Optional[int] = None, context_info: Optional[str] = None):
        """记录工具调用"""
        self._add_event(UserEvent(
            event_id="",
            event_type="tool",
            event_subtype="call",
            timestamp="",
            ui_element=tool_name,
            context_info=context_info,
            event_data={"args": tool_args, "result": tool_result},
            duration_ms=duration_ms
        ))
    
    def log_navigation(self, nav_type: str, target: str, context_info: Optional[str] = None):
        """记录导航操作"""
        self._add_event(UserEvent(
            event_id="",
            event_type="navigation",
            event_subtype=nav_type,
            timestamp="",
            context_info=context_info,
            new_value=target
        ))
    
    def log_action(self, action_type: str, element: str, value: Any = None,
                  context_info: Optional[str] = None,
                  previous_value: Any = None,
                  duration_ms: Optional[int] = None):
        """记录一般动作"""
        self._add_event(UserEvent(
            event_id="",
            event_type="action",
            event_subtype=action_type,
            timestamp="",
            ui_element=element,
            context_info=context_info,
            previous_value=previous_value,
            new_value=value,
            duration_ms=duration_ms
        ))
    
    def log_view(self, event: UserEvent):
        """直接记录用户事件对象"""
        self._add_event(event)
    
    # === 数据查询与获取 ===
    
    def _safe_json_parse(self, text: str) -> Any:
        """安全解析 JSON，避免格式错误"""
        if not text:
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    
    def get_recent_events(self, count: int = 50, 
                         event_type: Optional[str] = None,
                         since_timestamp: Optional[str] = None) -> List[UserEvent]:
        """获取最近的事件（健壮版本）"""
        events = []
        
        if not self.db_path or not self.db_path.parent.exists():
            return events
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = "SELECT * FROM events "
                params = []
                
                conditions = []
                if event_type:
                    conditions.append("event_type = ?")
                    params.append(event_type)
                if since_timestamp:
                    conditions.append("timestamp > ?")
                    params.append(since_timestamp)
                
                if conditions:
                    query += "WHERE " + " AND ".join(conditions) + " "
                
                query += "ORDER BY timestamp DESC LIMIT ?"
                params.append(count)
                
                for row in conn.execute(query, params):
                    if len(row) < 14:
                        continue
                    try:
                        events.append(UserEvent(
                            event_id=str(row[0]) if row[0] else "",
                            event_type=str(row[1]) if row[1] else "",
                            event_subtype=str(row[2]) if row[2] else None,
                            timestamp=str(row[3]) if row[3] else "",
                            event_data=self._safe_json_parse(row[4]),
                            file_path=str(row[5]) if row[5] else None,
                            file_name=str(row[6]) if row[6] else None,
                            file_operation=str(row[7]) if row[7] else None,
                            ui_element=str(row[8]) if row[8] else None,
                            context_info=str(row[9]) if row[9] else None,
                            previous_value=self._safe_json_parse(row[10]),
                            new_value=self._safe_json_parse(row[11]),
                            duration_ms=int(row[12]) if row[12] else None,
                            session_id=str(row[13]) if row[13] else None
                        ))
                    except (IndexError, ValueError, TypeError):
                        continue
        except sqlite3.OperationalError:
            pass
        
        return events
    
    def get_events_for_agent(self, count: int = 30) -> List[str]:
        """获取给Agent使用的事件摘要列表"""
        events = self.get_recent_events(count)
        return [e.to_summary() for e in events]
    
    def get_events_context(self, count: int = 30) -> str:
        """获取格式化的事件上下文文本"""
        events = self.get_recent_events(count)
        if not events:
            return "无最近用户操作记录"
        
        lines = ["### 用户最近操作历史"]
        for i, e in enumerate(events):
            lines.append(f"{i+1}. {e.to_summary()}")
        
        return "\n".join(lines)
    
    # === 同步机制 ===
    
    def get_unsynced_events(self) -> List[UserEvent]:
        """获取未同步的事件"""
        events = []
        with sqlite3.connect(self.db_path) as conn:
            for row in conn.execute(
                "SELECT * FROM events WHERE is_synced = 0 ORDER BY timestamp ASC"
            ):
                events.append(UserEvent(
                    event_id=row[0],
                    event_type=row[1],
                    event_subtype=row[2],
                    timestamp=row[3],
                    event_data=json.loads(row[4]) if row[4] else {},
                    file_path=row[5],
                    file_name=row[6],
                    file_operation=row[7],
                    ui_element=row[8],
                    context_info=row[9],
                    previous_value=json.loads(row[10]) if row[10] else None,
                    new_value=json.loads(row[11]) if row[11] else None,
                    duration_ms=row[12],
                    session_id=row[13]
                ))
        return events
    
    def mark_synced(self, event_ids: List[str]):
        """标记事件已同步"""
        if not event_ids:
            return
        event_id_placeholders = ','.join(['?'] * len(event_ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE events SET is_synced = 1 WHERE event_id IN ({event_id_placeholders})",
                event_ids
            )
    
    def clear_old_events(self, days: int = 7):
        """清理旧事件"""
        import time
        cutoff = datetime.fromtimestamp(time.time() - days * 86400).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
            conn.execute("VACUUM")


# 全局访问实例获取函数
def get_logger(storage_path: Optional[Path]) -> EventLogger:
    return EventLogger.get_instance(storage_path)


# ================ TS2 集成的便捷 API ================
# 这些函数可以被导入到 TS2 主程序中使用

# 全局实例引用
_global_logger: Optional[EventLogger] = None


def init_event_logger(storage_path: str):
    """
    TS2 初始化事件日志系统
    
    Args:
        storage_path: 存储路径（通常是 WS2 工作目录）
    """
    global _global_logger
    _global_logger = get_logger(Path(storage_path))
    return _global_logger


def log_file_op(path: str, operation: str, context: str = None, prev_val=None, new_val=None):
    """
    便捷函数：记录文件操作
    
    Args:
        path: 文件路径
        operation: 操作类型 (read, write, delete, rename, open, close 等)
        context: 可选的上下文信息
        prev_val: 可选的修改前值
        new_val: 可选的修改后值
    """
    if _global_logger:
        _global_logger.log_file_operation(path, operation, prev_val, new_val, context)


def log_tab_change(tab_name: str, prev_tab: str = None, context: str = None):
    """
    便捷函数：记录标签页切换
    
    Args:
        tab_name: 新的标签页名称
        prev_tab: 之前的标签页名称
        context: 可选的上下文
    """
    if _global_logger:
        _global_logger.log_tab_change(tab_name, prev_tab, context)


def log_input(input_type: str, content: str, element: str = "text_input", context: str = None):
    """
    便捷函数：记录用户输入
    
    Args:
        input_type: 输入类型
        content: 输入内容
        element: UI 元素标识
        context: 可选的上下文
    """
    if _global_logger:
        _global_logger.log_input(input_type, content, element, context)


def log_navigation(nav_type: str, target: str, context: str = None):
    """
    便捷函数：记录导航操作
    
    Args:
        nav_type: 导航类型
        target: 目标位置
        context: 可选的上下文
    """
    if _global_logger:
        _global_logger.log_navigation(nav_type, target, context)


def log_action(action_type: str, element: str, value=None, context=None, prev_val=None, duration_ms=None):
    """
    便捷函数：记录一般动作
    
    Args:
        action_type: 动作类型
        element: UI 元素
        value: 动作结果
        context: 上下文
        prev_val: 动作前值
        duration_ms: 操作耗时
    """
    if _global_logger:
        _global_logger.log_action(action_type, element, value, context, prev_val, duration_ms)


def get_event_context() -> str:
    """
    获取格式化的事件上下文文本，用于传给 Agent
    
    Returns:
        格式化的事件历史文本
    """
    if _global_logger:
        return _global_logger.get_events_context()
    return "无事件记录"

