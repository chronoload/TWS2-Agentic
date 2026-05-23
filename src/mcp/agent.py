#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 系统 - 基于 Cline / OpenCode / OpenClaw 架构设计
包含 Agent 循环、工具调用、并行执行、组件化提示
完全集成 WS2 系统
"""

import logging
import concurrent.futures
import time as time_module
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field

from .llm import LLM, LLMResponse, ToolCall, SimulatorLLM, MultiProviderManager, ProviderConfig
from .tools import Tool, get_tools
from .ws2_tools import get_ws2_tools
from .config import get_config_manager

logger = logging.getLogger(__name__)

# 尝试导入事件日志系统
try:
    from .event_logger import EventLogger
    HAS_EVENT_LOGGER = True
except ImportError:
    HAS_EVENT_LOGGER = False
    EventLogger = None

# 尝试导入新的提示系统
try:
    from .prompt import (
        build_system_prompt,
        estimate_messages_tokens,
        should_compact,
        auto_compact,
        resolve_workspace_injection,
        get_variant_registry,
    )
    HAS_MODERN_PROMPT = True
except ImportError:
    HAS_MODERN_PROMPT = False

# 导入缓存基础设施
try:
    from .cache import (
        StateManager,
        ModelCache,
        ContextReloader,
        ContextCheckpoint,
        get_model_cache,
        get_state_manager,
    )
    HAS_CACHE = True
except ImportError:
    HAS_CACHE = False


SYSTEM_PROMPT = """你是 WS2 Agent，一个强大的 AI 学习助手，负责管理课程学习和复习。

你可以使用以下工具帮助用户完成任务：

【WS2 总览与统计工具】
- ws2_get_overview：获取 WS2 总览信息：课程总数、总课时、完成进度、总学时等
- ws2_get_domain_stats：获取域分布统计，按领域统计课程数量
- ws2_list_domains：列出所有领域
- ws2_get_progress_by_domain：按领域获取进度统计，包括课程数、课时数、完成数、完成率

【WS2 课程管理工具】
- ws2_list_courses：列出所有课程，可按领域过滤，可限制显示数量
- ws2_search_courses：搜索课程，支持按标题、描述、作者、领域匹配
- ws2_get_course_detail：获取课程详情，包括基本信息、课时列表、进度等
- ws2_create_course：创建新课程模板
- ws2_remove_course：删除课程（从内存、进度、JSON文件中移除）
- ws2_find_duplicates：检测重复课程（按标题相似度）

【WS2 课时学习工具】
- ws2_mark_lesson_complete：标记课时完成，自动更新复习调度
- ws2_get_next_lesson：获取课程的下一个待学习课时
- ws2_get_course_progress：获取课程的详细进度信息

【WS2 复习调度工具】
- ws2_get_review_schedule：获取所有待复习课程列表
- ws2_mark_review_done：标记复习完成，计算下次复习时间

【WS2 资源管理工具】
- ws2_get_resources：获取课程的资源列表（PDF、链接、视频等）

【WS2 书签管理工具】
- ws2_list_bookmarks：列出所有书签，可按分类筛选
- ws2_search_bookmarks：搜索书签
- ws2_list_bookmark_categories：列出所有书签分类
- ws2_add_bookmark：添加新书签

【WS2 笔记管理工具】
- ws2_list_notes：列出所有笔记文件
- ws2_read_note：读取笔记文件内容
- ws2_write_note：创建或更新笔记文件

【WS2 项目管理工具】
- ws2_list_projects：列出所有项目
- ws2_create_project：创建新项目

【WS2 任务看板工具】
- ws2_list_tasks：列出所有任务，可按状态/日期筛选
- ws2_add_task：添加新任务
- ws2_update_task：更新任务

【WS2 数据库管理工具】
- ws2_reload_all_sources：重新加载所有数据库源（去重合并）
- ws2_add_db_path：添加数据库源
- ws2_get_db_paths：获取当前所有数据库源路径

【WS2 RAG 知识管理工具】
- ws2_rag_add_file：向 RAG 知识库添加文件（支持 .txt, .md, .json）
- ws2_rag_add_directory：向 RAG 知识库添加整个目录的文件
- ws2_rag_add_text：向 RAG 知识库添加文本内容
- ws2_rag_search：在 RAG 知识库中搜索相关内容
- ws2_rag_get_context：获取 RAG 知识库中的上下文，用于增强回答
- ws2_rag_get_stats：获取 RAG 知识库的统计信息
- ws2_rag_clear：清空 RAG 知识库（谨慎使用）

【通用工具】
- read_file：读取文件内容
- write_file：写入文件
- edit_file：通过搜索替换编辑文件
- list_directory：列出目录内容
- grep：在文件中搜索内容
- glob：用模式查找文件
- calculate：数学计算
- web_search：网络搜索
- analyze_paper：分析科研论文

当需要使用工具时，你会先调用工具，然后根据工具的结果继续思考。

请用中文回答，保持友好和专业。
"""


@dataclass
class AgentConfig:
    name: str = "WS2 Agent"
    system_prompt: str = SYSTEM_PROMPT
    max_rounds: int = 20
    base_dir: Optional[Path] = None
    ws2_system: Optional[Any] = None
    project_manager: Optional[Any] = None
    task_manager: Optional[Any] = None
    model_id: str = ""
    use_modern_prompt: bool = True
    auto_compact: bool = True
    workspace_root: Optional[str] = None
    user_instructions: str = ""
    mode: str = "act"


class Agent:
    def __init__(
        self,
        llm: Optional[LLM] = None,
        tools: Optional[List[Tool]] = None,
        config: Optional[AgentConfig] = None,
        event_logger: Optional[Any] = None,
    ):
        self.config = config or AgentConfig()
        self.llm = llm or SimulatorLLM()
        self._event_logger = event_logger
        
        # 收集所有工具
        self.tools = []
        
        # 添加通用工具
        if tools:
            self.tools.extend(tools)
        else:
            self.tools.extend(get_tools(self.config.base_dir))
        
        # 添加 WS2 专用工具
        ws2_tools = get_ws2_tools(
            self.config.ws2_system,
            self.config.project_manager,
            self.config.task_manager,
            self.config.base_dir
        )
        self.tools.extend(ws2_tools)
        
        self._tool_map = {tool.name: tool for tool in self.tools}
        self.messages: List[Dict[str, Any]] = []
        self._init_messages()

    def _init_messages(self):
        if self.config.use_modern_prompt and HAS_MODERN_PROMPT:
            context = {
                "cwd": str(self.config.base_dir) if self.config.base_dir else ".",
                "model_id": self.config.model_id or "",
                "agent_name": self.config.name,
                "user_instructions": self.config.user_instructions,
                "mode": self.config.mode,
            }
            system_prompt = build_system_prompt(
                model_id=self.config.model_id or "",
                context=context,
            )
            if self.config.workspace_root:
                ws_injection = resolve_workspace_injection(
                    self.config.workspace_root
                )
                if ws_injection:
                    system_prompt += f"\n\n{ws_injection}"
            self.messages = [
                {"role": "system", "content": system_prompt}
            ]
        else:
            self.messages = [
                {"role": "system", "content": self.config.system_prompt}
            ]

    # 缓存工具 schemas 避免每轮重新生成
    _tool_schemas_cache = None

    def _get_tool_schemas(self) -> List[Dict]:
        """返回缓存的工具 schemas（仅首次构造）"""
        if self._tool_schemas_cache is not None:
            return self._tool_schemas_cache
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
        self.__class__._tool_schemas_cache = schemas
        return schemas

    def _estimate_message_tokens(self, messages: List[Dict]) -> int:
        """快速估算消息 token 数（~4 char/token）"""
        total = 0
        for msg in messages:
            content = msg.get("content", "") or ""
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += len(part.get("text", ""))
            # 每则消息有~3 token 开销
            total += 12
        return total // 4

    def chat(
        self,
        user_input: str,
        on_token: Optional[Callable[[str], None]] = None,
        on_tool: Optional[Callable[[str, Dict], None]] = None,
        on_tool_result: Optional[Callable[[str, str], None]] = None,
        max_tool_tokens: int = 2000,  # 工具结果消息最大 token 预算
    ) -> str:
        """处理用户消息，返回最终回复（含推理内容前缀）

        优化:
        - 缓存 tool schemas 避免每轮重新构造
        - 工具结果自动截断以防止上下文膨胀
        - 跟踪每轮 token 使用量
        """
        self.messages.append({"role": "user", "content": user_input})

        model_id = self.config.model_id or "gpt-4o"

        # 自动压缩检查（使用 ModelCache 获取精确上下文窗口）
        if (self.config.auto_compact and HAS_MODERN_PROMPT
                and should_compact(self.messages, model_id)):
            self.messages, did_compact = auto_compact(self.messages, model_id)
            if did_compact:
                logger.info(f"自动压缩对话 (模型: {model_id})")
                # 压缩后刷新 schema 缓存
                self.__class__._tool_schemas_cache = None

        round_count = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for _ in range(self.config.max_rounds):
            round_count += 1
            response = self.llm.chat(
                self.messages,
                tools=self._get_tool_schemas(),
                on_token=on_token,
            )

            total_prompt_tokens += response.prompt_tokens
            total_completion_tokens += response.completion_tokens

            if not response.tool_calls:
                self.messages.append(response.message)
                final = response.content or ""
                if response.reasoning_content:
                    final = f"💭 思考过程：\n{response.reasoning_content}\n\n---\n\n{final}"
                logger.info(
                    f"Agent 完成 (轮次={round_count}, "
                    f"prompt={total_prompt_tokens}, completion={total_completion_tokens})"
                )
                return final

            self.messages.append(response.message)

            if len(response.tool_calls) == 1:
                tc = response.tool_calls[0]
                if on_tool:
                    on_tool(tc.name, tc.arguments)
                result = self._execute_tool(tc, max_tool_tokens=max_tool_tokens)
                if on_tool_result:
                    on_tool_result(tc.name, result)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            else:
                results = self._execute_tools_parallel(
                    response.tool_calls, on_tool, max_tool_tokens=max_tool_tokens
                )
                for tc, result in zip(response.tool_calls, results):
                    if on_tool_result:
                        on_tool_result(tc.name, result)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

            # 每轮后检查上下文预算
            if HAS_MODERN_PROMPT:
                est_tokens = self._estimate_message_tokens(self.messages)
                ctx_window = self.model_context_window
                if est_tokens > ctx_window * 0.8:
                    logger.warning(
                        f"上下文已使用 {est_tokens}/{ctx_window} tokens "
                        f"({est_tokens/ctx_window*100:.0f}%), "
                        f"触发自动压缩"
                    )
                    if should_compact(self.messages, model_id):
                        self.messages, did_compact = auto_compact(self.messages, model_id)
                        if did_compact:
                            self.__class__._tool_schemas_cache = None
                            logger.info("自动压缩已触发 (budget safe)")

        logger.warning(f"已达到最大轮次 ({self.config.max_rounds})")
        return "(已达到最大轮次)"

    def _execute_tool(self, tool_call: ToolCall,
                      max_tool_tokens: int = 2000) -> str:
        """执行单个工具调用，返回完整结果（保留日志追踪，不截断）"""
        tool = self._tool_map.get(tool_call.name)
        if tool is None:
            return f'{{"success":false,"error":"未知工具「{tool_call.name}」"}}'
        
        # 确保 WS2 工具能访问所有系统实例
        if hasattr(tool, 'set_system'):
            tool.set_system(
                ws2_system=self.config.ws2_system,
                project_manager=self.config.project_manager,
                task_manager=self.config.task_manager
            )
        
        # 记录工具调用事件
        _start = time_module.time()
        _error = None
        
        try:
            result = tool.execute(**tool_call.arguments)
            logger.info(f"工具 {tool_call.name} 执行完成 ({len(result)} 字符)")
            return result
        except TypeError as e:
            _error = str(e)
            logger.error(f"工具 {tool_call.name} 参数错误: {e}")
            return f'{{"success":false,"error":"参数不正确: {e}"}}'
        except Exception as e:
            _error = str(e)
            logger.error(f"工具 {tool_call.name} 执行失败: {e}")
            return f'{{"success":false,"error":"执行失败: {e}"}}'
        finally:
            # 通过 event_logger 记录工具调用事件
            if self._event_logger is not None and HAS_EVENT_LOGGER:
                try:
                    _duration = int((time_module.time() - _start) * 1000)
                    self._event_logger.log_tool_call(
                        tool_name=tool_call.name,
                        tool_args=tool_call.arguments,
                        tool_result=_error or "success",
                        duration_ms=_duration,
                        context_info=f"agent_execute_tool"
                    )
                except Exception:
                    pass  # 事件日志失败不影响主流程

    def _execute_tools_parallel(
        self,
        tool_calls: List[ToolCall],
        on_tool: Optional[Callable[[str, Dict], None]] = None,
        max_tool_tokens: int = 2000,
    ) -> List[str]:
        """并行执行多个工具调用（带结果截断）"""
        for tc in tool_calls:
            if on_tool:
                on_tool(tc.name, tc.arguments)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(self._execute_tool, tc, max_tool_tokens)
                for tc in tool_calls
            ]
            return [f.result() for f in futures]

    def reset(self):
        """重置对话"""
        self._init_messages()

    def create_checkpoint(self, summary: str = "") -> Optional[Any]:
        """创建会话检查点"""
        if not HAS_CACHE:
            return None
        reloader = ContextReloader()
        checkpoint = reloader.create_checkpoint(
            messages=self.messages,
            message_index=len(self.messages),
            total_tokens=estimate_messages_tokens(self.messages) if HAS_MODERN_PROMPT else 0,
            summary=summary,
        )
        reloader.save_checkpoint(checkpoint)
        return checkpoint

    def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """恢复会话检查点"""
        if not HAS_CACHE:
            return False
        reloader = ContextReloader()
        messages = reloader.rollback_to_checkpoint(checkpoint_id)
        if messages:
            self.messages = messages
            return True
        return False

    @property
    def model_context_window(self) -> int:
        """获取当前模型的上下文窗口大小"""
        if HAS_CACHE:
            mc = get_model_cache()
            model_id = self.config.model_id or "gpt-4o"
            return mc.get_context_window(model_id)
        return 128000

    @property
    def model_can_reason(self) -> bool:
        """获取当前模型是否支持推理"""
        if HAS_CACHE:
            mc = get_model_cache()
            model_id = self.config.model_id or "gpt-4o"
            return mc.can_reason(model_id)
        return False


def create_agent(
    name: str = "WS2 Agent",
    base_dir: Optional[Path] = None,
    ws2_system=None,
    project_manager=None,
    task_manager=None,
) -> Agent:
    """创建并配置 Agent（自动从 ws2_system 耦合 event_logger）"""
    config_manager = get_config_manager()
    llm = None
    model_id = ""

    # 尝试使用多提供商系统（MultiProviderManager 现在在 llm.py 中）
    try:
        provider_configs = config_manager.get_provider_configs_for_manager()
        if provider_configs:
            manager = MultiProviderManager(provider_configs)
            if manager.list_available_providers():
                # 直接使用 manager 的 chat_with_fallback 方法
                # 包装成 LLM 兼容接口
                class _ManagedLLM:
                    def __init__(self, mgr):
                        self.manager = mgr
                        self.total_prompt_tokens = 0
                        self.total_completion_tokens = 0
                    def chat(self, messages, tools=None, on_token=None):
                        resp = self.manager.chat_with_fallback(messages, tools, on_token)
                        self.total_prompt_tokens += resp.prompt_tokens
                        self.total_completion_tokens += resp.completion_tokens
                        return resp
                    def is_available(self):
                        return self.manager.get_provider() is not None
                llm = _ManagedLLM(manager)
                provider = manager.get_provider()
                if provider and hasattr(provider, 'config'):
                    model_id = provider.config.model or ""
                logger.info(f"使用多提供商系统，可用提供商: {manager.list_available_providers()}")
    except Exception as e:
        logger.warning(f"初始化多提供商系统失败，回退到旧系统：{e}")

    # 如果新系统不可用，使用旧系统
    if llm is None:
        enabled_apis = config_manager.get_enabled_apis()
        if enabled_apis:
            api_config = enabled_apis[0]
            model_id = api_config.model or ""
            try:
                llm = LLM(
                    model=api_config.model or "gpt-4o",
                    api_key=api_config.api_key,
                    base_url=api_config.base_url,
                    temperature=api_config.temperature,
                    max_tokens=api_config.max_tokens,
                    timeout=api_config.timeout,
                )
            except Exception as e:
                logger.warning(f"创建 LLM 失败，使用模拟器：{e}")

    if llm is None:
        llm = SimulatorLLM()

    # 获取启用的 Skill 配置
    enabled_skill_names = [s.name for s in config_manager.get_enabled_skills()]

    # 创建工作区路径
    workspace_root = str(base_dir) if base_dir else "."

    # 创建配置 - 使用现代化的提示系统
    config = AgentConfig(
        name=name,
        base_dir=base_dir,
        ws2_system=ws2_system,
        project_manager=project_manager,
        task_manager=task_manager,
        model_id=model_id,
        use_modern_prompt=True,
        auto_compact=True,
        workspace_root=workspace_root,
    )

    # 自动从 ws2_system 耦合 event_logger
    event_logger_instance = None
    if HAS_EVENT_LOGGER and ws2_system is not None:
        try:
            # 尝试从 ws2_system 获取 event_logger
            if hasattr(ws2_system, 'event_logger') and ws2_system.event_logger is not None:
                event_logger_instance = ws2_system.event_logger
                logger.info("从 ws2_system 自动耦合 event_logger")
            elif base_dir is not None:
                # 如果 ws2_system 没有 event_logger，尝试从 base_dir 初始化
                from .event_logger import get_logger
                event_logger_instance = get_logger(Path(base_dir) / "logs" / "events")
                logger.info("从 base_dir 自动初始化 event_logger")
        except Exception as e:
            logger.warning(f"自动耦合 event_logger 失败: {e}")

    return Agent(llm=llm, config=config, event_logger=event_logger_instance)
