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
        "你是 WS2 Agent，一个强大的 AI 学习助手。\n"
        "你拥有广泛的知识，涵盖物理学、计算机科学、数学等多个学科领域。\n"
        "你的核心职责是帮助用户管理课程学习、复习进度、笔记和项目。"
    )

    template = variant.componentOverrides.get(
        "AGENT_ROLE", {}
    ).get("template", default_template) if variant else default_template

    return TemplateEngine().resolve(template, ctx)


def get_dynamic_tool_use_section(active_tools, inactive_summaries: Optional[Dict[str, str]] = None) -> str:
    """动态生成工具使用说明 — 只列出当前活跃工具 + 未激活工具摘要

    Args:
        active_tools: 当前活跃的 Tool 实例列表
        inactive_summaries: 未激活工具的 {name: 一句话摘要} 字典
    """
    from ..tool_search import _classify_tool, _get_group_label, _get_available_prefix_rules

    # 按类别分组活跃工具
    categories = {
        "文件操作": [],
        "搜索": [],
        "网络": [],
        "计算与分析": [],
        "终端与系统": [],
        "配置与技能": [],
        "RAG检索": [],
        "沙箱": [],
        "MCP客户端": [],
        "WS2 课程管理": [],
        "WS2 课时与复习": [],
        "WS2 资源与笔记": [],
        "WS2 项目与任务": [],
        "WS2 数据库": [],
        "数据枢纽": [],
        "学术搜索": [],
        "Wolfram 数学": [],
        "Lean4 证明": [],
        "Manim 动画": [],
        "MathLens": [],
        "AutoResearch": [],
        "飞书": [],
        "GT 课程追踪": [],
        "子Agent": [],
        "开发工具": [],
        "其他": [],
    }

    # 分类映射 — 使用 _classify_tool 自动分类
    _group_to_category = {
        "core": None,  # 需要细分
        "ws2": None,   # 需要细分
        "datahub_core": "数据枢纽",
        "datahub_pro": "数据枢纽",
        "scholar": "学术搜索",
        "wolfram": "Wolfram 数学",
        "lean4": "Lean4 证明",
        "manim": "Manim 动画",
        "mathlens": "MathLens",
        "autoresearch": "AutoResearch",
        "feishu": "飞书",
        "gt": "GT 课程追踪",
        "team": "团队协作",
        "other": "其他",
    }

    def _classify(tool_name: str) -> str:
        # 核心工具细分
        if tool_name in ("read_file", "write_file", "edit_file", "search_files",
                         "list_directory", "file_info", "diff_files", "move_file",
                         "copy_file", "open_file"):
            return "文件操作"
        if tool_name in ("grep", "glob"):
            return "搜索"
        if tool_name in ("web_search", "fetch_url"):
            return "网络"
        if tool_name in ("calculate", "analyze_paper"):
            return "计算与分析"
        if tool_name in ("cli_execute", "terminal_open"):
            return "终端与系统"
        if tool_name in ("config_manage", "search_configs", "skill_manager", "search_skills"):
            return "配置与技能"
        if tool_name in ("rag_retrieval", "search_documents"):
            return "RAG检索"
        if tool_name == "sandbox_execute":
            return "沙箱"
        if tool_name in ("mcp_client", "search_mcp_tools"):
            return "MCP客户端"
        if tool_name == "sub_agent":
            return "子Agent"
        if tool_name == "macdev":
            return "开发工具"
        if tool_name == "workflow":
            return "开发工具"

        # WS2 工具细分
        if tool_name.startswith("ws2_hub_"):
            return "数据枢纽"
        if tool_name.startswith("ws2_") or tool_name in ("search_courses", "search_sessions"):
            if any(kw in tool_name for kw in ("lesson", "review", "progress", "next_lesson", "timetable", "course_slot", "semester")):
                return "WS2 课时与复习"
            if any(kw in tool_name for kw in ("resource", "bookmark", "note", "rmd", "knit")):
                return "WS2 资源与笔记"
            if any(kw in tool_name for kw in ("project", "task", "automation")):
                return "WS2 项目与任务"
            if any(kw in tool_name for kw in ("db", "reload", "source", "rag_")):
                return "WS2 数据库"
            return "WS2 课程管理"

        # 其他按前缀分组
        group = _classify_tool(tool_name)
        cat = _group_to_category.get(group)
        if cat:
            return cat
        return "其他"

    for tool in active_tools:
        cat = _classify(tool.name)
        categories[cat].append(tool)

    # 生成活跃工具说明
    lines = ["TOOL USE", ""]
    lines.append("你可以使用以下工具帮助用户完成任务。工具参数详见工具定义。")

    for cat_name, tools_in_cat in categories.items():
        if not tools_in_cat:
            continue
        lines.append(f"\n【{cat_name}】")
        for tool in tools_in_cat:
            desc = tool.description
            # 截断过长的描述为一行
            if len(desc) > 80:
                desc = desc[:77] + "..."
            lines.append(f"- {tool.name}：{desc}")

    # 未激活工具摘要 — 按前缀规则自动分组
    if inactive_summaries:
        lines.append("\n【其他可用工具（提及相关关键词时自动激活）】")
        # 收集所有意图组（有 keywords 的组，仅包含实际有工具的组）
        intent_groups: Dict[str, Dict] = {}
        for rule in _get_available_prefix_rules():
            g = rule["group"]
            if g not in intent_groups and rule.get("keywords"):
                intent_groups[g] = {"label": rule["label"], "prefix": rule["prefix"], "tools": set()}

        # 将未激活工具归入对应组
        for name in inactive_summaries:
            for g, gdef in intent_groups.items():
                if name.startswith(gdef["prefix"]):
                    gdef["tools"].add(name)
                    break

        for g, gdef in intent_groups.items():
            if gdef["tools"]:
                names = ", ".join(sorted(gdef["tools"]))
                lines.append(f"- {gdef['label']}：{names}")

        # 不属于任何意图组的未激活工具
        grouped_names = set()
        for gdef in intent_groups.values():
            grouped_names.update(gdef["tools"])
        ungrouped = {n: s for n, s in inactive_summaries.items() if n not in grouped_names}
        if ungrouped:
            names = ", ".join(sorted(ungrouped.keys()))
            lines.append(f"- 其他：{names}")

    lines.append("\n工具调用规则：")
    lines.append("- 每个工具使用后，等待结果再继续")
    lines.append("- 并行工具调用可以同时发出")
    lines.append("- 不要编造工具名，只使用上述列出的工具")
    lines.append("- 优先使用 search_* 替代全量 list 操作，以节省上下文空间")
    lines.append("- 需要完整详情时再使用对应的 list/get 工具")
    lines.append("- 需要使用未列出的专业工具时，先用 activate_tool_group 激活对应工具组")

    return "\n".join(lines)


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

【Search 工具（推荐替代全量列表）】
优先使用 search_* 系列工具替代对应的 list 操作（节省上下文）：
- search_files：搜索文件（关键词/扩展名/路径过滤，分页），替代 list_directory
- search_courses：搜索课程（关键词过滤），替代 ws2_list_courses
- search_sessions：搜索对话会话（标题关键词过滤），替代 session list
- search_configs：搜索系统配置（名称/值关键词过滤），替代 config get_all
- search_skills：搜索技能（名称/描述/状态过滤），替代 skill_manager list
- search_documents：搜索知识库文档（文件名关键词过滤），替代 rag list_documents
- search_mcp_tools：搜索外部 MCP 工具（名称/描述/服务器过滤），替代 mcp_client list_tools
说明：所有 search_* 工具均支持 keyword（关键词）、limit（每页数量，默认10）、offset（分页偏移，默认0）参数，一次只返回摘要信息。需要完整详情时再使用对应的 list/get 工具。

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

【开发工具 macdev（机器驱动开发库）】
- macdev：运行 macdev 机器驱动开发库命令（取代 plan_cli），参数：subcommand + args + project可选
  参数：
  • subcommand - 顶层命令（必填）：audit / plan / patch / log / requirement / dev / project / doc
  • args - 该命令的参数串（空格分隔，多行内容用 \n 转义）
  • project - 产物目录名（可选）：产物收敛到 <name>-project/（audit/log/requirement/dev 支持）
  子命令速览：
  • audit --task task.json --root . [--project <name>]：静态接口审计（亲属追逐依赖链 + 8维分析 + 4维扫描）
  • plan create --title ... / task add / step add / verify / ledger / export / review / tdd check / openspec：开发流程机器化，变更自动刷新双轨产物
  • patch gen / apply / verify / plugins：自演化修复闭环
  • log add --project <name> --category pitfalls --title ... / list / query / export：经验沉淀（随项目/随包双轨）
  • requirement add / list / update / delete / export / align --root . / scan：需求 CRUD + 规范接口对齐
  • dev map --target <目录> / audit --target <目录>：学习/模仿目标项目（目录编排 + 架构了解）
  • project init --name <name> [--git] / list / root：产物目录约定 <name>-project/
  • doc：自举生成使用/开发文档
  用法示例：
  - macdev(subcommand="plan", args="create --title \"接入新端点\"")
  - macdev(subcommand="audit", args="--task task.json --root .", project="TS2")
  - macdev(subcommand="log", args="add --category pitfalls --title 数据库列序问题")
  - macdev(subcommand="dev", args="map --target ../some-project", project="learn-x")

【开发工具 工作流（Workflow 引擎）】
- workflow：声明式多步骤编排，执行路径写死在定义里（非 LLM 逐步决策），带状态机/检查点/暂停恢复/持久化
  参数：
  • action - 操作类型（必填）：define / start / status / pause / resume / cancel / list / logs / step_results
  • workflow_id - 工作流 ID（define/start 需要）
  • instance_id - 实例 ID（status/pause/resume/cancel/logs/step_results 需要）
  • definition - 工作流定义对象（define 需要：steps + entry_step）
  • input_data - 启动输入数据（start 可选）
  说明：
  • action=list 查看已注册定义（内置 23 个预定义工作流）
  • 与 sub_agent 的区别：子Agent 是单任务自主执行；工作流是多步骤确定性编排，可暂停/恢复/续跑
  • AGENT 步骤会复用主 Agent 的 LLM 与工具；TOOL 步骤直接执行指定工具
  用法示例：
  - workflow(action="list")
  - workflow(action="start", workflow_id="research_v1")
  - workflow(action="status", instance_id="<inst_id>")

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
- 优先使用最合适的工具完成任务，减少不必要的追问
- 优先使用 search_* 工具（如 search_files、search_skills）而非全量 list 操作，以节省上下文空间；需要完整详情时再使用对应的 list/get 工具
- 开发类任务默认使用 macdev 追踪开发日志与动态：经验教训用 `macdev log add --project <名称> --category <pitfalls|lessons|patterns|decisions> --title ...` 沉淀，计划与进度用 `macdev plan` 维护（create/task add/step add/verify），让开发过程可追溯"""

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
- 搜索文件、技能、配置、文档和外部 MCP 工具（支持关键词过滤和分页）

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
    from datetime import datetime

    ctx = context or {}
    # 注入 CURRENT_DATE 到 context
    if "CURRENT_DATE" not in ctx:
        ctx = dict(ctx)
        today = datetime.now()
        ctx["CURRENT_DATE"] = today.strftime("%Y-%m-%d, %A")

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


def get_context_sources_section(variant=None, context: Optional[Dict] = None) -> str:
    """上下文来源 — 参考 Cline 的 .clinerules 三层上下文注入

    从 ContextProvider 收集 Rules/Files/Others 三层上下文，
    组装为结构化的系统提示段落。
    """
    from .context_provider import ContextProvider

    ctx = context or {}
    workspace_root = ctx.get("workspace_root", ctx.get("cwd", ""))

    provider = ContextProvider(workspace_root=workspace_root)

    # 收集静态上下文（Rules + Files）
    bundle = provider.collect(context=ctx)

    # 排除动态层（Others 由 chat 流程中动态注入）
    static_sections = [s for s in bundle.sections if s.layer != "others"]

    if not static_sections:
        return ""

    # 按层分组输出
    layer_labels = {"rules": "规则与约束", "files": "项目上下文"}
    layer_order = ["rules", "files"]
    parts = []

    for layer in layer_order:
        layer_sections = [s for s in static_sections if s.layer == layer]
        if not layer_sections:
            continue

        # 按优先级排序
        layer_sections.sort(key=lambda s: -s.priority)

        parts.append(f"{'=' * 40}")
        parts.append(f"  {layer_labels.get(layer, layer)}")
        parts.append(f"{'=' * 40}")

        for section in layer_sections:
            parts.append(f"\n## {section.label}")
            parts.append(section.content)

    return "\n".join(parts)


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
    ("CONTEXT_SOURCES", "上下文来源", get_context_sources_section, 10),
    ("SYSTEM_INFO", "系统信息", get_system_info_section, 11),
    ("OBJECTIVE", "目标", get_objective_section, 12),
    ("USER_INSTRUCTIONS", "用户指令", get_user_instructions_section, 13),
    ("SKILLS", "技能", get_skills_section, 14),
]:
    register_component(_comp_id, _comp_name, _comp_fn, _comp_order)


def apply_config_components(variant, components_cfg: Dict[str, Dict]) -> None:
    """把 config 中的提示词组件配置合并到 variant（内置覆盖 + 自定义注册）

    components_cfg: {component_id: {name?, template?, enabled?, order?}}
    - 内置组件（registry 已注册）→ 合并 template/enabled 到 variant.componentOverrides
    - 自定义组件（手写编排提示词）→ 注册通用生成器 + 追加到 componentOrder

    幂等：重复调用仅覆盖同名组件 / 不重复 append 顺序。
    """
    if not components_cfg or variant is None:
        return
    registry = get_component_registry()
    known = set(registry.all_ids)
    for cid, cfg in components_cfg.items():
        if not isinstance(cfg, dict):
            continue
        enabled = bool(cfg.get("enabled", True))
        template = str(cfg.get("template", "") or "")
        if cid in known:
            # 内置组件：模板覆盖 / 启停
            override = {"enabled": enabled}
            if template:
                override["template"] = template
            variant.componentOverrides[cid] = override
        else:
            # 自定义编排组件：注册通用生成器
            name = str(cfg.get("name", cid))
            order = int(cfg.get("order", 100))

            def _custom_gen(variant=None, context=None, _t=template):
                if not _t:
                    return ""
                return TemplateEngine().resolve(_t, context or {})

            registry.register(PromptComponent(
                id=cid, name=name, generator=_custom_gen, order=order))
            variant.componentOverrides[cid] = {"enabled": enabled}
            if cid not in variant.componentOrder:
                variant.componentOrder.append(cid)
            # baseTemplate 同步追加占位符，确保自定义编排段落被输出
            if variant.baseTemplate:
                variant.baseTemplate += f"\n\n====\n\n{{{{{cid}}}}}"