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

【文件操作工具】
- read_file：读取文件内容（参数：path, encoding可选, offset/limit可选）
- write_file：写入文件内容（参数：path, content, encoding可选, mode可选create/append, open_after可选False/True，写入后自动打开文件）
- edit_file：编辑文件（参数：file_path, old_str, new_str, mode可选replace/insert/append/delete_lines, open_after可选False/True，编辑后自动打开文件）
- list_directory：列出目录内容（参数：path）
- file_info：获取文件元数据（参数：path，返回大小、修改时间等）
- diff_files：比较两个文件差异（参数：path1, path2）
- move_file：移动/重命名文件（参数：src, dst）
- copy_file：复制文件（参数：src, dst）
- open_file：用默认程序打开文件（参数：path）

【终端工具】
- terminal_open：打开新终端窗口（参数：path可选工作目录, command可选执行命令, keep_open可选True命令执行后保持终端打开）

【搜索工具】
- grep：在文件中搜索文本（参数：pattern, path可选, case_sensitive可选）
- glob：按模式匹配文件（参数：pattern, path可选）

【网络工具】
- web_search：网络搜索（参数：query, num_results可选）
- fetch_url：获取网页内容（参数：url, max_length可选）

【计算与分析工具】
- calculate：数学计算（参数：expression）
- analyze_paper：分析科研论文（参数：path）

【系统工具】
- cli_execute：执行命令行命令（参数：command, timeout可选, cwd可选, open_terminal可选False/True在新终端中执行, keep_terminal_open可选True命令执行后保持终端打开）
- terminal_open：打开新的终端窗口（参数：path可选工作目录, command可选执行命令, keep_open可选True命令执行后保持终端打开）
- open_file：用默认程序打开文件（参数：path）

【配置与技能管理】
- config_manage：管理系统配置（参数：action=list_providers/get_settings/update_setting/list_skills, key/value可选）
- skill_manager：技能管理系统（参数：action=list/get_details/execute, skill_name参数可选, parameters可选）

【RAG检索系统】
- rag_retrieval：检索增强生成系统（参数：action=add_file/add_directory/retrieve/query/get_count/list_documents/clear）
  操作说明：
  • add_file：添加文件到向量库（参数：file_path, metadata可选）
  • add_directory：添加整个目录（参数：directory_path）
  • retrieve：基于语义相似度检索（参数：query, top_k可选默认4）
  • query：查询并格式化结果（参数：query, top_k可选）
  • get_count：获取向量库中文档数量
  • list_documents：列出所有文档
  • clear：清空向量库

【沙箱执行】
- sandbox_execute：沙箱安全执行命令（参数：command, allow_network可选False/True, max_time可选30秒, open_terminal可选False/True在新终端中执行, keep_terminal_open可选True命令执行后保持终端打开）
  与cli_execute的区别：沙箱执行有更严格的安全策略，适合执行不可信代码；终端模式下会打开新终端窗口，但安全限制可能较宽松

【MCP客户端】
- mcp_client：管理外部MCP服务（参数：action=list_tools/call_tool/get_status）
  操作说明：
  • list_tools：列出所有可用的MCP工具
  • call_tool：调用指定的MCP工具（参数：tool_name, arguments）
  • get_status：查看MCP客户端连接状态

【WS2 课程管理工具】
- ws2_get_overview：获取课程总览（返回总数、总课时、完成进度）
- ws2_get_domain_stats：获取领域分布统计
- ws2_list_domains：列出所有学习领域
- ws2_get_progress_by_domain：按领域获取学习进度

【WS2 课程 CRUD】
- ws2_list_courses：列出所有课程
- ws2_search_courses：搜索课程（参数：query）
- ws2_get_course_detail：获取课程详情（参数：course_id）
- ws2_create_course：创建新课程（参数：name, domain, description可选）
- ws2_remove_course：删除课程（参数：course_id）
- ws2_find_duplicates：查找重复课程
- ws2_update_course_info：更新课程信息（参数：course_id, field, value）

【WS2 课时学习】
- ws2_mark_lesson_complete：标记课时完成（参数：course_id, lesson_id）
- ws2_get_next_lesson：获取下一课时（参数：course_id）
- ws2_get_course_progress：获取课程进度（参数：course_id）

【WS2 复习调度】
- ws2_get_review_schedule：获取复习计划（参数：days可选，默认7天）
- ws2_mark_review_done：标记复习完成（参数：item_id）

【WS2 资源管理】
- ws2_get_resources：获取课程资源（参数：course_id, lesson_id可选）
- ws2_add_resource：添加资源（参数：course_id, lesson_id, title, url）
- ws2_list_bookmarks：列出书签（参数：category可选）
- ws2_search_bookmarks：搜索书签（参数：query）
- ws2_add_bookmark：添加书签（参数：name, url, category可选）
- ws2_list_bookmark_categories：列出书签分类

【WS2 笔记管理】
- ws2_list_notes：列出笔记（参数：course_id可选）
- ws2_read_note：读取笔记（参数：note_id）
- ws2_write_note：写入笔记（参数：course_id, title, content）

【WS2 项目管理】
- ws2_list_projects：列出所有项目
- ws2_create_project：创建项目（参数：name, description可选）

【WS2 任务看板】
- ws2_list_tasks：列出任务（参数：status可选）
- ws2_add_task：添加任务（参数：title, description可选, priority可选）
- ws2_update_task：更新任务（参数：task_id, field, value）

【WS2 数据库管理】
- ws2_reload_all_sources：重新加载所有数据源
- ws2_add_db_path：添加数据库路径（参数：path）
- ws2_get_db_paths：获取数据库路径列表

【数据枢纽 DataHub】
- ws2_hub_add_item：添加数据项（参数：title, url/content/summary可选, source_type/item_type可选, tags/keywords可选）
- ws2_hub_query_items：查询数据项（参数：source_type/item_type/tag/starred_only/unread_only/search可选, limit/offset可选）
- ws2_hub_get_item：获取单个数据项（参数：item_id）
- ws2_hub_update_item：更新数据项（参数：item_id, field, value）
- ws2_hub_delete_item：删除数据项（参数：item_id）
- ws2_hub_add_rss：添加RSS订阅（参数：name, url）
- ws2_hub_remove_rss：移除RSS订阅（参数：rss_id）
- ws2_hub_list_rss：列出所有RSS订阅
- ws2_hub_poll_rss：轮询RSS更新（参数：rss_id可选）
- ws2_hub_create_collection：创建数据集合（参数：name, description可选）
- ws2_hub_add_to_collection：添加数据到集合（参数：collection_id, item_id）
- ws2_hub_list_collections：列出所有数据集合
- ws2_hub_pipeline_crawl：管道爬取（参数：urls, collection_id可选）
- ws2_hub_pipeline_bookmark：书签管道（参数：urls, collection_id可选）
- ws2_hub_pipeline_analysis：分析管道（参数：item_id, collection_id可选）
- ws2_hub_pipeline_local：本地文件管道（参数：paths, collection_id可选）
- ws2_hub_bookmark_crawl：书签爬取（参数：urls）
- ws2_hub_generate_rss：生成RSS（参数：collection_id, name）
- ws2_hub_parse_content：解析内容（参数：url或content）
- ws2_hub_fetch_url：获取URL内容（参数：url）
- ws2_hub_auto_scan：自动扫描（参数：url或path）
- ws2_hub_lightweight_crawl：轻度爬取（参数：url，只获取元信息）
- ws2_hub_discover_subscriptions：发现订阅（参数：urls，发现RSS/Atom订阅）
- ws2_hub_run_pipeline：运行管道（参数：pipeline_id）
- ws2_hub_pipeline_status：获取管道状态（参数：pipeline_id）
- ws2_hub_get_stats：获取数据枢纽统计

【子Agent】
- sub_agent：委派任务给专门的子Agent（每个子Agent有独立会话空间）
  参数：
  • agent - 子Agent角色（必填）：coder(编程)/task(任务)/research(研究)/review(审查)
  • prompt - 完整任务描述（必填）
  • context - 上下文信息（可选）
  子Agent能力：
  • coder - 编写/调试/重构代码（15轮上限）
  • task - 完成特定任务（10轮上限）
  • research - 搜索/分析/总结信息（8轮上限）
  • review - 审查代码质量/安全性（5轮上限）

工具调用规则：
- 每个工具使用后，等待结果再继续
- 并行工具调用可以同时发出
- 不要编造工具名，只使用上述列出的工具
- 对于ws2系列工具，确保WS2系统已初始化
- 对于hub系列工具，确保DataHub已启动"""

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
- edit_file 支持4种模式：
  - replace（默认）：搜索替换，确保 old_str 精确匹配文件中的唯一内容
  - insert：在指定行号前插入新内容（需提供 line_number 和 new_str）
  - append：在文件末尾追加内容（需提供 new_str）
  - delete_lines：删除指定行范围（需提供 start_line 和 end_line）
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