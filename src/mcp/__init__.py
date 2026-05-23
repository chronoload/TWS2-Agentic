"""
WS2 MCP (Model Context Protocol) 模块
提供完整的 Agent 系统和工具集成
基于 CoreCoder 和 OpenClaude 设计
完全集成 WS2 系统
"""

__version__ = "2.2.0"
__author__ = "WS2 Team"

from .llm import LLM, LLMResponse, ToolCall, SimulatorLLM
from .tools import Tool, get_tools
from .ws2_tools import get_ws2_tools
from .agent import Agent, AgentConfig, create_agent
from .ui import AgentChatUI
from .config import APIConfig, SkillConfig, ConfigManager, get_config_manager
from .config_ui import show_enhanced_config_dialog

__all__ = [
    "LLM",
    "LLMResponse",
    "ToolCall",
    "SimulatorLLM",
    "Tool",
    "get_tools",
    "get_ws2_tools",
    "Agent",
    "AgentConfig",
    "create_agent",
    "AgentChatUI",
    "APIConfig",
    "SkillConfig",
    "ConfigManager",
    "get_config_manager",
    "show_enhanced_config_dialog",
]
