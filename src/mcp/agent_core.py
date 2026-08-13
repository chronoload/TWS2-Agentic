#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 核心系统 — 从 agent_assistant(GUI) 迁移的可独立运行能力层。

背景：agent_assistant.py 是 tkinter 窗口，其中包含大量不依赖 GUI 的核心能力
（断点调试/性能指标/会话历史/后台模块初始化/工作流/RAG/上下文注入等）。
本模块把这些能力收敛为 AgentCore，供服务端（mcp/server/app.py）、CLI、
未来前端直接初始化 —— 系统不再依赖 GUI 窗口也具备这些能力。

无 tkinter 依赖。agent_assistant.py 保持向后兼容（仍可引用本模块类）。

包含：
  - DebugManager        Agent 断点调试管理器
  - PerformanceMetrics  性能指标收集器
  - ConversationMessage / Conversation / ConversationHistory  会话历史(SQLite)
  - AgentCore           统一初始化：工作流引擎/插件系统/Agent/审批/RAG/上下文压缩
  - get_agent_core()    全局单例
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============ Agent 断点调试管理器 ============

class DebugManager:
    """Agent断点调试管理器（自 agent_assistant 迁移）"""

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
        self.breakpoint_hits.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "context": context.copy() if context else {},
        })
        return True

    def watch_variable(self, name: str, value: Any):
        self.watch_variables[name] = {"value": value, "timestamp": datetime.now().isoformat()}

    def push_stack(self, func_name: str, params: Dict = None):
        self.call_stack.append({
            "function": func_name,
            "params": params.copy() if params else {},
            "timestamp": datetime.now().isoformat(),
        })

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
        return {
            "enabled": self.debug_enabled,
            "breakpoints": self.breakpoints,
            "hit_count": len(self.breakpoint_hits),
            "stack_depth": len(self.call_stack),
            "watch_vars": len(self.watch_variables),
        }


# ============ 性能指标收集器 ============

class PerformanceMetrics:
    """性能指标收集器（自 agent_assistant 迁移）"""

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
        self.current_request = {
            "id": request_id,
            "user_input": user_input[:100],
            "start_time": datetime.now(),
            "start_timestamp": datetime.now().timestamp(),
            "token_count": 0,
            "tool_calls": [],
            "rag_used": False,
            "stages": {},
        }
        return request_id

    def record_stage(self, stage_name: str):
        if self.current_request:
            self.current_request["stages"][stage_name] = {
                "start": datetime.now(), "timestamp": datetime.now().timestamp(),
            }

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
            self.current_request["tool_calls"].append({
                "name": tool_name, "timestamp": datetime.now().isoformat(),
            })
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
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0,
            "avg_response_time_ms": round(self.avg_response_time, 2),
            "avg_token_count": self.avg_token_count,
            "tokens_per_second": round(self.tokens_per_second, 2),
            "total_tool_calls": self.tool_call_count,
            "rag_hit_count": self.rag_hit_count,
        }

    def get_history(self, limit: int = 10) -> List[Dict]:
        return self.metrics_history[-limit:]


# ============ 会话历史（SQLite 持久化） ============

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
    """对话历史管理器 - 类似 Cline 的会话存储（自 agent_assistant 迁移）"""

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

        # 迁移：添加 tool_args / tool_calls 列（如果不存在）
        for col in ("tool_args", "tool_calls"):
            try:
                cursor.execute(f"ALTER TABLE messages ADD COLUMN {col} TEXT")
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




# ============ attach_agent_core：把核心能力注入 Agent 实例 ============
# 设计：不创建旁路单例，而是把 agent_assistant 的非 GUI 能力
# 直接挂在 Agent 实例上（agent.debug_manager / agent.plugin_manager / ...），
# 由 agent.py 的 create_agent / Agent.__init__ 在实例化时调用。

_logger = logging.getLogger(__name__)


def _schema_desc(schema: Dict[str, Any]) -> str:
    """从 ToolRegistration.schema 提取描述（兼容 OpenAI function 格式与简写）。"""
    if not schema:
        return "插件工具"
    fn = schema.get("function", {}) if isinstance(schema.get("function"), dict) else {}
    if fn.get("description"):
        return fn["description"]
    return schema.get("description") or "插件工具"


def _schema_params(schema: Dict[str, Any]) -> Dict[str, Any]:
    """从 ToolRegistration.schema 提取 parameters（缺省给空 object）。"""
    if not schema:
        return {"type": "object", "properties": {}}
    fn = schema.get("function", {}) if isinstance(schema.get("function"), dict) else {}
    if fn.get("parameters"):
        return fn["parameters"]
    return schema.get("parameters") or {"type": "object", "properties": {}}


def _wrap_plugin_tool(reg) -> Any:
    """把插件 ToolRegistration 包装为 tools.Tool 子类实例（动态类）。"""
    try:
        from .tools import Tool
    except ImportError:
        return None

    class _PluginTool(Tool):
        # 类级默认值（会被下面实例级覆盖，避免污染类变量）
        pass

    _PluginTool.name = reg.name
    _PluginTool.description = _schema_desc(reg.schema)
    _PluginTool.parameters = _schema_params(reg.schema)
    _PluginTool.category = f"plugin_{getattr(reg, 'toolset', '') or 'misc'}"
    _PluginTool.keywords = [reg.name, getattr(reg, "toolset", "") or ""]
    _PluginTool.risk_level = getattr(reg, "risk_level", "medium") or "medium"
    _PluginTool.model_hint = f"[何时使用] 插件「{reg.toolset}」提供的工具，直接调用 handler 执行。"

    def execute(self, **kwargs):
        try:
            result = reg.handler(**kwargs)
        except TypeError:
            # 兼容只接收单个 dict 的 handler
            result = reg.handler(kwargs)
        if result is None:
            return "（插件工具执行完成，无返回值）"
        if isinstance(result, (dict, list)):
            try:
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                return str(result)
        return str(result)

    _PluginTool.execute = execute
    # Tool 是 ABC：类定义时 execute 未实现 → __abstractmethods__ 缓存了 {'execute'}，
    # 需在补齐实现后显式清空，否则无法实例化。
    _PluginTool.__abstractmethods__ = frozenset()
    return _PluginTool()


def attach_agent_core(agent, background: bool = True) -> Dict:
    """把 agent_assistant 的核心能力注入 Agent 实例（合并进 agent 设计）。

    注入内容（全部挂在 agent 上，惰性/后台初始化，失败不阻塞）：
      - agent.debug_manager / agent.metrics / agent.conversation_history（常驻）
      - agent.plugin_manager + 插件工具桥接（ToolRegistration → Tool 并入 tools/_tool_map）
      - agent.workflow_engine（复用全局单例 get_workflow_engine，不重复创建）
      - agent.git_searcher / agent.kg_rag（后台惰性）
      - agent.load_rag() / agent.async_compact() / agent.submit_workflow() 等方法

    返回注入摘要 dict。
    """
    injected: Dict[str, Any] = {"debug": False, "metrics": False, "conversation": False,
                                "plugin_tools": 0, "workflow": False}
    base_path = Path(getattr(agent.config, "base_dir", None) or Path.cwd())

    try:  # 1. 常驻组件
        agent.debug_manager = DebugManager()
        injected["debug"] = True
    except Exception as e:
        _logger.warning("[attach_agent_core] debug_manager 注入失败: %s", e)

    try:
        agent.metrics = PerformanceMetrics()
        injected["metrics"] = True
    except Exception as e:
        _logger.warning("[attach_agent_core] metrics 注入失败: %s", e)

    try:
        agent.conversation_history = ConversationHistory(
            str(base_path / "data" / "ws2_agent_history.db"))
        injected["conversation"] = True
    except Exception as e:
        _logger.warning("[attach_agent_core] conversation_history 注入失败: %s", e)

    # 2. 插件系统 + 工具桥接（补齐 agent_assistant 只 discover 不 load_all 的缺口）
    try:
        from .plugins.plugin_manager import PluginManager
        pm = PluginManager(plugins_dirs=[base_path / "plugins"])
        pm.discover_plugins()
        pm.load_all()
        agent.plugin_manager = pm

        # 桥接：把插件工具并入 agent.tools 与 _tool_map
        added = 0
        for reg_name, reg in pm.get_all_tools().items():
            # get_all_tools 可能是 ToolRegistration 或已包装对象
            if hasattr(reg, "schema") and hasattr(reg, "handler"):
                tool = _wrap_plugin_tool(reg)
                if tool is None:
                    continue
                # 重名保护：插件工具优先以 plugin_ 前缀注册，避免覆盖内置
                final_name = tool.name
                if final_name in getattr(agent, "_tool_map", {}) or final_name in {t.name for t in getattr(agent, "tools", [])}:
                    final_name = f"plugin_{final_name}"
                    tool.name = final_name
                if not hasattr(agent, "tools"):
                    agent.tools = []
                agent.tools.append(tool)
                if hasattr(agent, "_tool_map"):
                    agent._tool_map[final_name] = tool
                added += 1
        injected["plugin_tools"] = added
        _logger.info("[attach_agent_core] 插件桥接完成: +%d 工具", added)
    except Exception as e:
        _logger.warning("[attach_agent_core] 插件系统注入失败: %s", e)

    # 3. 工作流引擎（复用进程内全局单例）
    try:
        from .workflow_engine import get_workflow_engine
        agent.workflow_engine = get_workflow_engine(base_path / "data" / "workflow.db")
        injected["workflow"] = True
    except Exception as e:
        _logger.warning("[attach_agent_core] workflow 注入失败: %s", e)
        agent.workflow_engine = None

    # 4. 后台惰性模块（git searcher / knowledge graph）
    def _lazy_background():
        try:
            from .agent_assistant import _lazy_import_git_searcher, _lazy_import_kg_rag
            try:
                get_git_searcher = _lazy_import_git_searcher()
                agent.git_searcher = get_git_searcher(base_path / "data" / "git_cache")
            except Exception as e:
                _logger.warning("[attach_agent_core] git_searcher 加载失败: %s", e)
                agent.git_searcher = None
            try:
                get_kg_rag = _lazy_import_kg_rag()
                agent.kg_rag = get_kg_rag(base_path / "data" / "knowledge_graph.db")
            except Exception as e:
                _logger.warning("[attach_agent_core] kg_rag 加载失败: %s", e)
                agent.kg_rag = None
        except Exception as e:
            _logger.warning("[attach_agent_core] 后台模块加载失败: %s", e)

    if background:
        threading.Thread(target=_lazy_background, daemon=True).start()
    else:
        _lazy_background()

    # 5. 注入方法（RAG / 上下文压缩 / 工作流操作 / 状态）
    def _load_rag() -> bool:
        if getattr(agent, "_rag_loaded", False):
            return True
        try:
            from .agent_assistant import _lazy_import_rag
            initialize_rag_for_agent, _ = _lazy_import_rag()
            agent.rag_manager = initialize_rag_for_agent(str(base_path), ws2_system=getattr(agent.config, "ws2_system", None))
            agent._rag_loaded = True
            return True
        except Exception as e:
            _logger.warning("[attach_agent_core] RAG 加载失败: %s", e)
            return False

    def _async_compact():
        try:
            from .agent_assistant import _lazy_import_compactor
            auto_compact, _ = _lazy_import_compactor()
            return auto_compact(agent)
        except Exception as e:
            _logger.warning("[attach_agent_core] 上下文压缩失败: %s", e)
            return None

    def _submit_workflow(workflow_type: str, input_data: Dict[str, Any] = None) -> str:
        engine = getattr(agent, "workflow_engine", None)
        if engine is None:
            raise RuntimeError("workflow_engine 未就绪")
        from .predefined_workflows import get_workflow
        wf_def = get_workflow(workflow_type)
        return engine.start_workflow(wf_def, input_data or {})

    def _resume_workflow(instance_id: str) -> bool:
        engine = getattr(agent, "workflow_engine", None)
        return bool(engine and engine.resume_workflow(instance_id))

    def _list_recoverable_workflows():
        engine = getattr(agent, "workflow_engine", None)
        return engine.list_recoverable() if engine else []

    def _core_status() -> Dict:
        return {
            "debug_manager": getattr(agent, "debug_manager", None) is not None,
            "metrics": getattr(agent, "metrics", None) is not None,
            "conversation_history": getattr(agent, "conversation_history", None) is not None,
            "plugin_tools": sum(1 for t in getattr(agent, "tools", []) if getattr(t, "category", "").startswith("plugin_")),
            "workflow_engine": getattr(agent, "workflow_engine", None) is not None,
            "git_searcher": getattr(agent, "git_searcher", None) is not None,
            "kg_rag": getattr(agent, "kg_rag", None) is not None,
            "rag": getattr(agent, "_rag_loaded", False),
        }

    agent.load_rag = _load_rag
    agent.async_compact = _async_compact
    agent.submit_workflow = _submit_workflow
    agent.resume_workflow = _resume_workflow
    agent.list_recoverable_workflows = _list_recoverable_workflows
    agent.agent_core_status = _core_status

    _logger.info("[attach_agent_core] 注入完成: %s", injected)
    return injected


__all__ = [
    "DebugManager", "PerformanceMetrics",
    "ConversationMessage", "Conversation", "ConversationHistory",
    "attach_agent_core",
]
