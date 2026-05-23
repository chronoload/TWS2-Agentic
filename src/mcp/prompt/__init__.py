#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 系统提示架构 — 参考 Cline / OpenCode / OpenClaw 设计

组件化提示构建系统：
- 提示组件可组合、可覆盖
- 模板引擎支持 {{PLACEHOLDER}} 运行时解析
- 模型变体支持不同模型族的提示优化
- 工作区注入 (AGENTS.md / TOOLS.md)
- 上下文窗口感知
"""

from .components import (
    PromptComponent,
    PromptComponentRegistry,
    get_agent_role,
    get_tool_use_section,
    get_rules_section,
    get_capabilities_section,
    get_editing_files_section,
    get_system_info_section,
    get_objective_section,
    get_user_instructions_section,
    get_todo_section,
    get_feedback_section,
    get_skills_section,
    get_mcp_section,
    get_act_vs_plan_section,
)
from .templates import TemplateEngine, STANDARD_PLACEHOLDERS
from .variants import (
    PromptVariant,
    ModelFamily,
    VariantRegistry,
    get_variant_registry,
)
from .builder import PromptBuilder, build_system_prompt
from .context_window import (
    resolve_context_tokens,
    estimate_message_tokens,
    MODEL_CONTEXT_WINDOWS,
    compact_messages,
    should_compact,
    auto_compact,
)
from .workspace import (
    load_workspace_files,
    WorkspaceFiles,
    resolve_workspace_injection,
)

__all__ = [
    "PromptComponent",
    "PromptComponentRegistry",
    "get_agent_role",
    "get_tool_use_section",
    "get_rules_section",
    "get_capabilities_section",
    "get_editing_files_section",
    "get_system_info_section",
    "get_objective_section",
    "get_user_instructions_section",
    "get_todo_section",
    "get_feedback_section",
    "get_skills_section",
    "get_mcp_section",
    "get_act_vs_plan_section",
    "TemplateEngine",
    "STANDARD_PLACEHOLDERS",
    "PromptVariant",
    "ModelFamily",
    "VariantRegistry",
    "get_variant_registry",
    "PromptBuilder",
    "build_system_prompt",
    "resolve_context_tokens",
    "estimate_message_tokens",
    "MODEL_CONTEXT_WINDOWS",
    "compact_messages",
    "should_compact",
    "auto_compact",
    "load_workspace_files",
    "WorkspaceFiles",
    "resolve_workspace_injection",
]