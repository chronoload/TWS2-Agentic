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
    )
    HAS_CACHE = True
except ImportError as e:
    HAS_CACHE = False
    print(f"缓存模块加载失败: {e}")

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
    """对话消息结构"""
    id: str
    role: str  # system, user, assistant, tool
    content: str
    reasoning_content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[str] = None
    tool_calls: Optional[str] = None  # JSON 字符串，存储 assistant 消息的 tool_calls
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
        
        # 将 tool_args 转换为 JSON 字符串
        tool_args_json = None
        if message.tool_args:
            try:
                tool_args_json = json.dumps(message.tool_args, ensure_ascii=False)
            except (TypeError, ValueError):
                tool_args_json = str(message.tool_args)
        
        cursor.execute("""
            INSERT INTO messages 
            (id, conversation_id, role, content, reasoning_content, tool_call_id, tool_name, tool_args, tool_result, timestamp, approved, rejected)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            1 if message.rejected else 0
        ))
        cursor.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), conversation_id)
        )
        conn.commit()
        conn.close()
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        conn = sqlite3.connect(self.db_path)
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
            # 解析 tool_args（可能是JSON字符串）
            tool_args_raw = mr[7]
            tool_args = None
            if tool_args_raw:
                try:
                    tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                except (json.JSONDecodeError, TypeError):
                    tool_args = tool_args_raw
            
            messages.append({
                "id": mr[0],
                "role": mr[2],
                "content": mr[3],
                "reasoning_content": mr[4],
                "tool_call_id": mr[5],
                "tool_name": mr[6],
                "tool_args": tool_args,
                "tool_result": mr[8],
                "timestamp": mr[9],
                "approved": bool(mr[10]),
                "rejected": bool(mr[11])
            })
        
        return Conversation(
            id=row[0],
            title=row[1],
            created_at=row[2],
            updated_at=row[3],
            messages=messages,
            metadata=json.loads(row[4]) if row[4] else {}
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


class ToolApprovalDialog:
    """现代化的工具调用审批对话框"""
    
    def __init__(self, parent: tk.Tk, tool_name: str, tool_args: Dict, tool_result: str):
        self.parent = parent
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.tool_result = tool_result
        self.approved = False
        self.dialog = None
    
    def show(self) -> bool:
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(f"工具调用审批: {self.tool_name}")
        self.dialog.geometry("850x650")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        bg_color = "#f5f7fa"
        self.dialog.configure(bg=bg_color)
        
        main_frame = tk.Frame(self.dialog, bg=bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = tk.Label(main_frame, text=f"🔧 工具调用: {self.tool_name}",
                              font=("Microsoft YaHei UI", 16, "bold"),
                              bg=bg_color, fg="#2d3748")
        title_label.pack(anchor=tk.W, pady=(0, 20))
        
        args_frame = tk.LabelFrame(main_frame, text="📋 工具参数",
                                    bg="#ffffff", fg="#4a5568",
                                    font=("Microsoft YaHei UI", 10, "bold"),
                                    padx=10, pady=10)
        args_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 15))
        args_text = scrolledtext.ScrolledText(args_frame, height=6,
                                               font=("Consolas", 10),
                                               bg="#f7fafc", fg="#2d3748",
                                               insertbackground="#2d3748")
        args_text.pack(fill=tk.BOTH, expand=True)
        args_text.insert(1.0, json.dumps(self.tool_args, ensure_ascii=False, indent=2))
        args_text.config(state=tk.DISABLED)
        
        result_frame = tk.LabelFrame(main_frame, text="📤 执行结果",
                                      bg="#ffffff", fg="#4a5568",
                                      font=("Microsoft YaHei UI", 10, "bold"),
                                      padx=10, pady=10)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        result_text = scrolledtext.ScrolledText(result_frame, height=12,
                                                 font=("Consolas", 10),
                                                 bg="#f7fafc", fg="#2d3748",
                                                 insertbackground="#2d3748")
        result_text.pack(fill=tk.BOTH, expand=True)
        result_text.insert(1.0, self.tool_result)
        result_text.config(state=tk.DISABLED)
        
        dangerous_tools = ["write_note", "add_bookmark", "delete_note", "delete_bookmark",
                          "write_file", "delete_file", "edit_file"]
        if self.tool_name in dangerous_tools:
            warning_frame = tk.Frame(main_frame, bg="#fef2f2", bd=1, relief=tk.SOLID)
            warning_frame.pack(fill=tk.X, pady=(0, 15), ipady=8)
            warning_label = tk.Label(warning_frame, text="⚠️ 高风险操作！请仔细核对结果。",
                                    font=("Microsoft YaHei UI", 10),
                                    bg="#fef2f2", fg="#dc2626")
            warning_label.pack()
        
        button_frame = tk.Frame(main_frame, bg=bg_color)
        button_frame.pack(pady=10)
        
        approve_btn = tk.Button(button_frame, text="✅ 批准", command=self._approve,
                               bg="#10b981", fg="white",
                               font=("Microsoft YaHei UI", 11, "bold"),
                               width=14, height=1, relief=tk.FLAT, padx=10, pady=8)
        approve_btn.pack(side=tk.LEFT, padx=5)
        
        reject_btn = tk.Button(button_frame, text="❌ 拒绝", command=self._reject,
                              bg="#ef4444", fg="white",
                              font=("Microsoft YaHei UI", 11, "bold"),
                              width=14, height=1, relief=tk.FLAT, padx=10, pady=8)
        reject_btn.pack(side=tk.LEFT, padx=5)
        
        retry_btn = tk.Button(button_frame, text="🔄 重试", command=self._retry,
                             bg="#6b7280", fg="white",
                             font=("Microsoft YaHei UI", 11, "bold"),
                             width=14, height=1, relief=tk.FLAT, padx=10, pady=8)
        retry_btn.pack(side=tk.LEFT, padx=5)
        
        self.dialog.wait_window()
        return self.approved
    
    def _approve(self):
        self.approved = True
        self.dialog.destroy()
    
    def _reject(self):
        self.approved = False
        self.dialog.destroy()
    
    def _retry(self):
        self.approved = None
        self.dialog.destroy()


class ChangeComparisonDialog:
    """现代化的变更对比对话框"""
    
    def __init__(self, parent: tk.Tk, title: str, old_content: str, new_content: str, file_type: str = "笔记"):
        self.parent = parent
        self.title = title
        self.old_content = old_content
        self.new_content = new_content
        self.file_type = file_type
        self.dialog = None
    
    def show(self):
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(f"变更对比: {self.title}")
        self.dialog.geometry("1100x750")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        bg_color = "#f5f7fa"
        self.dialog.configure(bg=bg_color)
        
        main_frame = tk.Frame(self.dialog, bg=bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = tk.Label(main_frame, text=f"📝 {self.file_type}变更对比: {self.title}",
                              font=("Microsoft YaHei UI", 16, "bold"),
                              bg=bg_color, fg="#2d3748")
        title_label.pack(anchor=tk.W, pady=(0, 20))
        
        compare_frame = tk.Frame(main_frame, bg=bg_color)
        compare_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        left_frame = tk.LabelFrame(compare_frame, text="❌ 修改前",
                                    bg="#ffffff", fg="#4a5568",
                                    font=("Microsoft YaHei UI", 11, "bold"),
                                    padx=12, pady=12)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        old_text = scrolledtext.ScrolledText(left_frame, width=55, height=26,
                                              font=("Consolas", 10),
                                              bg="#fef2f2", fg="#dc2626",
                                              insertbackground="#dc2626")
        old_text.pack(fill=tk.BOTH, expand=True)
        old_text.insert(1.0, self.old_content)
        old_text.config(state=tk.DISABLED)
        
        right_frame = tk.LabelFrame(compare_frame, text="✅ 修改后",
                                     bg="#ffffff", fg="#4a5568",
                                     font=("Microsoft YaHei UI", 11, "bold"),
                                     padx=12, pady=12)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        new_text = scrolledtext.ScrolledText(right_frame, width=55, height=26,
                                              font=("Consolas", 10),
                                              bg="#f0fdf4", fg="#16a34a",
                                              insertbackground="#16a34a")
        new_text.pack(fill=tk.BOTH, expand=True)
        new_text.insert(1.0, self.new_content)
        new_text.config(state=tk.DISABLED)
        
        old_lines = self.old_content.split('\n')
        new_lines = self.new_content.split('\n')
        added = len([l for l in new_lines if l not in old_lines])
        removed = len([l for l in old_lines if l not in new_lines])
        
        stats_frame = tk.Frame(main_frame, bg="#eff6ff", bd=1, relief=tk.SOLID, padx=15, pady=10)
        stats_frame.pack(fill=tk.X, pady=(0, 15))
        stats_text = f"📊 变更统计: +{min(added, len(new_lines))} 行, -{min(removed, len(old_lines))} 行, ~{min(added, removed)} 行"
        tk.Label(stats_frame, text=stats_text, font=("Microsoft YaHei UI", 11),
                bg="#eff6ff", fg="#1e40af").pack()
        
        button_frame = tk.Frame(main_frame, bg=bg_color)
        button_frame.pack(pady=10)
        
        confirm_btn = tk.Button(button_frame, text="✅ 确认应用", command=self.dialog.destroy,
                               bg="#3b82f6", fg="white",
                               font=("Microsoft YaHei UI", 11, "bold"),
                               width=16, height=1, relief=tk.FLAT, padx=10, pady=8)
        confirm_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(button_frame, text="❌ 取消", command=self._cancel,
                              bg="#6b7280", fg="white",
                              font=("Microsoft YaHei UI", 11, "bold"),
                              width=16, height=1, relief=tk.FLAT, padx=10, pady=8)
        cancel_btn.pack(side=tk.LEFT, padx=5)
    
    def _cancel(self):
        self.dialog.destroy()


class AgentAssistantWindow:
    """
    现代化的 Cline 风格 Agent 助手窗口 - 完全增强版
    """
    
    def __init__(self, parent: tk.Tk, base_path: str, system=None, project_mgr=None, task_board_mgr=None, config=None):
        self.parent = parent
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.system = system
        self.project_mgr = project_mgr
        self.task_board_mgr = task_board_mgr
        self.config = config
        self.agent = None
        self.conversation_history = ConversationHistory()
        self.current_conversation_id = None
        self.current_conversation_title = "新对话"
        self.is_processing = False
        self.should_stop = False
        
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
        self._context_reloader = ContextReloader() if HAS_CACHE else None
        
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
        
        # 开始监听主窗口语境变化
        self._start_context_monitoring()
    
    def _create_ui(self):
        """创建现代化的 UI"""
        main_frame = tk.Frame(self.window, bg=self.bg_color)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self._create_header(main_frame)
        self._create_infra_status_panel(main_frame)
        self._create_toolbar(main_frame)
        self._create_chat_area(main_frame)
        self._create_input_area(main_frame)
        self._create_status_bar(main_frame)
        
        self._refresh_history_list()
    
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
        
        cp_btn = tk.Button(toolbar_frame, text="📌", command=self._create_checkpoint, **btn_style)
        cp_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        # 检查点回退按钮
        rollback_btn = tk.Button(toolbar_frame, text="↩️", command=self._show_checkpoint_list, **btn_style)
        rollback_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
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
        
        tk.Frame(toolbar_frame, width=2, bg=self.border_color).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=6)
        
        # RAG 知识库按钮
        rag_btn = tk.Button(toolbar_frame, text="📚", command=self._show_rag_controls, **btn_style)
        rag_btn.pack(side=tk.LEFT, padx=4, pady=6)
        
        # 调试/性能指标按钮
        debug_btn = tk.Button(toolbar_frame, text="🔧", command=self._show_debug_panel, **btn_style)
        debug_btn.pack(side=tk.LEFT, padx=4, pady=6)
    
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
                                                   state=tk.DISABLED)
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        # 绑定右键菜单
        self.chat_text.bind("<Button-3>", self._show_chat_context_menu)

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
                    AutoCompact, _ = _lazy_import_compactor()
                    self._compactor = AutoCompact(max_tokens=100000, threshold=0.90, keep_recent=4)
                    self._compactor_loaded = True
                except Exception as e:
                    print(f"[Async] AutoCompact加载失败: {e}")

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
            
            # 构建欢迎消息，包含语境信息
            welcome_msg = "🤖 **WS2 Agent 已就绪！**\n\n"
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
        """全面检查和修复文本格式 - 增强完善版"""
        if not content:
            return content
        
        result = content
        
        try:
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
            self._reason_label.config(text=f"推理: {'✅ 支持' if can_reason else '❌ 不支持'}")
            
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
        """将消息添加到可选中的聊天区域 - 优化版：简化渲染"""
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
        
        # 简化渲染：直接插入内容，保留基本样式标签
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
    
    def _append_tool_message(self, tool_name: str, tool_args: Dict = None, tool_result: str = None, is_thinking: bool = False, return_positions: bool = False):
        """添加工具调用消息 - 统一格式显示"""
        content_lines = []
        
        if is_thinking:
            content_lines.append(f"**计划调用**: {tool_name}")
        else:
            content_lines.append(f"**执行工具**: {tool_name}")
        
        if tool_args:
            content_lines.append("")
            content_lines.append("**参数**:")
            args_str = json.dumps(tool_args, ensure_ascii=False, indent=2)
            content_lines.append(args_str)
        
        if tool_result:
            content_lines.append("")
            content_lines.append("**结果**:")
            # 不截断结果，显示完整内容
            content_lines.append(tool_result)
        
        content = "\n".join(content_lines)
        
        icon = "💡" if is_thinking else "🔧"
        
        if return_positions:
            return self._append_message_to_chat(content, "tool_bg", icon, return_positions=True)
        else:
            return self._append_message_to_chat(content, "tool_bg", icon)

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
        if self.agent:
            self.agent.reset()
        
        self.current_conversation_id = self.conversation_history.create_conversation("新对话")
        self.current_conversation_title = "新对话"
        self._is_first_message = True  # 标记为第一条消息
        if hasattr(self, 'conversation_var'):
            self.conversation_var.set(self.current_conversation_title)
        
        # 清空聊天区域
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete(1.0, tk.END)
        self.chat_text.config(state=tk.DISABLED)

        # 清空导航侧边栏
        self._nav_blocks.clear()
        self._nav_current_idx = -1
        self.nav_listbox.delete(0, tk.END)

        self._init_agent()
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
        conversations = self.conversation_history.list_conversations()
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
    
    def _load_conversation(self, conversation_id: str):
        conversation = self.conversation_history.get_conversation(conversation_id)
        if not conversation:
            return
        
        self.current_conversation_id = conversation_id
        self.current_conversation_title = conversation.title
        self._is_first_message = False  # 已加载的对话不是新对话
        if hasattr(self, 'conversation_var'):
            self.conversation_var.set(self.current_conversation_title)
        
        # 清空聊天区域
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete(1.0, tk.END)
        self.chat_text.config(state=tk.DISABLED)

        # 清空导航侧边栏
        self._nav_blocks.clear()
        self._nav_current_idx = -1
        self.nav_listbox.delete(0, tk.END)

        # 重新初始化 Agent 的 messages
        if self.agent and hasattr(self.agent, 'messages'):
            # 重置为自定义系统提示词
            custom_system_prompt = self._get_contextualized_system_prompt()
            self.agent.messages = [{"role": "system", "content": custom_system_prompt}]
        
        # 加载对话历史到界面和 Agent 的 messages 中
        for msg in conversation.messages:
            role = msg.get("role", "assistant")
            content = msg.get("content", "")
            
            # 显示到界面
            if role == "tool":
                tool_name = msg.get("tool_name", "tool")
                tool_args = msg.get("tool_args", {})
                tool_result = msg.get("tool_result", "")
                self._append_tool_message(tool_name, tool_args=tool_args, tool_result=tool_result)
                # 不同步到 Agent messages：API 要求 tool 消息前面必须有 assistant 消息带 tool_calls，
                # 而恢复对话时无法重建 tool_calls 结构，跳过 tool 消息避免 API 400 错误
            elif role == "thinking":
                self._append_assistant_message(content, is_thinking=True)
                # 思考内容通常不加入对话历史
            elif role == "user":
                self._append_user_message(content)
                # 同步到 Agent messages
                if self.agent and hasattr(self.agent, 'messages'):
                    self.agent.messages.append({
                        "role": "user",
                        "content": content
                    })
            elif role == "assistant" and content:
                self._append_assistant_message(content)
                # 同步到 Agent messages
                if self.agent and hasattr(self.agent, 'messages'):
                    # 处理推理内容
                    reasoning_content = msg.get("reasoning_content", "")
                    assistant_msg = {"role": "assistant", "content": content}
                    if reasoning_content:
                        assistant_msg["reasoning_content"] = reasoning_content
                    self.agent.messages.append(assistant_msg)
            elif role == "system":
                # 系统消息不重复添加
                pass
        
        self._refresh_history_list()
        self._update_status(f"📂 已加载: {conversation.title}")
        self._update_infra_status()
    
    def _delete_conversation(self):
        if not self.current_conversation_id:
            return
        
        if messagebox.askyesno("删除", "确定要删除当前对话吗？"):
            self.conversation_history.delete_conversation(self.current_conversation_id)
            self._new_conversation()
    
    def _refresh_history_list(self):
        if hasattr(self, 'conversation_combo'):
            conversations = self.conversation_history.list_conversations()
            current_value = self.conversation_var.get()
            values = []
            for conv in conversations:
                display = f"{conv['title'][:20]} ({conv['updated_at'][5:10]})"
                values.append(display)
            self.conversation_combo['values'] = values
            if current_value in values:
                self.conversation_combo.current(values.index(current_value))
            elif values:
                self.conversation_combo.current(0)
    
    def _on_conversation_selected(self, event=None):
        if hasattr(self, 'conversation_combo'):
            selection = self.conversation_combo.current()
            conversations = self.conversation_history.list_conversations()
            if 0 <= selection < len(conversations):
                self._load_conversation(conversations[selection]["id"])
    
    def _create_checkpoint(self):
        """创建会话检查点"""
        if not self.agent or not hasattr(self, '_context_reloader'):
            messagebox.showinfo("检查点", "检查点功能不可用")
            return
        
        try:
            checkpoint = self.agent.create_checkpoint("手动保存")
            messagebox.showinfo("检查点", f"检查点已创建！\nID: {checkpoint.checkpoint_id}\n时间: {datetime.fromtimestamp(checkpoint.timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
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
        """显示检查点列表供选择回退"""
        if not self.agent or not hasattr(self, '_context_reloader'):
            messagebox.showinfo("检查点", "检查点功能不可用")
            return
        
        try:
            # 获取所有检查点
            checkpoints = []
            for cp_id in self._context_reloader.list_checkpoints():
                cp = self._context_reloader.restore_checkpoint(cp_id)
                if cp:
                    checkpoints.append(cp)
            
            if not checkpoints:
                messagebox.showinfo("检查点", "没有找到保存的检查点")
                return
            
            # 创建选择对话框
            dialog = tk.Toplevel(self.window)
            dialog.title("选择检查点回退")
            dialog.geometry("600x450")
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
                dt_str = datetime.fromtimestamp(cp.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                summary = cp.summary or "无标题"
                msg_count = cp.total_messages
                token_count = cp.total_tokens
                list_text = f"[{dt_str}] - {summary} (消息: {msg_count}, Token: {token_count})"
                listbox.insert(tk.END, list_text)
                cp_map[i] = cp
            
            # 按钮区域
            btn_frame = tk.Frame(dialog, bg=self.bg_color)
            btn_frame.pack(fill=tk.X, pady=10, padx=15)
            
            def on_rollback():
                sel_idx = listbox.curselection()
                if not sel_idx:
                    messagebox.showwarning("提示", "请选择一个检查点")
                    return
                
                cp = cp_map[sel_idx[0]]
                
                # 确认
                result = messagebox.askyesno("确认", 
                    f"确认回退到这个检查点？\n"
                    f"时间: {datetime.fromtimestamp(cp.timestamp).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"消息数: {cp.total_messages}\n\n"
                    f"当前对话内容将被替换！")
                
                if result:
                    self._rollback_to_checkpoint(cp.checkpoint_id)
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
                self._context_reloader.delete_checkpoint(cp.checkpoint_id)
                listbox.delete(sel_idx)
                messagebox.showinfo("成功", "检查点已删除！")
            except Exception as e:
                messagebox.showerror("错误", f"删除失败: {e}")
    
    def _rollback_to_checkpoint(self, checkpoint_id: str):
        """回退到指定检查点"""
        try:
            success = self.agent.restore_checkpoint(checkpoint_id)
            
            if success:
                # 清空当前聊天区域
                self.chat_text.config(state=tk.NORMAL)
                self.chat_text.delete(1.0, tk.END)
                
                # 更新对话历史（完全替换）
                if self.current_conversation_id and hasattr(self, 'conversation_history'):
                    # 清除当前对话的所有消息
                    conn = sqlite3.connect(self.conversation_history.db_path)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", 
                                (self.current_conversation_id,))
                    conn.commit()
                    conn.close()
                
                # 重新渲染检查点中的消息，并同时保存到对话历史
                for msg in self.agent.messages:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    reasoning = msg.get("reasoning_content", "")
                    tool_calls = msg.get("tool_calls", [])
                    
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
                messagebox.showinfo("成功", "已恢复到检查点！")
                self._update_status("✅ 已恢复检查点")
            else:
                messagebox.showerror("错误", "恢复检查点失败")
        except Exception as e:
            messagebox.showerror("错误", f"恢复失败: {e}")
    
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
        
        self.is_processing = True
        self.should_stop = False
        self._update_status("⏳ 处理中...")
        
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
        
        try:
            # 初始化状态
            self._current_thinking_content = ""
            self._current_assistant_content = ""
            self._thinking_start_pos = None
            self._assistant_start_pos = None
            self.should_stop = False
            # 工具调用跟踪
            self._pending_tool_calls = {}
            
            self._performance_metrics.record_stage("init")
            
            # 每次发送消息前，更新系统提示词中的语境信息
            custom_system_prompt = self._get_contextualized_system_prompt()
            self._performance_metrics.record_stage("context")
            
            # RAG 自动检索
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
            
            # 更新 Agent 的系统提示词
            if self.agent and hasattr(self.agent, 'messages'):
                if self.agent.messages and self.agent.messages[0]["role"] == "system":
                    self.agent.messages[0]["content"] = custom_system_prompt
            
            self._performance_metrics.record_stage("agent_ready")
            
            def on_token(token: str):
                """单参数回调 - 兼容 llm.py 的统一签名"""
                if self.should_stop:
                    return
                self._performance_metrics.add_token(token)
                # 检测是否为推理内容（以 💭 或 "思考" 开头）
                token_type = "reasoning" if (token.startswith("💭") or "思考" in token[:10]) else "content"
                self.window.after(0, lambda t=token, tt=token_type: self._on_token_receive(t, tt))
            
            def on_tool(name: str, args: Dict):
                if self.should_stop:
                    return
                self._performance_metrics.add_tool_call(name)
                self.window.after(0, lambda n=name, a=args: self._on_tool_call(n, a))
            
            def on_tool_result(name: str, result: str):
                if self.should_stop:
                    return
                self.window.after(0, lambda n=name, r=result: self._on_tool_result(n, r))
            
            self._performance_metrics.record_stage("calling_agent")
            
            # 发送前最后一道安全检查
            safe_user_input = self._sanitize_for_transmission(user_input)
            
            # 调用 agent 并获取响应（直接发送用户输入，上下文已在系统提示词中）
            response = self.agent.chat(safe_user_input, on_token=on_token, on_tool=on_tool, on_tool_result=on_tool_result)
            
            if self.should_stop:
                # 如果被停止，修复并保存当前已生成的内容
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
                    self._save_message("assistant", safe_partial)
                    self._append_system_message("🛑 操作已被用户停止，已生成的内容已保存")
                else:
                    self._append_system_message("🛑 操作已被用户停止")
            else:
                self.window.after(0, lambda r=response, ids=synced_ids: self._on_response_complete(r, ids))
                
        except Exception as exc:
            import traceback
            if not self.should_stop:
                err_msg = str(exc)
                tb = traceback.format_exc()
                self.window.after(0, lambda e=err_msg, t=tb: self._on_error(e, t))
        finally:
            self.is_processing = False
            
            # === 异常时的内容抢救保存（仅在异常退出时触发） ===
            # 如果既不是正常完成（response 不存在）也不是用户停止（should_stop=False），
            # 说明是异常退出，需要抢救当前已生成的内容
            if "response" not in dir() and not self.should_stop:
                partial_content = ""
                if self._current_thinking_content:
                    partial_content += f"💭 思考过程：\n{self._fix_incomplete_output(self._current_thinking_content)}\n\n"
                if self._current_assistant_content:
                    partial_content += self._fix_incomplete_output(self._current_assistant_content)
                if partial_content:
                    safe_partial = self._sanitize_for_transmission(partial_content)
                    self._save_message("assistant", safe_partial)
                    self.window.after(0, lambda: self._append_system_message(
                        "⚠️ 异常中断，已生成的内容已自动保存"
                    ))
            
            # 结束性能指标收集
            self._performance_metrics.record_stage("complete")
            success = not self.should_stop and "response" in dir()
            self._performance_metrics.end_request(success=success)
            
            # 清理定时器
            if self._token_update_timer:
                try:
                    self.window.after_cancel(self._token_update_timer)
                except:
                    pass
                self._token_update_timer = None
            
            # 清理所有处理状态，防止缓存损坏
            self._pending_tool_calls.clear()
            self._current_thinking_content = ""
            self._current_assistant_content = ""
            self._thinking_start_pos = None
            self._assistant_start_pos = None
            self._token_buffer = ""
            self._token_accumulated = ""
            self.window.after(0, lambda: self._set_processing(False))

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
    
    def _on_tool_result(self, name: str, result: str):
        """显示工具执行结果 - 安全追加，防止缓存损坏"""
        tool_call_id = None
        tool_args = None
        
        # 对结果进行安全检查和修复
        result = self._sanitize_for_transmission(result)
        result = self._check_and_fix_format(result)
        
        # 查找对应的工具调用
        for tid, data in list(self._pending_tool_calls.items()):
            if data['name'] == name:
                tool_call_id = tid
                tool_args = data['args']
                break
        
        try:
            if tool_call_id and tool_call_id in self._pending_tool_calls:
                data = self._pending_tool_calls[tool_call_id]
                tool_end_pos = data.get('end_pos')
                
                if tool_end_pos:
                    # 安全追加结果：先确保 chat_text 为 NORMAL 状态
                    self.chat_text.config(state=tk.NORMAL)
                    
                    # 插入结果（带分隔和格式）
                    result_prefix = "\n\n**结果**:\n"
                    self.chat_text.insert(tool_end_pos, result_prefix + result)
                    
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
        
        # 保存到对话历史（带上 tool_call_id，确保后续恢复时不为 None）
        self._save_message("tool", tool_name=name, tool_args=tool_args, tool_result=result, tool_call_id=tool_call_id)

    def _on_response_complete(self, response: str, synced_ids: Optional[List[str]] = None):
        import time
        elapsed = time.time() - self._round_start_time
        # 确保最终响应被显示（如果流式没有处理完）
        response_to_save = response
        if self._current_assistant_content and not response:
            response_to_save = self._current_assistant_content
        elif self._current_thinking_content and not response_to_save:
            response_to_save = self._current_thinking_content
        
        # 完整的安全检查和修复
        response_to_save = self._sanitize_for_transmission(response_to_save)
        response_to_save = self._fix_incomplete_output(response_to_save)
        response_to_save = self._check_and_fix_format(response_to_save)
        
        # 如果我们已经有流式显示，就不再重新添加
        if not self._assistant_start_pos and not self._thinking_start_pos and response_to_save:
            self._append_assistant_message(response_to_save)
        
        # 标记事件为已同步
        if synced_ids and self._event_logger:
            try:
                self._event_logger.mark_synced(synced_ids)
            except Exception as e:
                print(f"标记事件为已同步失败: {e}")
        
        # 保存对话
        self._save_message("assistant", response_to_save)
        
        # AutoCompact 检查
        self._check_compact_context()
        
        # Checkpoint 保存
        self._save_conversation_checkpoint()
        
        if elapsed < 60:
            self._update_status(f"✅ 处理完成 ({elapsed:.1f}s)")
        else:
            self._update_status(f"✅ 处理完成 ({elapsed/60:.1f}min)")
    
    def _check_compact_context(self):
        """AutoCompact 检查 - 当上下文过大时自动压缩（异步）"""
        if not self._compactor_loaded or not self._compactor or not self.agent:
            return
        if not hasattr(self.agent, "messages") or not self.agent.messages:
            return
        # 异步执行，不阻塞UI
        threading.Thread(target=self._async_compact, daemon=True).start()

    def _async_compact(self):
        """后台执行上下文压缩"""
        try:
            if self._compactor.should_compact(self.agent.messages):
                original = len(self.agent.messages)
                self.agent.messages = self._compactor.compact(self.agent.messages)
                self.window.after(0, lambda: self._append_system_message(
                    f"🔄 上下文自动压缩: {original} → {len(self.agent.messages)} 条消息"
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
        if not processing:
            self._update_status("✅ 就绪")
        # 确保输入框始终可用
        if hasattr(self, 'input_text'):
            self.input_text.config(state=tk.NORMAL)
    
    def _save_message(self, role: str, content: str = None, reasoning_content: str = None, tool_name: str = None, tool_args: Dict = None, tool_result: str = None, tool_call_id: str = None):
        """保存消息 - 支持工具调用信息"""
        if not self.current_conversation_id:
            return
        
        # 如果没有提供 content，初始化为空字符串
        if content is None:
            content = ""
        
        # 构造正确的内容格式
        if role == "tool" and tool_name:
            content_lines = []
            content_lines.append(f"调用工具: {tool_name}")
            if tool_args:
                content_lines.append(f"\n参数: {json.dumps(tool_args, ensure_ascii=False, indent=2)}")
            if tool_result:
                content_lines.append(f"\n结果: {tool_result}")
            content = "\n".join(content_lines)
        
        # 保存前检查和修复格式
        if content:
            content = self._sanitize_for_transmission(content)
            content = self._check_and_fix_format(content)
        if reasoning_content:
            reasoning_content = self._sanitize_for_transmission(reasoning_content)
            reasoning_content = self._check_and_fix_format(reasoning_content)
        
        msg = ConversationMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            reasoning_content=reasoning_content,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            tool_call_id=tool_call_id
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
        """停止处理 - 设置标志位"""
        self.should_stop = True
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
            
            menu.add_command(label="📋 复制全部", command=self._copy_all_messages)
            menu.add_separator()
            
            # 检查点相关
            menu.add_command(label="📌 创建检查点", command=self._create_checkpoint)
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
    
    def _on_close(self):
        """清理所有资源并关闭窗口"""
        # 清理基础设施更新定时器
        if hasattr(self, '_infra_timer_id') and self._infra_timer_id:
            self.window.after_cancel(self._infra_timer_id)
        
        # 清理语境监控定时器
        if hasattr(self, '_context_timer_id') and self._context_timer_id:
            self.window.after_cancel(self._context_timer_id)
        
        self._save_window_state()
        self.window.withdraw()
    
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
            input_preview = h.get('user_input', '')[:30]
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
