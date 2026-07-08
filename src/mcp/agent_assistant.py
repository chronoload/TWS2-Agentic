#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cline 风格的现代化 Agent 助手窗口 - 完全增强版
- 气泡式对话，文本可选中
- Markdown 渲染支持
- 现代化配色
- 美观的工具栏和基础设施状态面板
- 对话历史存储
- 工具调用审批
- 变更对比
- UI 状态持久化（窗口几何/主题）
- 会话检查点支持
- 停止按钮可工作
- 完整的 TS2 系统集成
- 实时语境感知
- 文件上传功能
"""

import logging
logger = logging.getLogger(__name__)

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional, Callable, Dict, List, Any, Union
import threading
from dataclasses import dataclass, field, asdict
import uuid
import sys


class ToolTip:
    """简易 ToolTip 悬停提示"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind('<Enter>', self.enter)
        widget.bind('<Leave>', self.leave)

    def enter(self, event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg="#333")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         bg="#333", fg="white",
                         font=("Microsoft YaHei UI", 9),
                         padx=8, pady=4)
        label.pack()

    def leave(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
import re
from pathlib import Path

try:
    import tex_to_utf8
    HAS_TEX_UTF8 = True
except ImportError:
    HAS_TEX_UTF8 = False

try:
    from . import agent as mcp_agent
    from . import ws2_tools
    from . import event_logger
    HAS_AGENT = True
    HAS_EVENT_LOGGER = True
except ImportError as e:
    HAS_AGENT = False
    HAS_EVENT_LOGGER = False
    print(f"Agent 模块加载失败: {e}")

# RAG 系统支持
try:
    from .rag import initialize_rag_for_agent, get_auto_rag
    HAS_RAG = True
except ImportError as e:
    HAS_RAG = False
    print(f"RAG 模块加载失败: {e}")

try:
    from .cache import (
        UIStateManager,
        StateManager,
        ContextReloader,
        WindowGeometry,
        get_ui_state_manager,
        get_state_manager,
        get_model_cache,
        get_context_reloader,
    )
    HAS_CACHE = True
except ImportError as e:
    HAS_CACHE = False
    print(f"缓存模块加载失败: {e}")

try:
    from .runtime import RunManager, RunRecord, RunStatus, RunJournal, JournalEntry, JournalEventType
    HAS_RUNTIME = True
except ImportError:
    HAS_RUNTIME = False

try:
    from .skill_system import SecurityScanner, Curator, SkillStatus
    HAS_SKILL_SYSTEM = True
except ImportError:
    HAS_SKILL_SYSTEM = False

try:
    from .plugins import PluginManager, PluginKind, TrustGate, LlmTrustConfig
    HAS_PLUGINS = True
except ImportError:
    HAS_PLUGINS = False

# 语音唤醒词检测
try:
    from .voice import WakeWordDetector, SimpleWakeWordDetector, create_wake_detector
    HAS_VOICE_WAKE = True
except ImportError as e:
    HAS_VOICE_WAKE = False
    logger.debug(f"语音唤醒模块加载失败: {e}")

# 统一渲染增强模块
try:
    from .renderer import EnhancedRenderer, create_renderer
    HAS_ENHANCED_RENDERER = True
except ImportError as e:
    HAS_ENHANCED_RENDERER = False
    logger.debug(f"增强渲染模块加载失败: {e}")

# ===== 调试和性能指标系统 =====

class DebugManager:
    """Agent断点调试管理器"""
    
    def __init__(self):
        self.breakpoints = {}
        self.debug_enabled = False
        self.breakpoint_hits = []
        self.call_stack = []
        self.watch_variables = {}
        self.step_mode = False
        self.current_step = 0
    
    def enable_debug(self):
        self.debug_enabled = True
        self.breakpoint_hits.clear()
    
    def disable_debug(self):
        self.debug_enabled = False
    
    def add_breakpoint(self, name: str, condition: str = None):
        self.breakpoints[name] = {"condition": condition, "hit_count": 0, "enabled": True}
    
    def remove_breakpoint(self, name: str):
        if name in self.breakpoints:
            del self.breakpoints[name]
    
    def check_breakpoint(self, name: str, context: Dict = None) -> bool:
        if not self.debug_enabled or name not in self.breakpoints:
            return False
        bp = self.breakpoints[name]
        if not bp["enabled"]:
            return False
        bp["hit_count"] += 1
        self.breakpoint_hits.append({"name": name, "timestamp": datetime.now().isoformat(), "context": context.copy() if context else {}})
        return True
    
    def watch_variable(self, name: str, value: Any):
        self.watch_variables[name] = {"value": value, "timestamp": datetime.now().isoformat()}
    
    def push_stack(self, func_name: str, params: Dict = None):
        self.call_stack.append({"function": func_name, "params": params.copy() if params else {}, "timestamp": datetime.now().isoformat()})
    
    def pop_stack(self):
        return self.call_stack.pop() if self.call_stack else None
    
    def get_stack_trace(self) -> List[Dict]:
        return self.call_stack.copy()
    
    def clear(self):
        self.breakpoint_hits.clear()
        self.call_stack.clear()
        self.watch_variables.clear()
        self.current_step = 0
    
    def get_debug_info(self) -> Dict:
        return {"enabled": self.debug_enabled, "breakpoints": self.breakpoints, "hit_count": len(self.breakpoint_hits), "stack_depth": len(self.call_stack), "watch_vars": len(self.watch_variables)}


class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self):
        self.metrics_history = []
        self.current_request = None
        self.tokens_per_second = 0.0
        self.avg_response_time = 0.0
        self.avg_token_count = 0
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.tool_call_count = 0
        self.rag_hit_count = 0
    
    def start_request(self, request_id: str, user_input: str):
        self.current_request = {"id": request_id, "user_input": user_input[:100], "start_time": datetime.now(), "start_timestamp": datetime.now().timestamp(), "token_count": 0, "tool_calls": [], "rag_used": False, "stages": {}}
        return request_id
    
    def record_stage(self, stage_name: str):
        if self.current_request:
            self.current_request["stages"][stage_name] = {"start": datetime.now(), "timestamp": datetime.now().timestamp()}
    
    def end_stage(self, stage_name: str):
        if self.current_request and stage_name in self.current_request["stages"]:
            stage = self.current_request["stages"][stage_name]
            stage["end"] = datetime.now()
            stage["duration"] = (datetime.now().timestamp() - stage["timestamp"]) * 1000
    
    def add_token(self, token: str):
        if self.current_request:
            self.current_request["token_count"] = self.current_request.get("token_count", 0) + len(token)
    
    def add_tool_call(self, tool_name: str):
        if self.current_request:
            self.current_request["tool_calls"].append({"name": tool_name, "timestamp": datetime.now().isoformat()})
            self.tool_call_count += 1
    
    def set_rag_used(self, used: bool):
        if self.current_request:
            self.current_request["rag_used"] = used
            if used:
                self.rag_hit_count += 1
    
    def end_request(self, success: bool = True) -> Dict:
        if not self.current_request:
            return {}
        end_time = datetime.now()
        end_timestamp = end_time.timestamp()
        self.current_request["end_time"] = end_time
        self.current_request["success"] = success
        duration = (end_timestamp - self.current_request["start_timestamp"]) * 1000
        self.current_request["duration_ms"] = duration
        token_count = self.current_request.get("token_count", 0)
        if duration > 0:
            self.tokens_per_second = (token_count / duration) * 1000
        self.current_request["tokens_per_second"] = self.tokens_per_second
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        if self.total_requests > 1:
            alpha = 0.2
            self.avg_response_time = alpha * duration + (1 - alpha) * self.avg_response_time
            self.avg_token_count = int(alpha * token_count + (1 - alpha) * self.avg_token_count)
        else:
            self.avg_response_time = duration
            self.avg_token_count = token_count
        metrics = self.current_request.copy()
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]
        self.current_request = None
        return metrics
    
    def get_current_metrics(self) -> Dict:
        return {"total_requests": self.total_requests, "successful_requests": self.successful_requests, "failed_requests": self.failed_requests, "success_rate": (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0, "avg_response_time_ms": round(self.avg_response_time, 2), "avg_token_count": self.avg_token_count, "tokens_per_second": round(self.tokens_per_second, 2), "total_tool_calls": self.tool_call_count, "rag_hit_count": self.rag_hit_count}
    
    def get_history(self, limit: int = 10) -> List[Dict]:
        return self.metrics_history[-limit:]


def optimize_math_display(text: str) -> str:
    """优化公式显示 - 将LaTeX公式转换为UTF-8显示"""
    if not text or not HAS_TEX_UTF8:
        return text
    
    try:
        import tex_to_utf8 as tex_module
        translator = tex_module.TeXToUTF8()
        result = translator.translate_for_display(text, enable_translation=True)
        return result
    except Exception:
        return text


# ===== 懒加载函数 — 避免启动阻塞 =====
def _lazy_import_workflow():
    from .workflow_engine import (
        WorkflowEngine, WorkflowStatus, get_workflow_engine,
    )
    from .predefined_workflows import get_workflow, list_workflows
    return WorkflowEngine, WorkflowStatus, get_workflow_engine, get_workflow, list_workflows

def _lazy_import_compactor():
    from .context_compactor import AutoCompact, estimate_messages_tokens
    return AutoCompact, estimate_messages_tokens

def _lazy_import_git_searcher():
    from .git_searcher import get_git_searcher
    return get_git_searcher

def _lazy_import_kg_rag():
    from .rag.knowledge_graph import get_kg_rag
    return get_kg_rag

def _lazy_import_rag():
    from .rag import initialize_rag_for_agent, get_auto_rag
    return initialize_rag_for_agent, get_auto_rag

# Markdown 渲染支持 - 简单的实现
def render_markdown_to_tags(text):
    """将简单的 Markdown 转换为标签配置"""
    # 处理粗体
    text = re.sub(r'\*\*(.*?)\*\*', r'<bold>\1</bold>', text)
    # 处理斜体
    text = re.sub(r'\*(.*?)\*', r'<italic>\1</italic>', text)
    # 处理代码
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    # 处理标题
    text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    # 处理列表
    text = re.sub(r'^- (.*?)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    return text


@dataclass
class ConversationMessage:
    id: str
    role: str  # system, user, assistant, tool
    content: str
    reasoning_content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[str] = None
    tool_calls: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    approved: bool = True
    rejected: bool = False


@dataclass
class Conversation:
    """对话会话结构"""
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class ConversationHistory:
    """对话历史管理器 - 类似 Cline 的会话存储"""
    
    def __init__(self, db_path: str = "ws2_agent_history.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库并迁移"""
        db_path_obj = Path(self.db_path)
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                reasoning_content TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                tool_args TEXT,
                tool_result TEXT,
                timestamp TEXT NOT NULL,
                approved INTEGER DEFAULT 1,
                rejected INTEGER DEFAULT 0,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        
        # 迁移：添加 tool_args 列（如果不存在）
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN tool_args TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        
        # 迁移：添加 tool_calls 列（如果不存在）
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN tool_calls TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        conn.close()
    
    def create_conversation(self, title: str = "新对话") -> str:
        conv_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        conn.commit()
        conn.close()
        return conv_id
    
    def save_message(self, conversation_id: str, message: ConversationMessage):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        tool_args_json = None
        if message.tool_args:
            try:
                tool_args_json = json.dumps(message.tool_args, ensure_ascii=False)
            except (TypeError, ValueError):
                tool_args_json = str(message.tool_args)

        tool_calls_json = None
        tc_data = getattr(message, 'tool_calls', None)
        if tc_data:
            try:
                tool_calls_json = json.dumps(tc_data, ensure_ascii=False) if isinstance(tc_data, (list, dict)) else str(tc_data)
            except (TypeError, ValueError):
                tool_calls_json = str(tc_data)

        cursor.execute("""
            INSERT INTO messages
            (id, conversation_id, role, content, reasoning_content, tool_call_id, tool_name, tool_args, tool_result, timestamp, approved, rejected, tool_calls)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message.id,
            conversation_id,
            message.role,
            message.content,
            message.reasoning_content,
            message.tool_call_id,
            message.tool_name,
            tool_args_json,
            message.tool_result,
            message.timestamp,
            1 if message.approved else 0,
            1 if message.rejected else 0,
            tool_calls_json,
        ))
        cursor.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), conversation_id)
        )
        conn.commit()
        conn.close()
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        cursor.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp", (conversation_id,))
        message_rows = cursor.fetchall()
        conn.close()

        messages = []
        for mr in message_rows:
            tool_args_raw = mr["tool_args"] if "tool_args" in mr.keys() else None
            tool_args = None
            if tool_args_raw:
                try:
                    tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                except (json.JSONDecodeError, TypeError):
                    tool_args = tool_args_raw

            tool_result = mr["tool_result"] if "tool_result" in mr.keys() else None
            if tool_result is not None and not isinstance(tool_result, str):
                try:
                    tool_result = str(tool_result)
                except Exception:
                    tool_result = repr(tool_result)

            msg_dict = {
                "id": mr["id"],
                "role": mr["role"],
                "content": mr["content"],
                "reasoning_content": mr["reasoning_content"] if "reasoning_content" in mr.keys() else None,
                "tool_call_id": mr["tool_call_id"] if "tool_call_id" in mr.keys() else None,
                "tool_name": mr["tool_name"] if "tool_name" in mr.keys() else None,
                "tool_args": tool_args,
                "tool_result": tool_result,
                "timestamp": mr["timestamp"],
                "approved": bool(mr["approved"]),
                "rejected": bool(mr["rejected"]) if "rejected" in mr.keys() else False,
            }
            if "tool_calls" in mr.keys() and mr["tool_calls"]:
                msg_dict["tool_calls"] = mr["tool_calls"]
            messages.append(msg_dict)

        metadata_raw = row["metadata"] if "metadata" in row.keys() else None
        return Conversation(
            id=row["id"],
            title=row["title"] or "未命名对话",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            messages=messages,
            metadata=json.loads(metadata_raw) if metadata_raw else {}
        )
    
    def list_conversations(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]}
            for r in rows
        ]
    
    def delete_conversation(self, conversation_id: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        conn.close()
    
    def update_conversation_title(self, conversation_id: str, title: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, datetime.now().isoformat(), conversation_id)
        )
        conn.commit()
        conn.close()


# 全局多实例管理 - 支持并行窗口
_global_agent_windows: list = []


def get_or_create_agent_window(parent, base_path, system=None, project_mgr=None, task_board_mgr=None, config=None, course_tracker=None):
    """获取已有的 agent 窗口或创建新的"""
    global _global_agent_windows
    
    # 查找已打开且有效的窗口
    for aw in _global_agent_windows:
        try:
            if aw.window.winfo_exists():
                aw.show()
                return aw
        except Exception:
            pass
    
    # 清理已销毁的窗口引用
    _global_agent_windows = [aw for aw in _global_agent_windows if _is_window_alive(aw)]
    
    # 创建新窗口
    return AgentAssistantWindow(parent, base_path, system, project_mgr, task_board_mgr, config, course_tracker)


def _is_window_alive(aw) -> bool:
    """检查窗口是否存活"""
    try:
        return aw.window.winfo_exists()
    except Exception:
        return False


class AgentAssistantWindow:
    """
    现代化的 Cline 风格 Agent 助手窗口 - 完全增强版
    """
    
    def __init__(self, parent: tk.Tk, base_path: str, system=None, project_mgr=None, task_board_mgr=None, config=None, course_tracker=None):
        global _global_agent_windows
        self.parent = parent
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.system = system
        self.project_mgr = project_mgr
        self.task_board_mgr = task_board_mgr
        self.config = config
        self.course_tracker = course_tracker
        self.agent = None
        db_path = self.base_path / "ws2_agent_history.db"
        self.conversation_history = ConversationHistory(str(db_path))
        self.current_conversation_id = None
        self.current_conversation_title = "新对话"
        self.is_processing = False
        self.should_stop = False
        self._session_messages: Dict[str, list] = {}
        
        # 注册到全局列表
        _global_agent_windows.append(self)
        
        # 输入历史记录（类似cline/terminal的Up/Down导航）
        self._input_history = []
        self._input_history_index = -1
        self._current_input_buffer = ""
        
        # 语境感知
        self.current_context = {
            "active_tab": None,
            "current_lesson": None,
            "selected_items": [],
            "timestamp": datetime.now().isoformat()
        }
        
        self._ui_state_mgr = get_ui_state_manager() if HAS_CACHE else None
        self._state_mgr = get_state_manager() if HAS_CACHE else None
        self._context_reloader = get_context_reloader() if HAS_CACHE else None
        
        # 事件日志系统
        self._event_logger = None
        if HAS_EVENT_LOGGER and self.base_path:
            try:
                self._event_logger = event_logger.get_logger(Path(self.base_path) / "logs" / "events")
            except Exception as e:
                print(f"事件日志系统初始化失败: {e}")
        
        # RAG 系统 - 懒加载
        self._rag_manager = None
        self._rag_loaded = False
        
        # 性能优化 - 节流和防抖相关
        self._token_buffer = ""
        self._token_buffer_start = 0
        self._token_update_timer = None
        self._last_token_update = 0
        self._token_update_interval = 50  # ms，控制UI更新频率，从30提升到50
        self._token_accumulated = ""
        self._max_token_buffer_size = 200  # 最大token缓冲大小，优化渲染频率
        self._token_count_for_next_update = 0  # 下次更新需要的token数量
        
        # 工作流引擎 - 懒加载
        self._workflow_engine = None
        self._workflow_loaded = False

        # AutoCompact 上下文压缩 - 懒加载
        self._compactor = None
        self._compactor_loaded = False

        # Git 搜索 - 懒加载
        self._git_searcher = None
        self._git_loaded = False

        # 知识图谱 - 懒加载
        self._kg_rag = None
        self._kg_loaded = False

        # 调试和性能指标系统
        self._debug_manager = DebugManager()
        self._performance_metrics = PerformanceMetrics()
        
        # 会话实例管理 - 支持多对话后台运行
        try:
            from .extensions.unified_session import get_unified_session_manager
            self._session_mgr = get_unified_session_manager()
        except Exception:
            self._session_mgr = None
        
        # 会话 Tab 管理器 - 支持多 Tab 并行
        try:
            from .extensions.session_tabs import get_session_tab_manager
            self._tab_mgr = get_session_tab_manager()
            self._tab_mgr.register_callback(self._on_tab_changed)
        except Exception:
            self._tab_mgr = None

        # 运行管理器 - 支持运行记录和日志
        self._run_manager = RunManager() if HAS_RUNTIME else None
        self._run_journal = RunJournal(
            journal_dir=str(self.base_path / "logs" / "journal")
        ) if HAS_RUNTIME else None

        # Plugin 管理器 - 支持扩展
        self._plugin_manager = None
        if HAS_PLUGINS:
            try:
                self._plugin_manager = PluginManager(
                    plugins_dirs=[self.base_path / "plugins"]
                )
                self._plugin_manager.discover_plugins()
            except Exception as e:
                logger.warning(f"Plugin系统初始化失败: {e}")

        # 语音唤醒词检测器
        self._wake_detector = None
        self._wake_enabled = False  # 是否启用唤醒检测
        if HAS_VOICE_WAKE:
            try:
                self._wake_detector = create_wake_detector(
                    wake_words=["hey_ws2", "你好ws2"],
                    on_wake=self._on_wake_detected,
                    threshold=0.5,
                )
                logger.info(f"语音唤醒检测器已创建: {type(self._wake_detector).__name__}")
            except Exception as e:
                logger.warning(f"语音唤醒检测器创建失败: {e}")
                self._wake_detector = None

        # Skill 进化管理器
        self._curator = None
        if HAS_SKILL_SYSTEM:
            try:
                self._curator = Curator(self.base_path / "skills")
            except Exception as e:
                logger.warning(f"Curator初始化失败: {e}")
        
        # Tab 相关 UI 元素
        self._tab_frames: Dict[str, tk.Frame] = {}
        self._tab_buttons: Dict[str, tk.Button] = {}
        self._tab_bar: Optional[tk.Frame] = None
        
        # 异步后台初始化
        self._init_background_modules()
        
        self.bg_color = "#f5f7fa"
        self.card_color = "#ffffff"
        self.primary_color = "#3b82f6"
        self.primary_hover = "#2563eb"
        self.success_color = "#10b981"
        self.warning_color = "#f59e0b"
        self.error_color = "#ef4444"
        self.text_color = "#2d3748"
        self.subtle_color = "#6b7280"
        self.border_color = "#e2e8f0"
        
        self.window = tk.Toplevel(parent)
        self.window.title("🤖 WS2 Agent")
        self.window.configure(bg=self.bg_color)
        self.window.attributes("-topmost", True)
        
        screen_w = parent.winfo_screenwidth()
        screen_h = parent.winfo_screenheight()
        window_w = 580
        window_h = int(screen_h * 0.9)
        x_pos = screen_w - window_w
        y_pos = int((screen_h - window_h) / 2)
        self.window.geometry(f"{window_w}x{window_h}+{x_pos}+{y_pos}")
        self.window.minsize(500, 600)
        
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self.window.bind("<FocusIn>", self._on_window_focus)
        self.window.bind("<Configure>", self._on_window_configure)
        
        self._create_ui()
        # 导航状态初始化
        self._nav_blocks: List[Dict] = []
        self._nav_current_idx = -1
        self._nav_show_all_mode = True
        self._init_agent()
        self._load_or_create_conversation()
        if hasattr(self, 'input_text'):
            # 确保输入框启用
            self.input_text.config(state=tk.NORMAL)
            self.window.after(100, lambda: self.input_text.focus_set())
        
        # 初始化全局审批管理器
        self._init_approval_manager()
        
        # 开始监听主窗口语境变化
        self._start_context_monitoring()
    
    def _init_approval_manager(self):
        """初始化全局审批管理器"""
        try:
            from .harness import get_global_approval_manager as get_harness_approval_manager
            
            harness_manager = get_harness_approval_manager()
            harness_manager.on_request(self._on_harness_approval_request)
            
            try:
                from .config_ui import GlobalApprovalManager
                ui_mgr = GlobalApprovalManager()
                ui_mgr.set_root_window(self.window)
            except Exception:
                pass
            
            logger.info("全局审批管理器已初始化")
        except Exception as e:
            logger.warning(f"全局审批管理器初始化失败: {e}")
    
    def _on_harness_approval_request(self, request):
        """处理来自 harness 的审批请求（可能在非主线程调用）"""
        try:
            from .harness import ApprovalDecision
            from .config_ui import ApprovalDialog
            
            req_id = request.id
            req_tool_name = request.tool_name
            
            def handle_decision(decision_str: str, _request=request, _tool_name=req_tool_name):
                decision_map = {
                    "approve": ApprovalDecision.APPROVE,
                    "deny": ApprovalDecision.DENY,
                    "always_approve": ApprovalDecision.ALWAYS_APPROVE,
                }
                decision = decision_map.get(decision_str, ApprovalDecision.DENY)
                _request.decide(decision)
                
                if decision_str == "always_approve" and _tool_name:
                    try:
                        from .config import get_config_manager
                        config_manager = get_config_manager()
                        config_manager.add_always_approved_tool(_tool_name)
                    except Exception:
                        pass
            
            if self.window and hasattr(self.window, 'winfo_exists') and self.window.winfo_exists():
                self.window.after(0, lambda _req=request, _cb=handle_decision: ApprovalDialog(self.window, _req, _cb))
            else:
                logger.warning("[审批] 主窗口不可用，自动拒绝")
                request.decide(ApprovalDecision.DENY)
        except Exception as e:
            logger.error(f"审批请求处理失败: {e}")
            try:
                request.decide(ApprovalDecision.DENY)
            except Exception:
                pass
    
    def _create_ui(self):
        """创建现代化的 UI"""
        main_frame = tk.Frame(self.window, bg=self.bg_color)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self._create_header(main_frame)
        self._create_infra_status_panel(main_frame)
        self._create_toolbar(main_frame)
        self._create_tab_bar(main_frame)
        self._create_chat_area(main_frame)
        self._create_input_area(main_frame)
        self._create_status_bar(main_frame)
        
        self._init_first_tab()
        self._refresh_history_list()
    
    def _create_tab_bar(self, parent):
        """创建会话 Tab 栏"""
        self._tab_bar = tk.Frame(parent, bg=self.border_color, height=36)
        self._tab_bar.pack(fill=tk.X, padx=8, pady=(4, 0))
        
        self._tab_container = tk.Frame(self._tab_bar, bg=self.border_color)
        self._tab_container.pack(fill=tk.X, side=tk.LEFT)
        
        self._new_tab_btn = tk.Button(
            self._tab_bar, text="+", 
            command=self._new_tab,
            font=("Segoe UI", 12, "bold"),
            bg=self.border_color, fg=self.primary_color,
            relief=tk.FLAT, padx=8, pady=2,
            cursor="hand2"
        )
        self._new_tab_btn.pack(side=tk.RIGHT, padx=4, pady=2)
    
    def _init_first_tab(self):
        """初始化第一个 Tab（用于兼容现有逻辑）"""
        if self._tab_mgr is None:
            return
        
        if not self.current_conversation_id:
            self.current_conversation_id = self.conversation_history.create_conversation("新对话")
            self.current_conversation_title = "新对话"
            self._is_first_message = True
        
        conversation_id = self.current_conversation_id
        title = self.current_conversation_title or "新对话"
        
        tab_id = self._tab_mgr.create_tab(conversation_id, title, self.agent)
        self._tab_mgr.set_active_tab(tab_id)
        
        self._rebuild_tab_buttons()
    
    def _rebuild_tab_buttons(self):
        """重建 Tab 按钮（含后台运行状态指示）"""
        for btn in self._tab_buttons.values():
            btn.destroy()
        self._tab_buttons.clear()
        
        if self._tab_mgr is None:
            return
        
        for tab_id, tab_state in self._tab_mgr.tabs.items():
            display_title = tab_state.title or "新对话"
            if tab_state.is_processing and not tab_state.is_active:
                display_title = f"⏳ {display_title}"
            
            btn = tk.Button(
                self._tab_container,
                text=f" {display_title} ",
                command=lambda tid=tab_id: self._switch_to_tab(tid),
                font=("Microsoft YaHei UI", 10, "bold"),
                bg=self.primary_color if tab_state.is_active else self.card_color,
                fg="white" if tab_state.is_active else self.text_color,
                relief=tk.SOLID if tab_state.is_active else tk.RAISED,
                padx=10, pady=4,
                width=8,
                cursor="hand2"
            )
            btn.pack(side=tk.LEFT, padx=3, pady=2, ipadx=5)
            
            close_btn = tk.Button(
                btn, text="×", 
                command=lambda tid=tab_id, b=btn: self._close_tab(tid),
                font=("Segoe UI", 10, "bold"),
                bg=self.primary_color if tab_state.is_active else self.card_color,
                fg=self.error_color,
                relief=tk.FLAT, padx=4, pady=2,
                cursor="hand2"
            )
            close_btn.pack(side=tk.RIGHT, padx=(0, 2))
            
            self._tab_buttons[tab_id] = btn
    
    def _new_tab(self):
        """创建新 Tab - 统一三套管理系统"""
        if self._tab_mgr is None:
            self._new_conversation()
            return
        
        self._save_current_tab_state()
        
        conversation_id = self.conversation_history.create_conversation("新对话")
        self.current_conversation_id = conversation_id
        self.current_conversation_title = "新对话"
        self._is_first_message = True
        
        if hasattr(self, 'conversation_var'):
            self.conversation_var.set(self.current_conversation_title)
        
        if self._session_mgr:
            self._session_mgr.associate_agent(self.current_conversation_id, self.agent)
            inst_mgr = self._session_mgr._get_instance_manager()
            if inst_mgr:
                inst_mgr.create_instance(conversation_id, "新对话")
                inst_mgr.set_active_instance(conversation_id)
        
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete(1.0, tk.END)
        self.chat_text.config(state=tk.DISABLED)
        self._nav_blocks.clear()
        self._nav_current_idx = -1
        self.nav_listbox.delete(0, tk.END)
        
        self._init_agent()
        
        if self._session_mgr and self.agent:
            self._session_mgr.associate_agent(conversation_id, self.agent)
        
        tab_id = self._tab_mgr.create_tab(
            conversation_id, 
            "新对话",
            self.agent
        )
        self._tab_mgr.set_active_tab(tab_id)
        self._rebuild_tab_buttons()
        self._refresh_history_list()
        self._update_status("🆕 新对话已创建")
    
    def _switch_to_tab(self, tab_id: str):
        """切换到指定 Tab - 同步三套管理系统和下拉框"""
        if self._tab_mgr is None:
            return
        
        tab_state = self._tab_mgr.get_tab(tab_id)
        if not tab_state:
            return
        
        self._save_current_tab_state()
        
        self._tab_mgr.set_active_tab(tab_id)
        self._restore_tab_state(tab_id, tab_state)
        
        if self._session_mgr:
            self._session_mgr.set_active_session(tab_state.conversation_id)
        
        if hasattr(self, 'conversation_var'):
            self.conversation_var.set(tab_state.title)
        self._refresh_history_list()
        
        self._rebuild_tab_buttons()
    
    def _save_current_tab_state(self):
        """保存当前 Tab 状态（含聊天内容、导航、滚动位置）"""
        if self._tab_mgr is None:
            return
        
        active_tab = self._tab_mgr.get_active_tab()
        if active_tab:
            active_tab.agent_instance = self.agent
            active_tab.is_processing = self.is_processing
            active_tab.should_stop = self.should_stop
            self._tab_mgr.update_agent(active_tab.tab_id, self.agent)
            
            if self.agent and hasattr(self.agent, 'messages') and self.current_conversation_id:
                self._session_messages[self.current_conversation_id] = self.agent.snapshot_messages()
            
            try:
                chat_html = ""
                if hasattr(self, 'chat_text') and self.chat_text.winfo_exists():
                    self.chat_text.config(state=tk.NORMAL)
                    chat_html = self.chat_text.get(1.0, tk.END)
                    self.chat_text.config(state=tk.DISABLED)
                
                scroll_pos = 1.0
                try:
                    scroll_pos = self.chat_text.yview()[1]
                except Exception:
                    pass
                
                nav_blocks_copy = list(self._nav_blocks) if self._nav_blocks else []
                
                self._tab_mgr.save_tab_ui_state(
                    active_tab.tab_id,
                    chat_html=chat_html,
                    nav_blocks=nav_blocks_copy,
                    nav_current_idx=self._nav_current_idx,
                    scroll_position=scroll_pos,
                )
            except Exception as e:
                logger.error(f"保存Tab UI状态失败: {e}")
    
    def _restore_tab_state(self, tab_id: str, tab_state):
        """恢复指定 Tab 状态（含聊天内容、导航、滚动位置）"""
        if tab_state.agent_instance:
            self.agent = tab_state.agent_instance
        
        if tab_state.conversation_id != self.current_conversation_id:
            self.current_conversation_id = tab_state.conversation_id
            self.current_conversation_title = tab_state.title
        
        if self.agent and hasattr(self.agent, 'messages') and self.current_conversation_id:
            saved = self._session_messages.get(self.current_conversation_id)
            if saved is not None:
                self.agent.restore_messages(saved)
            elif hasattr(self, 'conversation_history') and self.conversation_history:
                conversation = self.conversation_history.get_conversation(self.current_conversation_id)
                if conversation:
                    self._restore_conversation_to_agent(conversation)
        
        if hasattr(self, 'conversation_var'):
            self.conversation_var.set(tab_state.title)
        
        self.is_processing = tab_state.is_processing
        self.should_stop = tab_state.should_stop
        
        if self._workflow_engine and self.agent:
            self._workflow_engine.set_agent(self.agent, self.system)
        
        ui_state = self._tab_mgr.get_tab_ui_state(tab_id) if self._tab_mgr else None
        if ui_state and ui_state.get("chat_html"):
            try:
                self.chat_text.config(state=tk.NORMAL)
                self.chat_text.delete(1.0, tk.END)
                self.chat_text.insert(tk.END, ui_state["chat_html"])
                self.chat_text.config(state=tk.DISABLED)
                
                if ui_state.get("nav_blocks"):
                    self._nav_blocks = list(ui_state["nav_blocks"])
                    self._nav_current_idx = ui_state.get("nav_current_idx", -1)
                    self.nav_listbox.delete(0, tk.END)
                    for block in self._nav_blocks:
                        icon = block.get("icon", "💬")
                        label = block.get("label", "")
                        self.nav_listbox.insert(tk.END, f"{icon} {label}")
                    if 0 <= self._nav_current_idx < self.nav_listbox.size():
                        self.nav_listbox.selection_set(self._nav_current_idx)
                
                scroll_pos = ui_state.get("scroll_position", 1.0)
                self.chat_text.yview_moveto(scroll_pos)
            except Exception as e:
                logger.error(f"恢复Tab UI状态失败，回退到加载对话: {e}")
                self._load_conversation(tab_state.conversation_id, _skip_agent=True)
                # 修复：回退加载后需要显式恢复Agent消息上下文
                if self.agent and hasattr(self.agent, 'messages') and tab_state.conversation_id:
                    saved = self._session_messages.get(tab_state.conversation_id)
                    if saved:
                        self.agent.restore_messages(saved)
                        logger.info(f"回退恢复Agent消息快照: {tab_state.conversation_id[:8]} ({len(saved)} msgs)")
                    else:
                        self._restore_conversation_to_agent(
                            self.conversation_history.get_conversation(tab_state.conversation_id)
                        )
        else:
            self._load_conversation(tab_state.conversation_id, _skip_agent=True)
            # 修复：无UI状态时也需要恢复Agent消息上下文
            if self.agent and hasattr(self.agent, 'messages') and tab_state.conversation_id:
                saved = self._session_messages.get(tab_state.conversation_id)
                if saved:
                    self.agent.restore_messages(saved)
                    logger.info(f"无状态恢复Agent消息快照: {tab_state.conversation_id[:8]} ({len(saved)} msgs)")
                else:
                    self._restore_conversation_to_agent(
                        self.conversation_history.get_conversation(tab_state.conversation_id)
                    )
        
        if self.is_processing:
            self._update_status("⏳ 处理中...")
        else:
            self._update_status("✅ 就绪")
    
    def _close_tab(self, tab_id: str):
        """关闭指定 Tab"""
        if self._tab_mgr is None:
            return
        
        all_tabs = self._tab_mgr.get_all_tabs()
        if len(all_tabs) <= 1:
            self._append_system_message("至少需要保留一个 Tab", is_error=False)
            return
        
        tab_state = self._tab_mgr.get_tab(tab_id)
        if tab_state and tab_state.is_processing:
            self._append_system_message("该 Tab 正在处理中，无法关闭", is_error=True)
            return
        
        was_active = tab_state.is_active if tab_state else False
        
        self._tab_mgr.close_tab(tab_id)
        
        if was_active and self._tab_mgr.tabs:
            new_active = self._tab_mgr.get_active_tab()
            if new_active:
                self._restore_tab_state(new_active.tab_id, new_active)
                if hasattr(self, 'conversation_var'):
                    self.conversation_var.set(new_active.title)
        
        self._rebuild_tab_buttons()
        self._refresh_history_list()
    
    def _on_tab_changed(self, event_type: str, tab_id: str, **kwargs):
        """Tab 变更回调"""
        self.window.after(0, lambda: self._rebuild_tab_buttons())
    
    def _create_header(self, parent):
        """创建顶部标题栏"""
        header_frame = tk.Frame(parent, bg=self.primary_color, height=60)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(header_frame, text="🤖 WS2 Agent",
                              font=("Microsoft YaHei UI", 16, "bold"),
                              bg=self.primary_color, fg="white")
        title_label.pack(side=tk.LEFT, padx=15, pady=10)
        
        self.conversation_var = tk.StringVar()
        self.conversation_combo = ttk.Combobox(header_frame, textvariable=self.conversation_var,
                                               width=20, font=("Microsoft YaHei UI", 9))
        self.conversation_combo.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.X, expand=True)
        self.conversation_combo.bind("<<ComboboxSelected>>", self._on_conversation_selected)

        # 置顶切换按钮（与 popup_manager 风格一致）
        self._topmost_var = tk.BooleanVar(value=True)
        self._topmost_btn = tk.Checkbutton(
            header_frame, text="📌", variable=self._topmost_var,
            bg=self.primary_color, fg="white", selectcolor=self.primary_color,
            activebackground=self.primary_color, activeforeground="white",
            indicatoron=False, relief=tk.FLAT,
            command=self._toggle_topmost,
            font=("Segoe UI Symbol", 12),
        )
        self._topmost_btn.pack(side=tk.RIGHT, padx=8)

    def _toggle_topmost(self):
        """切换窗口置顶状态"""
        if self.window and self.window.winfo_exists():
            self.window.attributes("-topmost", self._topmost_var.get())
    
    def _create_infra_status_panel(self, parent):
        """创建基础设施状态面板"""
        infra_frame = tk.Frame(parent, bg="#1e293b", height=80)
        infra_frame.pack(fill=tk.X, padx=8, pady=(4, 0))
        infra_frame.pack_propagate(False)
        
        # 第一行状态
        status_row1 = tk.Frame(infra_frame, bg="#1e293b")
        status_row1.pack(fill=tk.X, padx=12, pady=(10, 4))
        
        self._model_label = tk.Label(status_row1, text="模型: GPT-4o",
                                    font=("Microsoft YaHei UI", 9),
                                    bg="#1e293b", fg="#a5b4fc", anchor=tk.W)
        self._model_label.pack(side=tk.LEFT, padx=(0, 15))
        
        self._context_label = tk.Label(status_row1, text="上下文: 128K",
                                       font=("Microsoft YaHei UI", 9),
                                       bg="#1e293b", fg="#6ee7b7", anchor=tk.W)
        self._context_label.pack(side=tk.LEFT, padx=(0, 15))
        
        self._reason_label = tk.Label(status_row1, text="推理: ✅",
                                     font=("Microsoft YaHei UI", 9),
                                     bg="#1e293b", fg="#fbbf24", anchor=tk.W)
        self._reason_label.pack(side=tk.LEFT)
        
        # 第二行状态
        status_row2 = tk.Frame(infra_frame, bg="#1e293b")
        status_row2.pack(fill=tk.X, padx=12, pady=(0, 10))
        
        self._cache_label = tk.Label(status_row2, text="缓存: 正常",
                                    font=("Microsoft YaHei UI", 9),
                                    bg="#1e293b", fg="#6b7280", anchor=tk.W)
        self._cache_label.pack(side=tk.LEFT, padx=(0, 15))
        
        self._session_label = tk.Label(status_row2, text="会话: 正常",
                                      font=("Microsoft YaHei UI", 9),
                                      bg="#1e293b", fg="#6b7280", anchor=tk.W)
        self._session_label.pack(side=tk.LEFT, padx=(0, 15))
        
        self._history_label = tk.Label(status_row2, text="历史: 0 条",
                                      font=("Microsoft YaHei UI", 9),
                                      bg="#1e293b", fg="#6b7280", anchor=tk.W)
        self._history_label.pack(side=tk.LEFT, padx=(0, 15))
        
        self._rag_label = tk.Label(status_row2, text="RAG: 未加载",
                                     font=("Microsoft YaHei UI", 9),
                                     bg="#1e293b", fg="#a7f3d0", anchor=tk.W)
        self._rag_label.pack(side=tk.LEFT)
        
        # 第三行状态 - 性能指标
        status_row3 = tk.Frame(infra_frame, bg="#1e293b")
        status_row3.pack(fill=tk.X, padx=12, pady=(0, 8))
        
        self._perf_label = tk.Label(status_row3, text="⚡ 性能: --",
                                     font=("Microsoft YaHei UI", 9),
                                     bg="#1e293b", fg="#60a5fa", anchor=tk.W)
        self._perf_label.pack(side=tk.LEFT)
    
    def _create_toolbar(self, parent):
        """创建工具栏"""
        toolbar_frame = tk.Frame(parent, bg=self.card_color, height=44)
        toolbar_frame.pack(fill=tk.X, pady=(4, 0))
        toolbar_frame.pack_propagate(False)
        
        btn_style = {
            "font": ("Segoe UI Symbol", 12),
            "width": 3,
            "height": 1,
            "relief": tk.FLAT,
            "bg": self.card_color,
            "fg": self.subtle_color,
            "activebackground": "#e0e7ff",
            "activeforeground": self.primary_color
        }
        
        new_btn = tk.Button(toolbar_frame, text="🆕", command=self._new_conversation, **btn_style)
        new_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        save_btn = tk.Button(toolbar_frame, text="💾", command=self._save_conversation, **btn_style)
        save_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        load_btn = tk.Button(toolbar_frame, text="📂", command=self._load_conversation_dialog, **btn_style)
        load_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        delete_btn = tk.Button(toolbar_frame, text="🗑️", command=self._delete_conversation, **btn_style)
        delete_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        tk.Frame(toolbar_frame, width=2, bg=self.border_color).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=6)
        
        # 文件上传按钮
        upload_btn = tk.Button(toolbar_frame, text="📎", command=self._upload_file, **btn_style)
        upload_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        reset_btn = tk.Button(toolbar_frame, text="🔄", command=self._reset_conversation, **btn_style)
        reset_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        # 检查点回退按钮
        rollback_btn = tk.Button(toolbar_frame, text="↩️", command=self._show_checkpoint_list, **btn_style)
        rollback_btn.pack(side=tk.LEFT, padx=4, pady=6)
        ToolTip(rollback_btn, "检查点 — 每轮对话自动保存，可回退对话或文件")
        
        tk.Frame(toolbar_frame, width=2, bg=self.border_color).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=6)
        
        # 复制全部按钮
        copy_all_btn = tk.Button(toolbar_frame, text="📋", command=self._copy_all_messages, **btn_style)
        copy_all_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        # 输入历史按钮
        history_btn = tk.Button(toolbar_frame, text="📜", command=self._show_input_history, **btn_style)
        history_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        # 修改标题按钮
        rename_btn = tk.Button(toolbar_frame, text="✏️", command=self._rename_conversation, **btn_style)
        rename_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        # 语境查看按钮
        context_btn = tk.Button(toolbar_frame, text="🌐", command=self._show_current_context, **btn_style)
        context_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        # ─── 上下文注入方式选择器 ───
        # 让用户自主选择启用哪些上下文层
        self._ctx_inject_var = tk.StringVar(value="智能")
        ctx_options = ["智能", "完整", "仅环境感知", "仅规则", "最小", "关闭"]
        ctx_menu_btn = tk.Menubutton(
            toolbar_frame,
            textvariable=self._ctx_inject_var,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            bg=self.card_color,
            fg=self.subtle_color,
            activebackground="#e0e7ff",
            activeforeground=self.primary_color,
            indicatoron=True,
        )
        ctx_menu = tk.Menu(ctx_menu_btn, tearoff=0)
        for opt in ctx_options:
            ctx_menu.add_radiobutton(
                label=opt,
                variable=self._ctx_inject_var,
                value=opt,
                command=lambda o=opt: self._on_context_mode_changed(o),
            )
        ctx_menu_btn.configure(menu=ctx_menu)
        ctx_menu_btn.pack(side=tk.LEFT, padx=2, pady=6)
        
        # 悬停提示
        try:
            ctx_menu_btn.tooltip = "上下文注入模式:\n智能=按需注入\n完整=全部注入\n仅环境感知=UI状态\n仅规则=规则文件\n最小=仅系统提示\n关闭=无额外上下文"
        except Exception:
            pass
        
        tk.Frame(toolbar_frame, width=2, bg=self.border_color).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=6)
        
        # 语音唤醒开关按钮
        self._wake_btn_text = tk.StringVar(value="🎤")
        self._wake_btn = tk.Button(
            toolbar_frame,
            textvariable=self._wake_btn_text,
            command=self._toggle_voice_wake,
            **btn_style
        )
        self._wake_btn.pack(side=tk.LEFT, padx=4, pady=6)
        self._update_wake_button_state()
        
        # RAG 知识库按钮
        rag_btn = tk.Button(toolbar_frame, text="📚", command=self._show_rag_controls, **btn_style)
        rag_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        # 调试/性能指标按钮
        debug_btn = tk.Button(toolbar_frame, text="🔧", command=self._show_debug_panel, **btn_style)
        debug_btn.pack(side=tk.LEFT, padx=4, pady=6)

        # 服务器启动按钮（本地文件同步分发）
        tk.Frame(toolbar_frame, width=2, bg=self.border_color).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=6)
        self._server_btn_text = tk.StringVar(value="🌐")
        self._server_btn = tk.Button(
            toolbar_frame,
            textvariable=self._server_btn_text,
            command=self._toggle_sync_server,
            **btn_style,
        )
        self._server_btn.pack(side=tk.LEFT, padx=4, pady=6)
        self._server_running = False
        self._server_process = None
    
    def _create_chat_area(self, parent):
        """创建对话区域 - 左侧导航 + 右侧聊天"""
        chat_container = tk.Frame(parent, bg=self.bg_color)
        chat_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # 使用 PanedWindow 实现可拖拽分割
        chat_paned = ttk.PanedWindow(chat_container, orient=tk.HORIZONTAL)
        chat_paned.pack(fill=tk.BOTH, expand=True)

        # ========== 左侧：聊天区 ==========
        left_frame = tk.Frame(chat_paned, bg=self.bg_color)
        chat_paned.add(left_frame, weight=1)

        # ========== 右侧：对话导航侧边栏 ==========
        nav_frame = tk.Frame(chat_paned, bg=self.card_color, width=200)
        chat_paned.add(nav_frame, weight=0)
        nav_frame.pack_propagate(False)

        # 导航标题
        nav_title = tk.Label(nav_frame, text="📑 对话导航",
                            font=("Microsoft YaHei UI", 9, "bold"),
                            bg=self.card_color, fg=self.subtle_color,
                            anchor=tk.W, padx=8, pady=4)
        nav_title.pack(fill=tk.X)

        # 导航列表
        self.nav_listbox = tk.Listbox(
            nav_frame,
            font=("Microsoft YaHei UI", 8),
            bg=self.card_color,
            fg=self.text_color,
            selectmode=tk.SINGLE,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
        )
        self.nav_listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.nav_listbox.bind("<<ListboxSelect>>", self._on_nav_select)
        self.nav_listbox.bind("<Double-Button-1>", self._on_nav_double_click)
        self.nav_listbox.bind("<Up>", self._on_nav_key_up)
        self.nav_listbox.bind("<Down>", self._on_nav_key_down)

        # 导航按钮
        nav_btn_frame = tk.Frame(nav_frame, bg=self.card_color)
        nav_btn_frame.pack(fill=tk.X, padx=4, pady=2)
        tk.Button(nav_btn_frame, text="⬆", font=("Segoe UI Symbol", 10),
                  command=self._nav_prev,
                  bg="#e0e7ff", fg=self.primary_color,
                  relief=tk.RAISED, padx=4, pady=2, bd=1).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(nav_btn_frame, text="⬇", font=("Segoe UI Symbol", 10),
                  command=self._nav_next,
                  bg="#e0e7ff", fg=self.primary_color,
                  relief=tk.RAISED, padx=4, pady=2, bd=1).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(nav_btn_frame, text="全部", font=("Microsoft YaHei UI", 8),
                  command=self._nav_show_all,
                  bg="#dbeafe", fg=self.primary_color,
                  relief=tk.RAISED, padx=4, pady=2, bd=1).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(nav_btn_frame, text="选中", font=("Microsoft YaHei UI", 8),
                  command=self._nav_show_selected,
                  bg="#dbeafe", fg=self.primary_color,
                  relief=tk.RAISED, padx=4, pady=2, bd=1).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 使用 ScrolledText 便于文本选中
        self.chat_text = scrolledtext.ScrolledText(left_frame,
                                                   font=("Microsoft YaHei UI", 10),
                                                   bg=self.bg_color, fg=self.text_color,
                                                   insertbackground=self.primary_color,
                                                   wrap=tk.WORD, relief=tk.FLAT,
                                                   padx=8, pady=8,
                                                   state=tk.NORMAL,  # 允许选中和复制
                                                   exportselection=True)  # 允许导出选中
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        # 禁用编辑但允许选中
        self.chat_text.bind("<Key>", lambda e: "break")  # 阻止键盘输入
        self.chat_text.bind("<Button-1>", self._on_chat_text_click)  # 点击事件
        self.chat_text.bind("<B1-Motion>", self._on_chat_text_motion)  # 拖拽选中

        # 绑定右键菜单
        self.chat_text.bind("<Button-3>", self._show_chat_context_menu)

        # 绑定 Ctrl+C 复制
        self.chat_text.bind("<Control-c>", self._on_ctrl_c_copy)

        # 配置标签样式
        self.chat_text.tag_config("time", foreground="#a0aec0", font=("Consolas", 8))
        self.chat_text.tag_config("system_bg", background="#f3f4f6")
        self.chat_text.tag_config("user_bg", background="#dbeafe")
        self.chat_text.tag_config("assistant_bg", background="#ffffff")
        self.chat_text.tag_config("thinking_bg", background="#f0fdf4")
        self.chat_text.tag_config("tool_bg", background="#fffbeb")
        self.chat_text.tag_config("error_bg", background="#fee2e2")

        self.chat_text.tag_config("icon", font=("Segoe UI Symbol", 12))

        # Markdown 标签
        self.chat_text.tag_config("bold", font=("Microsoft YaHei UI", 10, "bold"))
        self.chat_text.tag_config("italic", font=("Microsoft YaHei UI", 10, "italic"))
        self.chat_text.tag_config("code", font=("Consolas", 9), background="#f0f0f0", relief=tk.SOLID, borderwidth=1)
        self.chat_text.tag_config("h1", font=("Microsoft YaHei UI", 14, "bold"))
        self.chat_text.tag_config("h2", font=("Microsoft YaHei UI", 12, "bold"))
        self.chat_text.tag_config("h3", font=("Microsoft YaHei UI", 11, "bold"))
        self.chat_text.tag_config("li", lmargin1=20, lmargin2=20)

        # 初始化增强渲染器
        self._renderer = None
        if HAS_ENHANCED_RENDERER:
            try:
                self._renderer = create_renderer(self.chat_text)
            except Exception as e:
                logger.debug(f"增强渲染器初始化失败: {e}")

    def _create_input_area(self, parent):
        """创建输入区域 - 支持大文本"""
        # 可展开的输入容器
        self.input_container = tk.Frame(parent, bg=self.card_color, height=180)
        self.input_container.pack(fill=tk.X, pady=(4, 0), padx=8)
        self.input_container.pack_propagate(True)
        
        # 顶部工具栏
        top_bar = tk.Frame(self.input_container, bg=self.card_color)
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 2))
        
        # 字符计数
        self.char_count_label = tk.Label(top_bar, text="0 字符",
                                        font=("Microsoft YaHei UI", 8),
                                        bg=self.card_color, fg="#9ca3af")
        self.char_count_label.pack(side=tk.LEFT)
        
        # 展开/收起按钮
        self.is_input_expanded = False
        self.expand_btn = tk.Button(top_bar, text="🔍 展开",
                                   command=self._toggle_input_expand,
                                   bg=self.card_color, fg="#6b7280",
                                   font=("Microsoft YaHei UI", 8),
                                   relief=tk.FLAT, padx=4)
        self.expand_btn.pack(side=tk.RIGHT)
        
        # 清空按钮
        clear_btn = tk.Button(top_bar, text="🗑",
                             command=self._clear_input,
                             bg=self.card_color, fg="#6b7280",
                             font=("Segoe UI Symbol", 10),
                             relief=tk.FLAT, padx=4)
        clear_btn.pack(side=tk.RIGHT, padx=4)
        
        # 主要输入区
        input_frame = tk.Frame(self.input_container, bg=self.card_color)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 8))
        
        self.input_text = scrolledtext.ScrolledText(input_frame, height=5,
                                                    font=("Microsoft YaHei UI", 10),
                                                    bg="#f7fafc", fg=self.text_color,
                                                    insertbackground=self.primary_color,
                                                    relief=tk.FLAT, wrap=tk.WORD,
                                                    undo=True, maxundo=100,
                                                    state=tk.NORMAL)  # 明确设置为启用
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 绑定事件
        self.input_text.bind("<Return>", self._on_input_return)
        self.input_text.bind("<Shift-Return>", self._on_shift_return)
        self.input_text.bind("<Control-Return>", self._on_input_return)
        self.input_text.bind("<<Modified>>", self._on_text_modified)
        self.input_text.bind("<Tab>", self._tab_insert)
        
        # 绑定方向键实现历史导航
        self.input_text.bind("<Up>", self._on_history_up)
        self.input_text.bind("<Down>", self._on_history_down)
        self.input_text.bind("<Control-p>", self._on_history_up)
        self.input_text.bind("<Control-n>", self._on_history_down)
        
        button_frame = tk.Frame(input_frame, bg=self.card_color)
        button_frame.pack(side=tk.RIGHT, padx=(10, 0))
        
        send_btn = tk.Button(button_frame, text="📤 发送",
                            command=self._send_message,
                            bg=self.primary_color, fg="white",
                            font=("Microsoft YaHei UI", 10, "bold"),
                            width=10, relief=tk.FLAT, pady=8)
        send_btn.pack(pady=2)
        
        stop_btn = tk.Button(button_frame, text="🛑 停止",
                            command=self._stop_processing,
                            bg=self.error_color, fg="white",
                            font=("Microsoft YaHei UI", 10, "bold"),
                            width=10, relief=tk.FLAT, pady=8)
        stop_btn.pack(pady=2)
    
    def _create_status_bar(self, parent):
        """创建状态栏"""
        status_frame = tk.Frame(parent, bg="#374151", height=26)
        status_frame.pack(fill=tk.X)
        status_frame.pack_propagate(False)
        
        self.status_label = tk.Label(status_frame, text="✅ 就绪",
                                    font=("Microsoft YaHei UI", 9),
                                    bg="#374151", fg="#d1d5db",
                                    anchor=tk.W, padx=12)
        self.status_label.pack(fill=tk.BOTH, expand=True)
    
    def _scroll_to_bottom(self):
        """滚动到底部"""
        self.chat_text.see(tk.END)

    def _init_background_modules(self):
        """后台异步初始化各模块 - 不阻塞UI"""
        def _async_init():
            try:
                # 1. 延迟加载工作流引擎
                try:
                    WorkflowEngine, WorkflowStatus, get_workflow_engine, get_workflow, list_workflows = _lazy_import_workflow()
                    self._workflow_engine = get_workflow_engine(Path(self.base_path) / "data" / "workflow.db")
                    self._workflow_engine.persistence.save_definition(get_workflow("code_analysis"))
                    self._workflow_loaded = True
                except Exception as e:
                    print(f"[Async] 工作流加载失败: {e}")

                # 2. 延迟加载AutoCompact
                try:
                    pass
                except Exception as e:
                    print(f"[Async] AutoCompact已禁用: {e}")

                # 3. 延迟加载Git搜索
                try:
                    get_git_searcher = _lazy_import_git_searcher()
                    self._git_searcher = get_git_searcher(Path(self.base_path) / "data" / "git_cache")
                    self._git_loaded = True
                except Exception as e:
                    print(f"[Async] Git搜索加载失败: {e}")

                # 4. 延迟加载知识图谱
                try:
                    get_kg_rag = _lazy_import_kg_rag()
                    self._kg_rag = get_kg_rag(Path(self.base_path) / "data" / "knowledge_graph.db")
                    self._kg_loaded = True
                except Exception as e:
                    print(f"[Async] 知识图谱加载失败: {e}")

                print("[Async] 所有后台模块初始化完成")
            except Exception as e:
                print(f"[Async] 后台初始化异常: {e}")

        threading.Thread(target=_async_init, daemon=True).start()

    def _load_rag(self):
        """按需加载RAG系统"""
        if self._rag_loaded or not HAS_RAG:
            return True
        try:
            initialize_rag_for_agent, _ = _lazy_import_rag()
            self._rag_manager = initialize_rag_for_agent(str(self.base_path), ws2_system=self.system)
            if self.system is not None:
                self.system.rag = self._rag_manager
            self._rag_loaded = True
            # 更新RAG状态标签
            if hasattr(self, '_rag_label'):
                self.window.after(0, lambda: self._rag_label.config(text="RAG: 已加载"))
            return True
        except Exception as e:
            print(f"RAG 系统加载失败: {e}")
            return False

    def _init_agent(self):
        """初始化 Agent - 完全集成 TS2 系统"""
        if not HAS_AGENT:
            self._append_system_message("Agent 模块未加载")
            return
        
        try:
            # 使用传入的所有系统对象初始化 Agent
            self.agent = mcp_agent.create_agent(
                base_dir=self.base_path,
                ws2_system=self.system,
                project_manager=self.project_mgr,
                task_manager=self.task_board_mgr
            )
            
            # 替换 Agent 的系统提示词为我们自定义的版本
            if self.agent and hasattr(self.agent, 'messages'):
                custom_system_prompt = self._get_contextualized_system_prompt()
                # 更新第一条消息（系统提示词）
                if self.agent.messages and self.agent.messages[0]["role"] == "system":
                    self.agent.messages[0]["content"] = custom_system_prompt
                else:
                    self.agent.messages = [{"role": "system", "content": custom_system_prompt}]
            
            # 注册学习状态上下文注入器（如果提供了 course_tracker）
            self._register_learning_state_injector()
            
            # 构建欢迎消息，包含语境信息和Agent能力
            tool_count = len(self.agent.tools) if hasattr(self.agent, 'tools') else 0
            
            # 提取工具类别统计
            tool_categories = {}
            if hasattr(self.agent, 'tools'):
                for t in self.agent.tools:
                    cat = getattr(t, 'category', 'general')
                    tool_categories[cat] = tool_categories.get(cat, 0) + 1
            
            welcome_msg = "🤖 **WS2 Agent 已就绪！**\n\n"
            welcome_msg += f"📊 已加载 {tool_count} 个工具\n"
            
            # 显示主要工具类别
            if tool_categories:
                sorted_cats = sorted(tool_categories.items(), key=lambda x: x[1], reverse=True)
                cat_display = []
                for cat, count in sorted_cats[:6]:
                    cat_name_map = {
                        "file": "📂 文件",
                        "edit": "✏️ 编辑", 
                        "search": "🔍 搜索",
                        "ws2": "📚 课程",
                        "web": "🌐 网络",
                        "system": "⚙️ 系统",
                        "note": "📝 笔记",
                        "project": "📁 项目",
                        "task": "✅ 任务",
                        "bookmark": "🔖 书签",
                        "rag": "🧠 RAG",
                        "sandbox": "🏖️ 沙盒",
                        "general": "🔧 通用",
                    }
                    cat_display.append(f"{cat_name_map.get(cat, cat)}({count})")
                welcome_msg += f"🔧 工具: {' | '.join(cat_display)}\n\n"
            
            welcome_msg += "我可以帮助你：\n"
            welcome_msg += "- 查询课程信息和学习进度\n"
            welcome_msg += "- 搜索和管理学习资源\n"
            welcome_msg += "- 创建和编辑笔记\n"
            welcome_msg += "- 管理书签和项目\n"
            welcome_msg += "- 追踪学习任务\n"
            welcome_msg += "- 📎 点击附件按钮上传文件\n"
            welcome_msg += "- 🌐 查看当前界面语境\n\n"
            welcome_msg += "请输入你的问题，我会尽力帮助你！"
            
            self._append_system_message(welcome_msg)
            
            # 更新基础设施状态面板
            self._update_infra_status()
            
            # 启动定时更新
            self._start_infra_update_timer()
            
        except Exception as e:
            import traceback
            self._append_system_message(f"Agent 初始化失败: {e}", is_error=True)

    def _register_learning_state_injector(self):
        """注册学习状态注入器到 agent — 迁移到 ContextProvider 动态提供者
        
        同时保留旧的 register_context_injector 兼容路径，
        但优先使用新的 ContextProvider Others 层。
        """
        if not self.course_tracker or not self.agent:
            return

        # 避免重复注册
        if getattr(self.agent, '_learning_state_injector_registered', False):
            return
        self.agent._learning_state_injector_registered = True

        tracker = self.course_tracker

        # ─── 新路径：通过 ContextProvider Others 层注入 ───
        if hasattr(self.agent, '_context_provider') and self.agent._context_provider:
            def _learning_state_provider(agent=None, user_input=""):
                try:
                    state = tracker.get_learning_state()
                    if not state.get("exec_mode_active"):
                        return None
                    
                    parts = []
                    parts.append(f"正在学习: {state.get('course_title', state.get('course_id', '未知'))}")
                    if state.get('domain'):
                        parts.append(f"课程领域: {state['domain']}")
                    if state.get('current_lesson_number'):
                        parts.append(f"当前课时: 第 {state['current_lesson_number']} 节")
                    if state.get('timer_running'):
                        parts.append("计时器: 运行中")
                    if state.get('completed_count') is not None:
                        parts.append(f"进度: {state['completed_count']}/{state.get('total_lessons', '?')} 节 ({state.get('completion_pct', 0)}%)")
                    
                    from .prompt.context_provider import ContextSection
                    return ContextSection(
                        source="learning_state",
                        label="学习状态",
                        content="\n".join(parts),
                        priority=35,  # 最高优先级
                        layer="others",
                    )
                except Exception:
                    return None
            
            _learning_state_provider.__source__ = 'learning_state'
            self.agent._context_provider.register_dynamic(_learning_state_provider)
            return  # 新路径注册成功，跳过旧路径

        # ─── 旧路径：通过 register_context_injector 兼容 ───
        def _injector(agent_ref, user_input: str) -> str:
            try:
                state = tracker.get_learning_state()
                if not state.get("exec_mode_active"):
                    return ""

                ctx_lines = ["<!-- BEGIN_LEARNING_STATE -->", "【当前学习状态】"]
                ctx_lines.append(f"- 正在学习: {state.get('course_title', state.get('course_id', '未知'))}")
                if state.get('domain'):
                    ctx_lines.append(f"- 课程领域: {state['domain']}")
                if state.get('current_lesson_number'):
                    ctx_lines.append(f"- 当前课时: 第 {state['current_lesson_number']} 节")
                if state.get('timer_running'):
                    ctx_lines.append("- 计时器: 运行中")
                if state.get('completed_count') is not None:
                    ctx_lines.append(f"- 进度: {state['completed_count']}/{state.get('total_lessons', '?')} 节 ({state.get('completion_pct', 0)}%)")
                ctx_lines.append("<!-- END_LEARNING_STATE -->")
                return "\n".join(ctx_lines)
            except Exception:
                return ""

        self.agent.register_context_injector(_injector)
    
    def _restore_conversation_to_agent(self, conversation):
        if not self.agent or not hasattr(self.agent, 'messages'):
            return

        custom_system_prompt = self._get_contextualized_system_prompt()
        messages = [{"role": "system", "content": custom_system_prompt}]

        pending_tool_calls = {}

        for msg in conversation.messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                continue

            if role == "assistant":
                tool_calls_json = msg.get("tool_calls")
                if tool_calls_json:
                    try:
                        if isinstance(tool_calls_json, str):
                            parsed = json.loads(tool_calls_json)
                        else:
                            parsed = tool_calls_json
                        message = {
                            "role": "assistant",
                            "content": content or None,
                            "tool_calls": parsed,
                        }
                        for tc in parsed:
                            tc_id = tc.get("id", "")
                            if tc_id:
                                pending_tool_calls[tc_id] = tc.get("function", {}).get("name", "")
                    except (json.JSONDecodeError, TypeError):
                        message = {"role": "assistant", "content": content}
                else:
                    message = {"role": "assistant", "content": content}

                reasoning_content = msg.get("reasoning_content")
                if reasoning_content:
                    message["reasoning_content"] = reasoning_content

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                tool_name = msg.get("tool_name", "")
                if not tool_call_id:
                    if tool_name and pending_tool_calls:
                        for tc_id, tc_name in pending_tool_calls.items():
                            if tc_name == tool_name:
                                tool_call_id = tc_id
                                pending_tool_calls.pop(tc_id, None)
                                break
                    if not tool_call_id and tool_name:
                        tool_call_id = f"tc_{tool_name}_{len(messages)}"

                message = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": content or msg.get("tool_result", ""),
                }

            elif role == "user":
                message = {"role": "user", "content": content}

            else:
                message = {"role": role, "content": content}

            messages.append(message)

        self.agent.restore_messages(messages)
    
    def _upload_file(self):
        """文件上传功能 - 支持多编码自动检测并转换为UTF-8"""
        file_path = filedialog.askopenfilename(
            title="选择要上传的文件",
            filetypes=[
                ("所有文件", "*.*"),
                ("文本文件", "*.txt;*.md;*.py;*.json;*.csv"),
                ("PDF文件", "*.pdf"),
                ("图片文件", "*.png;*.jpg;*.jpeg;*.gif"),
            ]
        )
        
        if file_path:
            try:
                path = Path(file_path)
                file_size = path.stat().st_size
                
                # 读取文件内容（如果是文本文件）
                content = ""
                encoding_used = ""
                if path.suffix in ['.txt', '.md', '.py', '.json', '.csv', '.html', '.css', '.js']:
                    # 尝试多种编码
                    encodings_to_try = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'utf-16', 'latin-1']
                    
                    for encoding in encodings_to_try:
                        try:
                            with open(path, 'r', encoding=encoding) as f:
                                content = f.read()
                                encoding_used = encoding
                                break
                        except UnicodeDecodeError:
                            continue
                
                file_info = f"📎 **文件已上传**\n\n"
                file_info += f"- 文件名: {path.name}\n"
                file_info += f"- 大小: {file_size} 字节\n"
                file_info += f"- 路径: {file_path}\n"
                if encoding_used:
                    file_info += f"- 编码: {encoding_used} (已转换为UTF-8)\n"
                
                if content:
                    file_info += f"\n**内容**:\n```\n{content}\n```"
                
                self._append_system_message(file_info)
                
                # 将文件信息保存到语境中
                self.current_context["last_uploaded_file"] = {
                    "name": path.name,
                    "path": file_path,
                    "size": file_size,
                    "encoding": encoding_used,
                    "content": content,  # 保存完整内容供Agent使用
                    "content_preview": content[:1000] if content else None,
                    "timestamp": datetime.now().isoformat()
                }
                
                self._update_status(f"✅ 已上传: {path.name}")
                
            except Exception as e:
                self._append_system_message(f"❌ 文件上传失败: {e}", is_error=True)
    
    def _start_context_monitoring(self):
        """启动语境监控 - 定期检查主界面状态（降低频率）"""
        def monitor():
            self._update_context_from_parent()
            self._context_timer_id = self.window.after(5000, monitor)
        
        self._context_timer_id = self.window.after(5000, monitor)
    
    def _update_context_from_parent(self):
        """从父窗口更新语境信息 - 增强版"""
        try:
            context_changed = False
            
            # 检查执行模式
            if hasattr(self.parent, 'exec_mode_active'):
                if self.parent.exec_mode_active != self.current_context.get("exec_mode_active"):
                    self.current_context["exec_mode_active"] = self.parent.exec_mode_active
                    context_changed = True
            
            # 检查当前课程
            if hasattr(self.parent, '_current_detail_course'):
                current_course = self.parent._current_detail_course
                if current_course != self.current_context.get("current_course"):
                    self.current_context["current_course"] = current_course
                    context_changed = True
            
            # 检查当前标签页
            if hasattr(self.parent, '_current_tab'):
                current_tab = self.parent._current_tab
                if current_tab != self.current_context.get("current_tab"):
                    self.current_context["current_tab"] = current_tab
                    context_changed = True
            
            # 检查是否有选中的内容
            if hasattr(self.parent, '_selected_items'):
                selected_items = self.parent._selected_items
                if selected_items != self.current_context.get("selected_items"):
                    self.current_context["selected_items"] = selected_items
                    context_changed = True
            
            # 检查工作目录
            if hasattr(self.parent, 'working_dir'):
                work_dir = str(self.parent.working_dir)
                if work_dir != self.current_context.get("working_directory"):
                    self.current_context["working_directory"] = work_dir
                    context_changed = True
            
            # 更新时间戳
            self.current_context["timestamp"] = datetime.now().isoformat()
            
            # 语境变化时记录事件
            if context_changed and self._event_logger:
                try:
                    # 记录当前标签页变化
                    if self.current_context.get("current_tab"):
                        self._event_logger.log_tab_change(
                            tab_name=self.current_context["current_tab"],
                            context_info="agent_context_monitor"
                        )
                    # 记录当前课程变化
                    if self.current_context.get("current_course"):
                        self._event_logger.log_action(
                            action_type="course_view",
                            element="course_detail",
                            value=self.current_context["current_course"],
                            context_info="agent_context_monitor"
                        )
                except Exception:
                    pass
            
        except Exception:
            pass
    
    def _show_current_context(self):
        """显示当前语境信息 - 增强版"""
        context_str = json.dumps(self.current_context, indent=2, ensure_ascii=False)
        self._append_system_message(f"🌐 **当前界面语境**\n```json\n{context_str}\n```")
    
    def _inject_ui_context_to_agent(self):
        """将当前 UI 环境感知注入到 agent 的 ContextProvider Others 层
        
        参考 Cline 的 withExtensionContext 机制：
        - 让 agent 清楚地知道用户当前在什么界面、干什么
        - 通过 ContextProvider 的动态提供者注入，而非硬编码到 system prompt
        - 根据用户选择的上下文注入模式决定是否注入
        """
        if not self.agent or not hasattr(self.agent, '_context_provider'):
            return
        
        # 获取当前上下文注入模式
        mode = getattr(self, '_ctx_inject_var', None)
        mode = mode.get() if mode else "智能"
        
        # "关闭" 或 "仅规则" 模式下不注入 UI 环境
        if mode in ("关闭", "仅规则"):
            return
        
        try:
            from .prompt.context_provider import ContextSection
            
            # 构建环境感知摘要
            ctx = self.current_context
            parts = []
            
            # 当前标签页
            tab = ctx.get("current_tab")
            if tab:
                parts.append(f"当前界面: {tab}")
            
            # 执行模式
            exec_mode = ctx.get("exec_mode_active")
            if exec_mode:
                parts.append("执行模式: 已激活（用户正在执行学习任务）")
            
            # 当前课程
            course = ctx.get("current_course")
            if course:
                parts.append(f"正在查看课程: {course}")
            
            # 选中项
            selected = ctx.get("selected_items", [])
            if selected:
                parts.append(f"选中内容: {', '.join(str(s) for s in selected[:5])}")
            
            # 工作目录
            work_dir = ctx.get("working_directory")
            if work_dir:
                parts.append(f"工作目录: {work_dir}")
            
            # 上传文件
            uploaded = ctx.get("last_uploaded_file")
            if uploaded:
                parts.append(f"最近上传: {uploaded.get('name', '未知文件')}")
            
            if not parts:
                return
            
            content = "\n".join(parts)
            
            # 注册为动态提供者
            section = ContextSection(
                source="ui_environment",
                label="环境感知（当前界面状态）",
                content=content,
                priority=30,  # 高优先级，环境感知很重要
                layer="others",
            )
            
            # 直接注入到 agent 的 context_provider
            provider = self.agent._context_provider
            if provider:
                # 清除之前的 UI 环境注入，避免重复
                provider._dynamic_providers = [
                    p for p in provider._dynamic_providers
                    if getattr(p, '__source__', '') != 'ui_environment'
                ]
                
                # 创建闭包提供者
                def _ui_env_provider(agent=None, user_input=""):
                    return section
                
                _ui_env_provider.__source__ = 'ui_environment'
                provider.register_dynamic(_ui_env_provider)
        
        except Exception as e:
            # 静默失败，不影响核心功能
            pass
    
    def _on_context_mode_changed(self, mode: str):
        """用户切换上下文注入模式时的回调
        
        模式说明:
        - 智能: 按需注入（默认），Rules+Files 静态注入，Others 动态注入
        - 完整: 全部注入，不裁剪
        - 仅环境感知: 只注入 UI 状态和学习状态（Others 层）
        - 仅规则: 只注入规则文件（Rules 层）
        - 最小: 仅系统提示，无额外上下文
        - 关闭: 完全不注入任何额外上下文
        """
        try:
            if not self.agent or not hasattr(self.agent, '_context_provider'):
                return
            
            provider = self.agent._context_provider
            if not provider:
                return
            
            # 根据模式调整 ContextProvider 的行为
            # 通过设置 _enabled_layers 控制哪些层被收集
            if mode == "智能":
                provider._enabled_layers = {"rules", "files", "others"}
                provider._token_budget_override = 0  # 使用默认预算
            elif mode == "完整":
                provider._enabled_layers = {"rules", "files", "others"}
                provider._token_budget_override = -1  # 无限制
            elif mode == "仅环境感知":
                provider._enabled_layers = {"others"}
                provider._token_budget_override = 0
            elif mode == "仅规则":
                provider._enabled_layers = {"rules"}
                provider._token_budget_override = 0
            elif mode == "最小":
                provider._enabled_layers = set()  # 空集
                provider._token_budget_override = 0
            elif mode == "关闭":
                provider._enabled_layers = set()
                provider._token_budget_override = 0
            
            # 显示切换提示
            mode_labels = {
                "智能": "按需注入（默认）",
                "完整": "全部注入（可能增加 token 消耗）",
                "仅环境感知": "只注入 UI 状态和学习状态",
                "仅规则": "只注入规则文件",
                "最小": "仅系统提示",
                "关闭": "无额外上下文",
            }
            self._append_system_message(f"🌐 上下文注入模式: {mode} — {mode_labels.get(mode, '')}")
            
        except Exception:
            pass
    
    def _safe_text(self, value: Any, max_len: int = 100) -> str:
        """安全地将任意值转换为文本，避免破坏提示词结构"""
        if value is None:
            return ""
        
        text = str(value)
        
        if len(text) > max_len:
            text = text[:max_len - 3] + "..."
        
        return text.replace('\\', '\\\\').replace('`', '\\`').replace('*', '\\*').replace('_', '\\_')
    
    def _safe_format_event(self, event) -> str:
        """安全格式化事件为摘要字符串，避免破坏提示词结构"""
        if not event:
            return ""
        
        parts = []
        
        # 时间（精简）
        if event.timestamp:
            try:
                time_str = event.timestamp[11:19]
                parts.append(f"[{time_str}]")
            except (IndexError, TypeError):
                pass
        
        # 事件类型
        if event.event_type:
            parts.append(event.event_type)
        
        # 文件名（安全）
        if event.file_name:
            safe_name = str(event.file_name)[:50]  # 限制长度
            safe_name = safe_name.replace('\n', ' ').replace('*', '').replace('`', '')
            parts.append(f"📄{safe_name}")
        
        # 操作类型
        if event.file_operation:
            parts.append(f"[{event.file_operation}]")
        
        # UI 元素
        if event.ui_element and not event.file_name:
            safe_element = str(event.ui_element)[:30]
            safe_element = safe_element.replace('\n', ' ').replace('*', '').replace('`', '')
            parts.append(safe_element)
        
        # 新值（仅短文本）
        if event.new_value:
            val_str = str(event.new_value)
            # 过滤：跳过JSON、过长内容、包含特殊格式的内容
            if (len(val_str) <= 40 and 
                '{' not in val_str and '}' not in val_str and
                '[' not in val_str[:5] and  # 避免JSON数组开头
                '\n' not in val_str and 
                val_str.strip()):
                safe_val = val_str.replace('\r', ' ').replace('*', '').replace('`', '')
                parts.append(f"→ {safe_val}")
        
        # 限制总长度
        result = " ".join(parts)
        if len(result) > 120:
            result = result[:117] + "..."
        
        return result
    
    def _fix_incomplete_output(self, content: str) -> str:
        """修复不完整的输出格式，避免破坏上下文"""
        if not content:
            return content
        
        lines = content.split('\n')
        fixed_lines = []
        code_block_depth = 0
        list_depth = 0
        
        for i, line in enumerate(lines):
            fixed_lines.append(line)
            
            # 追踪代码块
            triple_backtick = line.count('```')
            code_block_depth += triple_backtick
            
            # 追踪列表
            stripped = line.strip()
            if stripped.startswith('- ') or stripped.startswith('* ') or stripped.startswith('+ '):
                list_depth += 1
            elif stripped and not stripped.startswith('#') and not stripped.startswith('```'):
                if list_depth > 0 and not line.startswith(' '):
                    list_depth = 0
            
            # 追踪未闭合的格式标记
            bold_count = line.count('**')
            italic_count = line.count('*') - bold_count
            code_count = line.count('`') - line.count('``')
            
            # 追踪括号
            paren_count = line.count('(') - line.count(')')
            bracket_count = line.count('[') - line.count(']')
            brace_count = line.count('{') - line.count('}')
            
            # 如果是最后一行且有未闭合的格式
            if i == len(lines) - 1:
                # 关闭代码块
                if code_block_depth % 2 != 0:
                    fixed_lines.append('```')
                    code_block_depth = 0
        
        result = '\n'.join(fixed_lines)
        
        # 添加截断标记
        if len(result) < len(content) * 0.9:
            result += '\n\n... [输出被中断，内容已截断]'
        
        return result
    
    def _check_and_fix_format(self, content: str) -> str:
        """全面检查和修复文本格式 - 增强完善版 - 支持JSON友好格式转换"""
        if not content:
            return content
        
        result = content
        
        try:
            # 首先，对整个内容尝试转换为友好格式（最优先）
            try:
                parsed_json = json.loads(result)
                friendly_format = self._json_to_friendly_format(parsed_json)
                # 如果转换成功，直接使用友好格式
                if friendly_format and friendly_format != "":
                    return friendly_format
            except (json.JSONDecodeError, TypeError):
                # 不是完整JSON，继续处理
                pass
            
            # 尝试查找并转换文本中的JSON片段
            result = self._format_json_in_text(result)
            
            # 步骤1: 基础清理
            # 移除控制字符（保留必要的换行和制表符）
            result = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', result)
            
            # 步骤2: 修复不完整的输出（复用已有的智能修复）
            result = self._fix_incomplete_output(result)
            
            # 步骤3: 追踪所有格式标记
            lines = result.split('\n')
            fixed_lines = []
            code_block_depth = 0
            list_depth = 0
            current_paren = 0
            current_bracket = 0
            current_brace = 0
            bold_depth = 0
            italic_depth = 0
            
            for i, line in enumerate(lines):
                current_line = line
                
                # 检查并处理代码块
                triple_backtick_count = line.count('```')
                code_block_depth += triple_backtick_count
                
                # 如果当前在代码块中
                if code_block_depth % 2 != 0:
                    fixed_lines.append(current_line)
                    continue
                
                # 普通行处理
                fixed_line = current_line
                
                # 检查并修复列表格式
                stripped = fixed_line.strip()
                if stripped.startswith(('- ', '* ', '+ ')):
                    list_depth += 1
                elif stripped and not stripped.startswith('#'):
                    if list_depth > 0 and not fixed_line.startswith(' '):
                        list_depth = 0
                
                # 检查括号平衡
                current_paren += fixed_line.count('(') - fixed_line.count(')')
                current_bracket += fixed_line.count('[') - fixed_line.count(']')
                current_brace += fixed_line.count('{') - fixed_line.count('}')
                
                # 检查粗体标记
                bold_depth += fixed_line.count('**')
                
                # 检查斜体标记
                single_star = fixed_line.count('*') - fixed_line.count('**')
                italic_depth += single_star
                
                # 最后一行：修复所有未闭合的标记
                if i == len(lines) - 1:
                    # 修复未闭合的括号
                    if current_paren > 0:
                        fixed_line += ')' * current_paren
                    if current_bracket > 0:
                        fixed_line += ']' * current_bracket
                    if current_brace > 0:
                        fixed_line += '}' * current_brace
                    
                    # 修复未闭合的粗体
                    if bold_depth % 2 != 0:
                        fixed_line += '**'
                    
                    # 修复未闭合的斜体
                    if italic_depth % 2 != 0:
                        fixed_line += '*'
                
                fixed_lines.append(fixed_line)
            
            # 处理未闭合的代码块
            if code_block_depth % 2 != 0:
                fixed_lines.append('```')
            
            result = '\n'.join(fixed_lines)
            
            # 步骤4: 最终验证和清理
            
            # 验证代码块成对
            code_blocks = result.count('```')
            if code_blocks % 2 != 0:
                result += '\n```'
            
            # 修复连续空行
            while '\n\n\n' in result:
                result = result.replace('\n\n\n', '\n\n')
            
            # 修复行首尾空格
            result = '\n'.join(line.strip() for line in result.split('\n'))
            
            # 修复JSON安全问题
            result = result.replace('\r', '\\r').replace('\t', '\\t')
            
            # 步骤5: 确保消息不以特殊字符开头/结尾
            result = result.strip()
            
            # 如果结果是空的，返回原始内容
            if not result.strip():
                return content
                
        except Exception as e:
            # 如果修复过程中出现异常，返回原始内容
            print(f"格式修复异常: {e}")
            return content
        
        return result
    
    def _format_json_in_text(self, text: str) -> str:
        """在文本中查找JSON片段并转换为友好的表格/列表格式"""
        try:
            # 首先尝试整个文本是否为JSON
            try:
                parsed_json = json.loads(text)
                # 成功解析为JSON，转换为友好格式
                return self._json_to_friendly_format(parsed_json)
            except (json.JSONDecodeError, TypeError):
                pass
            
            # 如果整个文本不是JSON，尝试查找其中的JSON块
            def find_json_blocks(s):
                """查找字符串中的JSON块"""
                blocks = []
                i = 0
                n = len(s)
                
                while i < n:
                    # 查找可能的JSON开始位置
                    if s[i] in '{[':
                        start = i
                        stack = 1
                        j = i + 1
                        
                        while j < n and stack > 0:
                            if s[j] in '{[':
                                stack += 1
                            elif s[j] in '}]':
                                stack -= 1
                            j += 1
                        
                        if stack == 0:
                            blocks.append((start, j))
                            i = j
                        else:
                            i += 1
                    else:
                        i += 1
                
                return blocks
            
            # 找到所有JSON块
            json_blocks = find_json_blocks(text)
            
            if not json_blocks:
                return text
            
            # 从后向前处理，避免位置偏移问题
            result = list(text)
            for start, end in reversed(json_blocks):
                json_str = ''.join(result[start:end])
                try:
                    parsed = json.loads(json_str)
                    formatted = self._json_to_friendly_format(parsed)
                    result[start:end] = list(formatted)
                except:
                    # 格式化失败，保留原样
                    pass
            
            return ''.join(result)
        except:
            # 任何异常都返回原文
            return text
    
    def _json_to_friendly_format(self, data) -> str:
        """将JSON数据转换为友好的可读格式"""
        if isinstance(data, dict):
            return self._dict_to_friendly_format(data)
        elif isinstance(data, list):
            return self._list_to_friendly_format(data)
        else:
            # 其他类型，返回格式化的JSON
            return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _dict_to_friendly_format(self, data: dict) -> str:
        """将字典转换为易读的键值对表格格式"""
        if not data:
            return "【空字典】"
        
        lines = []
        
        # 检查是否是工具结果结构（包含 success, data, message, error）
        if 'success' in data or 'data' in data:
            return self._format_as_tool_result(data)
        
        # 检查是否是任务列表等常见结构
        keys = list(data.keys())
        
        # 检查是否有常见的任务字段
        task_like_fields = ['id', 'title', 'status', 'description', 'priority', 'due_date', 
                           'start_time', 'end_time', 'created_at', 'updated_at', 'tasks', 'total']
        has_task_like = any(k.lower() in [f.lower() for f in task_like_fields] for k in keys)
        
        if has_task_like:
            # 任务格式
            return self._format_as_task_list(data)
        
        lines.append("📋 数据表格:")
        lines.append("─" * 60)
        
        # 普通字典格式
        for key, value in data.items():
            key_display = self._beautify_key(key)
            value_display = self._beautify_value(value)
            lines.append(f"  {key_display}: {value_display}")
        
        lines.append("─" * 60)
        return '\n'.join(lines)
    
    def _format_as_tool_result(self, data: dict) -> str:
        """格式化工具结果结构"""
        lines = []
        
        # 先显示成功状态和消息
        if 'success' in data:
            success = data['success']
            icon = "✅" if success else "❌"
            lines.append(f"{icon} 操作结果")
        
        if 'message' in data and data['message']:
            # 如果有现成的友好消息，直接显示
            lines.append(data['message'])
        
        if 'error' in data and data['error']:
            lines.append(f"❌ 错误: {data['error']}")
        
        # 然后处理 data 字段
        if 'data' in data and data['data']:
            sub_data = data['data']
            if isinstance(sub_data, dict):
                # 检查是否有 tasks 字段（任务列表结构）
                if 'tasks' in sub_data and isinstance(sub_data['tasks'], list):
                    lines.append("\n📊 详细数据:")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    # 处理任务列表
                    task_list = sub_data['tasks']
                    if task_list:
                        for i, task in enumerate(task_list, 1):
                            task_line = f"  {i}. "
                            # 添加状态图标
                            if isinstance(task, dict):
                                status = task.get('status', '')
                                title = task.get('title', str(task))
                                icon = "✅" if status == "done" else "🔄" if status == "in_progress" else "⭕"
                                task_line += f"{icon} {title}"
                                if status:
                                    task_line += f" ({status})"
                            else:
                                task_line += str(task)
                            lines.append(task_line)
                    
                    if 'total' in sub_data:
                        lines.append(f"\n📈 总计: {sub_data['total']} 项")
                    
                    if 'filtered_by_status' in sub_data and sub_data['filtered_by_status']:
                        lines.append("🔍 已按状态筛选")
                else:
                    # 普通数据字典
                    lines.append("\n📊 详细数据:")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    for key, value in sub_data.items():
                        key_display = self._beautify_key(key)
                        value_display = self._beautify_value(value)
                        lines.append(f"  {key_display}: {value_display}")
            elif isinstance(sub_data, list):
                # 数据列表
                lines.append("\n📊 详细数据:")
                lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                for i, item in enumerate(sub_data, 1):
                    lines.append(f"  {i}. {self._beautify_value(item)}")
                lines.append(f"\n📈 总计: {len(sub_data)} 项")
            else:
                # 其他数据
                lines.append(f"\n📊 详细数据: {self._beautify_value(sub_data)}")
        
        if 'truncated' in data and data['truncated']:
            lines.append(f"\n⚠️ 结果已截断 (原始 {data.get('original_length', '')} 字符)")
        
        return '\n'.join(lines)
    
    def _list_to_friendly_format(self, data: list) -> str:
        """将列表转换为易读的表格格式"""
        if not data:
            return "【空列表】"
        
        # 检查是否是字典列表（表格形式）
        if all(isinstance(item, dict) for item in data):
            return self._list_of_dicts_to_table(data)
        
        # 普通列表
        lines = []
        lines.append("📋 列表数据:")
        lines.append("─" * 60)
        
        for i, item in enumerate(data, 1):
            value_display = self._beautify_value(item)
            lines.append(f"  {i}. {value_display}")
        
        lines.append("─" * 60)
        return '\n'.join(lines)
    
    def _list_of_dicts_to_table(self, data: list) -> str:
        """将字典列表转换为表格格式"""
        if not data:
            return "【空表格】"
        
        # 获取所有列
        all_keys = set()
        for item in data:
            all_keys.update(item.keys())
        columns = sorted(all_keys)
        
        lines = []
        lines.append("📊 表格数据:")
        lines.append("─" * 80)
        
        # 表头
        header = " | ".join(self._beautify_key(col)[:15] for col in columns)
        lines.append(f"  {header}")
        lines.append("─" * 80)
        
        # 数据行
        for i, item in enumerate(data, 1):
            row_values = []
            for col in columns:
                value = item.get(col, "-")
                value_display = self._beautify_value(value, max_length=20)
                row_values.append(value_display)
            
            row = " | ".join(row_values)
            lines.append(f"  {row}")
            
            if i < len(data):
                lines.append("  " + "-" * 78)
        
        lines.append("─" * 80)
        lines.append(f"共 {len(data)} 条记录")
        return '\n'.join(lines)
    
    def _format_as_task_list(self, data: dict) -> str:
        """将数据格式化为任务列表"""
        lines = []
        lines.append("📝 任务详情:")
        lines.append("─" * 60)
        
        # 优先显示重要字段
        priority_fields = ['title', 'name', 'status', 'priority', 'id', 
                          'description', 'content', 'due_date', 'start_time']
        
        # 先显示优先级字段
        for key in priority_fields:
            if key in data:
                key_display = self._beautify_key(key)
                value_display = self._beautify_value(data[key])
                lines.append(f"  {key_display}: {value_display}")
        
        # 再显示其他字段
        for key in sorted(data.keys()):
            if key not in priority_fields:
                key_display = self._beautify_key(key)
                value_display = self._beautify_value(data[key])
                lines.append(f"  {key_display}: {value_display}")
        
        lines.append("─" * 60)
        return '\n'.join(lines)
    
    def _beautify_key(self, key: str) -> str:
        """美化键名显示"""
        key_map = {
            'id': '编号',
            'title': '标题',
            'name': '名称',
            'status': '状态',
            'description': '描述',
            'content': '内容',
            'priority': '优先级',
            'due_date': '截止日期',
            'start_time': '开始时间',
            'end_time': '结束时间',
            'created_at': '创建时间',
            'updated_at': '更新时间',
            'created': '创建时间',
            'updated': '更新时间',
            'date': '日期',
            'time': '时间',
            'type': '类型',
            'category': '分类',
            'tags': '标签',
            'notes': '备注',
            'lesson_number': '课时编号',
            'lesson_title': '课时标题',
            'tasks': '任务',
            'total': '总计',
            'filtered_by_status': '筛选状态'
        }
        
        # 先尝试翻译
        if key.lower() in key_map:
            return f"【{key_map[key.lower()]}】"
        
        # 驼峰转空格
        result = []
        for i, char in enumerate(key):
            if char.isupper() and i > 0 and key[i-1].islower():
                result.append(' ')
            elif char == '_':
                result.append(' ')
            else:
                result.append(char)
        
        beautified = ''.join(result).title()
        return f"【{beautified}】"
    
    def _beautify_value(self, value, max_length: int = None) -> str:
        """美化值显示"""
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "✅ 是" if value else "❌ 否"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            if len(value) == 0:
                return "-"
            elif len(value) <= 3:
                return ", ".join(str(v) for v in value)
            else:
                return f"{len(value)} 项 (前3项: {', '.join(str(v) for v in value[:3])}...)"
        if isinstance(value, dict):
            if len(value) == 0:
                return "-"
            else:
                # 检查是否是简单字典可以内联显示
                simple_keys = ['title', 'name', 'status']
                if len(value) <= 3 and any(k in value for k in simple_keys):
                    # 尝试内联显示
                    parts = []
                    if 'status' in value:
                        status = value['status']
                        icon = "✅" if status == "done" else "🔄" if status == "in_progress" else "⭕"
                        parts.append(f"{icon}")
                    if 'title' in value:
                        parts.append(str(value['title']))
                    elif 'name' in value:
                        parts.append(str(value['name']))
                    return ' '.join(parts) if parts else f"对象 (含 {len(value)} 个字段)"
                else:
                    return f"对象 (含 {len(value)} 个字段)"
        
        # 字符串处理
        s = str(value).strip()
        if not s:
            return "-"
        
        if max_length and len(s) > max_length:
            s = s[:max_length-3] + "..."
        
        return s
    
    def _sanitize_for_transmission(self, content: str) -> str:
        """为传输准备安全的内容 - 在发送前最后一道检查"""
        if not content:
            return content
        
        result = content
        
        # 移除BOM
        if result.startswith('\ufeff'):
            result = result[1:]
        
        # 移除可能导致问题的Unicode字符
        result = result.replace('\u200b', '')  # 零宽空格
        result = result.replace('\u200c', '')  # 零宽非连接符
        result = result.replace('\u200d', '')  # 零宽连接符
        result = result.replace('\ufeff', '')  # BOM
        
        # 确保没有截断的Unicode
        result = result.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        
        return result
    
    def _get_contextualized_system_prompt(self):
        """获取带语境信息的系统提示 - 精简版"""
        base_prompt = """你是 WS2 Agent，一个强大的 AI 学习助手，完全集成于 WS2 教学管理系统。

你的特点：
1. 能感知用户当前在系统中的操作环境
2. 能调用 WS2 系统的各种工具
3. 能帮助用户管理学习、查找资源、创建笔记

**环境常识参数**：
- 创建笔记时默认使用 R Markdown (.rmd) 格式
- 笔记默认添加 YAML 头信息
- 优先使用系统内建的 write_note 工具来创建和编辑笔记
- 尽量使用系统内建方法来管理课程、笔记和项目
- **搜索优先原则**：查找文件或代码时，优先使用 `search_files` 或 `grep` 工具进行搜索定位，而不是先用 `list_directory` 列出所有文件后再逐个查看

**服务端工具（桌面/移动端 Web 界面控制）**：
- `ensure_server`: 检测并启动 TS2 服务端（端口 6906），返回运行状态和 PID
- `open_in_editor`: 在 Web 编辑器中打开指定文件，用户可直接编辑
- `list_server_files`: 列出服务端工作目录中的文件和文件夹
- `read_server_file`: 读取服务端任意文件内容（不受 EXPOSED_DIRS 限制）
- `write_server_file`: 写入或创建服务端任意文件（不受 EXPOSED_DIRS 限制）
- `switch_panel`: 切换 Web 前端显示的面板（可选值: files/tasks/bookmarks/projects/source/courses/execution/agent/stats）
- `navigate_source`: 在源码浏览器中导航到指定目录

使用场景提示：
- 当你需要打开文件让用户查看/编辑时，优先使用 `open_in_editor`
- 当你需要切换用户界面到某个面板时，使用 `switch_panel`
- 当你发现服务端未运行时，自动调用 `ensure_server` 启动

请尽可能使用中文回复。
"""
        
        context_lines = []
        
        # 工作环境（安全格式化）
        if self.current_context.get("working_directory"):
            safe_dir = self._safe_text(self.current_context['working_directory'], 80)
            context_lines.append(f"- 工作目录: `{safe_dir}`")
        
        # 标签页信息（安全格式化）
        if self.current_context.get("current_tab"):
            safe_tab = self._safe_text(self.current_context['current_tab'], 50)
            context_lines.append(f"- 当前标签页: {safe_tab}")
        
        # 课程信息（安全格式化）
        if self.current_context.get("current_course"):
            safe_course = self._safe_text(self.current_context['current_course'], 80)
            context_lines.append(f"- 查看课程: {safe_course}")
        
        # 选中项目（安全格式化）
        if self.current_context.get("selected_items"):
            selected = self.current_context["selected_items"]
            if selected:
                safe_selected = self._safe_text(selected, 100)
                context_lines.append(f"- 已选中: {safe_selected}")
        
        # 执行模式
        if self.current_context.get("exec_mode_active"):
            context_lines.append("- 执行模式: 活动中")
        
        # 文件上传（安全格式化）
        if self.current_context.get("last_uploaded_file"):
            file_info = self.current_context["last_uploaded_file"]
            safe_name = self._safe_text(file_info.get('name', ''), 60)
            context_lines.append(f"- 最近上传: {safe_name}")
            # 文件内容：代码块内相对安全，但仍需清理
            if file_info.get("content"):
                content = file_info['content']
                if len(content) <= 500:
                    safe_content = content.replace('```', '\\`\\`\\`')[:500]
                    context_lines.append(f"  内容:\n```\n{safe_content}\n```")
        
        if context_lines:
            base_prompt += "\n\n**当前环境**:\n" + "\n".join(context_lines)
        
        # 事件日志只保留最近5条，且更精简（健壮版本）
        if self._event_logger:
            try:
                events = self._event_logger.get_recent_events(count=5)
                if events:
                    lines = ["**最近操作**（5条）:"]
                    for e in events:
                        # 安全格式化摘要，避免破坏提示词结构
                        summary = self._safe_format_event(e)
                        if summary:
                            lines.append(f"- {summary}")
                    if len(lines) > 1:  # 如果有有效的事件
                        base_prompt += "\n\n" + "\n".join(lines)
            except Exception as e:
                pass  # 日志格式化失败不影响主流程
        
        base_prompt += "\n\n请根据用户的问题和当前环境提供帮助。"
        
        return base_prompt
    
    def _build_contextual_input(self, user_input: str) -> str:
        """构建包含语境的用户输入 - 增强版"""
        context_info = self._get_contextualized_system_prompt()
        return f"当前环境信息:\n{context_info}\n\n用户问题: {user_input}"
    
    def _start_infra_update_timer(self):
        """启动定时更新基础设施状态的定时器（降低频率）"""
        if hasattr(self, '_infra_timer_id') and self._infra_timer_id:
            self.window.after_cancel(self._infra_timer_id)
        
        def update():
            self._update_infra_status()
            self._infra_timer_id = self.window.after(10000, update)
        
        self._infra_timer_id = self.window.after(10000, update)
    
    def _update_infra_status(self):
        """更新基础设施状态面板 - 增强健壮性"""
        if not hasattr(self, '_model_label'):
            return
        
        try:
            # 基础信息 - 安全获取
            model_id = "未知"
            ctx = 0
            can_reason = False
            
            if self.agent:
                try:
                    config = getattr(self.agent, 'config', None)
                    if config:
                        model_id = getattr(config, 'model_id', 'generic') or 'generic'
                    ctx = getattr(self.agent, 'model_context_window', 8192)
                    can_reason = getattr(self.agent, 'model_can_reason', False)
                except Exception:
                    pass
            
            self._model_label.config(text=f"模型: {model_id}")
            self._context_label.config(text=f"上下文: {ctx // 1000}K")
            thinking_status = ""
            try:
                if self.agent and hasattr(self.agent, 'llm'):
                    llm_obj = self.agent.llm
                    if hasattr(llm_obj, 'manager'):
                        provider = llm_obj.manager.get_provider()
                        if provider and hasattr(provider, 'config'):
                            cfg = provider.config
                            if getattr(cfg, 'thinking_enabled', None):
                                thinking_status = " 🧠"
            except Exception:
                pass
            self._reason_label.config(text=f"推理: {'✅ 支持' if can_reason else '❌ 不支持'}{thinking_status}")
            
            # 缓存状态 - 安全获取
            cache_status = "未加载"
            if HAS_CACHE:
                try:
                    from .cache import get_model_cache
                    mc = get_model_cache()
                    if mc:
                        cache_size = len(getattr(mc, '_cache', {}))
                        cache_status = f"正常 ({cache_size}项)"
                    else:
                        cache_status = "正常"
                except Exception:
                    cache_status = "异常"
            
            self._cache_label.config(text=f"缓存: {cache_status}")
            
            # 会话状态
            self._session_label.config(text=f"会话: {'活跃' if self.is_processing else '就绪'}")
            
            # 历史对话状态 - 安全获取
            if hasattr(self, 'conversation_history'):
                try:
                    convs = self.conversation_history.list_conversations()
                    self._history_label.config(text=f"历史: {len(convs)} 条")
                except Exception:
                    self._history_label.config(text="历史: --")
            
            # RAG 状态 - 安全获取
            rag_status = "未加载"
            if HAS_RAG and self._rag_manager:
                try:
                    stats = self._rag_manager.get_stats()
                    doc_count = stats.get('document_count', 0)
                    auto_trigger = stats.get('auto_trigger', False)
                    rag_status = f"{'✅' if auto_trigger else '❌'} {doc_count} 文档"
                except Exception:
                    rag_status = "异常"
            if hasattr(self, '_rag_label'):
                self._rag_label.config(text=f"RAG: {rag_status}")
            
            # 性能指标 - 安全获取
            if hasattr(self, '_perf_label') and hasattr(self, '_performance_metrics'):
                try:
                    metrics = self._performance_metrics.get_current_metrics()
                    if metrics.get('total_requests', 0) > 0:
                        avg_time = metrics.get('avg_response_time_ms', 0)
                        tps = metrics.get('tokens_per_second', 0)
                        self._perf_label.config(text=f"⚡ 性能: {avg_time:.0f}ms | {tps:.1f} token/s")
                    else:
                        self._perf_label.config(text="⚡ 性能: --")
                except Exception:
                    self._perf_label.config(text="⚡ 性能: --")
            
        except Exception as e:
            print(f"更新基础设施状态失败: {e}")
    
    def _append_message_to_chat(self, content: str, bg_tag: str, icon: str = "", return_positions: bool = False):
        """将消息添加到可选中的聊天区域 - 增强版：支持 Markdown 和代码渲染"""
        # 安全检查
        content = self._sanitize_for_transmission(content)
        # 优化公式显示
        content = optimize_math_display(content)
        
        self.chat_text.config(state=tk.NORMAL)
        
        # 记录插入前的位置
        start_pos = self.chat_text.index(tk.END)
        
        # 添加时间戳
        now = datetime.now().strftime("%H:%M:%S")
        self.chat_text.insert(tk.END, f"[{now}] ", "time")
        
        # 添加图标
        if icon:
            self.chat_text.insert(tk.END, icon + " ", ("icon", bg_tag))
        
        # 增强渲染：如果启用了渲染器，尝试渲染 Markdown
        if self._renderer:
            self._render_content_with_markdown(content, bg_tag)
        else:
            # 回退到普通渲染
            self.chat_text.insert(tk.END, content + "\n\n", bg_tag)
        
        # 记录结束位置（在添加空行之后）
        end_pos = self.chat_text.index(tk.END)
        
        # 配置标签背景 - 应用到整个消息块
        self.chat_text.tag_add(bg_tag, start_pos, end_pos)
        
        self.chat_text.config(state=tk.DISABLED)
        self._scroll_to_bottom()

        # === 添加到导航侧边栏 ===
        self._add_nav_block(bg_tag, content)

        if return_positions:
            return start_pos, end_pos
        return start_pos  # 返回起始位置，便于后续更新

    def _render_content_with_markdown(self, content: str, bg_tag: str):
        """使用增强渲染器渲染 Markdown 内容"""
        # 先提取并渲染代码块
        code_block_pattern = r'```(\w*)\n([\s\S]*?)```'
        code_blocks = list(re.finditer(code_block_pattern, content))
        
        if not code_blocks:
            # 没有代码块，直接渲染 Markdown
            self._insert_markdown_text(content, bg_tag)
            self.chat_text.insert(tk.END, "\n\n")
            return
        
        # 有代码块，分段处理
        last_end = 0
        for match in code_blocks:
            # 渲染代码块之前的 Markdown
            if match.start() > last_end:
                self._insert_markdown_text(content[last_end:match.start()], bg_tag)
            
            # 渲染代码块
            lang = match.group(1) or "text"
            code = match.group(2)
            if self._renderer:
                self._renderer.render_code(code, lang)
                self.chat_text.insert(tk.END, "\n")
            
            last_end = match.end()
        
        # 渲染最后一个代码块之后的内容
        if last_end < len(content):
            self._insert_markdown_text(content[last_end:], bg_tag)
        
        self.chat_text.insert(tk.END, "\n\n")

    def _insert_markdown_text(self, text: str, bg_tag: str):
        """插入带有 Markdown 格式的文本"""
        lines = text.split("\n")
        for line in lines:
            line = line.rstrip()
            if not line:
                self.chat_text.insert(tk.END, "\n")
                continue
            
            # 处理内联元素：粗体、斜体、代码、链接、数学公式
            self._insert_line_with_inline_md(line, bg_tag)
            self.chat_text.insert(tk.END, "\n")

    def _insert_line_with_inline_md(self, line: str, bg_tag: str):
        """处理单行中的内联 Markdown 元素"""
        # 分割模式：代码 > 数学公式 > 粗体/斜体 > 链接
        patterns = [
            (r'`([^`]+)`', 'code'),           # 内联代码
            (r'\*\*(.+?)\*\*', 'bold'),       # 粗体
            (r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', 'italic'),  # 斜体（避免匹配粗体）
            (r'\[([^\]]+)\]\(([^)]+)\)', 'link'),  # 链接
        ]
        
        remaining = line
        while remaining:
            # 查找最近的匹配
            earliest_match = None
            earliest_start = len(remaining)
            earliest_pattern = None
            earliest_type = None
            
            for pattern, tag_name in patterns:
                match = re.search(pattern, remaining)
                if match and match.start() < earliest_start:
                    earliest_match = match
                    earliest_start = match.start()
                    earliest_pattern = pattern
                    earliest_type = tag_name
            
            if earliest_match:
                # 插入匹配前的普通文本
                if earliest_start > 0:
                    self.chat_text.insert(tk.END, remaining[:earliest_start], bg_tag)
                
                # 插入匹配的元素
                groups = earliest_match.groups()
                if earliest_type == 'code':
                    self.chat_text.insert(tk.END, groups[0], ("code", bg_tag))
                elif earliest_type == 'bold':
                    self.chat_text.insert(tk.END, groups[0], ("bold", bg_tag))
                elif earliest_type == 'italic':
                    self.chat_text.insert(tk.END, groups[0], ("italic", bg_tag))
                elif earliest_type == 'link':
                    label = groups[0]
                    url = groups[1]
                    self.chat_text.insert(tk.END, label, ("md_link",))
                
                remaining = remaining[earliest_match.end():]
            else:
                # 没有更多匹配，插入剩余文本
                self.chat_text.insert(tk.END, remaining, bg_tag)
                break
    
    def _append_tool_message(self, tool_name: str, tool_args: Dict = None, tool_result: str = None, is_thinking: bool = False, return_positions: bool = False):
        """添加工具调用消息 - 统一格式显示 - 优化版：避免渲染过多参数"""
        content_lines = []
        
        if is_thinking:
            content_lines.append(f"**计划调用**: {tool_name}")
        else:
            content_lines.append(f"**执行工具**: {tool_name}")
        
        if tool_args:
            content_lines.append("")
            content_lines.append("**参数**:")
            # 优化：只显示部分关键参数，或截断大参数
            args_display = self._truncate_large_args(tool_args)
            content_lines.append(args_display)
        
        if tool_result:
            content_lines.append("")
            content_lines.append("**结果**:")
            # 先尝试转换为友好格式，然后再截断
            try:
                parsed_json = json.loads(tool_result)
                friendly_result = self._json_to_friendly_format(parsed_json)
                if friendly_result:
                    # 使用友好格式的截断版本
                    if len(friendly_result) > 3000:
                        friendly_result = friendly_result[:2950] + "\n\n... [结果已截断]"
                    content_lines.append(friendly_result)
                else:
                    # 友好格式为空，使用原方法
                    truncated_result = self._truncate_tool_result(tool_result)
                    content_lines.append(truncated_result)
            except (json.JSONDecodeError, TypeError):
                # 不是JSON，使用原方法
                truncated_result = self._truncate_tool_result(tool_result)
                content_lines.append(truncated_result)
        
        content = "\n".join(content_lines)
        
        icon = "💡" if is_thinking else "🔧"
        
        if return_positions:
            return self._append_message_to_chat(content, "tool_bg", icon, return_positions=True)
        else:
            return self._append_message_to_chat(content, "tool_bg", icon)
    
    def _truncate_large_args(self, tool_args: Any) -> str:
        """截断大参数，避免渲染性能问题 - 总限制约3000字符 - 支持字符串类型兼容"""
        if not tool_args:
            return "{}"
        
        # 兼容旧数据：如果是字符串，尝试解析为字典，否则直接截断字符串
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except:
                # 解析失败，直接返回截断后的字符串
                if len(tool_args) > 3000:
                    return tool_args[:3000] + f"\n... [截断了 {len(tool_args)-3000} 字符]"
                return tool_args
        
        # 如果还是不是字典，转换为字符串
        if not isinstance(tool_args, dict):
            tool_args_str = str(tool_args)
            if len(tool_args_str) > 3000:
                return tool_args_str[:3000] + f"\n... [截断了 {len(tool_args_str)-3000} 字符]"
            return tool_args_str
        
        truncated_args = {}
        for key, value in tool_args.items():
            if isinstance(value, str):
                # 单个字符串值限制500字符
                if len(value) > 500:
                    truncated_args[key] = value[:500] + "... [已截断]"
                else:
                    truncated_args[key] = value
            elif isinstance(value, list):
                # 列表只显示前5项或简化信息
                if len(value) > 5:
                    truncated_args[key] = f"[列表, 共 {len(value)} 项] (前5项: {str(value[:5])[:200]}...)"
                else:
                    truncated_args[key] = value
            elif isinstance(value, dict):
                # 字典只显示前5个键或简化信息
                if len(value) > 5:
                    truncated_args[key] = f"{{字典, 共 {len(value)} 个键}} (部分键: {str(list(value.keys())[:5])[:100]}...)"
                else:
                    truncated_args[key] = value
            else:
                truncated_args[key] = value
        
        # 先获取初步的JSON字符串
        args_json = json.dumps(truncated_args, ensure_ascii=False, indent=2)
        
        # 如果总长度超过3000字符，进一步截断
        if len(args_json) > 3000:
            # 先获取简短版本
            summary_args = {}
            for key in list(truncated_args.keys())[:10]:  # 最多保留前10个键
                value = truncated_args[key]
                # 进一步简化值的显示
                if isinstance(value, str):
                    summary_args[key] = value[:100] + ("..." if len(value) > 100 else "")
                else:
                    summary_args[key] = str(type(value).__name__)
            
            if len(truncated_args) > 10:
                summary_args["_"] = f"[还有 {len(truncated_args) - 10} 个参数已省略]"
            
            args_json = json.dumps(summary_args, ensure_ascii=False, indent=2)
            
            # 确保最终结果不超过3000字符
            if len(args_json) > 3000:
                args_json = args_json[:2950] + "\n\n... [参数显示已截断，总长度限制3000字符]"
        
        return args_json
    
    def _truncate_tool_result(self, tool_result: Any) -> str:
        """专门用于截断工具返回结果，提升渲染性能 - 支持JSON友好格式转换"""
        if not tool_result:
            return ""
        
        # 确保是字符串类型
        if not isinstance(tool_result, str):
            try:
                tool_result = str(tool_result)
            except:
                tool_result = repr(tool_result)
        
        # 首先尝试转换为友好格式
        try:
            parsed_json = json.loads(tool_result)
            friendly_format = self._json_to_friendly_format(parsed_json)
            # 如果转换后的格式长度合适，直接使用
            if len(friendly_format) <= 3000:
                return friendly_format
            # 否则使用友好格式的截断版本
            result_length = len(friendly_format)
            if result_length > 10000:
                start_part = friendly_format[:1500]
                end_part = friendly_format[-1400:]
                truncated = f"{start_part}\n\n... [内容已截断，省略了中间部分]\n\n{end_part}"
            else:
                truncated = friendly_format[:2950] + f"\n\n... [结果已截断]"
            return truncated
        except (json.JSONDecodeError, TypeError):
            # 不是JSON，继续原有流程
            pass
        
        if len(tool_result) <= 3000:
            return tool_result
        
        # 更智能的截断逻辑
        result_length = len(tool_result)
        
        # 对于特别长的内容，显示开头和结尾，中间省略
        if result_length > 10000:
            # 取前1500字符和后1400字符
            start_part = tool_result[:1500]
            end_part = tool_result[-1400:]
            truncated = f"{start_part}\n\n... [内容已截断，省略了中间 {result_length - 2900} 字符]\n\n{end_part}"
        else:
            # 对于中等长度的内容，显示前3000字符
            truncated = tool_result[:2950] + f"\n\n... [结果已截断，原始长度 {result_length} 字符]"
        
        return truncated

    def _append_system_message(self, content: str, is_error: bool = False):
        """添加系统消息"""
        bg_tag = "error_bg" if is_error else "system_bg"
        icon = "❌" if is_error else "📢"
        return self._append_message_to_chat(content, bg_tag, icon)

    def _append_user_message(self, content: str):
        """添加用户消息"""
        fixed_content = self._check_and_fix_format(content)
        return self._append_message_to_chat(fixed_content, "user_bg", "👤")

    def _append_assistant_message(self, content: str, is_thinking: bool = False):
        """添加助手消息 - 返回起始位置用于更新"""
        fixed_content = self._check_and_fix_format(content)
        bg_tag = "thinking_bg" if is_thinking else "assistant_bg"
        icon = "💭" if is_thinking else "🤖"
        return self._append_message_to_chat(fixed_content, bg_tag, icon)
    
    def _update_streaming_message(self, start_pos: str, new_content: str, bg_tag: str, icon: str = ""):
        """更新流式消息 - 优化版：增量更新"""
        # 流式更新时做轻量级检查
        safe_content = new_content
        # 优化公式显示
        safe_content = optimize_math_display(safe_content)
        
        try:
            # 检查是否有明显的格式破坏
            if '```' in safe_content:
                # 简单检查代码块成对，但不要过度修复流式内容
                pass
        except:
            pass
        
        self.chat_text.config(state=tk.NORMAL)
        
        try:
            # 检查当前聊天区域是否已经有内容
            current_content = self.chat_text.get(start_pos, tk.END).strip()
            if current_content:
                # 尝试找到新内容和当前内容的差异，只追加新部分
                if safe_content.startswith(current_content):
                    # 只追加新增的部分
                    delta = safe_content[len(current_content):]
                    if delta:
                        self.chat_text.insert(tk.END, delta, bg_tag)
                else:
                    # 如果无法增量更新，则全量替换
                    self.chat_text.delete(start_pos, tk.END)
                    # 重新添加内容
                    now = datetime.now().strftime("%H:%M:%S")
                    self.chat_text.insert(tk.END, f"[{now}]\n", "time")
                    if icon:
                        self.chat_text.insert(tk.END, icon + " ", "icon")
                    self.chat_text.insert(tk.END, safe_content + "\n\n", bg_tag)
            else:
                # 第一次添加
                now = datetime.now().strftime("%H:%M:%S")
                self.chat_text.insert(tk.END, f"[{now}]\n", "time")
                if icon:
                    self.chat_text.insert(tk.END, icon + " ", "icon")
                self.chat_text.insert(tk.END, safe_content + "\n\n", bg_tag)
            
            # 重新应用标签
            self.chat_text.tag_add(bg_tag, start_pos, tk.END)
        except:
            # 发生错误时回退到全量替换
            self.chat_text.delete(start_pos, tk.END)
            now = datetime.now().strftime("%H:%M:%S")
            self.chat_text.insert(tk.END, f"[{now}]\n", "time")
            if icon:
                self.chat_text.insert(tk.END, icon + " ", "icon")
            self.chat_text.insert(tk.END, safe_content + "\n\n", bg_tag)
            self.chat_text.tag_add(bg_tag, start_pos, tk.END)
        
        self.chat_text.config(state=tk.DISABLED)
        self._scroll_to_bottom()
    
    def _load_or_create_conversation(self):
        conversations = self.conversation_history.list_conversations()
        if conversations:
            self._load_conversation(conversations[0]["id"])
            self._is_first_message = False  # 已有对话不是新对话
        else:
            self._new_conversation()
    
    def _new_conversation(self):
        if self.agent and hasattr(self.agent, 'messages') and self.current_conversation_id:
            self._session_messages[self.current_conversation_id] = self.agent.snapshot_messages()

        if self._session_mgr and self.agent and self.current_conversation_id:
            inst_mgr = self._session_mgr._get_instance_manager()
            if inst_mgr:
                inst_mgr.associate_agent(self.current_conversation_id, self.agent)

        self.current_conversation_id = self.conversation_history.create_conversation("新对话")
        self.current_conversation_title = "新对话"
        self._is_first_message = True
        if hasattr(self, 'conversation_var'):
            self.conversation_var.set(self.current_conversation_title)
        
        # 通过统一管理器注册会话（使用同一个conversation_id）
        if self._session_mgr:
            inst_mgr = self._session_mgr._get_instance_manager()
            if inst_mgr:
                inst_mgr.create_instance(self.current_conversation_id, "新对话")
                inst_mgr.set_active_instance(self.current_conversation_id)
        
        # 清空聊天区域
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete(1.0, tk.END)
        self.chat_text.config(state=tk.DISABLED)

        # 清空导航侧边栏
        self._nav_blocks.clear()
        self._nav_current_idx = -1
        self.nav_listbox.delete(0, tk.END)

        # 创建新的独立 Agent 实例
        self._init_agent()
        
        # 关联新 Agent 到会话
        if self._session_mgr and self.agent:
            inst_mgr = self._session_mgr._get_instance_manager()
            if inst_mgr:
                inst_mgr.associate_agent(self.current_conversation_id, self.agent)
        
        if self._workflow_engine and self.agent:
            self._workflow_engine.set_agent(self.agent, self.system)
        
        self._refresh_history_list()
        self._update_status("🆕 新对话已创建")
        self._update_infra_status()
    
    def _rename_conversation(self):
        """修改对话标题"""
        if not self.current_conversation_id:
            return
        
        dialog = tk.Toplevel(self.window)
        dialog.title("修改标题")
        dialog.geometry("400x150")
        dialog.transient(self.window)
        dialog.configure(bg=self.bg_color)
        
        main_frame = tk.Frame(dialog, bg=self.bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(main_frame, text="输入新标题:", bg=self.bg_color, fg=self.text_color).pack(anchor=tk.W)
        
        title_var = tk.StringVar(value=self.current_conversation_title)
        title_entry = tk.Entry(main_frame, textvariable=title_var, font=("Microsoft YaHei UI", 11))
        title_entry.pack(fill=tk.X, pady=(5, 15))
        title_entry.select_range(0, tk.END)
        title_entry.focus()
        
        def save_title():
            new_title = title_var.get().strip()
            if new_title:
                self.current_conversation_title = new_title
                self.conversation_history.update_conversation_title(
                    self.current_conversation_id, new_title
                )
                if hasattr(self, 'conversation_var'):
                    self.conversation_var.set(new_title)
                self._refresh_history_list()
            dialog.destroy()
        
        btn_frame = tk.Frame(main_frame, bg=self.bg_color)
        btn_frame.pack()
        
        tk.Button(btn_frame, text="保存", command=save_title,
                 bg=self.primary_color, fg="white", font=("Microsoft YaHei UI", 10),
                 width=10, relief=tk.FLAT, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="取消", command=dialog.destroy,
                 bg="#6b7280", fg="white", font=("Microsoft YaHei UI", 10),
                 width=10, relief=tk.FLAT, pady=5).pack(side=tk.LEFT, padx=5)
        
        dialog.bind("<Return>", lambda e: save_title())
    
    def _auto_generate_title(self, user_input: str):
        """根据用户输入自动生成标题"""
        # 取用户输入的前50个字符作为标题
        title = user_input.strip()[:50]
        if len(user_input.strip()) > 50:
            title += "..."
        if not title:
            title = "新对话"
        
        self.current_conversation_title = title
        self.conversation_history.update_conversation_title(
            self.current_conversation_id, title
        )
        if hasattr(self, 'conversation_var'):
            self.conversation_var.set(title)
        self._refresh_history_list()
    
    def _save_conversation(self):
        if self.current_conversation_id:
            self._update_status("💾 对话已保存")
            messagebox.showinfo("保存", "对话已保存")
    
    def _load_conversation_dialog(self):
        conversations = getattr(self, '_cached_conversations', None) or self.conversation_history.list_conversations()
        if not conversations:
            messagebox.showinfo("加载", "没有保存的对话")
            return
        
        dialog = tk.Toplevel(self.window)
        dialog.title("选择对话")
        dialog.geometry("500x550")
        dialog.transient(self.window)
        dialog.configure(bg=self.bg_color)
        
        main_frame = tk.Frame(dialog, bg=self.bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(main_frame, text="📂 选择历史对话",
                font=("Microsoft YaHei UI", 14, "bold"),
                bg=self.bg_color, fg=self.text_color).pack(anchor=tk.W, pady=(0, 15))
        
        listbox_frame = tk.Frame(main_frame, bg=self.card_color)
        listbox_frame.pack(fill=tk.BOTH, expand=True)
        
        listbox = tk.Listbox(listbox_frame, font=("Microsoft YaHei UI", 10),
                            bg="#f7fafc", fg=self.text_color,
                            selectbackground=self.primary_color,
                            selectforeground="white",
                            borderwidth=1, relief=tk.SOLID)
        listbox.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        for conv in conversations:
            display = f"{conv['title']} - {conv['updated_at'][:10]}"
            listbox.insert(tk.END, display)
        
        button_frame = tk.Frame(main_frame, bg=self.bg_color)
        button_frame.pack(pady=15)
        
        def on_select():
            selection = listbox.curselection()
            if selection:
                conv_id = conversations[selection[0]]["id"]
                self._load_conversation(conv_id)
                dialog.destroy()
        
        load_btn = tk.Button(button_frame, text="加载", command=on_select,
                            bg=self.primary_color, fg="white",
                            font=("Microsoft YaHei UI", 11, "bold"),
                            width=12, relief=tk.FLAT, pady=8)
        load_btn.pack()
    
    def _load_conversation(self, conversation_id: str, _skip_agent: bool = False):
        conversation = self.conversation_history.get_conversation(conversation_id)
        if not conversation:
            logger.warning(f"对话不存在: {conversation_id[:8]}")
            return

        logger.info(f"开始加载对话: {conversation.title or '未命名'} ({conversation_id[:8]})")

        if not _skip_agent:
            if self.agent and hasattr(self.agent, 'messages') and self.current_conversation_id:
                self._session_messages[self.current_conversation_id] = self.agent.snapshot_messages()
                logger.debug(f"保存当前对话消息快照: {self.current_conversation_id[:8]} ({len(self._session_messages[self.current_conversation_id])} msgs)")

            if self._session_mgr and self.current_conversation_id and self.agent:
                self._session_mgr.associate_agent(self.current_conversation_id, self.agent)

        self.current_conversation_id = conversation_id
        self.current_conversation_title = conversation.title or "未命名对话"
        self._is_first_message = False
        if hasattr(self, 'conversation_var'):
            self.conversation_var.set(self.current_conversation_title)

        if not _skip_agent:
            if self._session_mgr:
                inst_mgr = self._session_mgr._get_instance_manager()
                if inst_mgr:
                    inst_mgr.set_active_instance(conversation_id)
                    existing_agent = inst_mgr.get_agent(conversation_id)
                    if existing_agent:
                        self.agent = existing_agent
                        logger.info(f"复用已有Agent: {conversation_id[:8]}")
                    else:
                        logger.info(f"创建新Agent实例: {conversation_id[:8]}")
                        self._init_agent()
                        if self.agent:
                            inst_mgr.associate_agent(conversation_id, self.agent)
                            logger.info(f"关联新Agent到会话: {conversation_id[:8]}")
            else:
                if self.agent and hasattr(self.agent, 'messages'):
                    logger.warning("会话管理器不可用，重置Agent消息")
                    self.agent.reset()

            if self.agent and hasattr(self.agent, 'messages'):
                saved = self._session_messages.get(conversation_id)
                if saved:
                    self.agent.restore_messages(saved)
                    logger.info(f"恢复对话消息快照: {conversation_id[:8]} ({len(saved)} msgs)")
                else:
                    self._restore_conversation_to_agent(conversation)

                # 创建初始检查点，确保 ↩️ 按钮可以回退
                if hasattr(self.agent, 'create_checkpoint') and not saved:
                    try:
                        self.agent.create_checkpoint(
                            summary="📂 加载: " + (conversation.title or "历史对话")[:60],
                            snapshot_files=False
                        )
                        logger.info(f"已为加载的对话创建初始检查点")
                    except Exception as e:
                        logger.debug(f"创建初始检查点失败: {e}")

            if self._workflow_engine and self.agent:
                self._workflow_engine.set_agent(self.agent, self.system)

        self._update_status(f"⏳ 正在加载: {conversation.title}...")
        self.window.update_idletasks()

        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete(1.0, tk.END)

        self._nav_blocks.clear()
        self._nav_current_idx = -1
        self.nav_listbox.delete(0, tk.END)

        agent_messages_to_add = []
        nav_items = []

        for msg in conversation.messages:
            role = msg.get("role", "assistant")
            content = msg.get("content", "")

            if role == "tool":
                tool_name = msg.get("tool_name", "tool")
                tool_args = msg.get("tool_args", {})
                tool_result = msg.get("tool_result", "")

                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except:
                        pass

                if tool_result is not None and not isinstance(tool_result, str):
                    try:
                        tool_result = str(tool_result)
                    except:
                        tool_result = repr(tool_result)

                tool_content_lines = [f"**执行工具**: {tool_name}"]
                if tool_args:
                    tool_content_lines.append("")
                    tool_content_lines.append("**参数**:")
                    tool_content_lines.append(self._truncate_large_args(tool_args))
                if tool_result:
                    tool_content_lines.append("")
                    tool_content_lines.append("**结果**:")
                    tool_content_lines.append(self._truncate_tool_result(tool_result))
                tool_content = "\n".join(tool_content_lines)

                start_pos = self.chat_text.index(tk.END)
                now_str = datetime.now().strftime("%H:%M:%S")
                self.chat_text.insert(tk.END, f"[{now_str}] ", "time")
                self.chat_text.insert(tk.END, "🔧 ", ("icon", "tool_bg"))
                self.chat_text.insert(tk.END, tool_content + "\n\n", "tool_bg")
                end_pos = self.chat_text.index(tk.END)
                self.chat_text.tag_add("tool_bg", start_pos, end_pos)
                nav_items.append(("tool_bg", tool_content))

            elif role == "thinking":
                start_pos = self.chat_text.index(tk.END)
                now_str = datetime.now().strftime("%H:%M:%S")
                self.chat_text.insert(tk.END, f"[{now_str}] ", "time")
                self.chat_text.insert(tk.END, "💭 ", ("icon", "thinking_bg"))
                self.chat_text.insert(tk.END, content + "\n\n", "thinking_bg")
                end_pos = self.chat_text.index(tk.END)
                self.chat_text.tag_add("thinking_bg", start_pos, end_pos)
                nav_items.append(("thinking_bg", content))

            elif role == "user":
                fixed_content = self._check_and_fix_format(content)
                start_pos = self.chat_text.index(tk.END)
                now_str = datetime.now().strftime("%H:%M:%S")
                self.chat_text.insert(tk.END, f"[{now_str}] ", "time")
                self.chat_text.insert(tk.END, "👤 ", ("icon", "user_bg"))
                self.chat_text.insert(tk.END, fixed_content + "\n\n", "user_bg")
                end_pos = self.chat_text.index(tk.END)
                self.chat_text.tag_add("user_bg", start_pos, end_pos)
                nav_items.append(("user_bg", fixed_content))
                agent_messages_to_add.append({"role": "user", "content": content})

            elif role == "assistant" and content:
                fixed_content = self._check_and_fix_format(content)
                start_pos = self.chat_text.index(tk.END)
                now_str = datetime.now().strftime("%H:%M:%S")
                self.chat_text.insert(tk.END, f"[{now_str}] ", "time")
                self.chat_text.insert(tk.END, "🤖 ", ("icon", "assistant_bg"))
                self.chat_text.insert(tk.END, fixed_content + "\n\n", "assistant_bg")
                end_pos = self.chat_text.index(tk.END)
                self.chat_text.tag_add("assistant_bg", start_pos, end_pos)
                nav_items.append(("assistant_bg", fixed_content))
                assistant_msg = {"role": "assistant", "content": content}
                reasoning_content = msg.get("reasoning_content", "")
                if reasoning_content:
                    assistant_msg["reasoning_content"] = reasoning_content
                agent_messages_to_add.append(assistant_msg)

            elif role == "system":
                pass

        self.chat_text.config(state=tk.DISABLED)
        self._scroll_to_bottom()

        for bg_tag, nav_content in nav_items:
            self._add_nav_block(bg_tag, nav_content)

        # 注意：agent.messages 已在 _restore_conversation_to_agent 中设置，无需重复添加

        # 确保 Agent 实例关联到会话管理器（如果之前创建了新实例）
        if self._session_mgr and self.agent and self.current_conversation_id:
            inst_mgr = self._session_mgr._get_instance_manager()
            if inst_mgr:
                existing = inst_mgr.get_agent(self.current_conversation_id)
                if not existing:
                    inst_mgr.associate_agent(self.current_conversation_id, self.agent)
                    logger.debug(f"关联新创建的Agent到会话: {self.current_conversation_id[:8]}")

        self._refresh_history_list()
        self._update_status(f"📂 已加载: {conversation.title}")
        self._update_infra_status()
    
    def _delete_conversation(self):
        if not self.current_conversation_id:
            return
        
        if messagebox.askyesno("删除", "确定要删除当前对话吗？"):
            # 通过统一管理器清理会话（取消后台任务）
            if self._session_mgr:
                self._session_mgr.delete_session(self.current_conversation_id)
            
            self.conversation_history.delete_conversation(self.current_conversation_id)
            self._new_conversation()
    
    def _refresh_history_list(self):
        if hasattr(self, 'conversation_combo'):
            self._cached_conversations = self.conversation_history.list_conversations()
            values = []
            match_idx = 0
            for i, conv in enumerate(self._cached_conversations):
                display = f"{conv['title'][:20]} ({conv['updated_at'][5:10]})"
                values.append(display)
                if conv['id'] == self.current_conversation_id:
                    match_idx = i
            self.conversation_combo['values'] = values
            if values:
                self.conversation_combo.current(match_idx)
    
    def _on_conversation_selected(self, event=None):
        if hasattr(self, 'conversation_combo'):
            selection = self.conversation_combo.current()
            conversations = getattr(self, '_cached_conversations', None) or self.conversation_history.list_conversations()
            if 0 <= selection < len(conversations):
                conv_id = conversations[selection]["id"]
                self._switch_to_conversation(conv_id)
    
    def _switch_to_conversation(self, conversation_id: str):
        """切换到指定对话 - 统一通过 Tab 系统管理"""
        if self._tab_mgr:
            for tab_id, tab_state in self._tab_mgr.tabs.items():
                if tab_state.conversation_id == conversation_id:
                    self._switch_to_tab(tab_id)
                    return
            
            self._save_current_tab_state()
            
            conversation = self.conversation_history.get_conversation(conversation_id)
            title = conversation.title if conversation else "对话"
            
            if self._session_mgr:
                inst_mgr = self._session_mgr._get_instance_manager()
                if inst_mgr:
                    inst_mgr.get_or_create_instance(conversation_id, title)
            
            existing_agent = None
            if self._session_mgr:
                existing_agent = self._session_mgr.get_agent(conversation_id)
            
            if existing_agent:
                self.agent = existing_agent
            else:
                self._init_agent()
                if self.agent and self._session_mgr:
                    self._session_mgr.associate_agent(conversation_id, self.agent)
            
            tab_id = self._tab_mgr.create_tab(conversation_id, title, self.agent)
            self._tab_mgr.set_active_tab(tab_id)
            
            self.current_conversation_id = conversation_id
            self.current_conversation_title = title
            if hasattr(self, 'conversation_var'):
                self.conversation_var.set(title)
            
            self._load_conversation(conversation_id)
            
            self._rebuild_tab_buttons()
            self._refresh_history_list()
        else:
            self._load_conversation(conversation_id)
    
    def _create_checkpoint(self):
        """创建会话检查点（增强版 — 可选文件快照）"""
        if not self.agent or not hasattr(self, '_context_reloader'):
            messagebox.showinfo("检查点", "检查点功能不可用")
            return
        
        try:
            # 询问是否包含文件快照
            result = messagebox.askyesnocancel(
                "创建检查点",
                "是否包含工作区文件快照？\n\n"
                "是 = 包含文件快照（可回退代码修改，但较慢）\n"
                "否 = 仅保存对话历史（快速，推荐日常使用）\n"
                "取消 = 取消创建"
            )
            if result is None:
                return  # 取消
            
            snapshot = bool(result)
            checkpoint = self.agent.create_checkpoint("手动保存", snapshot_files=snapshot)
            
            info = f"检查点已创建！\nID: {checkpoint.checkpoint_id}\n时间: {datetime.fromtimestamp(checkpoint.timestamp).strftime('%Y-%m-%d %H:%M:%S')}"
            if snapshot:
                info += f"\n文件快照: {len(checkpoint.file_snapshots)} 个文件"
                if checkpoint.git_commit_hash:
                    info += f"\nGit: {checkpoint.git_commit_hash}"
            
            messagebox.showinfo("检查点", info)
        except Exception as e:
            messagebox.showerror("错误", f"创建检查点失败: {e}")
    
    def _copy_all_messages(self):
        """复制所有对话到剪贴板"""
        if not hasattr(self, 'conversation_history') or not self.current_conversation_id:
            return
        
        try:
            conv = self.conversation_history.get_conversation(self.current_conversation_id)
            if not conv or not conv.messages:
                messagebox.showinfo("提示", "当前没有对话内容")
                return
            
            # 格式化对话内容
            lines = []
            for msg in conv.messages:
                role = msg.get("role", "unknown")
                lines.append(f"【{role.upper()}】")
                content = msg.get("content", "")
                if content:
                    lines.append(content)
                reasoning = msg.get("reasoning_content", "")
                if reasoning:
                    lines.append("💭 思考: " + reasoning)
                tool_name = msg.get("tool_name", "")
                if tool_name:
                    lines.append(f"🔧 调用工具: {tool_name}")
                lines.append("")
            
            all_text = "\n".join(lines)
            self.window.clipboard_clear()
            self.window.clipboard_append(all_text)
            messagebox.showinfo("成功", "已复制全部对话到剪贴板！")
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")
    
    def _show_checkpoint_list(self):
        """显示检查点列表供选择回退 — 合并 context_reloader + CheckpointMiddleware"""
        if not self.agent:
            messagebox.showinfo("检查点", "Agent 未就绪")
            return
        
        try:
            # 收集所有检查点（统一格式）
            checkpoints = []  # [{id, timestamp, summary, msg_count, type}]

            # 来源1: ContextReloader（消息快照）
            if hasattr(self, '_context_reloader') and self._context_reloader:
                for cp_id in self._context_reloader.list_checkpoints():
                    cp = self._context_reloader.restore_checkpoint(cp_id)
                    if cp:
                        checkpoints.append({
                            "id": cp.checkpoint_id,
                            "timestamp": cp.timestamp,
                            "summary": cp.summary or "消息快照",
                            "msg_count": cp.total_messages,
                            "token_count": cp.total_tokens,
                            "type": "reloader",
                        })

            # 来源2: CheckpointMiddleware（文件快照，仅当 middleware 可用）
            if self.agent and hasattr(self.agent, '_middleware_chain') and self.agent._middleware_chain:
                for mw in self.agent._middleware_chain._middlewares:
                    try:
                        from .middleware.shadow_checkpoint import CheckpointMiddleware
                        if isinstance(mw, CheckpointMiddleware) and mw.checkpointer:
                            commits = mw.checkpointer.get_commits(count=50) if mw.checkpointer else []
                            for c in commits:
                                # 使用结构化元数据
                                meta = c.get("meta", {})
                                summary = meta.get("tool", "") or (c.get("message") or "").replace("TS2 checkpoint: ", "") or "文件快照"
                                step = meta.get("step", 0)
                                source = meta.get("source", "auto")
                                if step:
                                    summary = f"#{step} {summary}"
                                if source == "baseline":
                                    summary = "baseline"
                                diff_count = c.get("diff_count", 0)
                                checkpoints.append({
                                    "id": c.get("full_hash") or c["hash"],  # 优先用完整 hash
                                    "timestamp": c["timestamp"],
                                    "summary": summary,
                                    "msg_count": 0,
                                    "token_count": 0,
                                    "type": "middleware",
                                    "diff_count": diff_count,
                                    "meta": meta,
                                })
                            break
                    except ImportError:
                        pass

            # 按时间排序（最新在前）
            checkpoints.sort(key=lambda x: x["timestamp"], reverse=True)

            if not checkpoints:
                if self.agent and hasattr(self.agent, 'create_checkpoint'):
                    create = messagebox.askyesno(
                        "检查点",
                        "当前没有保存的检查点。\n\n"
                        "检查点会在每轮对话后自动保存。\n"
                        "如需立即创建一个，请点击「是」。\n\n"
                        "或者先发送一条消息开始对话。"
                    )
                    if create:
                        try:
                            self.agent.create_checkpoint(summary="手动创建", snapshot_files=False)
                            messagebox.showinfo("检查点", "✅ 检查点已创建，请重新点击 ↩️ 查看")
                        except Exception as e:
                            messagebox.showerror("错误", f"创建失败: {e}")
                else:
                    messagebox.showinfo("检查点", "暂无检查点 — 发送消息后系统会自动创建")
                return

            # 创建选择对话框
            dialog = tk.Toplevel(self.window)
            dialog.title("选择检查点回退")
            dialog.geometry("650x480")
            dialog.transient(self.window)
            dialog.grab_set()
            dialog.configure(bg=self.bg_color)

            # 标题
            title_frame = tk.Frame(dialog, bg=self.primary_color, height=50)
            title_frame.pack(fill=tk.X)
            tk.Label(title_frame, text="选择要回退的检查点",
                    font=("Microsoft YaHei UI", 12, "bold"),
                    bg=self.primary_color, fg="white").pack(pady=10)

            # 列表框
            list_frame = tk.Frame(dialog, bg=self.bg_color)
            list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

            scrollbar = tk.Scrollbar(list_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            listbox = tk.Listbox(list_frame,
                                yscrollcommand=scrollbar.set,
                                font=("Microsoft YaHei UI", 10),
                                bg=self.card_color,
                                fg=self.text_color,
                                selectbackground=self.primary_color,
                                selectforeground="white",
                                relief=tk.FLAT,
                                height=12)
            listbox.pack(fill=tk.BOTH, expand=True)

            scrollbar.config(command=listbox.yview)

            # 填充列表
            cp_map = {}  # 索引到检查点的映射
            for i, cp in enumerate(checkpoints):
                dt_str = datetime.fromtimestamp(cp["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                msg_part = f"消息: {cp['msg_count']}" if cp["msg_count"] else ""
                src_tag = {"reloader": "💬消息", "middleware": "📁文件"}.get(cp["type"], "")
                diff_part = f"{cp.get('diff_count', 0)} files" if cp.get("diff_count") else ""
                parts = [f"[{dt_str}]", src_tag, cp["summary"]]
                if diff_part:
                    parts.append(f"({diff_part})")
                if msg_part:
                    parts.append(f"({msg_part})")
                listbox.insert(tk.END, " ".join(parts))
                cp_map[i] = cp

            # 按钮区域
            btn_frame = tk.Frame(dialog, bg=self.bg_color)
            btn_frame.pack(fill=tk.X, pady=10, padx=15)

            def on_view_diff():
                sel_idx = listbox.curselection()
                if not sel_idx:
                    messagebox.showwarning("提示", "请选择一个检查点")
                    return
                cp = cp_map[sel_idx[0]]
                diff_text = "该检查点无差异信息"
                # 尝试从 middleware 获取 diff（使用 get_diff_set 获取结构化数据）
                if cp["type"] == "middleware" and self.agent and hasattr(self.agent, '_middleware_chain'):
                    try:
                        for mw in self.agent._middleware_chain._middlewares:
                            from .middleware.shadow_checkpoint import CheckpointMiddleware
                            if isinstance(mw, CheckpointMiddleware) and mw.checkpointer:
                                diff_files = mw.checkpointer.get_diff_set(cp["id"])
                                if diff_files:
                                    lines = []
                                    total_adds = 0
                                    total_dels = 0
                                    for f in diff_files:
                                        status = f.get("status", "M")
                                        path = f.get("path", "?")
                                        adds = f.get("additions", 0)
                                        dels = f.get("deletions", 0)
                                        total_adds += adds
                                        total_dels += dels
                                        lines.append(f"{status} {path} (+{adds} -{dels})")
                                        fc = mw.checkpointer.get_diff_content(cp["id"], path, 50)
                                        if fc:
                                            lines.append(fc)
                                    lines.insert(0, f"总计: +{total_adds} -{total_dels} ({len(diff_files)} files)")
                                    diff_text = "\n".join(lines)
                                break
                    except Exception:
                        pass
                elif cp["type"] == "reloader" and hasattr(self, '_context_reloader') and self._context_reloader:
                    try:
                        d = self._context_reloader.get_checkpoint_diff(cp["id"])
                        if d:
                            diff_text = d
                    except Exception:
                        pass
                # 显示差异弹窗
                diff_win = tk.Toplevel(dialog)
                diff_win.title("检查点差异")
                diff_win.geometry("650x400")
                diff_win.transient(dialog)
                diff_win.configure(bg=self.card_color)
                text_w = tk.Text(diff_win, wrap=tk.NONE, font=("Consolas", 10),
                                bg="#1e1e1e", fg="#d4d4d4",
                                padx=10, pady=10)
                text_w.pack(fill=tk.BOTH, expand=True)
                scroll_s = tk.Scrollbar(diff_win, command=text_w.yview)
                scroll_s.pack(side=tk.RIGHT, fill=tk.Y)
                text_w.config(yscrollcommand=scroll_s.set)
                text_w.insert(tk.END, diff_text)
                text_w.config(state=tk.DISABLED)

            def on_rollback():
                sel_idx = listbox.curselection()
                if not sel_idx:
                    messagebox.showwarning("提示", "请选择一个检查点")
                    return

                cp = cp_map[sel_idx[0]]

                type_label = "消息快照" if cp["type"] == "reloader" else "文件快照"
                result = messagebox.askyesno("确认回退",
                    f"确认回退到这个检查点？\n\n"
                    f"📅 时间: {datetime.fromtimestamp(cp['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📋 摘要: {cp['summary']}\n"
                    f"🏷️ 类型: {type_label}\n\n"
                    f"点击「确定」后将弹出「恢复模式」选择框：\n"
                    f"  - 对话+文件: 同时恢复对话和工作区\n"
                    f"  - 仅对话: 只恢复对话，保留文件\n"
                    f"  - 仅文件: 只恢复文件，保留对话\n\n"
                    f"⚠️ 此操作不可撤销！")

                if result:
                    self._rollback_to_checkpoint(cp)
                    dialog.destroy()

            tk.Button(btn_frame, text="✓ 回退",
                     command=on_rollback,
                     bg=self.primary_color,
                     fg="white",
                     font=("Microsoft YaHei UI", 10, "bold"),
                     width=15,
                     relief=tk.FLAT,
                     padx=10,
                     pady=6).pack(side=tk.LEFT, padx=5)

            tk.Button(btn_frame, text="📊 差异",
                     command=on_view_diff,
                     bg="#6366f1",
                     fg="white",
                     font=("Microsoft YaHei UI", 10),
                     width=12,
                     relief=tk.FLAT,
                     padx=10,
                     pady=6).pack(side=tk.LEFT, padx=5)

            tk.Button(btn_frame, text="✕ 取消",
                     command=dialog.destroy,
                     bg="#ef4444",
                     fg="white",
                     font=("Microsoft YaHei UI", 10, "bold"),
                     width=15,
                     relief=tk.FLAT,
                     padx=10,
                     pady=6).pack(side=tk.RIGHT, padx=5)

            tk.Button(btn_frame, text="🗑️ 删除选中",
                     command=lambda: self._delete_selected_checkpoint(cp_map, listbox),
                     bg="#f59e0b",
                     fg="white",
                     font=("Microsoft YaHei UI", 10),
                     width=12,
                     relief=tk.FLAT,
                     padx=10,
                     pady=6).pack(side=tk.RIGHT, padx=5)
        except Exception as e:
            messagebox.showerror("错误", f"加载检查点失败: {e}")
    
    def _delete_selected_checkpoint(self, cp_map, listbox):
        """删除选中的检查点"""
        sel_idx = listbox.curselection()
        if not sel_idx:
            messagebox.showwarning("提示", "请选择一个检查点")
            return

        cp = cp_map[sel_idx[0]]
        result = messagebox.askyesno("确认", "确定要删除这个检查点吗？")

        if result:
            try:
                if cp["type"] == "reloader" and hasattr(self, '_context_reloader') and self._context_reloader:
                    self._context_reloader.delete_checkpoint(cp["id"])
                listbox.delete(sel_idx)
                messagebox.showinfo("成功", "检查点已删除！")
            except Exception as e:
                messagebox.showerror("错误", f"删除失败: {e}")

    def _rollback_to_checkpoint(self, cp: dict):
        """回退到指定检查点 — 统一恢复流程"""
        cp_id = cp["id"]
        cp_type = cp["type"]

        try:
            # 让用户选择恢复模式
            mode_dialog = tk.Toplevel(self.window)
            mode_dialog.title("选择恢复模式")
            mode_dialog.geometry("400x220")
            mode_dialog.resizable(False, False)
            mode_dialog.configure(bg=self.card_color)
            mode_dialog.transient(self.window)
            mode_dialog.grab_set()

            mode_dialog.update_idletasks()
            x = self.window.winfo_x() + (self.window.winfo_width() - 400) // 2
            y = self.window.winfo_y() + (self.window.winfo_height() - 220) // 2
            mode_dialog.geometry(f"400x220+{x}+{y}")

            selected_mode = tk.StringVar(value="taskAndWorkspace")

            tk.Label(mode_dialog, text="选择恢复模式", font=("Segoe UI", 14, "bold"),
                     bg=self.card_color, fg=self.text_color).pack(pady=(16, 12))

            modes = [
                ("taskAndWorkspace", "对话 + 文件", "同时恢复对话历史和工作区文件（推荐）"),
                ("task", "仅对话", "只恢复对话历史，保留当前文件"),
                ("workspace", "仅文件", "只恢复工作区文件，保留当前对话"),
            ]

            for value, label, desc in modes:
                frame = tk.Frame(mode_dialog, bg=self.card_color)
                frame.pack(fill=tk.X, padx=20, pady=2)
                rb = tk.Radiobutton(
                    frame, text=f"{label} — {desc}",
                    variable=selected_mode, value=value,
                    bg=self.card_color, fg=self.text_color,
                    selectcolor=self.card_color,
                    activebackground=self.card_color,
                    font=("Segoe UI", 10),
                )
                rb.pack(anchor=tk.W)

            def do_restore():
                mode_dialog.destroy()
                restore_type = selected_mode.get()

                files_restored = False
                msgs_restored = False

                # 文件恢复：通过 middleware
                if restore_type in ("workspace", "taskAndWorkspace"):
                    try:
                        if cp_type == "middleware" and self.agent and hasattr(self.agent, '_middleware_chain'):
                            for mw in self.agent._middleware_chain._middlewares:
                                from .middleware.shadow_checkpoint import CheckpointMiddleware
                                if isinstance(mw, CheckpointMiddleware) and mw.checkpointer:
                                    files_restored = mw.checkpointer.restore_files(cp_id)
                                    break
                    except Exception as e:
                        logger.warning(f"文件恢复失败: {e}")

                # 对话恢复：通过 agent.restore_checkpoint 或 context_reloader
                if restore_type in ("task", "taskAndWorkspace"):
                    try:
                        if cp_type == "reloader" and self.agent and hasattr(self.agent, 'restore_checkpoint'):
                            msgs_restored = self.agent.restore_checkpoint(cp_id, restore_type="task")
                        elif cp_type == "middleware":
                            # middleware 检查点：只恢复了文件，消息保留当前
                            pass
                    except Exception as e:
                        logger.warning(f"对话恢复失败: {e}")

                if msgs_restored and restore_type in ("task", "taskAndWorkspace"):
                    # 清空当前聊天区域并重新渲染
                    self.chat_text.config(state=tk.NORMAL)
                    self.chat_text.delete(1.0, tk.END)

                    if self.current_conversation_id and hasattr(self, 'conversation_history'):
                        conn = sqlite3.connect(self.conversation_history.db_path)
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM messages WHERE conversation_id = ?",
                                     (self.current_conversation_id,))
                        conn.commit()
                        conn.close()

                    for msg in self.agent.snapshot_messages():
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        reasoning = msg.get("reasoning_content", "")

                        if role == "user":
                            self._append_user_message(content)
                            self._save_message("user", content)
                        elif role == "assistant":
                            if reasoning:
                                self._append_assistant_message(reasoning, is_thinking=True)
                            if content:
                                self._append_assistant_message(content)
                            if reasoning or content:
                                self._save_message("assistant", content, reasoning)
                        elif role == "system":
                            self._append_system_message(content)
                            self._save_message("system", content)

                    self._scroll_to_bottom()

                mode_labels = {
                    "task": "仅对话",
                    "workspace": "仅文件",
                    "taskAndWorkspace": "对话 + 文件",
                }
                self._append_system_message(
                    f"✅ 已恢复检查点（模式: {mode_labels.get(restore_type, restore_type)}）"
                )
                self._update_status("✅ 已恢复检查点")

            tk.Button(mode_dialog, text="✓ 确认恢复",
                     command=do_restore,
                     bg=self.primary_color, fg="white",
                     font=("Segoe UI", 11, "bold"),
                     width=18, relief=tk.FLAT,
                     padx=10, pady=6).pack(side=tk.LEFT, padx=(60, 10), pady=16)

            tk.Button(mode_dialog, text="✕ 取消",
                     command=mode_dialog.destroy,
                     bg="#ef4444", fg="white",
                     font=("Segoe UI", 11, "bold"),
                     width=10, relief=tk.FLAT,
                     padx=10, pady=6).pack(side=tk.LEFT, pady=16)
        except Exception as e:
            messagebox.showerror("错误", f"回退失败: {e}")
    
    def _send_message(self):
        if not hasattr(self, 'input_text'):
            return
        user_input = self.input_text.get(1.0, tk.END).strip()
        if not user_input or self.is_processing:
            return
        
        if not self.agent:
            self._append_system_message("Agent 未初始化", is_error=True)
            return
        
        # 添加到输入历史
        self._add_to_input_history(user_input)
        
        # 如果是第一条消息且标题为默认标题，自动生成标题
        if getattr(self, '_is_first_message', False) and self.current_conversation_title == "新对话":
            self._auto_generate_title(user_input)
            self._is_first_message = False
        
        self.input_text.delete(1.0, tk.END)
        
        # 记录用户输入事件到 event_logger
        if self._event_logger:
            try:
                self._event_logger.log_input(
                    input_type="agent_chat",
                    content=user_input[:200],  # 只记录前200字符避免日志膨胀
                    element="agent_input",
                    context_info=f"conversation: {self.current_conversation_title}"
                )
            except Exception:
                pass
        
        # 增量同步事件日志
        synced_ids = []
        if self._event_logger:
            try:
                unsynced = self._event_logger.get_unsynced_events()
                if unsynced:
                    synced_ids = [e.event_id for e in unsynced]
                    msg = f"📋 同步了 {len(unsynced)} 条操作记录"
                    self._append_system_message(msg)
            except Exception as e:
                print(f"增量同步失败: {e}")
        
        # 发送前检查和修复用户输入格式
        fixed_user_input = self._check_and_fix_format(user_input)
        # 最后一道安全检查
        safe_input = self._sanitize_for_transmission(fixed_user_input)
        self._append_user_message(safe_input)
        self._save_message("user", safe_input)
        
        # ─── 环境感知注入 ─── 在发送前将 UI 上下文注入到 agent 的 ContextProvider Others 层
        self._inject_ui_context_to_agent()
        
        self.is_processing = True
        self.should_stop = False
        self._update_status("⏳ 处理中...")
        
        if self._tab_mgr:
            active_tab = self._tab_mgr.get_active_tab()
            if active_tab:
                self._tab_mgr.set_processing(active_tab.tab_id, True)
                self._tab_mgr.set_should_stop(active_tab.tab_id, False)
                self._tab_mgr.update_agent(active_tab.tab_id, self.agent)
        
        # 更新语境
        self._update_context_from_parent()
        
        thread = threading.Thread(target=self._process_message, args=(user_input, synced_ids))
        thread.daemon = True
        thread.start()
    
    def _process_message(self, user_input: str, synced_ids: Optional[List[str]] = None):
        import time
        self._round_start_time = time.time()
        request_id = str(uuid.uuid4())[:8]
        self._performance_metrics.start_request(request_id, user_input)
        self._performance_metrics.record_stage("start")
        
        current_tab_id = None
        current_conv_id = self.current_conversation_id
        if self._tab_mgr:
            active_tab = self._tab_mgr.get_active_tab()
            if active_tab:
                current_tab_id = active_tab.tab_id
                current_conv_id = active_tab.conversation_id
        
        def _check_tab_stop():
            if current_tab_id and self._tab_mgr:
                return self._tab_mgr.get_should_stop(current_tab_id) or self.should_stop
            return self.should_stop
        
        def _save_msg(role, content=None, **kwargs):
            orig_conv_id = self.current_conversation_id
            try:
                self.current_conversation_id = current_conv_id
                self._save_message(role, content, **kwargs)
            finally:
                self.current_conversation_id = orig_conv_id
        
        try:
            self._current_thinking_content = ""
            self._current_assistant_content = ""
            self._thinking_start_pos = None
            self._assistant_start_pos = None
            self.should_stop = False
            if current_tab_id and self._tab_mgr:
                self._tab_mgr.set_should_stop(current_tab_id, False)
            self._pending_tool_calls = {}
            self._tool_call_msg_saved = False
            
            self._performance_metrics.record_stage("init")
            
            custom_system_prompt = self._get_contextualized_system_prompt()
            self._performance_metrics.record_stage("context")
            
            rag_context = ""
            used_rag = False
            if self._rag_manager:
                try:
                    enhanced_prompt, has_context = self._rag_manager.inject_context(
                        user_input, 
                        system_prompt=custom_system_prompt
                    )
                    if has_context:
                        custom_system_prompt = enhanced_prompt
                        used_rag = True
                        self._performance_metrics.set_rag_used(True)
                        self.window.after(0, lambda: self._append_system_message("📚 从知识库检索到相关内容"))
                except Exception as e:
                    print(f"RAG 检索失败: {e}")
            
            self._performance_metrics.record_stage("rag")
            
            if self.agent and hasattr(self.agent, 'snapshot_messages'):
                msgs = self.agent.snapshot_messages()
                if msgs and msgs[0]["role"] == "system":
                    msgs[0]["content"] = custom_system_prompt
                    self.agent.restore_messages(msgs)
            
            self._performance_metrics.record_stage("agent_ready")
            
            def on_token(token: str):
                if _check_tab_stop():
                    return
                self._performance_metrics.add_token(token)
                token_type = "reasoning" if (token.startswith("💭") or "思考" in token[:10]) else "content"
                def _ui_update(t=token, tt=token_type):
                    if self._tab_mgr and self._tab_mgr.active_tab_id != current_tab_id:
                        return
                    self._on_token_receive(t, tt)
                self.window.after(0, _ui_update)
            
            def on_tool(name: str, args: Dict):
                if _check_tab_stop():
                    return
                self._performance_metrics.add_tool_call(name)
                # 保存带 tool_calls 的 assistant 消息（仅在首条工具调用时触发）
                if self.agent and hasattr(self.agent, 'snapshot_messages'):
                    for msg in reversed(self.agent.snapshot_messages()):
                        if msg.get("role") == "assistant" and msg.get("tool_calls") and not getattr(self, '_tool_call_msg_saved', False):
                            try:
                                import json
                                tc_str = json.dumps(msg["tool_calls"], ensure_ascii=False)
                                self._save_message("assistant", "", tool_calls=tc_str)
                                self._tool_call_msg_saved = True
                            except Exception:
                                pass
                            break
                def _ui_update(n=name, a=args):
                    if self._tab_mgr and self._tab_mgr.active_tab_id != current_tab_id:
                        return
                    self._on_tool_call(n, a)
                self.window.after(0, _ui_update)
            
            def on_tool_result(name: str, result: str):
                if _check_tab_stop():
                    return
                tc_id = None
                if self.agent and hasattr(self.agent, 'snapshot_messages'):
                    for msg in reversed(self.agent.snapshot_messages()):
                        if msg.get("role") == "assistant" and msg.get("tool_calls"):
                            for tc in msg["tool_calls"]:
                                tc_dict = tc if isinstance(tc, dict) else {}
                                tc_func = tc_dict.get("function", {})
                                if tc_func.get("name") == name:
                                    tc_id = tc_dict.get("id")
                                    break
                            if tc_id:
                                break
                def _ui_update(n=name, r=result, tid=tc_id):
                    if self._tab_mgr and self._tab_mgr.active_tab_id != current_tab_id:
                        orig_conv_id = self.current_conversation_id
                        try:
                            self.current_conversation_id = current_conv_id
                            r_safe = self._sanitize_for_transmission(r)
                            r_safe = self._check_and_fix_format(r_safe)
                            self._save_message("tool", tool_name=n, tool_result=r_safe, tool_call_id=tid)
                        finally:
                            self.current_conversation_id = orig_conv_id
                        return
                    self._on_tool_result(n, r, llm_tool_call_id=tc_id)
                self.window.after(0, _ui_update)
            
            self._performance_metrics.record_stage("calling_agent")
            
            safe_user_input = self._sanitize_for_transmission(user_input)

            if self._run_manager:
                try:
                    from .runtime import MultitaskStrategy
                    run_record = self._run_manager.create_or_reject(
                        thread_id=current_conv_id,
                        model_name=getattr(self.agent.config, 'model_id', '') if self.agent else '',
                        multitask_strategy=MultitaskStrategy.INTERRUPT,
                    )
                    self._run_manager.mark_running(run_record.run_id)
                except Exception:
                    run_record = None
            else:
                run_record = None

            response = self.agent.chat(safe_user_input, on_token=on_token, on_tool=on_tool, on_tool_result=on_tool_result, session_id=current_conv_id or "")

            if self._run_manager and run_record:
                try:
                    if response and not _check_tab_stop():
                        self._run_manager.mark_success(run_record.run_id)
                    elif _check_tab_stop():
                        self._run_manager.mark_interrupted(run_record.run_id)
                except Exception:
                    pass

            if self._run_journal and run_record:
                try:
                    self._run_journal.record(
                        run_id=run_record.run_id,
                        event_type=JournalEventType.RUN_END if HAS_RUNTIME else None,
                        status="success" if not _check_tab_stop() else "interrupted",
                        duration_ms=run_record.duration_ms if run_record else 0,
                    )
                except Exception:
                    pass
            
            is_stopped = _check_tab_stop()
            is_active = not self._tab_mgr or self._tab_mgr.active_tab_id == current_tab_id
            
            if is_stopped:
                if is_active:
                    self.window.after(0, lambda: self._update_status("🛑 已停止"))
                content_to_save = ""
                if self._current_thinking_content:
                    fixed_thinking = self._fix_incomplete_output(self._current_thinking_content)
                    content_to_save = f"💭 思考过程：\n{fixed_thinking}\n\n"
                if self._current_assistant_content:
                    fixed_content = self._fix_incomplete_output(self._current_assistant_content)
                    content_to_save += fixed_content
                if content_to_save:
                    safe_partial = self._sanitize_for_transmission(content_to_save)
                    _save_msg("assistant", safe_partial)
                    if is_active:
                        self._append_system_message("🛑 操作已被用户停止，已生成的内容已保存")
                else:
                    if is_active:
                        self._append_system_message("🛑 操作已被用户停止")
            else:
                if is_active:
                    def _complete_on_ui(r=response, ids=synced_ids, conv_id=current_conv_id):
                        orig_conv_id = self.current_conversation_id
                        try:
                            self.current_conversation_id = conv_id
                            self._on_response_complete(r, ids)
                        finally:
                            self.current_conversation_id = orig_conv_id
                    self.window.after(0, _complete_on_ui)
                else:
                    # agent.chat() 返回 str，兼容处理
                    if response:
                        resp_content = response if isinstance(response, str) else getattr(response, 'content', None)
                        if resp_content:
                            _save_msg("assistant", resp_content)
                        resp_reasoning = getattr(response, 'reasoning_content', None) if not isinstance(response, str) else None
                        if resp_reasoning:
                            _save_msg("assistant", resp_reasoning)
                
        except Exception as exc:
            import traceback
            if not _check_tab_stop():
                err_msg = str(exc)
                tb = traceback.format_exc()
                if not self._tab_mgr or self._tab_mgr.active_tab_id == current_tab_id:
                    self.window.after(0, lambda e=err_msg, t=tb: self._on_error(e, t))
        finally:
            if current_tab_id and self._tab_mgr:
                self._tab_mgr.set_processing(current_tab_id, False)
                self._tab_mgr.set_should_stop(current_tab_id, False)
            
            is_current_tab_final = not self._tab_mgr or self._tab_mgr.active_tab_id == current_tab_id
            if is_current_tab_final:
                self.is_processing = False
            
            is_stopped_final = _check_tab_stop() or self.should_stop
            is_active_final = not self._tab_mgr or self._tab_mgr.active_tab_id == current_tab_id
            
            if "response" not in locals() and not is_stopped_final:
                partial_content = ""
                if self._current_thinking_content:
                    partial_content += f"💭 思考过程：\n{self._fix_incomplete_output(self._current_thinking_content)}\n\n"
                if self._current_assistant_content:
                    partial_content += self._fix_incomplete_output(self._current_assistant_content)
                if partial_content:
                    safe_partial = self._sanitize_for_transmission(partial_content)
                    _save_msg("assistant", safe_partial)
                    if is_active_final:
                        self.window.after(0, lambda: self._append_system_message(
                            "⚠️ 异常中断，已生成的内容已自动保存"
                        ))
            
            self._performance_metrics.record_stage("complete")
            success = not is_stopped_final and "response" in locals()
            self._performance_metrics.end_request(success=success)
            
            if self._token_update_timer:
                try:
                    self.window.after_cancel(self._token_update_timer)
                except:
                    pass
                self._token_update_timer = None
            
            self._pending_tool_calls.clear()
            self._tool_call_msg_saved = False
            self._current_thinking_content = ""
            self._current_assistant_content = ""
            self._thinking_start_pos = None
            self._assistant_start_pos = None
            self._token_buffer = ""
            self._token_accumulated = ""
            
            if current_conv_id and self.agent and hasattr(self.agent, 'messages'):
                self._session_messages[current_conv_id] = self.agent.snapshot_messages()
            
            is_current_tab = (current_tab_id and self._tab_mgr and 
                              self._tab_mgr.active_tab_id == current_tab_id)
            if is_current_tab:
                self.window.after(0, lambda: self._set_processing(False))
            else:
                if current_tab_id and self._tab_mgr:
                    tab = self._tab_mgr.get_tab(current_tab_id)
                    if tab:
                        tab.is_processing = False
                        self.window.after(0, lambda t=tab.title: self._append_system_message(
                            f"✅ 后台任务完成: {t}"
                        ))
                        self.window.after(0, lambda: self._rebuild_tab_buttons())

    def _on_token_receive(self, token: str, token_type: str):
        """处理接收到的token - 按次数批量更新UI"""
        # 对token进行安全检查
        token = self._sanitize_for_transmission(token)
        
        # 累加token
        if token_type == "reasoning":
            self._current_thinking_content += token
        else:
            self._current_assistant_content += token
        
        # 按次数计数：每收到 N 次 token 更新一次 UI
        self._token_count_for_next_update += 1
        
        if self._token_count_for_next_update >= self._max_token_buffer_size:
            self._flush_tokens(token_type)
    
    def _flush_tokens(self, token_type: str):
        """批量更新token到UI"""
        self._token_update_timer = None
        self._token_count_for_next_update = 0  # 重置计数
        
        if token_type == "reasoning":
            if self._thinking_start_pos is None:
                self._thinking_start_pos = self._append_assistant_message(
                    self._current_thinking_content, 
                    is_thinking=True
                )
            else:
                self._update_streaming_message(
                    self._thinking_start_pos, 
                    self._current_thinking_content, 
                    "thinking_bg", 
                    "💭"
                )
        else:
            if self._assistant_start_pos is None:
                self._assistant_start_pos = self._append_assistant_message(
                    self._current_assistant_content
                )
            else:
                self._update_streaming_message(
                    self._assistant_start_pos, 
                    self._current_assistant_content, 
                    "assistant_bg", 
                    "🤖"
                )

    def _on_tool_call(self, name: str, args: Dict):
        """显示工具调用 - 记录位置以便后续添加结果"""
        # 保存当前工具调用位置和参数
        tool_call_id = f"{name}_{len(self._pending_tool_calls)}"
        pos, end_pos = self._append_tool_message(name, tool_args=args, is_thinking=True, return_positions=True)
        self._pending_tool_calls[tool_call_id] = {
            'pos': pos,
            'end_pos': end_pos,  # 保存结束位置用于后续追加结果
            'name': name,
            'args': args
        }
    
    def _on_tool_result(self, name: str, result: str, llm_tool_call_id: Optional[str] = None):
        """显示工具执行结果 - 安全追加，防止缓存损坏 - 优化版：带截断"""
        tool_call_id = None
        tool_args = None
        
        # 对结果进行安全检查和修复
        result = self._sanitize_for_transmission(result)
        result = self._check_and_fix_format(result)
        
        # 应用工具结果截断（只对显示的内容截断，保存的还是完整结果）
        display_result = self._truncate_tool_result(result)
        
        # 查找对应的工具调用
        for tid, data in list(self._pending_tool_calls.items()):
            if data['name'] == name:
                tool_call_id = tid
                tool_args = data['args']
                break
        
        # 优先使用 LLM 端的 tool_call_id（与 tool_calls 中的 id 一致）
        save_tool_call_id = llm_tool_call_id or tool_call_id or f"tc_{name}_{len(self._pending_tool_calls)}"
        
        try:
            if tool_call_id and tool_call_id in self._pending_tool_calls:
                data = self._pending_tool_calls[tool_call_id]
                tool_end_pos = data.get('end_pos')
                
                if tool_end_pos:
                    # 安全追加结果：先确保 chat_text 为 NORMAL 状态
                    self.chat_text.config(state=tk.NORMAL)
                    
                    # 插入结果（带分隔和格式）- 使用截断后的内容用于显示
                    result_prefix = "\n\n**结果**:\n"
                    self.chat_text.insert(tool_end_pos, result_prefix + display_result)
                    
                    # 恢复 DISABLED 状态
                    self.chat_text.config(state=tk.DISABLED)
                    self.chat_text.see(tk.END)
                else:
                    # 如果没有保存结束位置，则追加新消息
                    self._append_tool_message(name, tool_args=data['args'], tool_result=result)
                
                # 清除等待列表
                del self._pending_tool_calls[tool_call_id]
            else:
                # 找不到对应的调用，直接显示
                self._append_tool_message(name, tool_result=result)
        except Exception as e:
            # 异常时确保 chat_text 状态恢复
            try:
                self.chat_text.config(state=tk.DISABLED)
            except:
                pass
            # 异常时用安全方式追加
            self._append_tool_message(name, tool_args=tool_args, tool_result=result)
            # 清理所有同名待处理调用
            keys_to_del = [k for k, v in self._pending_tool_calls.items() if v['name'] == name]
            for k in keys_to_del:
                del self._pending_tool_calls[k]
        
        # 保存到对话历史（保存完整的 result，不是截断后的）
        self._save_message("tool", tool_name=name, tool_args=tool_args, tool_result=result, tool_call_id=save_tool_call_id)

    def _on_response_complete(self, response: str, synced_ids: Optional[List[str]] = None):
        import time
        elapsed = time.time() - self._round_start_time
        response_to_save = response
        if self._current_assistant_content and not response:
            response_to_save = self._current_assistant_content
        elif self._current_thinking_content and not response_to_save:
            response_to_save = self._current_thinking_content

        response_to_save = self._sanitize_for_transmission(response_to_save)
        response_to_save = self._fix_incomplete_output(response_to_save)
        response_to_save = self._check_and_fix_format(response_to_save)

        reasoning_to_save = None
        if self._current_thinking_content and response_to_save != self._current_thinking_content:
            reasoning_to_save = self._sanitize_for_transmission(self._current_thinking_content)
            reasoning_to_save = self._fix_incomplete_output(reasoning_to_save)

        if not self._assistant_start_pos and not self._thinking_start_pos and response_to_save:
            self._append_assistant_message(response_to_save)

        if synced_ids and self._event_logger:
            try:
                self._event_logger.mark_synced(synced_ids)
            except Exception as e:
                print(f"标记事件为已同步失败: {e}")

        self._save_message("assistant", response_to_save, reasoning_content=reasoning_to_save)

        self._check_compact_context()

        self._save_conversation_checkpoint()

        if elapsed < 60:
            self._update_status(f"✅ 处理完成 ({elapsed:.1f}s)")
        else:
            self._update_status(f"✅ 处理完成 ({elapsed/60:.1f}min)")
    
    def _check_compact_context(self):
        return

    def _async_compact(self):
        try:
            current = self.agent.snapshot_messages()
            if self._compactor.should_compact(current):
                original = len(current)
                compacted = self._compactor.compact(current)
                self.agent.restore_messages(compacted)
                self.window.after(0, lambda: self._append_system_message(
                    f"🔄 上下文自动压缩: {original} → {len(compacted)} 条消息"
                ))
                self._compactor._compaction_count += 1
        except Exception as e:
            print(f"AutoCompact 失败: {e}")

    def _save_conversation_checkpoint(self):
        """保存对话检查点（异步）"""
        if not self.current_conversation_id:
            return
        if not self._workflow_loaded or not self._workflow_engine:
            return
        # 异步执行，不阻塞UI
        conv_id = self.current_conversation_id
        conv_title = self.current_conversation_title
        threading.Thread(
            target=self._async_save_checkpoint,
            args=(conv_id, conv_title),
            daemon=True
        ).start()

    def _async_save_checkpoint(self, conv_id: str, conv_title: str):
        """后台保存检查点"""
        try:
            self._workflow_engine.persistence.save_artifact(
                conv_id,
                "checkpoint",
                f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                content=json.dumps({
                    "title": conv_title,
                    "timestamp": datetime.now().isoformat(),
                }, ensure_ascii=False),
                step_id="conversation",
            )
        except Exception as e:
            print(f"Checkpoint 保存失败: {e}")

    def submit_workflow(self, workflow_type: str, input_data: Dict[str, Any] = None):
        """提交后台工作流"""
        if not self._workflow_loaded or not self._workflow_engine:
            self._append_system_message("工作流引擎加载中，请稍候...", is_error=True)
            return ""
        
        try:
            WorkflowEngine, WorkflowStatus, get_workflow_engine, get_workflow, list_workflows = _lazy_import_workflow()
            wf_def = get_workflow(workflow_type)
            self._workflow_engine.set_agent(self.agent, self.system)
            instance_id = self._workflow_engine.start_workflow(
                wf_def, input_data or {},
            )
            status = self._workflow_engine.get_status(instance_id)
            self._append_system_message(
                f"🚀 后台工作流已启动: {wf_def.name}\n"
                f"ID: {instance_id}\n"
                f"状态: {status['status']}"
            )
            return instance_id
        except KeyError:
            try:
                _, _, _, _, list_workflows = _lazy_import_workflow()
                available = ", ".join(list_workflows().keys())
            except:
                available = "code_analysis, research, note_generation, code_review, dependency_scan"
            self._append_system_message(
                f"未知工作流: {workflow_type}\n可用: {available}",
                is_error=True,
            )
        except Exception as e:
            self._append_system_message(f"工作流启动失败: {e}", is_error=True)
        
        return ""

    def resume_workflow(self, instance_id: str):
        """恢复中断的工作流"""
        if not self._workflow_loaded or not self._workflow_engine:
            self._append_system_message("工作流引擎加载中", is_error=True)
            return
        try:
            if self._workflow_engine.resume_workflow(instance_id):
                self._append_system_message(f"✅ 工作流 {instance_id} 已恢复")
            else:
                self._append_system_message(
                    f"⚠️ 无法恢复工作流 {instance_id}", is_error=True
                )
        except Exception as e:
            self._append_system_message(f"恢复失败: {e}", is_error=True)

    def list_recoverable_workflows(self):
        """列出可恢复的工作流"""
        if not self._workflow_loaded or not self._workflow_engine:
            return []
        return self._workflow_engine.list_recoverable()
    
    def _on_error(self, error: str, traceback_str: str = ""):
        self._append_system_message(f"❌ {error}", is_error=True)
        if traceback_str:
            print(traceback_str)
        self._update_status(f"❌ 错误: {error[:50]}")
    
    def _set_processing(self, processing: bool):
        self.is_processing = processing
        if self._tab_mgr:
            active_tab = self._tab_mgr.get_active_tab()
            if active_tab:
                self._tab_mgr.set_processing(active_tab.tab_id, processing)
        if not processing:
            self._update_status("✅ 就绪")
            self._rebuild_tab_buttons()
        if hasattr(self, 'input_text'):
            self.input_text.config(state=tk.NORMAL)
    
    def _save_message(self, role: str, content: str = None, reasoning_content: str = None, tool_name: str = None, tool_args: Dict = None, tool_result: str = None, tool_call_id: str = None, tool_calls: str = None):
        if not self.current_conversation_id:
            return

        if content is None:
            content = ""

        if role == "tool" and tool_name:
            content_lines = []
            content_lines.append(f"调用工具: {tool_name}")
            if tool_args:
                content_lines.append(f"\n参数: {json.dumps(tool_args, ensure_ascii=False, indent=2)}")
            if tool_result:
                content_lines.append(f"\n结果: {tool_result}")
            content = "\n".join(content_lines)

        if content:
            content = self._sanitize_for_transmission(content)
            content = self._check_and_fix_format(content)
        if reasoning_content:
            reasoning_content = self._sanitize_for_transmission(reasoning_content)
            reasoning_content = self._check_and_fix_format(reasoning_content)

        if tool_calls is None and role == "assistant" and not getattr(self, '_tool_call_msg_saved', False) and self.agent and hasattr(self.agent, 'snapshot_messages'):
            for msg in reversed(self.agent.snapshot_messages()):
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    try:
                        tool_calls = json.dumps(msg["tool_calls"], ensure_ascii=False)
                    except (TypeError, ValueError):
                        tool_calls = str(msg["tool_calls"])
                    break

        msg = ConversationMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            reasoning_content=reasoning_content,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            tool_call_id=tool_call_id,
            tool_calls=tool_calls,
        )
        self.conversation_history.save_message(self.current_conversation_id, msg)
    
    def _reset_conversation(self):
        if self.agent:
            self.agent.reset()
        
        # 清空聊天区域
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete(1.0, tk.END)
        self.chat_text.config(state=tk.DISABLED)

        # 清空导航侧边栏
        self._nav_blocks.clear()
        self._nav_current_idx = -1
        self.nav_listbox.delete(0, tk.END)
        
        self._append_system_message("对话已重置，请开始新的对话。")
        self._update_status("🔄 对话已重置")
    
    def _stop_processing(self):
        """停止处理 - 设置当前Tab的标志位并发送取消信号"""
        if self._tab_mgr:
            active_tab = self._tab_mgr.get_active_tab()
            if active_tab:
                self._tab_mgr.set_should_stop(active_tab.tab_id, True)
                self._tab_mgr.set_processing(active_tab.tab_id, False)
                if active_tab.agent_instance and hasattr(active_tab.agent_instance, 'cancel'):
                    active_tab.agent_instance.cancel()
        
        self.should_stop = True
        if self.agent:
            self.agent.cancel()
        
        self._update_status("🛑 正在停止...")
    
    def _show_chat_context_menu(self, event):
        """显示聊天区域右键菜单"""
        try:
            menu = tk.Menu(self.window, tearoff=0)
            
            # 检查是否有选中的文本
            try:
                selected_text = self.chat_text.get(tk.SEL_FIRST, tk.SEL_LAST)
                has_selection = bool(selected_text.strip())
            except:
                has_selection = False
                selected_text = ""
            
            if has_selection:
                menu.add_command(label="📋 复制选中", command=lambda: self._copy_selected_text(selected_text))
                menu.add_separator()
            
            # 按段复制：右键所在位置的消息
            menu.add_command(label="📄 按段复制", command=lambda: self._copy_block_at_cursor(event.x, event.y))
            menu.add_separator()
            
            menu.add_command(label="📋 复制全部", command=self._copy_all_messages)
            menu.add_separator()
            
            # 检查点相关
            menu.add_command(label="↩️ 查看检查点", command=self._show_checkpoint_list)
            
            menu.post(event.x_root, event.y_root)
        except Exception as e:
            print(f"右键菜单错误: {e}")
    
    def _copy_selected_text(self, text):
        """复制选中的文本"""
        try:
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")
    
    def _copy_block_at_cursor(self, click_x, click_y):
        """复制右键点击所在位置的整个对话块"""
        try:
            click_pos = self.chat_text.index(f"@{click_x},{click_y}")
            line_num = int(click_pos.split(".")[0])

            content = self.chat_text.get("1.0", tk.END)
            lines = content.split("\n")

            # 块起始标记：角色图标 + 时间戳
            icon_prefixes = ("👤", "🤖", "📢", "⚙️", "🔧", "💭")

            # 向上找块开始：遇到角色图标行
            start_line = line_num - 1
            for i in range(line_num - 1, -1, -1):
                line = lines[i].strip()
                if any(line.startswith(p) for p in icon_prefixes):
                    start_line = i
                    break

            # 向下找块结束：遇到下一个角色图标行
            end_line = len(lines)
            for i in range(line_num, len(lines)):
                line = lines[i].strip()
                if any(line.startswith(p) for p in icon_prefixes):
                    end_line = i
                    break

            block_text = "\n".join(lines[start_line:end_line]).strip()
            if block_text:
                # 清理时间戳（[HH:MM:SS] 或 [YYYY-MM-DD HH:MM:SS] 格式）
                import re
                block_text = re.sub(r'\[[\d\-\s:]+\]\s*', '', block_text)
                self.chat_text.clipboard_clear()
                self.chat_text.clipboard_append(block_text)
        except Exception as e:
            print(f"按段复制失败: {e}")
    
    def _on_ctrl_c_copy(self, event=None):
        """Ctrl+C 复制选中文本"""
        try:
            selected = self.chat_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            if selected:
                self.window.clipboard_clear()
                self.window.clipboard_append(selected)
        except Exception:
            pass
        return "break"
    
    def _on_chat_text_click(self, event):
        """点击聊天文本"""
        pass
    
    def _on_chat_text_motion(self, event):
        """拖拽选中聊天文本"""
        pass
    
    def _update_status(self, status: str):
        if hasattr(self, 'status_label'):
            self.status_label.config(text=status)
    
    def _on_input_return(self, event):
        """Return 键发送消息"""
        # 检查是否是正常的 Return 键（没有 Shift/Alt）
        if event and hasattr(event, 'state'):
            # 检查是否有 Shift 或其他修饰键
            if event.state & 0x1:  # Shift
                return self._on_shift_return(event)
        # 正常发送消息
        self._send_message()
        return "break"
    
    def _on_shift_return(self, event):
        """Shift+Return 添加换行"""
        if hasattr(self, 'input_text'):
            try:
                self.input_text.insert(tk.INSERT, "\n")
                self.input_text.see(tk.INSERT)
            except:
                pass
        return "break"
    
    def _toggle_input_expand(self):
        """切换输入框展开/收起"""
        self.is_input_expanded = not self.is_input_expanded
        
        if self.is_input_expanded:
            # 展开模式
            self.input_text.config(height=15)
            self.expand_btn.config(text="🔽 收起")
            self.input_container.config(height=350)
        else:
            # 收起模式
            self.input_text.config(height=5)
            self.expand_btn.config(text="🔍 展开")
            self.input_container.config(height=180)
    
    def _clear_input(self):
        """清空输入框"""
        if hasattr(self, 'input_text'):
            self.input_text.delete(1.0, tk.END)
            self._update_char_count()
    
    def _on_text_modified(self, event=None):
        """文本修改时更新字符计数"""
        if hasattr(self, 'input_text'):
            self.input_text.edit_modified(0)  # 重置修改标志
            self._update_char_count()
    
    def _update_char_count(self):
        """更新字符计数"""
        if hasattr(self, 'char_count_label') and hasattr(self, 'input_text'):
            content = self.input_text.get(1.0, tk.END)
            count = len(content) - 1  # 减去末尾的换行
            self.char_count_label.config(text=f"{count} 字符")
            
            # 字符数过多时显示警告颜色
            if count > 2000:
                self.char_count_label.config(fg="#ef4444")
            elif count > 1000:
                self.char_count_label.config(fg="#f59e0b")
            else:
                self.char_count_label.config(fg="#9ca3af")
    
    def _tab_insert(self, event):
        """处理 Tab 键，插入4个空格"""
        if hasattr(self, 'input_text'):
            try:
                self.input_text.insert(tk.INSERT, "    ")
            except:
                pass
        return "break"
    
    def _on_history_up(self, event):
        """处理向上方向键 - 浏览上一条历史"""
        if not self._input_history:
            return "break"
        
        # 保存当前输入到缓冲区
        if self._input_history_index == -1:
            current_content = self.input_text.get(1.0, tk.END).strip()
            if current_content:
                self._current_input_buffer = current_content
        
        # 移动到上一条历史
        if self._input_history_index < len(self._input_history) - 1:
            self._input_history_index += 1
            idx = len(self._input_history) - 1 - self._input_history_index
            self._set_input_text(self._input_history[idx])
        
        return "break"
    
    def _on_history_down(self, event):
        """处理向下方向键 - 浏览下一条历史"""
        if not self._input_history or self._input_history_index <= 0:
            # 回到最新输入
            if self._input_history_index != -1:
                self._input_history_index = -1
                if self._current_input_buffer:
                    self._set_input_text(self._current_input_buffer)
                else:
                    self._set_input_text("")
            return "break"
        
        # 移动到下一条历史
        self._input_history_index -= 1
        idx = len(self._input_history) - 1 - self._input_history_index
        self._set_input_text(self._input_history[idx])
        
        return "break"
    
    def _set_input_text(self, text: str):
        """设置输入框文本"""
        self.input_text.config(state=tk.NORMAL)
        self.input_text.delete(1.0, tk.END)
        self.input_text.insert(1.0, text)
        self.input_text.see(tk.END)
        self._update_char_count()
    
    def _add_to_input_history(self, text: str):
        """添加输入到历史记录"""
        if not text or not text.strip():
            return
        
        # 避免重复添加相同的最后一条
        if self._input_history and self._input_history[-1] == text:
            return
        
        self._input_history.append(text)
        
        # 限制历史长度
        max_history = 100
        if len(self._input_history) > max_history:
            self._input_history = self._input_history[-max_history:]
        
        # 重置历史索引
        self._input_history_index = -1
        self._current_input_buffer = ""
    
    def _clear_input_history(self):
        """清空输入历史"""
        self._input_history = []
        self._input_history_index = -1
        self._current_input_buffer = ""
    
    def _show_input_history(self):
        """显示输入历史记录对话框"""
        if not self._input_history:
            self._append_system_message("📜 输入历史为空")
            return
        
        dialog = tk.Toplevel(self.window)
        dialog.title("📜 输入历史")
        dialog.geometry("600x400")
        dialog.transient(self.window)
        
        bg_color = "#f5f7fa"
        dialog.configure(bg=bg_color)
        
        main_frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = tk.Label(main_frame, text="输入历史记录 (↑↓ 方向键导航)",
                             font=("Microsoft YaHei UI", 12, "bold"),
                             bg=bg_color, fg="#2d3748")
        title_label.pack(pady=(0, 10))
        
        list_frame = tk.Frame(main_frame, bg=bg_color)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        history_listbox = tk.Listbox(list_frame, font=("Consolas", 10),
                                    yscrollcommand=scrollbar.set,
                                    bg="#ffffff", fg="#2d3748",
                                    selectbackground="#3b82f6",
                                    selectforeground="white",
                                    relief=tk.FLAT)
        history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=history_listbox.yview)
        
        # 添加历史记录到列表（倒序显示，最新的在前面）
        for i, text in enumerate(reversed(self._input_history)):
            display_text = text[:80] + "..." if len(text) > 80 else text
            display_text = display_text.replace("\n", " ")
            history_listbox.insert(tk.END, f"{i+1}. {display_text}")
        
        def use_selected():
            selection = history_listbox.curselection()
            if selection:
                idx = len(self._input_history) - 1 - selection[0]
                self._set_input_text(self._input_history[idx])
                dialog.destroy()
        
        def clear_history():
            if messagebox.askyesno("确认", "确定要清空输入历史吗？"):
                self._clear_input_history()
                dialog.destroy()
        
        button_frame = tk.Frame(main_frame, bg=bg_color)
        button_frame.pack(pady=(10, 0))
        
        use_btn = tk.Button(button_frame, text="使用选中项", command=use_selected,
                           bg="#3b82f6", fg="white",
                           font=("Microsoft YaHei UI", 10),
                           width=12, relief=tk.FLAT, pady=6)
        use_btn.pack(side=tk.LEFT, padx=5)
        
        clear_btn = tk.Button(button_frame, text="清空历史", command=clear_history,
                            bg="#ef4444", fg="white",
                            font=("Microsoft YaHei UI", 10),
                            width=12, relief=tk.FLAT, pady=6)
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        close_btn = tk.Button(button_frame, text="关闭", command=dialog.destroy,
                            bg="#6b7280", fg="white",
                            font=("Microsoft YaHei UI", 10),
                            width=12, relief=tk.FLAT, pady=6)
        close_btn.pack(side=tk.LEFT, padx=5)
    
    def _on_window_focus(self, event=None):
        if hasattr(self, 'input_text'):
            self.input_text.focus_set()
    
    # ── 语音唤醒词检测 ──

    def _toggle_voice_wake(self):
        """切换语音唤醒开关"""
        if not HAS_VOICE_WAKE:
            self._update_status("抱歉，语音唤醒模块不可用")
            return

        if not self._wake_detector:
            try:
                self._wake_detector = create_wake_detector(
                    wake_words=["hey_ws2", "你好ws2"],
                    on_wake=self._on_wake_detected,
                    threshold=0.5,
                )
            except Exception as e:
                logger.error(f"创建唤醒检测器失败: {e}")
                self._update_status("抱歉，唤醒词检测功能初始化失败")
                self._wake_detector = None
                return

            if not self._wake_detector:
                self._update_status("抱歉，当前系统不支持语音唤醒功能")
                return

        if self._wake_enabled:
            # 关闭唤醒检测
            try:
                self._wake_detector.stop()
            except Exception as e:
                logger.warning(f"停止唤醒检测失败: {e}")
            self._wake_enabled = False
            self._update_wake_button_state()
            self._update_status("语音唤醒已关闭")
        else:
            # 开启唤醒检测
            try:
                if self._wake_detector.start():
                    self._wake_enabled = True
                    self._update_wake_button_state()
                    self._update_status("语音唤醒已开启 (Hey WS2 / 你好WS2)")
                else:
                    self._update_status("抱歉，唤醒词检测启动失败，请检查麦克风")
            except OSError as e:
                # 麦克风设备错误
                logger.error(f"麦克风设备错误: {e}")
                self._update_status("抱歉，未检测到麦克风设备")
            except Exception as e:
                logger.error(f"启动唤醒检测失败: {e}")
                self._update_status("抱歉，唤醒词检测启动失败")

    def _update_wake_button_state(self):
        """更新唤醒按钮的视觉状态"""
        if not hasattr(self, '_wake_btn'):
            return
        if self._wake_enabled:
            self._wake_btn_text.set("🎤🔴")
            self._wake_btn.config(fg=self.error_color)
        else:
            self._wake_btn_text.set("🎤")
            self._wake_btn.config(fg=self.subtle_color)

    def _on_wake_detected(self, wake_word: str):
        """唤醒回调 — 检测到唤醒词后触发"""
        logger.info(f"检测到唤醒词: {wake_word}")

        # 在主线程中执行 UI 操作，并捕获异常
        try:
            self.window.after(0, lambda: self._handle_wake(wake_word))
        except Exception as e:
            logger.error(f"唤醒回调执行失败: {e}")
            self._update_status("抱歉，唤醒响应失败")

    def _handle_wake(self, wake_word: str):
        """处理唤醒事件（在主线程中执行）"""
        try:
            # 1. 确保窗口可见并置顶
            self.window.deiconify()
            self.window.attributes("-topmost", True)
            self.window.focus_force()
        except Exception as e:
            logger.warning(f"窗口激活失败: {e}")

        # 2. 播放提示音（跨平台）
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"],
                               capture_output=True, timeout=2)
        except Exception:
            pass

        # 3. 更新状态栏
        self._update_status(f"已唤醒，等待输入...")

        # 4. 自动开始语音输入（带错误处理）
        try:
            self._start_voice_input()
        except Exception as e:
            logger.error(f"语音输入启动失败: {e}")
            self._update_status("抱歉，语音输入功能不可用")

    def _start_voice_input(self):
        """启动语音输入 — 优先使用系统内置语音输入"""
        platform = sys.platform

        if platform == "win32":
            # Windows: Win+H
            try:
                result = self._use_windows_voice_input()
                if result:
                    self._update_status(f"已识别: {result[:30]}...")
                    return
            except Exception as e:
                logger.debug(f"Windows 语音输入不可用: {e}")

        elif platform == "darwin":
            # macOS: Fn+Fn (双击)
            try:
                result = self._use_macos_voice_input()
                if result:
                    self._update_status(f"已识别: {result[:30]}...")
                    return
            except Exception as e:
                logger.debug(f"macOS 语音输入不可用: {e}")

        # 回退到 SpeechRecognition 方案
        try:
            import speech_recognition as sr
            self._use_speech_recognition_input()
        except ImportError:
            self._update_status("抱歉，当前系统不支持语音输入功能")

    def _use_windows_voice_input(self) -> Optional[str]:
        """使用 Windows 内置语音输入（模拟 Win+H 快捷键）"""
        try:
            import ctypes

            # 聚焦输入框
            if hasattr(self, 'input_text'):
                self.input_text.focus_set()
                self.input_text.update_idletasks()

            # 模拟 Win+H 快捷键
            VK_LWIN = 0x5B
            VK_H = 0x48
            KEYEVENTF_KEYUP = 0x0002

            ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_H, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_H, 0, KEYEVENTF_KEYUP, 0)
            ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

            self._update_status("正在使用 Windows 语音输入...")
            return None

        except Exception as e:
            logger.debug(f"Windows 语音输入失败: {e}")
            return None

    def _use_macos_voice_input(self) -> Optional[str]:
        """使用 macOS 内置语音输入（模拟 Fn+Fn 快捷键）"""
        try:
            import subprocess

            # 聚焦输入框
            if hasattr(self, 'input_text'):
                self.input_text.focus_set()
                self.input_text.update_idletasks()

            # macOS 语音输入快捷键是双击 Fn 键
            # 使用 AppleScript 模拟按键
            applescript = '''
            tell application "System Events"
                key code 63  -- Fn key (第一次按下)
                delay 0.1
                key code 63  -- Fn key (第二次按下)
            end tell
            '''
            subprocess.run(["osascript", "-e", applescript], capture_output=True, timeout=2)

            self._update_status("正在使用 macOS 语音输入...")
            return None

        except subprocess.TimeoutExpired:
            logger.debug("macOS 语音输入超时")
            return None
        except Exception as e:
            logger.debug(f"macOS 语音输入失败: {e}")
            return None

    def _use_speech_recognition_input(self):
        """使用 SpeechRecognition 进行语音输入（备选方案）"""
        try:
            import speech_recognition as sr
        except ImportError:
            self._update_status("抱歉，语音输入功能需要安装: pip install SpeechRecognition")
            return

        def recognize_thread():
            try:
                r = sr.Recognizer()
                with sr.Microphone() as source:
                    self._update_status("🎤 正在听...")
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    audio = r.listen(source, timeout=8, phrase_time_limit=15)

                self._update_status("🎤 识别中...")
                # 尝试中文识别
                text = r.recognize_google(audio, language="zh-CN")

                # 在主线程中填入输入框
                self.window.after(0, lambda: self._fill_input(text))

            except sr.UnknownValueError:
                self._update_status("抱歉，未能识别您的语音")
            except sr.WaitTimeoutError:
                self._update_status("抱歉，未检测到语音输入")
            except sr.RequestError as e:
                self._update_status("抱歉，语音识别服务暂时不可用")
            except OSError as e:
                self._update_status("抱歉，系统未检测到麦克风设备")
                logger.error(f"麦克风不可用: {e}")
            except Exception as e:
                self._update_status("抱歉，语音输入功能出现错误")
                logger.error(f"语音识别失败: {e}")

        threading.Thread(target=recognize_thread, daemon=True).start()

    def _fill_input(self, text: str):
        """将识别结果填入输入框"""
        if hasattr(self, 'input_text') and text:
            self.input_text.config(state=tk.NORMAL)
            self.input_text.delete(1.0, tk.END)
            self.input_text.insert(tk.END, text)
            self.input_text.focus_set()
            self._update_status(f"🎤 已识别: {text[:30]}...")

    # ── 窗口关闭 ──
    
    def _on_close(self):
        """清理所有资源并关闭窗口"""
        global _global_agent_windows
        
        # 停止语音唤醒检测器
        if self._wake_detector and self._wake_enabled:
            try:
                self._wake_detector.stop()
                logger.info("语音唤醒检测器已停止")
            except Exception as e:
                logger.warning(f"停止唤醒检测器失败: {e}")
        
        # 停止同步服务器
        if self._server_running:
            self._stop_sync_server()
        
        # 清理基础设施更新定时器
        if hasattr(self, '_infra_timer_id') and self._infra_timer_id:
            self.window.after_cancel(self._infra_timer_id)
        
        # 清理语境监控定时器
        if hasattr(self, '_context_timer_id') and self._context_timer_id:
            self.window.after_cancel(self._context_timer_id)
        
        self._save_window_state()
        
        # 从全局列表中移除此窗口
        if self in _global_agent_windows:
            _global_agent_windows.remove(self)
        
        self.window.destroy()
    
    def refresh_system_refs(self, system=None, project_mgr=None, task_board_mgr=None):
        """刷新系统引用 - 在课程系统重载后调用"""
        if system is not None:
            self.system = system
        if project_mgr is not None:
            self.project_mgr = project_mgr
        if task_board_mgr is not None:
            self.task_board_mgr = task_board_mgr
        
        # 如果 agent 已初始化，更新其引用
        if self.agent:
            if hasattr(self.agent, 'ws2_system'):
                self.agent.ws2_system = self.system
            if hasattr(self.agent, 'project_manager'):
                self.agent.project_manager = self.project_mgr
            if hasattr(self.agent, 'task_manager'):
                self.agent.task_manager = self.task_board_mgr
    
    def _on_window_configure(self, event=None):
        if not hasattr(self, '_configure_after_id'):
            self._configure_after_id = None
        if self._configure_after_id:
            self.window.after_cancel(self._configure_after_id)
        self._configure_after_id = self.window.after(1000, self._save_window_state)  # 从500ms增加到1000ms
    
    def _save_window_state(self):
        if not self._ui_state_mgr or not self.window.winfo_exists():
            return
        try:
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            w = self.window.winfo_width()
            h = self.window.winfo_height()
            self._ui_state_mgr.save_window_geometry("agent_assistant", x, y, w, h)
            self._ui_state_mgr.persist()
        except Exception:
            pass
    
    def show(self):
        self.window.deiconify()
        self.window.lift()
        if hasattr(self, 'input_text'):
            # 确保输入框启用
            self.input_text.config(state=tk.NORMAL)
            self.window.after(50, lambda: self.input_text.focus_set())
    
    def _import_ws2_to_rag(self):
        """从 WS2 系统导入数据到 RAG 知识库"""
        if not HAS_RAG or not self._rag_manager:
            messagebox.showinfo("提示", "RAG 系统未初始化")
            return
        
        if not self.system:
            messagebox.showinfo("提示", "WS2 系统未连接")
            return
        
        def _do_import():
            try:
                added = self._rag_manager.add_knowledge_from_ws2(self.system)
                self.window.after(0, lambda: messagebox.showinfo(
                    "导入完成",
                    f"成功导入 {added} 个文档到知识库\n\n"
                    f"文档总数: {self._rag_manager.get_stats().get('document_count', 0)}"
                ))
            except Exception as e:
                self.window.after(0, lambda: messagebox.showerror("导入失败", str(e)))
        
        threading.Thread(target=_do_import, daemon=True).start()
        messagebox.showinfo("导入中", "正在从 WS2 系统导入数据，请稍候...")
    
    def _show_rag_controls(self):
        """显示 RAG 知识库控制面板"""
        if not HAS_RAG:
            messagebox.showinfo("提示", "RAG 系统不可用")
            return
        
        # 按需加载RAG
        if not self._rag_manager:
            if not self._load_rag():
                messagebox.showinfo("提示", "RAG 系统加载失败")
                return
        
        # 创建对话框
        dialog = tk.Toplevel(self.window)
        dialog.title("📚 知识库管理")
        dialog.geometry("600x500")
        dialog.configure(bg=self.bg_color)
        dialog.transient(self.window)
        dialog.grab_set()
        
        # 主容器
        main_frame = tk.Frame(dialog, bg=self.bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = tk.Label(
            main_frame,
            text="📚 知识库管理",
            font=("Microsoft YaHei UI", 16, "bold"),
            bg=self.bg_color,
            fg=self.text_color
        )
        title_label.pack(anchor=tk.W, pady=(0, 20))
        
        # 状态面板
        stats_frame = tk.Frame(main_frame, bg=self.card_color, padx=15, pady=15)
        stats_frame.pack(fill=tk.X, pady=(0, 15))
        
        stats = self._rag_manager.get_stats()
        stats_text = f"""文档数量: {stats.get('document_count', 0)}
自动检索: {'✅ 开启' if stats.get('auto_trigger', False) else '❌ 关闭'}
缓存条目: {stats.get('cache_size', 0)}"""
        
        stats_label = tk.Label(
            stats_frame,
            text=stats_text,
            font=("Consolas", 10),
            bg=self.card_color,
            fg=self.text_color,
            justify=tk.LEFT
        )
        stats_label.pack(anchor=tk.W)
        
        # 操作按钮区域
        button_frame = tk.Frame(main_frame, bg=self.bg_color)
        button_frame.pack(fill=tk.X, pady=10)
        
        def add_files():
            filepaths = filedialog.askopenfilenames(
                title="选择文档文件",
                filetypes=[
                    ("支持的文档", "*.txt *.md *.json"),
                    ("所有文件", "*.*")
                ]
            )
            if filepaths and self._rag_manager and self._rag_manager.rag_engine:
                count = 0
                for filepath in filepaths:
                    try:
                        self._rag_manager.rag_engine.add_file(filepath)
                        count += 1
                    except Exception as e:
                        print(f"添加文件失败: {e}")
                self._rag_manager.rag_engine.persist()
                messagebox.showinfo("成功", f"已添加 {count} 个文档到知识库")
                dialog.destroy()
        
        def add_directory():
            dirpath = filedialog.askdirectory(title="选择目录")
            if dirpath and self._rag_manager and self._rag_manager.rag_engine:
                try:
                    result = self._rag_manager.rag_engine.add_directory(dirpath)
                    self._rag_manager.rag_engine.persist()
                    messagebox.showinfo("成功", f"已从目录添加 {len(result)} 个文档")
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("错误", f"添加目录失败: {e}")
        
        def toggle_auto_rag():
            if self._rag_manager:
                self._rag_manager.config.auto_trigger = not self._rag_manager.config.auto_trigger
                status = "开启" if self._rag_manager.config.auto_trigger else "关闭"
                messagebox.showinfo("设置", f"自动检索已{status}")
        
        def clear_cache():
            if self._rag_manager:
                self._rag_manager.clear_cache()
                messagebox.showinfo("完成", "检索缓存已清空")
        
        def clear_knowledge():
            if self._rag_manager and self._rag_manager.rag_engine:
                if messagebox.askyesno("确认", "确定要清空知识库吗？此操作不可撤销！"):
                    self._rag_manager.rag_engine.clear()
                    self._rag_manager.rag_engine.persist()
                    messagebox.showinfo("完成", "知识库已清空")
                    dialog.destroy()
        
        # 按钮布局
        tk.Button(
            button_frame,
            text="📄 添加文件",
            command=add_files,
            bg=self.primary_color,
            fg="white",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=15,
            pady=8,
            relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        tk.Button(
            button_frame,
            text="🚀 从WS2导入",
            command=lambda: (dialog.destroy(), self._import_ws2_to_rag()),
            bg="#8b5cf6",
            fg="white",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=15,
            pady=8,
            relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        tk.Button(
            button_frame,
            text="📁 添加目录",
            command=add_directory,
            bg=self.success_color,
            fg="white",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=15,
            pady=8,
            relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        tk.Button(
            button_frame,
            text="🔄 自动检索",
            command=toggle_auto_rag,
            bg=self.warning_color,
            fg="white",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=15,
            pady=8,
            relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        tk.Button(
            button_frame,
            text="🧹 清空缓存",
            command=clear_cache,
            bg="#6b7280",
            fg="white",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=15,
            pady=8,
            relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        tk.Button(
            button_frame,
            text="⚠️ 清空知识库",
            command=clear_knowledge,
            bg=self.error_color,
            fg="white",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=15,
            pady=8,
            relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        # 关闭按钮
        tk.Button(
            main_frame,
            text="关闭",
            command=dialog.destroy,
            bg="#9ca3af",
            fg="white",
            font=("Microsoft YaHei UI", 10),
            padx=30,
            pady=8,
            relief=tk.FLAT
        ).pack(anchor=tk.CENTER, pady=20)

    # ─── 同步服务器管理 ──────────────────────────────────

    def _toggle_sync_server(self):
        """切换同步服务器启停"""
        if self._server_running:
            self._stop_sync_server()
        else:
            self._start_sync_server()

    def _start_sync_server(self):
        """启动本地文件同步分发服务器（自动端口检测，支持多实例）"""
        try:
            from .server import run_server, find_available_port
            import subprocess
            import sys
            import socket

            workspace = str(self.base_path)
            start_port = 6906

            # 获取局域网 IP
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                local_ip = "127.0.0.1"

            # 自动查找可用端口
            try:
                port = find_available_port(start_port)
            except OSError:
                self._append_system_message(f"无法找到可用端口（{start_port}-{start_port+99} 均被占用）")
                return

            # 记录实际使用的端口
            self._server_port = port

            if port != start_port:
                logger.info(f"端口 {start_port} 已被占用，自动使用 {port}")

            # 自动配置防火墙规则（允许局域网和公用网络访问）
            try:
                import sys as _sys
                _mcp_dir = str(Path(__file__).parent)
                if _mcp_dir not in _sys.path:
                    _sys.path.insert(0, _mcp_dir)
                try:
                    from .server.network import configure_firewall
                except ImportError:
                    from server.network import configure_firewall
                ok, msg = configure_firewall(port, allow=True)
                if ok:
                    logger.info(f"防火墙配置成功: {msg}")
                else:
                    logger.warning(f"防火墙配置失败: {msg}")
            except Exception as e:
                logger.debug(f"防火墙配置跳过: {e}")

            # 在子进程中启动服务器，监听 0.0.0.0 允许局域网访问
            # auto_port=False 因为已经在上层选好了端口
            server_script = f'''
import sys
sys.path.insert(0, {repr(str(Path(__file__).parent.parent))})
from mcp.server.app import run_server
run_server(workspace_dir={repr(workspace)}, host="0.0.0.0", port={port}, open_browser=True, auto_port=False)
'''
            self._server_process = subprocess.Popen(
                [sys.executable, "-c", server_script],
                cwd=str(self.base_path),
            )
            self._server_running = True
            self._server_btn_text.set("🌐🟢")
            self._server_btn.config(fg="#22c55e")

            self._try_open_browser(port)

            self._append_system_message(
                f"同步服务器已启动 (端口: {port})\n"
                f"本机访问: http://127.0.0.1:{port}\n"
                f"手机访问: http://{local_ip}:{port}\n"
                f"工作区: {workspace}\n"
                f"支持：文件浏览/编辑/上传/下载/同步"
            )
            logger.info(f"TS2 Sync Server started on port {port}, LAN: http://{local_ip}:{port}")

        except ImportError as e:
            self._append_system_message(f"服务器启动失败（缺少依赖）: {e}\n请安装: pip install fastapi uvicorn")
            logger.error(f"Server import failed: {e}")
        except Exception as e:
            self._append_system_message(f"服务器启动失败: {e}")
            logger.error(f"Server start failed: {e}")

    def _try_open_browser(self, port: int):
        """尝试在浏览器中打开服务器地址"""
        try:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass

    def _wake_server(self):
        """切换服务器启停：运行则停止，停止则启动"""
        # 检测僵尸进程：标记为运行但进程已退出
        if self._server_running and self._server_process:
            if self._server_process.poll() is not None:
                self._server_running = False
                self._server_process = None
                self._server_btn_text.set("🌐")
        if self._server_running and not self._server_process:
            self._server_running = False
            self._server_btn_text.set("🌐")
        self._toggle_sync_server()

    def _stop_sync_server(self):
        """真实停止同步服务器（增强版：处理僵尸进程和端口残留）"""
        if self._server_process:
            try:
                proc = self._server_process
                if sys.platform == "win32":
                    import subprocess
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                   capture_output=True, timeout=8)
                else:
                    import signal
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except:
                        proc.send_signal(signal.SIGKILL)
                        proc.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Server stop error: {e}")
                try:
                    self._server_process.kill()
                except Exception:
                    pass

            # 确认进程已退出
            try:
                if self._server_process.poll() is None:
                    if sys.platform == "win32":
                        import subprocess
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self._server_process.pid)],
                                       capture_output=True, timeout=5)
                    else:
                        import signal
                        os.kill(self._server_process.pid, signal.SIGKILL)
            except Exception:
                pass

            self._server_process = None

        # 清理残留端口占用
        try:
            _port = getattr(self, '_server_port', 6906)
            if sys.platform == "win32":
                import subprocess
                result = subprocess.run(
                    ["netstat", "-ano", "-p", "TCP"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if f":{_port}" in line and "LISTENING" in line:
                        parts = line.strip().split()
                        if parts:
                            pid = parts[-1]
                            if pid.isdigit() and int(pid) != os.getpid():
                                subprocess.run(["taskkill", "/F", "/PID", pid],
                                               capture_output=True, timeout=5)
            elif sys.platform != "win32":
                import subprocess
                result = subprocess.run(
                    ["lsof", "-ti", f":{_port}"],
                    capture_output=True, text=True, timeout=5
                )
                if result.stdout.strip():
                    for pid_str in result.stdout.strip().split('\n'):
                        pid = pid_str.strip()
                        if pid and pid.isdigit() and int(pid) != os.getpid():
                            import signal
                            try:
                                os.kill(int(pid), signal.SIGKILL)
                            except Exception:
                                pass
        except Exception:
            pass

        self._server_running = False
        self._server_btn_text.set("🌐")
        self._server_btn.config(fg=self.subtle_color)
        self._append_system_message("同步服务器已完全停止")
        logger.info("TS2 Sync Server stopped")

    def _show_debug_panel(self):
        """显示调试和性能指标面板"""
        dialog = tk.Toplevel(self.window)
        dialog.title("🔧 调试与性能指标")
        dialog.geometry("700x550")
        dialog.configure(bg=self.bg_color)
        dialog.transient(self.window)
        dialog.grab_set()
        
        main_frame = tk.Frame(dialog, bg=self.bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = tk.Label(main_frame, text="🔧 调试与性能指标",
                             font=("Microsoft YaHei UI", 14, "bold"),
                             bg=self.bg_color, fg=self.text_color)
        title_label.pack(anchor=tk.W, pady=(0, 15))
        
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # 性能指标标签页
        metrics_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(metrics_frame, text="📊 性能指标")
        
        metrics = self._performance_metrics.get_current_metrics()
        
        metrics_text = f"""
📈 请求统计:
  • 总请求数: {metrics.get('total_requests', 0)}
  • 成功: {metrics.get('successful_requests', 0)} | 失败: {metrics.get('failed_requests', 0)}
  • 成功率: {metrics.get('success_rate', 0):.1f}%

⏱️ 响应时间:
  • 平均响应: {metrics.get('avg_response_time_ms', 0):.0f} ms

📝 Token统计:
  • 平均Token数: {metrics.get('avg_token_count', 0)}
  • Token/秒: {metrics.get('tokens_per_second', 0):.1f}

🔧 工具调用:
  • 总调用次数: {metrics.get('total_tool_calls', 0)}

📚 RAG:
  • RAG命中次数: {metrics.get('rag_hit_count', 0)}
"""
        tk.Label(metrics_frame, text=metrics_text, font=("Consolas", 10),
                bg=self.bg_color, fg=self.text_color, justify=tk.LEFT, anchor=tk.W).pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        history_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(history_frame, text="📜 历史记录")
        
        history_text = scrolledtext.ScrolledText(history_frame, font=("Consolas", 9), bg="#f7fafc")
        history_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        history = self._performance_metrics.get_history(5)
        for h in reversed(history):
            duration = h.get('duration_ms', 0)
            tokens = h.get('token_count', 0)
            input_preview = (h.get('user_input') or '')[:30]
            success = h.get('success', False)
            status = "✅" if success else "❌"
            history_text.insert(tk.END, f"{status} [{duration:.0f}ms] {tokens} tokens | {input_preview}...\n")
        
        history_text.config(state=tk.DISABLED)
        
        # 调试标签页
        debug_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(debug_frame, text="🔍 调试")
        
        debug_info = self._debug_manager.get_debug_info()
        
        debug_text = f"""
🐛 调试状态: {'已启用' if debug_info.get('enabled') else '已禁用'}

📍 断点:
  • 断点数量: {len(debug_info.get('breakpoints', {}))}
  • 命中次数: {debug_info.get('hit_count', 0)}

📚 调用栈:
  • 栈深度: {debug_info.get('stack_depth', 0)}

👁️ 监视变量:
  • 变量数量: {debug_info.get('watch_vars', 0)}
"""
        tk.Label(debug_frame, text=debug_text, font=("Consolas", 10),
                bg=self.bg_color, fg=self.text_color, justify=tk.LEFT, anchor=tk.W).pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        btn_frame = tk.Frame(main_frame, bg=self.bg_color)
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        
        def toggle_debug():
            if self._debug_manager.debug_enabled:
                self._debug_manager.disable_debug()
                toggle_btn.config(text="启用调试", bg="#6b7280")
            else:
                self._debug_manager.enable_debug()
                toggle_btn.config(text="禁用调试", bg=self.error_color)
            dialog.destroy()
            self._show_debug_panel()
        
        def clear_metrics():
            self._performance_metrics.metrics_history.clear()
            self._debug_manager.clear()
            dialog.destroy()
            self._show_debug_panel()
        
        toggle_btn = tk.Button(btn_frame, text="禁用调试" if self._debug_manager.debug_enabled else "启用调试",
                             command=toggle_debug,
                             bg=self.error_color if self._debug_manager.debug_enabled else "#6b7280",
                             fg="white", font=("Microsoft YaHei UI", 10),
                             width=12, relief=tk.FLAT, padx=10, pady=6)
        toggle_btn.pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="清空数据", command=clear_metrics,
                 bg="#f59e0b", fg="white", font=("Microsoft YaHei UI", 10),
                 width=12, relief=tk.FLAT, padx=10, pady=6).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="关闭", command=dialog.destroy,
                 bg="#9ca3af", fg="white", font=("Microsoft YaHei UI", 10),
                 width=12, relief=tk.FLAT, padx=10, pady=6).pack(side=tk.RIGHT, padx=5)

    # ==================== 对话侧边导航 ====================

    def _add_nav_block(self, bg_tag: str, content: str):
        """添加对话块到导航侧边栏"""
        role_map = {
            "user_bg": "👤",
            "assistant_bg": "🤖",
            "system_bg": "⚙️",
            "tool_bg": "🔧",
            "thinking_bg": "💭",
            "error_bg": "❌",
        }
        icon = role_map.get(bg_tag, "📄")
        label = f"{icon} {content[:25].replace(chr(10), ' ')}"

        self._nav_blocks.append({"icon": icon, "content": content, "label": label})
        self._nav_current_idx = len(self._nav_blocks) - 1

        self.nav_listbox.insert(tk.END, label)
        self.nav_listbox.selection_clear(0, tk.END)
        self.nav_listbox.selection_set(tk.END)
        self.nav_listbox.see(tk.END)

    def _on_nav_select(self, event):
        """导航选择 - 快速跳转到对应块"""
        selection = self.nav_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx < 0 or idx >= len(self._nav_blocks):
            return
        self._nav_current_idx = idx

        if self._nav_show_all_mode:
            # 全部模式：滚动到对应块标记
            tag_name = f"nav_block_{idx}"
            try:
                self.chat_text.see(tag_name)
            except tk.TclError:
                pass
        else:
            # 选中模式：只显示这个块
            self._rebuild_chat_for_nav()

    def _nav_prev(self):
        """上一块"""
        if self._nav_current_idx > 0:
            self._nav_current_idx -= 1
            self.nav_listbox.selection_clear(0, tk.END)
            self.nav_listbox.selection_set(self._nav_current_idx)
            self.nav_listbox.see(self._nav_current_idx)
            self._jump_to_nav_block(self._nav_current_idx)

    def _nav_next(self):
        """下一块"""
        if self._nav_current_idx < len(self._nav_blocks) - 1:
            self._nav_current_idx += 1
            self.nav_listbox.selection_clear(0, tk.END)
            self.nav_listbox.selection_set(self._nav_current_idx)
            self.nav_listbox.see(self._nav_current_idx)
            self._jump_to_nav_block(self._nav_current_idx)

    def _nav_show_all(self):
        """显示全部块"""
        self._nav_show_all_mode = True
        self._rebuild_chat_for_nav()

    def _nav_show_selected(self):
        """只显示选中块"""
        self._nav_show_all_mode = False
        if self._nav_current_idx >= 0:
            self._rebuild_chat_for_nav()

    def _jump_to_nav_block(self, idx: int):
        """跳转到指定块"""
        if self._nav_show_all_mode:
            tag_name = f"nav_block_{idx}"
            try:
                self.chat_text.see(tag_name)
            except tk.TclError:
                pass
        else:
            self._rebuild_chat_for_nav()

    def _rebuild_chat_for_nav(self):
        """根据导航模式重建聊天区"""
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        self.chat_text.config(state=tk.DISABLED)

        if self._nav_show_all_mode:
            # 重新发送所有消息到聊天区
            for i, block in enumerate(self._nav_blocks):
                self._render_nav_block(i, block)
        else:
            if 0 <= self._nav_current_idx < len(self._nav_blocks):
                block = self._nav_blocks[self._nav_current_idx]
                self._render_nav_block(self._nav_current_idx, block)

    def _on_nav_double_click(self, event):
        """双击导航项 - 自动跳转到选中块"""
        self._on_nav_select(event)
        # 双击时自动切换到"选中"模式，聚焦显示该块
        self._nav_show_selected()

    def _on_nav_key_up(self, event):
        """方向键上 - 切换到上一块"""
        self._nav_prev()
        return "break"

    def _on_nav_key_down(self, event):
        """方向键下 - 切换到下一块"""
        self._nav_next()
        return "break"

    def _render_nav_block(self, idx: int, block: dict):
        """渲染单个导航块到聊天区"""
        self.chat_text.config(state=tk.NORMAL)

        # 添加导航标记
        tag_name = f"nav_block_{idx}"
        self.chat_text.mark_set(tag_name, tk.END)
        self.chat_text.mark_gravity(tag_name, tk.LEFT)

        # 块分隔线
        if idx > 0:
            self.chat_text.insert(tk.END, f"─── 对话块 {idx} ───\n", "time")

        # 根据图标确定背景色
        icon = block["icon"]
        bg_tag = "system_bg"
        if icon == "👤":
            bg_tag = "user_bg"
        elif icon == "🤖":
            bg_tag = "assistant_bg"
        elif icon == "🔧":
            bg_tag = "tool_bg"
        elif icon == "💭":
            bg_tag = "thinking_bg"
        elif icon == "❌":
            bg_tag = "error_bg"

        self.chat_text.insert(tk.END, f"{icon} ", "icon")
        self.chat_text.insert(tk.END, block["content"] + "\n\n", bg_tag)
        self.chat_text.see(tk.END)
        self.chat_text.config(state=tk.DISABLED)
