"""TS2 依赖链特化生成策略：TS2 语义表（类型/helper/别名/形参提示）+ agent 内置变换。"""
from __future__ import annotations

import sys
from pathlib import Path

from .base import ChainStrategy

_MCP_ROOT = Path(__file__).resolve().parent.parent


class Ts2ChainStrategy(ChainStrategy):
    name = "ts2"

    # 已知类型 → 源文件（import 反查失败时的兜底）
    known_type_files = {
        "Agent": "mcp/agent.py",
        "SessionStore": "mcp/harness/session_store.py",
        "FileVersionDB": "mcp/middleware/file_version_db.py",
        "ContextReloader": "mcp/cache/context_reloader.py",
        "CheckpointMiddleware": "mcp/middleware/shadow_checkpoint.py",
        "MultiProviderManager": "mcp/llm.py",
        "SimulatorLLM": "mcp/llm.py",
        "Coordinator": "mcp/subagent/coordinator.py",
        "SessionAgent": "mcp/subagent/session.py",
        "ParamChain": "mcp/param_chain.py",
        "CourseSystem": "course_tracker.py",
        "ShadowGitCheckpointer": "mcp/middleware/shadow_checkpoint.py",
        "ModelSelector": "mcp/model_selector.py",
    }

    # 已知 helper 的返回类型约定（来自代码语义，跨文件变量流简化）
    helper_return_types = {
        "_get_agent_for_session": "Agent",          # mcp/agent.py
        "_get_web_agent": "Agent",
        "_get_agent_base": "AgentBase",
        "_get_session_store": "SessionStore",       # mcp/harness/session_store.py
        "_get_fdb_for_workspace": "FileVersionDB",  # mcp/middleware/file_version_db.py
        "get_context_reloader": "ContextReloader",  # mcp/cache/context_reloader.py
        "_get_model_selector": "ModelSelector",
    }

    # 常见局部变量别名 → 类型（来自代码语义，如 cp = mw.checkpointer）
    type_aliases = {
        "cp": "ShadowGitCheckpointer",     # mw.checkpointer
        "reloader": "ContextReloader",     # get_context_reloader()
        "coordinator": "Coordinator",      # agent._coordinator
        "fdb": "FileVersionDB",            # _get_fdb_for_workspace() / mw.fdb
        "llm": "MultiProviderManager",     # app 侧注入的 LLM
    }

    # 已知 helper 的形参类型约定（用于方法调用归属：store.get → SessionStore.get）
    param_type_hints = {
        "_sync_agent_from_store": {"agent": "Agent", "store": "SessionStore"},
        "_get_session_preview": {"messages_snapshot": "list"},
        "_build_multimodal_message": {"attachments": "list"},
        "agent_session_delete": {"store": "SessionStore"},
    }

    def collect_builtin_transforms(self) -> list:
        """TS2 内置变换名（param_chain._BUILTIN_TRANSFORMS）。"""
        try:
            sys.path.insert(0, str(_MCP_ROOT))
            import param_chain
            return sorted(param_chain._BUILTIN_TRANSFORMS.keys())
        except Exception:
            return []
