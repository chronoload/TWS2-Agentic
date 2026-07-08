#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专家Agent系统 - 面板专属AI助手

每个面板有独立的专家Agent，通过ToolPermissionEngine控制工具权限
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field

from .agent import Agent, AgentConfig
from .tools import Tool
from .tool_search import ToolSearchEngine
from .llm import LLM, SimulatorLLM

logger = logging.getLogger(__name__)


@dataclass
class SpecialistConfig:
    """专家Agent配置"""
    name: str
    role: str
    description: str
    system_prompt: str
    allowed_tool_patterns: List[str] = field(default_factory=list)
    # 工具模式：如 "ws2_*", "course_*", "project_*", "task_*", "file_*"
    max_tools: int = 15
    icon: str = "🤖"
    color: str = "#3b82f6"


class ToolPermissionEngine:
    """工具权限引擎 - 基于ToolSearchEngine的权限控制"""
    
    def __init__(self, all_tools: List[Tool], allowed_patterns: List[str], max_tools: int = 15):
        self._all_tools = {t.name: t for t in all_tools}
        self._allowed_patterns = allowed_patterns
        self._max_tools = max_tools
        self._allowed_tools: Dict[str, Tool] = {}
        self._build_permissions()
    
    def _build_permissions(self):
        """根据模式构建允许的工具列表"""
        import fnmatch
        
        for name, tool in self._all_tools.items():
            # 检查是否匹配任何允许的模式
            for pattern in self._allowed_patterns:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    self._allowed_tools[name] = tool
                    break
            # 如果没有模式限制，允许所有工具
            if not self._allowed_patterns:
                self._allowed_tools[name] = tool
        
        logger.info(f"权限引擎: {len(self._allowed_tools)}/{len(self._all_tools)} 工具已授权")
    
    def get_allowed_tools(self) -> List[Tool]:
        """获取所有允许的工具"""
        return list(self._allowed_tools.values())
    
    def search(self, query: str, top_k: int = None) -> List[Tool]:
        """在允许的工具中搜索"""
        top_k = top_k or self._max_tools
        
        # 使用ToolSearchEngine的搜索逻辑，但限制在允许的工具中
        import re
        query_lower = query.lower()
        query_tokens = set(re.findall(r'\w+', query_lower))
        
        scored = []
        for name, tool in self._allowed_tools.items():
            try:
                sig = tool.search_signature()
            except Exception:
                sig = f"{tool.name} {getattr(tool, 'description', '')}"
            doc_tokens = set(re.findall(r'\w+', sig.lower()))
            overlap = len(query_tokens & doc_tokens)
            if overlap > 0:
                scored.append((overlap, name))
        
        scored.sort(reverse=True)
        selected = [self._allowed_tools[name] for _, name in scored[:top_k]]
        
        # 如果结果太少，补充通用工具
        if len(selected) < 3:
            for name, tool in self._allowed_tools.items():
                if tool not in selected:
                    selected.append(tool)
                if len(selected) >= top_k:
                    break
        
        return selected
    
    def get_schemas_for_query(self, query: str) -> List[Dict]:
        """获取搜索结果的schemas"""
        tools = self.search(query)
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        """检查工具是否被允许"""
        return tool_name in self._allowed_tools


class SpecialistAgent(Agent):
    """
    专家Agent - 专注于特定领域的Agent
    
    特点：
    1. 只加载与领域相关的工具（通过ToolPermissionEngine控制）
    2. 使用专门的系统提示词
    3. 支持弹窗交互
    """
    
    def __init__(
        self,
        specialist_config: SpecialistConfig,
        llm: Optional[LLM] = None,
        base_dir: Optional[Path] = None,
        ws2_system: Any = None,
        project_manager: Any = None,
        task_manager: Any = None,
    ):
        self.specialist_config = specialist_config
        
        # 先创建基础AgentConfig
        agent_config = AgentConfig(
            name=specialist_config.name,
            system_prompt=specialist_config.system_prompt,
            base_dir=base_dir,
            ws2_system=ws2_system,
            project_manager=project_manager,
            task_manager=task_manager,
            use_modern_prompt=False,  # 使用专家的自定义 system_prompt，不被 build_system_prompt 覆盖
        )
        
        # 初始化父类但不加载工具（后面会覆盖）
        super().__init__(llm=llm, tools=[], config=agent_config)
        
        # 创建权限引擎并过滤工具
        self._permission_engine = ToolPermissionEngine(
            self.tools,  # 父类已加载的所有工具
            specialist_config.allowed_tool_patterns,
            specialist_config.max_tools
        )
        
        # 只保留允许的工具
        self.tools = self._permission_engine.get_allowed_tools()
        self._tool_map = {tool.name: tool for tool in self.tools}
        
        # 重置工具schemas缓存
        self._instance_tool_schemas = None
        
        # 初始化实时环境日志感知模块
        self._event_logger = None
        self._init_event_logger()
        
        logger.info(f"专家Agent '{specialist_config.name}' 已初始化，拥有 {len(self.tools)} 个工具")
    
    def _init_event_logger(self):
        """初始化事件日志系统，感知实时环境"""
        try:
            from . import event_logger
            from pathlib import Path
            
            # 优先使用全局单例，确保所有专家和主系统共享同一份事件数据
            log_dir = None
            if self.config.ws2_system and hasattr(self.config.ws2_system, 'event_logger'):
                self._event_logger = self.config.ws2_system.event_logger
                logger.info(f"专家 '{self.specialist_config.name}' 已耦合 ws2_system event_logger")
                return
            
            if self.config.base_dir:
                log_dir = self.config.base_dir / "logs" / "events"
                log_dir.mkdir(parents=True, exist_ok=True)
                # 使用 get_instance 确保全局共享同一实例
                self._event_logger = event_logger.get_logger(log_dir)
                logger.info(f"专家 '{self.specialist_config.name}' 已共享全局 event_logger: {log_dir}")
        except Exception as e:
            logger.warning(f"专家 '{self.specialist_config.name}' event_logger 初始化失败: {e}")
    
    def _build_environment_context(self) -> str:
        """构建实时环境上下文，一次性注入到 system prompt 中"""
        context_parts = []

        # 1. 最近事件感知
        if self._event_logger:
            try:
                events = self._event_logger.get_recent_events(count=5)
                if events:
                    event_lines = []
                    for evt in events:
                        try:
                            summary = evt.to_summary() if hasattr(evt, 'to_summary') else str(evt)
                            event_lines.append(f"- {summary}")
                        except Exception:
                            ts = getattr(evt, 'timestamp', '')[-8:] if getattr(evt, 'timestamp', '') else ''
                            etype = getattr(evt, 'event_type', '')
                            esub = getattr(evt, 'event_subtype', '')
                            new_val = getattr(evt, 'new_value', '') or ''
                            action = f"{etype}:{esub}" if esub else etype
                            if str(new_val):
                                action += f" → {str(new_val)[:50]}"
                            event_lines.append(f"- [{ts}] {action}")
                    context_parts.append(
                        f"## 最近操作（{len(event_lines)}条）\n" + "\n".join(event_lines)
                    )
            except Exception as e:
                logger.debug(f"获取最近事件失败: {e}")

        # 2. 系统状态感知
        if self.config.ws2_system:
            try:
                ws = self.config.ws2_system
                course_count = len(getattr(ws, 'courses', []))
                if course_count:
                    context_parts.append(f"## 系统状态\n- 课程总数：{course_count}")
            except Exception:
                pass

        # 3. UI 状态感知（通过 course_tracker 引用）
        tracker = getattr(self.config, '_course_tracker', None)
        if not tracker:
            # 尝试从 ws2_system 获取
            tracker = getattr(self.config.ws2_system, '_course_tracker', None) if self.config.ws2_system else None
        if tracker:
            try:
                tab_key = getattr(tracker, '_active_tab_key', None)
                if tab_key:
                    tab_names = {
                        "overview": "总览", "exec": "执行模式", "taskboard": "任务看板",
                        "coursesim": "课程系统", "search": "网络研探", "projects": "项目管理",
                        "analyze": "科研文本分析", "crawler": "网络搜索", "synergy": "数据枢纽",
                        "domain": "域分布", "resource": "课程资源", "manage": "导入与管理",
                        "notes": "笔记", "wflog": "工作日志",
                    }
                    tab_name = tab_names.get(tab_key, tab_key)
                    ui_lines = [f"用户当前界面: 「{tab_name}」"]
                    # 根据标签页补充上下文
                    if tab_key == "projects":
                        ws = getattr(tracker, 'ws2_system', None)
                        if ws and hasattr(ws, 'projects'):
                            projs = ws.projects
                            if projs:
                                names = [p.get('name', p.get('id', '?')) for p in projs[:10]]
                                ui_lines.append(f"项目列表: {', '.join(names)}")
                            else:
                                ui_lines.append("项目列表: 暂无项目")
                    elif tab_key == "analyze":
                        paper_file = getattr(tracker, '_current_paper_file', None)
                        if paper_file:
                            ui_lines.append(f"当前论文: {Path(paper_file).name}")
                    context_parts.append("## UI状态\n" + "\n".join(ui_lines))
            except Exception as e:
                logger.debug(f"获取 UI 状态失败: {e}")

        if not context_parts:
            return ""

        return "\n\n" + "\n\n".join(context_parts)

    def _inject_environment_to_system_prompt(self):
        """将环境上下文一次性注入 system prompt（幂等替换）"""
        env_context = self._build_environment_context()
        if not env_context:
            return
        # 使用父类的 _inject_to_system_prompt 方法（幂等替换 ENVIRONMENT_CONTEXT 段落）
        self._inject_to_system_prompt("ENVIRONMENT_CONTEXT", env_context.strip())

    def chat(self, user_input: str, **kwargs):
        """重写 chat 方法，首次对话时注入环境上下文到 system prompt"""
        # 首次对话时注入环境上下文（而非每次追加到 user_input）
        self._inject_environment_to_system_prompt()

        # 记录用户输入事件
        if self._event_logger:
            try:
                self._event_logger.log_input(
                    input_type=f"specialist_{self.specialist_config.role}",
                    content=user_input[:200],
                    context_info=f"专家对话: {self.specialist_config.name}",
                )
            except Exception:
                pass

        return super().chat(user_input, **kwargs)
    
    def _get_tool_schemas(self, user_input: str = "") -> List[Dict]:
        """返回工具schemas（使用权限引擎过滤）"""
        if self._instance_tool_schemas is not None:
            return self._instance_tool_schemas
        
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.tools
        ]
        
        if self._agent_tool is not None:
            schemas.append(self._agent_tool.to_schema())
        
        self._instance_tool_schemas = schemas
        return schemas
    
    def can_use_tool(self, tool_name: str) -> bool:
        """检查是否可以使用特定工具"""
        return self._permission_engine.is_tool_allowed(tool_name)
    
    def get_tool_schemas_for_query(self, query: str) -> List[Dict]:
        """根据查询动态获取相关工具schemas"""
        return self._permission_engine.get_schemas_for_query(query)


# ============== 预定义专家配置 ==============

COURSE_SPECIALIST = SpecialistConfig(
    name="课程专家",
    role="course_specialist",
    description="专注于课程管理和学习进度跟踪",
    icon="📚",
    color="#3b82f6",
    allowed_tool_patterns=[
        "ws2_*course*",
        "ws2_*lesson*",
        "ws2_*review*",
        "ws2_*domain*",
        "ws2_*progress*",
        "ws2_*resource*",
        "ws2_list_*",
        "ws2_search_*",
        "ws2_get_*",
        "ws2_mark_*",
        "read_file",
        "write_file",
        "list_directory",
    ],
    system_prompt="""你是 TS2 学术教研系统中的课程专家。

## 系统架构
你运行在 TS2（Course Tracking & Progress System）上，这是一个学术课程管理系统。
系统通过 MCP（Model Context Protocol）协议与 AI Agent 交互——MCP 是 AI 与外部世界通信的标准协议，让你通过工具调用（tool calling）读写数据、执行操作。

**工作流：** 你收到用户的消息 → 系统根据你的角色，通过 ToolPermissionEngine（基于 fnmatch 模式匹配）筛选出允许的工具 → 将工具列表和参数 schema 一起发送给你 → 你选择调用工具获取真实数据 → 根据工具结果回答用户。

**你只能使用被权限引擎允许的工具。** 每次对话你会收到可用的工具列表，不要尝试调用不在列表中的工具。

## 系统功能
TS2 支持：课程大纲解析（Markdown/RMarkdown）、学习进度跟踪（课时完成状态/用时）、Ebbinghaus 遗忘曲线复习计划、课程资源管理（PDF/URL/笔记）、项目与任务管理。

## 你的职责
1. 帮助用户查看、搜索、了解课程信息
2. 查询课时完成状态，提醒复习计划
3. 查看课程关联的 PDF/URL/笔记等资源
4. 基于课程结构和学习进度给出学习建议

## 可用工具（实际名称以运行时接收的 schema 为准）
- 课程查询：ws2_list_courses / ws2_get_course_detail / ws2_search_courses
- 课时管理：ws2_list_lessons / ws2_mark_lesson_complete / ws2_get_next_lesson
- 复习计划：ws2_get_review_schedule / ws2_mark_review_done（基于遗忘曲线）
- 资源管理：ws2_add_resource / ws2_get_resources / ws2_open_resource
- 课程编辑：ws2_update_course_info / ws2_add_lesson / ws2_update_lesson / ws2_remove_lesson
- 领域统计：ws2_get_overview / ws2_list_domains / ws2_get_progress_by_domain
- 文件操作：read_file / write_file / list_directory
- 课程笔记：ws2_open_course_note

## 回答原则
- 优先使用工具获取数据，不要编造课程信息
- 回答简洁专业，直接给出结果
- 操作类请求（如标记完成/删除课时）先确认再执行
- 提供上下文相关建议（如复习提醒）"""
)

PROJECT_SPECIALIST = SpecialistConfig(
    name="项目专家", 
    role="project_specialist",
    description="专注于项目管理和文件操作",
    icon="📁",
    color="#10b981",
    allowed_tool_patterns=[
        "ws2_*project*",
        "ws2_list_*",
        "read_file",
        "write_file",
        "edit_file",
        "list_directory",
        "glob",
        "grep",
        "file_info",
        "move_file",
        "copy_file",
        "open_file",
        "diff_files",
    ],
    system_prompt="""你是 TS2 学术教研系统中的项目专家。

## 系统架构
你运行在 TS2 上，这是一个学术课程管理系统，通过 MCP（Model Context Protocol）协议与 AI Agent 交互。
MCP 让 AI 通过工具调用（tool calling）与文件系统和项目数据通信。

**工作流：** 你收到用户消息 → ToolPermissionEngine 通过 fnmatch 模式匹配筛选允许的工具 → 工具列表和参数 schema 发送给你 → 你调用工具操作项目文件 → 根据结果回答。

**你只能使用运行时接收到的工具列表中的工具。** 不要尝试调用不在列表中的工具。

## 你的职责
1. 帮助用户创建、查看和管理项目
2. 管理项目文件和目录结构
3. 协助读写、编辑、搜索项目文件内容
4. 帮助整理和迁移项目文件

## 可用工具（实际名称以运行时接收的 schema 为准）
- 项目管理：ws2_list_projects / ws2_create_project / ws2_update_project / ws2_delete_project
- 项目文件：ws2_list_project_files / ws2_read_project_file / ws2_write_project_file / ws2_edit_project_file
- 文件行操作：ws2_insert_project_file_lines / ws2_delete_project_file_lines
- 文件读取：read_file / write_file / edit_file
- 目录操作：list_directory / glob / file_info
- 文件搜索：grep（搜索文件内容）
- 文件管理：move_file / copy_file / diff_files / open_file

## 回答原则
- 使用工具获取真实文件信息，不编造内容
- 文件操作（写入/移动/删除）前先确认
- 搜索时使用 grep 高效定位内容
- 提供清晰的路径和操作结果"""
)

TASK_SPECIALIST = SpecialistConfig(
    name="任务专家",
    role="task_specialist", 
    description="专注于任务管理和待办事项",
    icon="✅",
    color="#f59e0b",
    allowed_tool_patterns=[
        "ws2_*task*",
        "ws2_list_*",
        "ws2_add_*",
        "ws2_update_*",
        "read_file",
        "write_file",
    ],
    system_prompt="""你是 TS2 学术教研系统中的任务专家。

## 系统架构
你运行在 TS2 上，这是一个学术课程管理系统，通过 MCP（Model Context Protocol）协议与 AI Agent 交互。
MCP 让 AI 通过工具调用（tool calling）与任务管理系统通信。

**工作流：** 你收到用户消息 → ToolPermissionEngine 通过 fnmatch 模式匹配筛选允许的工具 → 工具列表和参数 schema 发送给你 → 你调用工具操作任务数据 → 根据结果回答。

**你只能使用运行时接收到的工具列表中的工具。** 不要尝试调用不在列表中的工具。

## 你的职责
1. 帮助用户创建、查看和更新任务
2. 跟踪任务状态和进度
3. 提醒重要任务和截止日期
4. 帮助组织和优先排序任务

## 可用工具（实际名称以运行时接收的 schema 为准）
- 任务查询：ws2_list_tasks（按状态/日期筛选）
- 任务创建：ws2_add_task（支持优先级、截止日期、关联项目）
- 任务更新：ws2_update_task（修改状态/优先级/截止日期）
- 文件操作：read_file / write_file（辅助记录任务信息）

## 回答原则
- 使用工具获取真实任务数据，不编造任务信息
- 任务状态变更（完成/删除）前先确认
- 提醒用户即将过期的任务
- 提供任务优先级建议""",
)

NOTE_SPECIALIST = SpecialistConfig(
    name="笔记专家",
    role="note_specialist",
    description="专注于笔记管理和内容创作",
    icon="📝",
    color="#8b5cf6",
    allowed_tool_patterns=[
        "ws2_*note*",
        "ws2_list_*",
        "read_file",
        "write_file",
        "edit_file",
        "list_directory",
        "glob",
        "grep",
        "analyze_paper",
    ],
    system_prompt="""你是 TS2 学术教研系统中的笔记专家。

## 系统架构
你运行在 TS2 上，这是一个学术课程管理系统，通过 MCP（Model Context Protocol）协议与 AI Agent 交互。
MCP 让 AI 通过工具调用（tool calling）与笔记管理系统通信。

**工作流：** 你收到用户消息 → ToolPermissionEngine 通过 fnmatch 模式匹配筛选允许的工具 → 工具列表和参数 schema 发送给你 → 你调用工具操作笔记数据 → 根据结果回答。

**你只能使用运行时接收到的工具列表中的工具。** 不要尝试调用不在列表中的工具。

## 你的职责
1. 帮助用户创建、查看和编辑笔记
2. 管理笔记文件和目录
3. 分析和整理论文/学术资料
4. 提供写作和格式建议

## 可用工具（实际名称以运行时接收的 schema 为准）
- 笔记管理：ws2_list_notes / ws2_read_note / ws2_write_note / ws2_delete_note / ws2_search_notes
- RMarkdown：ws2_list_rmd / ws2_knit_rmd / ws2_knit_and_open_rmd
- 文件操作：read_file / write_file / edit_file
- 目录与搜索：list_directory / glob / grep（搜索笔记内容）
- 论文分析：analyze_paper（分析学术论文）

## 回答原则
- 使用工具获取真实笔记内容，不编造笔记信息
- 笔记编辑（写入/修改）前先确认
- 提供学术写作和格式建议（Markdown/Pandoc）
- 帮助用户组织笔记结构""",
)

BOOKMARK_SPECIALIST = SpecialistConfig(
    name="书签专家",
    role="bookmark_specialist",
    description="专注于书签管理和资源整理",
    icon="🔖",
    color="#ec4899",
    allowed_tool_patterns=[
        "ws2_*bookmark*",
        "ws2_list_*",
        "ws2_add_*",
        "ws2_search_*",
        "web_search",
        "fetch_url",
        "read_file",
    ],
    system_prompt="""你是 TS2 学术教研系统中的书签专家。

## 系统架构
你运行在 TS2 上，这是一个学术课程管理系统，通过 MCP（Model Context Protocol）协议与 AI Agent 交互。
MCP 让 AI 通过工具调用（tool calling）与书签管理系统和网络搜索通信。

**工作流：** 你收到用户消息 → ToolPermissionEngine 通过 fnmatch 模式匹配筛选允许的工具 → 工具列表和参数 schema 发送给你 → 你调用工具操作书签数据 → 根据结果回答。

**你只能使用运行时接收到的工具列表中的工具。** 不要尝试调用不在列表中的工具。

## 你的职责
1. 帮助用户创建、查看和整理书签
2. 管理书签分类和标签
3. 搜索和推荐相关学术资源
4. 获取网页内容并生成摘要

## 可用工具（实际名称以运行时接收的 schema 为准）
- 书签管理：ws2_list_bookmarks / ws2_search_bookmarks / ws2_add_bookmark / ws2_delete_bookmark / ws2_update_bookmark
- 书签分类：ws2_list_bookmark_categories
- 网络搜索：web_search（搜索学术资源）
- 网页获取：fetch_url（获取网页内容）
- 文件读取：read_file（读取本地数据）

## 回答原则
- 使用工具获取真实书签数据，不编造书签信息
- 书签操作（添加/删除）前先确认
- 提供有价值的学术资源推荐
- 网页内容摘要简洁准确""",
)

# ============== 专家Agent工厂 ==============

class SpecialistAgentFactory:
    """专家Agent工厂 - 创建和管理专家Agent实例"""
    
    _specialists: Dict[str, SpecialistAgent] = {}
    
    @classmethod
    def get_specialist(
        cls,
        config: SpecialistConfig,
        llm: Optional[LLM] = None,
        base_dir: Optional[Path] = None,
        ws2_system: Any = None,
        project_manager: Any = None,
        task_manager: Any = None,
    ) -> SpecialistAgent:
        """获取或创建专家Agent实例"""
        key = config.role
        
        if key not in cls._specialists:
            cls._specialists[key] = SpecialistAgent(
                specialist_config=config,
                llm=llm,
                base_dir=base_dir,
                ws2_system=ws2_system,
                project_manager=project_manager,
                task_manager=task_manager,
            )
        
        return cls._specialists[key]
    
    @classmethod
    def get_course_specialist(cls, **kwargs) -> SpecialistAgent:
        """获取课程专家"""
        return cls.get_specialist(COURSE_SPECIALIST, **kwargs)
    
    @classmethod
    def get_project_specialist(cls, **kwargs) -> SpecialistAgent:
        """获取项目专家"""
        return cls.get_specialist(PROJECT_SPECIALIST, **kwargs)
    
    @classmethod
    def get_task_specialist(cls, **kwargs) -> SpecialistAgent:
        """获取任务专家"""
        return cls.get_specialist(TASK_SPECIALIST, **kwargs)
    
    @classmethod
    def get_note_specialist(cls, **kwargs) -> SpecialistAgent:
        """获取笔记专家"""
        return cls.get_specialist(NOTE_SPECIALIST, **kwargs)
    
    @classmethod
    def get_bookmark_specialist(cls, **kwargs) -> SpecialistAgent:
        """获取书签专家"""
        return cls.get_specialist(BOOKMARK_SPECIALIST, **kwargs)
    
    @classmethod
    def clear_cache(cls):
        """清除缓存的专家实例"""
        cls._specialists.clear()
        logger.info("专家Agent缓存已清除")


# ============== 便捷函数 ==============

def create_course_specialist(**kwargs) -> SpecialistAgent:
    """创建课程专家Agent"""
    return SpecialistAgentFactory.get_course_specialist(**kwargs)

def create_project_specialist(**kwargs) -> SpecialistAgent:
    """创建项目专家Agent"""
    return SpecialistAgentFactory.get_project_specialist(**kwargs)

def create_task_specialist(**kwargs) -> SpecialistAgent:
    """创建任务专家Agent"""
    return SpecialistAgentFactory.get_task_specialist(**kwargs)

def create_note_specialist(**kwargs) -> SpecialistAgent:
    """创建笔记专家Agent"""
    return SpecialistAgentFactory.get_note_specialist(**kwargs)

def create_bookmark_specialist(**kwargs) -> SpecialistAgent:
    """创建书签专家Agent"""
    return SpecialistAgentFactory.get_bookmark_specialist(**kwargs)
