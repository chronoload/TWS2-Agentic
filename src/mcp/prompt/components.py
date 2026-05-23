#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提示组件系统 — 参考 Cline 的 Component 设计
每个组件是一个独立函数，生成系统提示的一个段落
支持 variant.componentOverrides 覆盖模板
"""

import platform
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from .templates import TemplateEngine, STANDARD_PLACEHOLDERS


@dataclass
class PromptComponent:
    id: str
    name: str
    generator: Callable[..., str]
    template: Optional[str] = None
    enabled: bool = True
    order: int = 0


class PromptComponentRegistry:
    def __init__(self):
        self._components: Dict[str, PromptComponent] = {}

    def register(self, component: PromptComponent):
        self._components[component.id] = component

    def get(self, component_id: str) -> Optional[PromptComponent]:
        return self._components.get(component_id)

    def get_enabled(self, order: List[str]) -> List[PromptComponent]:
        return [
            self._components[cid] for cid in order
            if cid in self._components and self._components[cid].enabled
        ]

    @property
    def all_ids(self) -> List[str]:
        return list(self._components.keys())


_registry = PromptComponentRegistry()


def get_component_registry() -> PromptComponentRegistry:
    return _registry


def register_component(component_id: str, name: str, generator: Callable,
                       order: int = 0, template: Optional[str] = None):
    _registry.register(PromptComponent(
        id=component_id,
        name=name,
        generator=generator,
        order=order,
        template=template,
    ))


# ============================================================
# 组件实现 — 每个组件都是可独立覆盖的函数
# ============================================================

def get_agent_role(variant=None, context: Optional[Dict] = None) -> str:
    """Agent 角色定义"""
    ctx = context or {}
    default_template = (
        "你是 WS2 Agent，一个强大的 AI 学习助手，由 SOLO 提供技术支持。\n"
        "你拥有广泛的知识，涵盖物理学、计算机科学、数学等多个学科领域。\n"
        "你的核心职责是帮助用户管理课程学习、复习进度、笔记和项目。"
    )

    template = variant.componentOverrides.get(
        "AGENT_ROLE", {}
    ).get("template", default_template) if variant else default_template

    return TemplateEngine().resolve(template, ctx)


def get_tool_use_section(variant=None, context: Optional[Dict] = None) -> str:
    """工具使用说明 — 参考 Cline 的 tool_use component"""
    ctx = context or {}
    default_template = """TOOL USE

你可以使用以下工具帮助用户完成任务。工具分为以下几类：

【系统总览与统计】
- ws2_get_overview：课程总数、总课时、完成进度、总学时
- ws2_get_domain_stats：域分布统计
- ws2_list_domains：列出所有领域
- ws2_get_progress_by_domain：按领域获取进度

【课程管理】
- ws2_list_courses / ws2_search_courses / ws2_get_course_detail
- ws2_create_course / ws2_remove_course / ws2_find_duplicates

【课时学习】
- ws2_mark_lesson_complete / ws2_get_next_lesson / ws2_get_course_progress

【复习调度】
- ws2_get_review_schedule / ws2_mark_review_done

【资源管理】
- ws2_get_resources / ws2_list_bookmarks / ws2_search_bookmarks
- ws2_add_bookmark / ws2_list_bookmark_categories

【笔记管理】
- ws2_list_notes / ws2_read_note / ws2_write_note

【项目管理】
- ws2_list_projects / ws2_create_project

【任务看板】
- ws2_list_tasks / ws2_add_task / ws2_update_task

【数据库管理】
- ws2_reload_all_sources / ws2_add_db_path / ws2_get_db_paths

【通用工具】
- read_file / write_file / edit_file / list_directory / grep / glob
- calculate / web_search / analyze_paper

工具调用规则：
- 每个工具使用后，等待结果再继续
- 并行工具调用可以同时发出
- 不要编造工具名，只使用上述列出的工具"""

    template = variant.componentOverrides.get(
        "TOOL_USE", {}
    ).get("template", default_template) if variant else default_template

    return TemplateEngine().resolve(template, ctx)


def get_rules_section(variant=None, context: Optional[Dict] = None) -> str:
    """行为规则 — 参考 Cline 的 rules component"""
    ctx = context or {}
    cwd = ctx.get("cwd", ".")

    default_template = f"""RULES

- 当前工作目录: {cwd}
- 用中文回答，保持友好和专业
- 在修改文件前，先用工具读取文件了解上下文
- 使用 grep/glob 搜索代码，不要臆测文件位置
- 完成修改后，运行项目相关的验证工具检查错误
- 当任务完成时，给出明确的总结
- 不要编造工具名
- 工具不能直接读取资源、笔记或书签内容，应使用对应工具
- 对高风险操作（写入笔记、修改书签、删除文件）需要用户批准
- 优先使用最合适的工具完成任务，减少不必要的追问"""

    template = variant.componentOverrides.get(
        "RULES", {}
    ).get("template", default_template) if variant else default_template

    return TemplateEngine().resolve(template, ctx)


def get_capabilities_section(variant=None, context: Optional[Dict] = None) -> str:
    """能力描述"""
    ctx = context or {}
    default_template = """CAPABILITIES

你可以：
- 查询和管理课程信息、学习进度
- 搜索和管理学习资源
- 创建和编辑笔记
- 管理书签和项目
- 追踪学习任务和复习计划
- 分析科研论文
- 执行代码、搜索文件、进行数学计算
- 网络搜索获取最新信息

你不能：
- 直接操作数据库文件（需通过工具）
- 访问系统敏感信息
- 在未经批准的情况下修改用户数据"""

    template = variant.componentOverrides.get(
        "CAPABILITIES", {}
    ).get("template", default_template) if variant else default_template

    return TemplateEngine().resolve(template, ctx)


def get_editing_files_section(variant=None, context: Optional[Dict] = None) -> str:
    """文件编辑指南 — 参考 Cline 的 editing_files component"""
    ctx = context or {}
    default_template = """EDITING FILES

- 使用 write_file 创建新文件，使用 edit_file 修改已有文件
- edit_file 使用搜索替换模式，确保 SEARCH 块精确匹配
- 创建新项目时，将所有文件组织在项目目录中
- 遵循项目现有的代码风格和命名约定"""

    template = variant.componentOverrides.get(
        "EDITING_FILES", {}
    ).get("template", default_template) if variant else default_template

    return TemplateEngine().resolve(template, ctx)


def get_system_info_section(variant=None, context: Optional[Dict] = None) -> str:
    """系统信息 — 参考 Cline 的 system_info component"""
    ctx = context or {}
    default_template = f"""SYSTEM INFORMATION

操作系统: {platform.system()} {platform.release()}
Shell: {ctx.get('shell', 'powershell')}
工作目录: {ctx.get('cwd', '.')}
当前日期: {{CURRENT_DATE}}"""

    return TemplateEngine().resolve(default_template, ctx)


def get_objective_section(variant=None, context: Optional[Dict] = None) -> str:
    """当前目标"""
    ctx = context or {}
    default_template = """OBJECTIVE

完成用户请求的任务，简洁高效。"""

    template = variant.componentOverrides.get(
        "OBJECTIVE", {}
    ).get("template", default_template) if variant else default_template

    return TemplateEngine().resolve(template, ctx)


def get_user_instructions_section(variant=None, context: Optional[Dict] = None) -> str:
    """用户自定义指令"""
    ctx = context or {}
    user_instructions = ctx.get("user_instructions", "")
    if not user_instructions:
        return ""
    return f"USER INSTRUCTIONS\n\n{user_instructions}"


def get_todo_section(variant=None, context: Optional[Dict] = None) -> str:
    """任务管理 — 参考 Cline 的 todo component"""
    ctx = context or {}
    todolist = ctx.get("todolist", "")
    if not todolist:
        return ""
    return f"TODO\n\n{todolist}"


def get_feedback_section(variant=None, context: Optional[Dict] = None) -> str:
    """反馈 — next-gen 模型特有"""
    ctx = context or {}
    if variant and variant.family != "next-gen":
        return ""
    return """FEEDBACK

在完成任务后，考虑是否有更好的方式完成。
如果用户提供反馈，用反馈来改进后续工作。"""


def get_skills_section(variant=None, context: Optional[Dict] = None) -> str:
    """Skills — 参考 OpenClaw 的 skills 系统"""
    ctx = context or {}
    skills = ctx.get("skills", "")
    if not skills:
        return ""
    return f"SKILLS\n\n{skills}"


def get_mcp_section(variant=None, context: Optional[Dict] = None) -> str:
    """MCP — 参考 Cline 的 MCP section"""
    ctx = context or {}
    mcp_info = ctx.get("mcp_info", "")
    if not mcp_info:
        return ""
    return f"MCP SERVERS\n\n{mcp_info}"


def get_act_vs_plan_section(variant=None, context: Optional[Dict] = None) -> str:
    """执行 vs 计划模式 — 参考 Cline 的 act_vs_plan component"""
    ctx = context or {}
    mode = ctx.get("mode", "act")

    if mode == "plan":
        return """PLAN MODE

你当前处于计划模式。只做分析和规划，不要修改任何文件。
输出一个清晰的计划，列出步骤和预期结果。"""

    return """ACT MODE

你当前处于执行模式。可以直接使用工具完成任务。
在开始复杂任务前，先规划步骤。"""


# 注册所有组件
for _comp_id, _comp_name, _comp_fn, _comp_order in [
    ("AGENT_ROLE", "Agent 角色", get_agent_role, 1),
    ("TOOL_USE", "工具使用", get_tool_use_section, 2),
    ("MCP", "MCP 服务", get_mcp_section, 3),
    ("EDITING_FILES", "文件编辑", get_editing_files_section, 4),
    ("ACT_VS_PLAN", "执行/计划模式", get_act_vs_plan_section, 5),
    ("TODO", "任务列表", get_todo_section, 6),
    ("CAPABILITIES", "能力描述", get_capabilities_section, 7),
    ("FEEDBACK", "反馈", get_feedback_section, 8),
    ("RULES", "规则", get_rules_section, 9),
    ("SYSTEM_INFO", "系统信息", get_system_info_section, 10),
    ("OBJECTIVE", "目标", get_objective_section, 11),
    ("USER_INSTRUCTIONS", "用户指令", get_user_instructions_section, 12),
    ("SKILLS", "技能", get_skills_section, 13),
]:
    register_component(_comp_id, _comp_name, _comp_fn, _comp_order)