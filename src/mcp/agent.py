#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 系统 - 基于 Cline / OpenCode / OpenClaw 架构设计
包含 Agent 循环、工具调用、并行执行、组件化提示
完全集成 WS2 系统
"""

import logging
import threading
import concurrent.futures
import time as time_module
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field

from .llm import LLM, LLMResponse, ToolCall, SimulatorLLM, MultiProviderManager, ProviderConfig
from .tools import Tool, get_tools
from .ws2_tools import get_ws2_tools
from .ws2_hub_tools import get_hub_tools
from .config import get_config_manager

try:
    from .subagent import Coordinator, SessionAgent, AgentRole, AgentSpec, SubAgentResult
    from .subagent.agent_tool import AgentTool
    HAS_SUBAGENT = True
except ImportError:
    HAS_SUBAGENT = False

try:
    from .sandbox import SandboxExecutor, SandboxPolicy, ShellSession
    HAS_SANDBOX = True
except ImportError:
    HAS_SANDBOX = False

try:
    from .harness import (
        HarnessRunner, EventStream, EventType, Turn, TurnResult,
        HookPipeline, HookSpec, ApprovalManager, ApprovalMode, ApprovalDecision,
        SessionStore,
    )
    HAS_HARNESS = True
except ImportError:
    HAS_HARNESS = False

try:
    from .mcp_client import MCPClientManager, MCPToolAdapter
    HAS_MCP_CLIENT = True
except ImportError:
    HAS_MCP_CLIENT = False

# 尝试导入 Wolfram 工具
try:
    from .wolfram_tools import register_wolfram_tools
    HAS_WOLFRAM = True
except ImportError:
    HAS_WOLFRAM = False
    register_wolfram_tools = None

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
        get_context_reloader,
    )
    HAS_CACHE = True
except ImportError:
    HAS_CACHE = False

# 导入中间件管道系统
try:
    from .middleware import (
        AgentMiddleware,
        MiddlewareContext,
        MiddlewareResult,
        MiddlewareChain,
        LoopDetectionMiddleware,
        ToolErrorMiddleware,
        DynamicContextMiddleware,
        MemoryMiddleware,
        MiddlewareAction,
    )
    HAS_MIDDLEWARE = True
except ImportError:
    HAS_MIDDLEWARE = False


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
- read_file：读取文件内容，支持按行读取和截断
- write_file：写入文件，支持 create/append 模式，**建议设置 open_after=true 以便预览**
- edit_file：编辑文件，支持5种模式：replace(搜索替换), insert(行号前插入), append(末尾追加), delete_lines(删除行范围), undo(恢复备份)，**建议设置 open_after=true 以便预览**
- list_directory：列出目录内容，支持递归、详情、过滤
- grep：搜索文件内容，支持正则、大小写忽略、上下文行
- glob：用模式查找文件，支持递归和文件信息
- calculate：数学计算，支持 numpy/scipy
- web_search：网络搜索
- fetch_url：获取网页内容
- analyze_paper：分析科研论文，支持元数据提取和分页
- open_file：用系统默认程序打开文件
- diff_files：比较两个文件差异
- move_file：移动/重命名文件
- copy_file：复制文件
- file_info：获取文件元数据

【服务端工具】（通过 WebSocket 操作 Web 前端）
- open_in_editor：在 Web 编辑器中打开文件，用户可在浏览器中查看和编辑
- list_server_files：列出服务端工作目录中的文件和子目录（不受 EXPOSED_DIRS 限制）
- read_server_file：读取服务端任意文件内容（不受 EXPOSED_DIRS 限制，适合读取项目源码）
- write_server_file：写入服务端文件（不受 EXPOSED_DIRS 限制，适合修改项目源码）
- switch_panel：切换 Web 前端面板（files/tasks/bookmarks/projects/source/courses/execution/agent/stats）
- navigate_source：在源码浏览器中导航到指定目录

【Wolfram 数学计算工具】（需要 Mathematica/Wolfram Engine）
- wolfram_calculate：通用数学计算，支持数值计算、符号计算、单位转换等
- wolfram_solve：解方程/方程组/不等式
- wolfram_integrate：计算积分（不定积分/定积分）
- wolfram_differentiate：计算导数/高阶导数
- wolfram_simplify：简化表达式（Simplify/FullSimplify/Expand/Factor）
- wolfram_linear_algebra：线性代数计算（逆矩阵/行列式/特征值等）
- wolfram_statistics：统计计算（分布/期望/方差/随机数等）
- wolfram_plot：绘制图形（2D/3D/等高线/散点）
- wolfram_query：直接运行任意 Wolfram 代码（高级功能）

【GT Agent 几何拓扑证明工具】
- gt_validate：验证证明代码的完整性和安全性
- gt_rate：对证明草图评分，检测策略性缺陷
- gt_gap_ledger：分析代码中的未解决问题(gaps)
- gt_assumption_audit：审计几何/拓扑假设
- gt_search_replace：精确搜索替换操作
- gt_evolve：在 EVOLVE 标记区域内替换占位符
- gt_workflow_run：运行完整 GT 工作流（basic/evolution 模式）

当需要使用工具时，你会先调用工具，然后根据工具的结果继续思考。

请用中文回答，保持友好和专业。
"""


def sanitize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """验证并修复消息列表，确保 tool_calls/tool 消息配对正确。

    OpenAI API 要求：assistant 消息带 tool_calls 时，必须紧跟对应的 tool 响应消息。
    此函数处理以下情况：
    1. assistant 有 tool_calls 但缺少对应的 tool 响应 → 补充占位 tool 响应
    2. 孤立的 tool 消息（无对应 tool_call）→ 移除
    3. assistant 消息中 tool_call.id 为空 → 移除该无效 tool_call
    4. assistant 消息 content 为空且无有效 tool_calls → 移除（中途打断残留）
    5. 消息角色顺序异常 → 修复
    """
    if not messages:
        return messages

    # 预处理：清理无效的 tool_calls 条目
    cleaned = []
    for msg in messages:
        role = msg.get("role", "")

        if role == "assistant" and msg.get("tool_calls"):
            # 过滤掉 id 为空/None 的 tool_call 条目
            valid_tcs = []
            for tc in msg["tool_calls"]:
                tc_dict = tc if isinstance(tc, dict) else {}
                tc_id = tc_dict.get("id")
                if tc_id:  # 只保留有有效 id 的 tool_call
                    valid_tcs.append(tc)
                else:
                    logger.debug(f"sanitize: 移除无效 tool_call (id 为空, name={tc_dict.get('function', {}).get('name', '?')})")

            if valid_tcs:
                # 保留 assistant 消息，但用清理后的 tool_calls
                cleaned_msg = dict(msg)
                cleaned_msg["tool_calls"] = valid_tcs
                cleaned.append(cleaned_msg)
            else:
                # 所有 tool_calls 都无效，检查 content 是否有意义
                content = msg.get("content", "")
                if content and content.strip():
                    # 有内容，保留为普通 assistant 消息（去掉空的 tool_calls）
                    cleaned_msg = dict(msg)
                    cleaned_msg.pop("tool_calls", None)
                    cleaned.append(cleaned_msg)
                    logger.debug("sanitize: assistant 消息的 tool_calls 全部无效，降级为普通消息")
                else:
                    # content 为空且无有效 tool_calls，跳过（中途打断残留）
                    logger.debug("sanitize: 移除空 assistant 消息（content 为空且无有效 tool_calls）")
                    continue
        else:
            # 普通 assistant 消息（无 tool_calls）：移除空 content 的
            if role == "assistant":
                c = msg.get("content", "")
                if not c or not c.strip():
                    logger.debug("sanitize: 移除空 content 的 assistant 消息")
                    continue
            cleaned.append(msg)

    # 收集所有 assistant 消息中的 tool_call_id
    assistant_tool_call_ids = set()
    for msg in cleaned:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_dict = tc if isinstance(tc, dict) else {}
                tc_id = tc_dict.get("id")
                if tc_id:
                    assistant_tool_call_ids.add(tc_id)

    # 收集所有 tool 消息中的 tool_call_id
    tool_msg_ids = set()
    for msg in cleaned:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            tool_msg_ids.add(msg["tool_call_id"])

    # 需要补充的 tool 响应（assistant 有 tool_calls 但没有对应 tool 消息）
    missing_tool_ids = assistant_tool_call_ids - tool_msg_ids

    # 需要移除的孤立 tool 消息（有 tool 消息但没有对应 tool_call）
    orphan_tool_ids = tool_msg_ids - assistant_tool_call_ids

    result = []
    for msg in cleaned:
        role = msg.get("role", "")

        # 移除孤立的 tool 消息
        if role == "tool" and msg.get("tool_call_id") in orphan_tool_ids:
            logger.debug(f"santrize: 移除孤立 tool 消息 (tool_call_id={msg['tool_call_id']})")
            continue

        # 如果 assistant 消息有 tool_calls，剔除丢失响应的 tool_call
        if role == "assistant" and msg.get("tool_calls"):
            valid_tcs = []
            for tc in msg["tool_calls"]:
                tc_dict = tc if isinstance(tc, dict) else {}
                tc_id = tc_dict.get("id")
                if tc_id and tc_id in missing_tool_ids:
                    tool_name = tc_dict.get("function", {}).get("name", "unknown")
                    logger.debug(f"santrize: 剔除丢失响应的 tool_call (id={tc_id}, tool={tool_name})")
                else:
                    valid_tcs.append(tc)
            if valid_tcs:
                msg = dict(msg)
                msg["tool_calls"] = valid_tcs
                result.append(msg)
            else:
                m = dict(msg)
                m.pop("tool_calls", None)
                result.append(m)
                logger.debug("santrize: 所有 tool_call 丢失，降级为普通消息")
        else:
            result.append(msg)

    # 二次验证：移除残留在 assistant tool_calls 中无对应 tool 响应的 id
    final = []
    i = 0
    while i < len(result):
        msg = result[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            collected_ids = set()
            j = i + 1
            while j < len(result) and result[j].get("role") == "tool":
                collected_ids.add(result[j].get("tool_call_id", ""))
                j += 1

            valid_tcs = []
            for tc in msg["tool_calls"]:
                tc_dict = tc if isinstance(tc, dict) else {}
                tc_id = tc_dict.get("id")
                if tc_id and tc_id not in collected_ids:
                    logger.debug(f"santrize: 二次验证剔除丢失响应的 tool_call (id={tc_id})")
                else:
                    valid_tcs.append(tc)

            if valid_tcs:
                msg = dict(msg)
                msg["tool_calls"] = valid_tcs
                final.append(msg)
            else:
                m = dict(msg)
                m.pop("tool_calls", None)
                final.append(m)
                logger.debug("santrize: 二次验证全部 tool_call 丢失，降级为普通消息")

            # 添加紧跟的 tool 消息
            for k in range(i + 1, j):
                final.append(result[k])
            i = j
        else:
            final.append(msg)
            i += 1

    return final


@dataclass
class AgentConfig:
    name: str = "WS2 Agent"
    system_prompt: str = SYSTEM_PROMPT
    max_rounds: int = 100
    base_dir: Optional[Path] = None
    ws2_system: Optional[Any] = None
    project_manager: Optional[Any] = None
    task_manager: Optional[Any] = None
    model_id: str = ""
    use_modern_prompt: bool = True
    auto_compact: bool = False
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
            self.tools.extend(get_tools(self.config.base_dir, enabled_only=True))
        
        # 添加 WS2 专用工具
        ws2_tools = get_ws2_tools(
            self.config.ws2_system,
            self.config.project_manager,
            self.config.task_manager,
            self.config.base_dir
        )
        self.tools.extend(ws2_tools)
        
        # 添加 DataHub 工具
        hub_tools = get_hub_tools(base_dir=self.config.base_dir)
        self.tools.extend(hub_tools)
        
        # 添加 Wolfram 数学工具
        if HAS_WOLFRAM and register_wolfram_tools:
            try:
                wolfram_tools = register_wolfram_tools()
                self.tools.extend(wolfram_tools)
                logger.info(f"已加载 {len(wolfram_tools)} 个 Wolfram 工具")
            except Exception as e:
                logger.exception(f"加载 Wolfram 工具失败: {e}")
        
        # 加载 GT Agent 工具
        try:
            from .gt.gt_tools import get_gt_tools
            gt_tools = get_gt_tools()
            self.tools.extend(gt_tools)
            logger.info(f"已加载 {len(gt_tools)} 个 GT Agent 工具")
        except Exception as e:
            logger.warning(f"加载 GT Agent 工具失败: {e}")

        try:
            from .feishu.feishu_tools import get_feishu_tools
            feishu_tools = get_feishu_tools()
            self.tools.extend(feishu_tools)
            logger.info(f"已加载 {len(feishu_tools)} 个飞书工具")
        except Exception as e:
            logger.warning(f"加载飞书工具失败: {e}")

        try:
            from .research.lean4.lean4_tools import get_lean4_tools
            lean4_tools = get_lean4_tools()
            self.tools.extend(lean4_tools)
            logger.info(f"已加载 {len(lean4_tools)} 个 Lean4 工具")
        except Exception as e:
            logger.warning(f"加载 Lean4 工具失败: {e}")

        try:
            from .research.manim.manim_tools import get_manim_tools
            manim_tools = get_manim_tools()
            self.tools.extend(manim_tools)
            logger.info(f"已加载 {len(manim_tools)} 个 Manim 工具")
        except Exception as e:
            logger.warning(f"加载 Manim 工具失败: {e}")

        try:
            from .research.mathlens.mathlens_tools import get_mathlens_tools
            mathlens_tools = get_mathlens_tools()
            self.tools.extend(mathlens_tools)
            logger.info(f"已加载 {len(mathlens_tools)} 个 MathLens 工具")
        except Exception as e:
            logger.warning(f"加载 MathLens 工具失败: {e}")
        
        try:
            from .research.autoresearch.autoresearch_tools import get_autoresearch_tools
            autoresearch_tools = get_autoresearch_tools()
            self.tools.extend(autoresearch_tools)
            logger.info(f"已加载 {len(autoresearch_tools)} 个 AutoResearch 工具")
        except Exception as e:
            logger.warning(f"加载 AutoResearch 工具失败: {e}")

        # 加载服务端工具（操作 Web 前端，动态发现 ws_manager）
        try:
            from .server.server_tools import get_server_tools
            server_tools = get_server_tools(workspace_dir=str(self.config.base_dir) if self.config.base_dir else "")
            self.tools.extend(server_tools)
            logger.info(f"已加载 {len(server_tools)} 个服务端工具")
        except Exception as e:
            logger.debug(f"加载服务端工具失败: {e}")

        # 加载多媒体工具（图片/视频读取）
        try:
            from .media_tools import get_media_tools
            media_tools = get_media_tools(base_dir=self.config.base_dir)
            self.tools.extend(media_tools)
            logger.info(f"已加载 {len(media_tools)} 个多媒体工具")
        except Exception as e:
            logger.debug(f"加载多媒体工具失败: {e}")

        # save_skill 工具已移除（技能自动保存，无需 LLM 审核）

        # 加载远程 MCP 服务工具（如百度搜索等）
        try:
            from .tools import load_mcp_service_tools
            mcp_service_tools = load_mcp_service_tools()
            if mcp_service_tools:
                self.tools.extend(mcp_service_tools)
                logger.info(f"已加载 {len(mcp_service_tools)} 个远程 MCP 服务工具")
        except Exception as e:
            logger.debug(f"加载远程 MCP 服务工具失败: {e}")

        # 确保 DataHub 全局实例已初始化
        try:
            from ws2_data_hub import init_data_hub, get_data_hub
            if not get_data_hub():
                init_data_hub(self.config.base_dir)
        except Exception:
            pass
        
        self._tool_map = {tool.name: tool for tool in self.tools}
        self.messages: List[Dict[str, Any]] = []
        self._messages_lock = threading.Lock()
        self._chat_active = threading.Event()  # 标记 chat 是否在进行中
        self._chat_active.set()  # 初始状态：无 chat 运行
        self._cancelled = False  # 标记对话是否被取消

        # 上下文注入器列表（如学习状态等外部回调）
        # 每个注入器是 Callable[[Agent, str], str]，返回要注入的上下文文本
        self._context_injectors: List = []

        # 上下文提供者（Rules/Files/Others 三层框架）— 必须在 _init_messages 之前
        try:
            from .prompt.context_provider import ContextProvider
            self._context_provider = ContextProvider(
                workspace_root=self.config.workspace_root
            )
        except Exception:
            self._context_provider = None

        self._init_messages()

        self._coordinator = None
        self._agent_tool = None
        self._sandbox = None
        self._harness = None
        self._mcp_client = None
        self._middleware_chain = MiddlewareChain() if HAS_MIDDLEWARE else None

        if HAS_MIDDLEWARE:
            try:
                self._middleware_chain.add(ToolErrorMiddleware())
                self._middleware_chain.add(DynamicContextMiddleware())
                self._middleware_chain.add(MemoryMiddleware())
                self._middleware_chain.add(LoopDetectionMiddleware())  # 连续工具错误强制停止
                from .middleware.shadow_checkpoint import CheckpointMiddleware
                ws_root = self.config.workspace_root or ""
                self._middleware_chain.add(CheckpointMiddleware(workspace_root=ws_root))
                logger.info(f"中间件管道已初始化 ({len(self._middleware_chain.middlewares)} 层)")
            except Exception as e:
                logger.warning(f"中间件管道初始化失败: {e}")
                self._middleware_chain = None

        if HAS_SUBAGENT:
            try:
                from .config import get_config_manager
                # 将主 Agent 的工具注册表传给 Coordinator，子 Agent 可按 spec 过滤使用
                tool_registry = {tool.name: tool for tool in self.tools}
                self._coordinator = Coordinator(llm=self.llm, tool_registry=tool_registry)
                self._agent_tool = AgentTool(coordinator=self._coordinator)
                self._instance_tool_schemas = None
                
                config_manager = get_config_manager()
                sub_agent_configs = config_manager.get_sub_agent_configs()
                
                role_map = {
                    "coder": AgentRole.CODER,
                    "task": AgentRole.TASK,
                    "research": AgentRole.RESEARCH,
                    "review": AgentRole.REVIEW,
                    "custom": AgentRole.CUSTOM
                }
                
                if sub_agent_configs:
                    for cfg in sub_agent_configs:
                        if not cfg.enabled:
                            continue
                        
                        agent_role = role_map.get(cfg.role, AgentRole.CUSTOM)
                        agent_spec = AgentSpec(
                            role=agent_role,
                            name=cfg.name,
                            system_prompt=cfg.system_prompt or "",
                            max_turns=cfg.max_turns
                        )
                        
                        # 如果配置了特定模型，使用该模型的 LLM
                        sub_llm = self.llm
                        if cfg.model:
                            try:
                                if hasattr(self, '_multi_provider'):
                                    # 使用 MultiProviderManager 创建子 LLM
                                    manager = self._multi_provider
                                    # 创建一个带有特定模型的新 manager
                                    from .llm import MultiProviderManager
                                    import copy
                                    
                                    # 复制配置并更新模型
                                    new_provider_configs = []
                                    for pc in manager.provider_configs:
                                        new_pc = copy.deepcopy(pc)
                                        new_pc.model = cfg.model
                                        new_provider_configs.append(new_pc)
                                    
                                    sub_manager = MultiProviderManager(new_provider_configs)
                                    
                                    # 包装成 LLM 兼容接口
                                    class _SubManagedLLM:
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
                                    
                                    sub_llm = _SubManagedLLM(sub_manager)
                                else:
                                    # 尝试直接使用 LLM 类
                                    from .llm import LLM
                                    if hasattr(self.llm, 'config'):
                                        parent_cfg = self.llm.config
                                        sub_llm = LLM(
                                            model=cfg.model or parent_cfg.model,
                                            api_key=parent_cfg.api_key,
                                            base_url=parent_cfg.base_url,
                                            temperature=parent_cfg.temperature,
                                            max_tokens=parent_cfg.max_tokens,
                                            timeout=parent_cfg.timeout,
                                        )
                            except Exception as e:
                                logger.warning(f"无法为子 Agent {cfg.name} 创建专用 LLM，使用默认 LLM: {e}")
                        
                        self._coordinator.register_agent(agent_spec, llm=sub_llm)
                    logger.info(f"子Agent系统已初始化 ({len([c for c in sub_agent_configs if c.enabled])} 个已启用)")
                else:
                    # 回退到默认配置
                    self._coordinator.register_agent(AgentSpec(
                        role=AgentRole.CODER, name="coder",
                        system_prompt="你是一个专业的编程助手。根据用户需求编写、修改、调试代码。",
                        max_turns=15,
                    ))
                    self._coordinator.register_agent(AgentSpec(
                        role=AgentRole.TASK, name="task",
                        system_prompt="你是一个任务执行助手。按照指令完成特定任务。",
                        max_turns=10,
                    ))
                    self._coordinator.register_agent(AgentSpec(
                        role=AgentRole.RESEARCH, name="research",
                        system_prompt="你是一个研究助手。搜索、分析、总结信息。",
                        max_turns=8,
                    ))
                    self._coordinator.register_agent(AgentSpec(
                        role=AgentRole.REVIEW, name="review",
                        system_prompt="你是一个代码审查助手。审查代码质量和安全性。",
                        max_turns=5,
                    ))
                    logger.info("子Agent系统已初始化 (使用默认配置)")
            except Exception as e:
                logger.warning(f"子Agent系统初始化失败: {e}")

        if HAS_SANDBOX:
            try:
                self._sandbox = SandboxExecutor(cwd=str(self.config.base_dir) if self.config.base_dir else None)
                logger.info("沙盒执行器已初始化")
            except Exception as e:
                logger.warning(f"沙盒初始化失败: {e}")

        try:
            from .sandbox.docker_sandbox import DockerSandbox
            self._docker_sandbox = DockerSandbox()
            if self._docker_sandbox.available:
                logger.info("Docker沙盒可用")
        except Exception:
            self._docker_sandbox = None

        try:
            from .tool_search import ToolGroupManager
            self._tool_group_mgr = ToolGroupManager(self.tools)
            logger.info(f"Tool Group管理器已初始化 ({len(self.tools)} 工具)")
            # 注入 group manager 到 ActivateToolGroupTool
            activate_tool = self._tool_map.get("activate_tool_group")
            if activate_tool and hasattr(activate_tool, 'set_group_manager'):
                activate_tool.set_group_manager(self._tool_group_mgr)
        except Exception as e:
            self._tool_group_mgr = None
            logger.warning(f"Tool Group管理器初始化失败: {e}")

        # 向后兼容
        self._tool_search = None

        self._memory = None
        self._user_profile = None
        try:
            from .memory import CuratedMemoryManager, UserProfileManager
            if self.config.base_dir:
                data_dir = self.config.base_dir / "data"
                self._memory = CuratedMemoryManager(data_dir / "memory.db")
                self._user_profile = UserProfileManager(data_dir / "user_profile.json")
                logger.info("记忆系统已初始化")
        except Exception as e:
            logger.warning(f"记忆系统初始化失败: {e}")

        self._skill_creator = None
        try:
            from .skill_evolution import SkillCreator
            if self.config.base_dir:
                skills_dir = self.config.base_dir / "skills"
                self._skill_creator = SkillCreator(skills_dir, llm=self.llm)
                logger.info("技能进化系统已初始化")
        except Exception as e:
            logger.warning(f"技能进化系统初始化失败: {e}")

        if HAS_HARNESS:
            try:
                from .harness import get_global_approval_manager, HarnessRunner
                
                self._harness = HarnessRunner(
                    llm=self.llm,
                    tool_registry={name: tool.execute for name, tool in self._tool_map.items()},
                    use_global_approval=True,
                )
                logger.info("Harness运行时已初始化 (使用全局审批管理器)")
            except Exception as e:
                logger.warning(f"Harness初始化失败: {e}")

        if HAS_MCP_CLIENT:
            try:
                self._mcp_client = MCPClientManager()
                logger.info("MCP客户端管理器已初始化")
            except Exception as e:
                logger.warning(f"MCP客户端初始化失败: {e}")

    def register_context_injector(self, injector):
        """注册上下文注入器，在每次 chat() 调用时回调

        Args:
            injector: callable(agent, user_input) -> str，返回要注入的上下文文本
        """
        self._context_injectors.append(injector)

    def _init_messages(self):
        with self._messages_lock:
            if self.config.use_modern_prompt and HAS_MODERN_PROMPT:
                # 加载技能内容
                skills_content = ""
                if self.config.workspace_root:
                    try:
                        from .prompt.workspace import load_workspace_files
                        ws = load_workspace_files(self.config.workspace_root)
                        if ws.skills:
                            skills_content = "\n\n---\n\n".join(ws.skills)
                    except Exception:
                        pass

                # 收集上下文提供者的静态层（Rules + Files）
                context_sources_content = ""
                if self._context_provider:
                    try:
                        # 上下文来源 token 预算：总上下文窗口的 10%
                        ctx_budget = 0
                        try:
                            from .prompt.context_window import resolve_context_tokens
                            max_tokens = resolve_context_tokens(self.config.model_id or "")
                            ctx_budget = max_tokens // 10  # 10% 给上下文来源
                        except Exception:
                            pass

                        bundle = self._context_provider.collect(
                            context={
                                "cwd": str(self.config.base_dir) if self.config.base_dir else ".",
                                "workspace_root": self.config.workspace_root or "",
                            },
                            token_budget=ctx_budget,
                        )
                        # 只注入静态层（Rules + Files），Others 由 chat 动态注入
                        static_sections = [s for s in bundle.sections if s.layer != "others"]
                        if static_sections:
                            context_sources_content = bundle.to_prompt()
                    except Exception as e:
                        logger.debug(f"上下文提供者收集失败: {e}")

                context = {
                    "cwd": str(self.config.base_dir) if self.config.base_dir else ".",
                    "model_id": self.config.model_id or "",
                    "agent_name": self.config.name,
                    "user_instructions": self.config.user_instructions,
                    "mode": self.config.mode,
                    "skills": skills_content,
                    "workspace_root": self.config.workspace_root or "",
                }
                system_prompt = build_system_prompt(
                    model_id=self.config.model_id or "",
                    context=context,
                )
                # 注入上下文来源（Rules + Files 层）
                if context_sources_content:
                    system_prompt += f"\n\n{context_sources_content}"
                # 保留旧的工作区注入兼容（仅当 context_provider 未覆盖时）
                if self.config.workspace_root and not context_sources_content:
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

    # 缓存工具 schemas 避免每轮重新生成（仅在无动态过滤时使用）
    _instance_tool_schemas: Optional[List[Dict]] = None

    def _get_tool_schemas(self, user_input: str = "") -> List[Dict]:
        """返回当前轮应发送的工具 schemas（动态过滤）

        有 ToolGroupManager 时：核心组 + WS2基本组 + 已激活意图组
        无 ToolGroupManager 时：回退到全量发送（缓存）
        """
        mgr = getattr(self, '_tool_group_mgr', None)
        if mgr is None:
            # 回退：全量发送（兼容旧逻辑）
            if self._instance_tool_schemas is not None:
                return self._instance_tool_schemas
            schemas = self._build_schemas_for_tools(self.tools)
            if self._agent_tool is not None:
                schemas.append(AgentTool.to_schema())
            self._instance_tool_schemas = schemas
            return schemas

        # 动态过滤：根据意图激活工具组
        if user_input:
            mgr.activate_for_query(user_input)

        active_tools = mgr.get_active_tools()
        schemas = self._build_schemas_for_tools(active_tools)

        if self._agent_tool is not None:
            schemas.append(AgentTool.to_schema())

        active_count = len(active_tools)
        total_count = len(self.tools)
        logger.debug(f"工具过滤: {active_count}/{total_count} 个工具发送 (激活组: {mgr._activated_groups})")

        return schemas

    def _build_schemas_for_tools(self, tools: List[Tool]) -> List[Dict]:
        """为工具列表构建 schemas"""
        schemas = []
        for tool in tools:
            tool_schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            # 注入 model_hint 到 description 末尾（model_hint 本身已带前缀，直接拼接）
            if getattr(tool, 'model_hint', ''):
                tool_schema["function"]["description"] = f"{tool.description}\n\n{tool.model_hint}"
            schemas.append(tool_schema)
        return schemas

    def _mark_tool_used(self, tool_name: str):
        """标记工具已使用，确保后续轮次保留该工具"""
        mgr = getattr(self, '_tool_group_mgr', None)
        if mgr:
            mgr.mark_tool_used(tool_name)

    def _inject_to_system_prompt(self, section_name: str, content: str):
        """向 system prompt 注入/替换指定段落（幂等，不重复）

        使用标记注释包裹段落，每次调用替换旧内容而非追加。
        格式: <!-- BEGIN_{SECTION} -->...<!-- END_{SECTION} -->
        """
        if not self.messages or self.messages[0].get("role") != "system":
            return

        begin_marker = f"<!-- BEGIN_{section_name} -->"
        end_marker = f"<!-- END_{section_name} -->"
        new_block = f"{begin_marker}\n{content}\n{end_marker}"

        system_content = self.messages[0]["content"]
        start_idx = system_content.find(begin_marker)
        end_idx = system_content.find(end_marker)

        if start_idx != -1 and end_idx != -1:
            # 替换已有段落
            self.messages[0]["content"] = (
                system_content[:start_idx]
                + new_block
                + system_content[end_idx + len(end_marker):]
            )
        else:
            # 首次注入，追加到末尾
            self.messages[0]["content"] = system_content + "\n\n" + new_block

    def _update_tool_use_in_prompt(self):
        """动态更新 system prompt 中的工具使用说明

        当 ToolGroupManager 可用时，将 TOOL_USE 部分替换为
        当前活跃工具的详细说明 + 未激活工具的摘要

        注意：如果子类（如 SpecialistAgent）重写了 _get_tool_schemas，
        则跳过此方法，因为子类有自己的工具过滤机制
        """
        mgr = getattr(self, '_tool_group_mgr', None)
        if not mgr:
            return

        # 检查子类是否重写了 _get_tool_schemas（如 SpecialistAgent）
        # 如果重写了，说明子类有自己的工具过滤逻辑，不需要动态 TOOL_USE
        if type(self)._get_tool_schemas is not Agent._get_tool_schemas:
            return

        if not self.messages or self.messages[0].get("role") != "system":
            return

        try:
            from .prompt.components import get_dynamic_tool_use_section
            active_tools = mgr.get_active_tools()
            inactive_summaries = mgr.get_inactive_tool_summaries()
            new_tool_use = get_dynamic_tool_use_section(active_tools, inactive_summaries)

            system_content = self.messages[0]["content"]

            # 优先使用标记替换（幂等）
            begin_marker = "<!-- BEGIN_TOOL_USE -->"
            end_marker = "<!-- END_TOOL_USE -->"

            start_idx = system_content.find(begin_marker)
            end_idx = system_content.find(end_marker)

            if start_idx != -1 and end_idx != -1:
                # 替换标记段落
                new_block = f"{begin_marker}\n{new_tool_use}\n{end_marker}"
                self.messages[0]["content"] = (
                    system_content[:start_idx]
                    + new_block
                    + system_content[end_idx + len(end_marker):]
                )
                return

            # 回退：查找原始 TOOL_USE 段落边界
            marker_start = "\n\nTOOL USE"
            marker_end = "\n\nRULES"

            start_idx = system_content.find(marker_start)
            end_idx = system_content.find(marker_end)

            if start_idx != -1 and end_idx != -1:
                # 首次替换，加上标记以便后续幂等替换
                new_block = f"{begin_marker}\n{new_tool_use}\n{end_marker}"
                self.messages[0]["content"] = (
                    system_content[:start_idx]
                    + "\n\n" + new_block
                    + system_content[end_idx:]
                )
            elif start_idx != -1:
                new_block = f"{begin_marker}\n{new_tool_use}\n{end_marker}"
                self.messages[0]["content"] = (
                    system_content[:start_idx]
                    + "\n\n" + new_block
                )
            else:
                # compact 后可能丢失所有标记，追加到末尾
                new_block = f"{begin_marker}\n{new_tool_use}\n{end_marker}"
                self.messages[0]["content"] = system_content + "\n\n" + new_block
        except Exception as e:
            logger.debug(f"动态更新 TOOL_USE prompt 失败: {e}")

    def _estimate_message_tokens(self, messages: List[Dict]) -> int:
        """估算消息 token 数——计入 tool_calls 结构、reasoning_content
        
        中文/代码场景中 1 char ≈ 1-2 token，此处用保守估算（÷2），
        比 ÷4 更接近实际 API 计费 token 数。
        """
        total = 0
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "") or ""
            # content
            if isinstance(content, str):
                total += len(content) // 2
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += len(part.get("text", "")) // 2
            # reasoning_content（深度思考链）
            reasoning = msg.get("reasoning_content", "") or ""
            if reasoning:
                total += len(reasoning) // 2
            # tool_calls 结构开销（assistant 消息中）
            tool_calls = msg.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list):
                for tc in tool_calls:
                    tc_args = tc.get("arguments", "") if isinstance(tc, dict) else ""
                    if isinstance(tc_args, dict):
                        import json
                        tc_args = json.dumps(tc_args)
                    total += len(str(tc.get("name", ""))) + len(str(tc_args)) + 50
            # tool_call_id（tool 消息中）
            if role == "tool" and msg.get("tool_call_id"):
                total += 20
            # 每则消息固定开销
            total += 20
        return max(total, 1)

    def _get_read_files(self) -> list:
        """获取当前会话已读取的文件列表（参考 Crush FileTracker）

        从 CheckpointMiddleware 的 FileVersionDB 中查询 read_files 表。
        """
        try:
            if hasattr(self, '_middleware_chain') and self._middleware_chain:
                for mw in self._middleware_chain._middlewares:
                    from .middleware.shadow_checkpoint import CheckpointMiddleware
                    if isinstance(mw, CheckpointMiddleware):
                        fdb = mw.fdb
                        if fdb and mw.instance_id:
                            return fdb.get_read_files(mw.instance_id)
        except Exception:
            pass
        return []

    def _compress_and_save_to_memory(self, reason: str = ""):
        """压缩上下文前让模型总结关键信息，保存到记忆

        三步流程：
        1. 生成关键信息摘要（从现有对话中提取）
        2. 存储到 CuratedMemoryManager
        3. 执行 auto_compact 压缩

        FileTracker 集成（参考 Crush）：
        - 压缩时优先保留包含已读取文件内容的消息
        - 将已读取文件列表注入摘要，避免丢失用户关注的上下文
        """
        if not self.messages or len(self.messages) < 10:
            return

        try:
            # 获取当前会话已读取的文件列表（参考 Crush FileTracker）
            read_files = self._get_read_files()

            # 步骤 1: 从对话中提取关键信息摘要
            summary_text = ""
            if HAS_MODERN_PROMPT:
                from .prompt.context_window import generate_summary
                # 只总结非 system 消息（保留最近 5 条不总结）
                summarize_msgs = []
                for msg in self.messages:
                    if msg.get("role") == "system":
                        continue
                    summarize_msgs.append(msg)
                if len(summarize_msgs) > 5:
                    summarize_msgs = summarize_msgs[:-5]  # 保留最近 5 条
                if summarize_msgs:
                    summary_text = generate_summary(summarize_msgs)
                else:
                    summary_text = "（对话内容较少，无需摘要）"

                # 将已读取文件列表追加到摘要（参考 Crush FileTracker）
                if read_files:
                    file_list = "\n".join(f"  - {p}" for p in read_files[:20])
                    summary_text += f"\n\n[用户当前关注的文件（已读取）]:\n{file_list}"
            else:
                summary_text = f"上下文压缩（原因: {reason}）"

            # 步骤 2: 存储到 CuratedMemoryManager
            if summary_text and self._memory:
                try:
                    from datetime import datetime
                    tags = ["context_summary", "compression"]
                    full_content = (
                        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] "
                        f"上下文压缩摘要 (原因: {reason or '上下文窗口接近上限'}):\n{summary_text}"
                    )
                    self._memory.store_observation(
                        content=full_content,
                        category="context",
                        importance=0.6,
                        tags=tags,
                    )
                    logger.info(f"上下文压缩摘要已保存到记忆: {len(summary_text)} 字符")
                except Exception as e:
                    logger.debug(f"记忆存储失败: {e}")

            # 步骤 3: 执行 auto_compact
            if HAS_MODERN_PROMPT:
                from .prompt.context_window import auto_compact
                original_count = len(self.messages)
                compacted, did_compact = auto_compact(self.messages, self.config.model_id or "gpt-4o", context_window_override=self.model_context_window)
                if did_compact:
                    self.messages = compacted
                compacted_count = len(self.messages)
                removed = original_count - compacted_count
                logger.info(
                    f"上下文压缩完成: {original_count}→{compacted_count} 条消息, "
                    f"移除 {removed} 条, 摘要长度 {len(summary_text)} 字符"
                )

        except Exception as e:
            logger.warning(f"上下文压缩+记忆保存失败: {e}")

    def chat(
        self,
        user_input: str,
        on_token: Optional[Callable[[str], None]] = None,
        on_tool: Optional[Callable[[str, Dict], None]] = None,
        on_tool_result: Optional[Callable[[str, str], None]] = None,
        max_tool_tokens: int = 2000,
        session_id: str = "",
    ) -> str:
        self._cancelled = False  # 新对话，清除取消标志
        self._chat_active.clear()  # 标记 chat 正在进行
        try:
            return self._chat_impl(
                user_input, on_token, on_tool, on_tool_result,
                max_tool_tokens, session_id,
            )
        finally:
            self._chat_active.set()  # 标记 chat 已结束

    def _chat_impl(
        self,
        user_input: str,
        on_token: Optional[Callable[[str], None]] = None,
        on_tool: Optional[Callable[[str, Dict], None]] = None,
        on_tool_result: Optional[Callable[[str, str], None]] = None,
        max_tool_tokens: int = 2000,
        session_id: str = "",
    ) -> str:
        with self._messages_lock:
            self.messages.append({"role": "user", "content": user_input})

        if self._memory:
            try:
                memory_ctx = self._memory.get_memory_context(user_input)
                if memory_ctx and self.messages and self.messages[0].get("role") == "system":
                    # 替换而非追加，避免重复注入
                    self._inject_to_system_prompt("MEMORY_CONTEXT", memory_ctx)
            except Exception as e:
                logger.debug(f"记忆上下文注入失败: {e}")

        if self._user_profile:
            try:
                profile_ctx = self._user_profile.get_system_prompt_injection()
                if profile_ctx and self.messages and self.messages[0].get("role") == "system":
                    pass
            except Exception:
                pass

        # 外部上下文注入（如学习状态等）— 通过 ContextProvider 的 Others 层
        if self._context_provider and self.messages and self.messages[0].get("role") == "system":
            try:
                others_sections = self._context_provider.collect_others(
                    agent=self, user_input=user_input
                )
                if others_sections:
                    others_content = "\n\n".join(
                        f"## {s.label}\n{s.content}" for s in others_sections
                    )
                    self._inject_to_system_prompt("DYNAMIC_CONTEXT", others_content)
            except Exception as e:
                logger.debug(f"动态上下文注入失败: {e}")

        # 兼容旧式上下文注入器
        if self._context_injectors and self.messages and self.messages[0].get("role") == "system":
            for injector in self._context_injectors:
                try:
                    ctx = injector(self, user_input)
                    if ctx:
                        self._inject_to_system_prompt("EXTERNAL_CONTEXT", ctx)
                except Exception as e:
                    logger.debug(f"上下文注入失败: {e}")

        model_id = self.config.model_id or "gpt-4o"

        mw_ctx = None
        if HAS_MIDDLEWARE and self._middleware_chain:
            mw_ctx = MiddlewareContext(
                session_id=session_id,
                model_id=model_id,
            )
            processed = self._middleware_chain.run_before_agent(self.messages, mw_ctx)
            if processed is None:
                return "(中间件拦截：请求被阻止)"
            self.messages = processed

        # 对话开始时预检：如果上下文已超过 55%，提前压缩
        if HAS_MODERN_PROMPT:
            est_tokens = self._estimate_message_tokens(self.messages)
            ctx_window = self.model_context_window
            if est_tokens > ctx_window * 0.55:
                logger.info(
                    f"对话开始时上下文已使用 {est_tokens}/{ctx_window} tokens "
                    f"({est_tokens/ctx_window*100:.0f}%)，自动压缩+记忆保存"
                )
                self._compress_and_save_to_memory(reason="对话开始时上下文超出阈值")

        # 动态工具过滤：首轮用用户输入激活意图组
        mgr = getattr(self, '_tool_group_mgr', None)
        if mgr and user_input:
            mgr.activate_for_query(user_input)

        # 动态更新 system prompt 中的工具使用说明
        self._update_tool_use_in_prompt()

        round_count = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        # 保存上一轮 API 实际返回的 prompt_tokens，用于更准确的判断
        _last_actual_prompt_tokens = 0

        for _ in range(self.config.max_rounds):
            round_count += 1
            # 检查是否已被取消（reset/session 切换时设置）
            if self._cancelled:
                logger.info("Agent 对话已被取消（外部 reset/session 切换），终止循环")
                return "(已取消)"
            if mw_ctx:
                mw_ctx.turn_count = round_count

            tool_schemas = self._get_tool_schemas(user_input if round_count == 1 else "")

            # 发送给 LLM 前验证消息格式，修复 tool_calls/tool 不配对问题
            safe_messages = sanitize_messages(self.messages)

            # ── 在 llm.chat() 前预检上下文，超限则提前压缩 ──
            if HAS_MODERN_PROMPT:
                # 用本轮实际估算（计入 tool_calls 结构）
                est_tokens = self._estimate_message_tokens(safe_messages)
                ctx_window = self.model_context_window

                # 优先用上一轮 API 返回的实际 prompt_tokens（更准确）
                if _last_actual_prompt_tokens > 0:
                    effective_tokens = max(est_tokens, _last_actual_prompt_tokens)
                else:
                    effective_tokens = est_tokens

                # 硬限：超过窗口 85% → 立即压缩（否则下一轮 llm.chat 必炸）
                # 软限：超过 55% → 提前压缩
                soft_limit = int(ctx_window * 0.55)
                hard_limit = int(ctx_window * 0.85)

                if effective_tokens > hard_limit:
                    logger.warning(
                        f"上下文预检 HIT HARD LIMIT: "
                        f"估算={est_tokens}, API={_last_actual_prompt_tokens}, "
                        f"窗口={ctx_window} ({effective_tokens/ctx_window*100:.0f}%), "
                        f"紧急压缩"
                    )
                    self._compress_and_save_to_memory(reason="上下文预检触及硬限")
                    safe_messages = sanitize_messages(self.messages)
                    _last_actual_prompt_tokens = 0  # 压缩后 API token 不准了

                elif effective_tokens > soft_limit:
                    logger.info(
                        f"上下文预检触发软限压缩: "
                        f"估算={est_tokens}, API={_last_actual_prompt_tokens}, "
                        f"窗口={ctx_window} ({effective_tokens/ctx_window*100:.0f}%)"
                    )
                    self._compress_and_save_to_memory(reason="上下文预检触发软限压缩")
                    safe_messages = sanitize_messages(self.messages)
                    _last_actual_prompt_tokens = 0

            if HAS_MIDDLEWARE and self._middleware_chain and mw_ctx:
                def _llm_handler(msgs):
                    return self.llm.chat(msgs, tools=tool_schemas, on_token=on_token)
                response = self._middleware_chain.run_wrap_model_call(
                    safe_messages, _llm_handler, mw_ctx
                )
            else:
                response = self.llm.chat(
                    safe_messages,
                    tools=tool_schemas,
                    on_token=on_token,
                )

            total_prompt_tokens += response.prompt_tokens
            total_completion_tokens += response.completion_tokens
            if mw_ctx:
                mw_ctx.total_prompt_tokens = total_prompt_tokens
                mw_ctx.total_completion_tokens = total_completion_tokens

            # 保存 API 实际返回的 prompt_tokens，用于下一轮预检
            _last_actual_prompt_tokens = getattr(response, 'prompt_tokens', 0)

            if getattr(response, 'cancelled', False) or self._cancelled:
                logger.info("Agent 收到取消信号，终止对话循环")
                return response.content or "(已取消)"

            if HAS_MIDDLEWARE and self._middleware_chain and mw_ctx:
                mw_result = self._middleware_chain.run_after_model(response, self.messages, mw_ctx)
                if mw_result and mw_result.force_stop:
                    logger.warning(f"中间件强制停止: {mw_result.reason}")
                    return f"(中间件停止: {mw_result.reason})"

            if not response.tool_calls:
                # 跳过空内容的 assistant 消息（无 tool_calls 且 content 为空）
                content = response.content or ""
                if not content.strip() and not response.reasoning_content:
                    logger.debug("跳过空 assistant 消息（无 tool_calls 且 content 为空）")
                    continue
                with self._messages_lock:
                    self.messages.append(response.message)
                if HAS_MIDDLEWARE and self._middleware_chain and mw_ctx:
                    self.messages = self._middleware_chain.run_after_agent(self.messages, mw_ctx)
                final = response.content or ""
                if response.reasoning_content:
                    final = f"💭 思考过程：\n{response.reasoning_content}\n\n---\n\n{final}"
                logger.info(
                    f"Agent 完成 (轮次={round_count}, "
                    f"prompt={total_prompt_tokens}, completion={total_completion_tokens})"
                )
                if self._skill_creator:
                    try:
                        creation_request = self._skill_creator.should_create_skill(self.messages)
                        if creation_request:
                            draft = self._skill_creator.generate_skill_for_review(creation_request)
                            if draft:
                                skill_name = self._skill_creator._generate_skill_name(creation_request.trigger)
                                if skill_name:
                                    result = self._skill_creator.save_skill(draft, skill_name)
                                    if result.success:
                                        logger.info(f"技能自动保存成功: {skill_name}")
                                    else:
                                        logger.debug(f"技能自动保存失败: {result.error}")
                    except Exception as e:
                        logger.debug(f"技能自动创建检查失败: {e}")
                return final

            with self._messages_lock:
                self.messages.append(response.message)

            if len(response.tool_calls) == 1:
                tc = response.tool_calls[0]
                if on_tool:
                    on_tool(tc.name, tc.arguments)
                result = self._execute_tool(tc, max_tool_tokens=max_tool_tokens, mw_ctx=mw_ctx)
                if on_tool_result:
                    on_tool_result(tc.name, result)
                # 中间件强制停止时立即终止
                if self._cancelled:
                    return "(连续工具错误，已强制停止)"
                with self._messages_lock:
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                # 标记工具已使用，确保后续轮次保留
                self._mark_tool_used(tc.name)
                # 如果激活了工具组，立即更新 prompt 和 schemas
                if tc.name == "activate_tool_group":
                    self._update_tool_use_in_prompt()
            else:
                results = self._execute_tools_parallel(
                    response.tool_calls, on_tool, max_tool_tokens=max_tool_tokens, mw_ctx=mw_ctx
                )
                # 中间件强制停止时立即终止
                if self._cancelled:
                    return "(连续工具错误，已强制停止)"
                for tc, result in zip(response.tool_calls, results):
                    if on_tool_result:
                        on_tool_result(tc.name, result)
                    with self._messages_lock:
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })
                    self._mark_tool_used(tc.name)
                    if tc.name == "activate_tool_group":
                        self._update_tool_use_in_prompt()

            # 每轮工具执行后检查上下文窗口（安全网，主防线在 llm.chat 前）
            if HAS_MODERN_PROMPT:
                est_tokens = self._estimate_message_tokens(self.messages)
                ctx_window = self.model_context_window

                if est_tokens > ctx_window * 0.65:
                    logger.warning(
                        f"上下文已使用 {est_tokens}/{ctx_window} tokens "
                        f"({est_tokens/ctx_window*100:.0f}%), 工具执行后自动压缩"
                    )
                    self._compress_and_save_to_memory(reason="工具执行后上下文超过 65%")

        if HAS_MIDDLEWARE and self._middleware_chain and mw_ctx:
            self.messages = self._middleware_chain.run_after_agent(self.messages, mw_ctx)

        logger.warning(f"已达到最大轮次 ({self.config.max_rounds})")
        return "(已达到最大轮次)"

    def _execute_tool(self, tool_call: ToolCall,
                      max_tool_tokens: int = 2000,
                      mw_ctx: Optional[Any] = None) -> str:
        _start = time_module.time()
        _error = None

        if HAS_MIDDLEWARE and self._middleware_chain and mw_ctx:
            mw_before = self._middleware_chain.run_before_tool(
                tool_call.name, tool_call.arguments or {}, mw_ctx
            )
            if mw_before.action == MiddlewareAction.STOP:
                return f'{{"success":false,"error":"中间件拦截: {mw_before.reason}"}}'

        if tool_call.name == "sub_agent" and self._agent_tool is not None:
            try:
                args = tool_call.arguments or {}
                result = self._agent_tool(
                    agent=args.get("agent", ""),
                    prompt=args.get("prompt", ""),
                    context=args.get("context"),
                )
                logger.info(f"子Agent执行完成 ({len(str(result))} 字符)")
                _result = str(result)
            except Exception as e:
                logger.error(f"子Agent执行失败: {e}")
                _result = f'{{"success":false,"error":"子Agent执行失败: {e}"}}'
                _error = str(e)
            finally:
                if self._event_logger is not None and HAS_EVENT_LOGGER:
                    _duration = int((time_module.time() - _start) * 1000)
                    try:
                        self._event_logger.log_tool_call(
                            tool_name="sub_agent",
                            tool_args=tool_call.arguments,
                            tool_result=_error or "success",
                            duration_ms=_duration,
                            context_info="agent_sub_agent_tool",
                        )
                    except Exception:
                        pass
            return _result

        tool = self._tool_map.get(tool_call.name)
        if tool is None:
            return f'{{"success":false,"error":"未知工具「{tool_call.name}」"}}'

        if hasattr(tool, 'set_system'):
            tool.set_system(
                ws2_system=self.config.ws2_system,
                project_manager=self.config.project_manager,
                task_manager=self.config.task_manager
            )

        if self._harness and self._harness.approval:
            approval = self._harness.approval
            risk_level = getattr(tool, 'risk_level', 'medium') or 'medium'
            reason = getattr(tool, 'description', None) or f"工具: {tool_call.name}"
            
            decision = approval.request_approval(
                tool_name=tool_call.name,
                tool_input=tool_call.arguments or {},
                reason=reason,
                risk_level=risk_level,
            )
            
            if decision == ApprovalDecision.DENY:
                logger.warning(f"工具 {tool_call.name} 被审批拒绝")
                return f'{{"success":false,"error":"操作被审批拒绝"}}'
            elif decision == ApprovalDecision.APPROVE or decision == ApprovalDecision.ALWAYS_APPROVE:
                logger.info(f"工具 {tool_call.name} 审批通过 (decision={decision})")

        try:
            args = tool_call.arguments or {}
            result = tool.execute(**args)
            logger.info(f"工具 {tool_call.name} 执行完成 ({len(result)} 字符)")
            if HAS_MIDDLEWARE and self._middleware_chain and mw_ctx:
                mw_after = self._middleware_chain.run_after_tool(tool_call.name, tool_call.arguments or {}, result, mw_ctx)
                if mw_after and mw_after.action == MiddlewareAction.STOP and mw_after.force_stop:
                    logger.warning(f"中间件强制停止（工具执行后）: {mw_after.reason}")
                    self._cancelled = True
                    return f'{{"success":false,"error":"中间件强制停止: {mw_after.reason}"}}'
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
            if self._event_logger is not None and HAS_EVENT_LOGGER:
                _duration = int((time_module.time() - _start) * 1000)
                try:
                    self._event_logger.log_tool_call(
                        tool_name=tool_call.name,
                        tool_args=tool_call.arguments,
                        tool_result=_error or "success",
                        duration_ms=_duration,
                        context_info="agent_execute_tool",
                    )
                except Exception:
                    pass

    def _execute_tools_parallel(
        self,
        tool_calls: List[ToolCall],
        on_tool: Optional[Callable[[str, Dict], None]] = None,
        max_tool_tokens: int = 2000,
        mw_ctx: Optional[Any] = None,
    ) -> List[str]:
        for tc in tool_calls:
            if on_tool:
                on_tool(tc.name, tc.arguments)

        timeout_per_tool = 120
        result_map: Dict[int, str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tool_calls), 8)) as executor:
            future_to_tc = {
                executor.submit(self._execute_tool, tc, max_tool_tokens, mw_ctx): tc
                for tc in tool_calls
            }
            try:
                for f in concurrent.futures.as_completed(future_to_tc, timeout=timeout_per_tool * len(tool_calls)):
                    tc = future_to_tc[f]
                    try:
                        result_map[id(tc)] = f.result(timeout=timeout_per_tool)
                    except concurrent.futures.TimeoutError:
                        result_map[id(tc)] = f'{{"success":false,"error":"工具 {tc.name} 执行超时"}}'
                    except Exception as e:
                        result_map[id(tc)] = f'{{"success":false,"error":"工具 {tc.name} 执行异常: {e}"}}'
            except concurrent.futures.TimeoutError:
                logger.error(f"工具并行执行整体超时 ({timeout_per_tool * len(tool_calls)}s)，为剩余工具填充超时结果")
                for tc in tool_calls:
                    if id(tc) not in result_map:
                        result_map[id(tc)] = f'{{"success":false,"error":"工具 {tc.name} 批处理超时"}}'

        return [
            result_map.get(id(tc), f'{{"success":false,"error":"工具 {tc.name} 结果丢失"}}')
            for tc in tool_calls
        ]

    def snapshot_messages(self) -> List[Dict[str, Any]]:
        with self._messages_lock:
            return list(self.messages)

    def restore_messages(self, messages: List[Dict[str, Any]]):
        with self._messages_lock:
            self.messages = list(messages)

    def reset(self):
        """重置对话，等待当前 chat 完成后再清空"""
        # 设置取消标志，让正在运行的 chat 立即停止追加消息
        self._cancelled = True
        # 取消 LLM 调用
        if self.llm and hasattr(self.llm, 'cancel'):
            self.llm.cancel()
        # 等待当前 chat 完成（最多等 5 秒）
        self._chat_active.wait(timeout=5.0)
        self._init_messages()
        # 重置工具组状态，避免跨对话残留
        mgr = getattr(self, '_tool_group_mgr', None)
        if mgr:
            mgr.reset_session()
        # 清除缓存的工具 schemas
        self._instance_tool_schemas = None
        # 清除取消标志，为下次 chat 做准备
        self._cancelled = False

    def cancel(self):
        """取消当前对话请求"""
        self._cancelled = True
        if self.llm and hasattr(self.llm, 'cancel'):
            self.llm.cancel()
            logger.info("[Agent.cancel] 已发送取消信号")

    def run_sub_agent(self, agent_name: str, prompt: str, context: Optional[Dict[str, Any]] = None) -> "SubAgentResult":
        """委派任务给子Agent执行"""
        if not self._coordinator:
            from .subagent.types import SubAgentResult as _SAR
            result = _SAR(agent_name=agent_name)
            result.mark_failed(error="子Agent系统未初始化")
            return result
        return self._coordinator.run(agent_name, prompt, context)

    def sandbox_execute(self, command: str, stdin_data: Optional[str] = None) -> Any:
        """在沙盒中安全执行命令"""
        if not self._sandbox:
            from .sandbox.executor import ExecutionResult
            return ExecutionResult(command=command, error="沙盒未初始化")
        return self._sandbox.execute(command, stdin_data=stdin_data)

    def sandbox_execute_script(self, script: str, language: str = "python") -> Any:
        """在沙盒中执行脚本"""
        if not self._sandbox:
            from .sandbox.executor import ExecutionResult
            return ExecutionResult(command=f"<{language} script>", error="沙盒未初始化")
        return self._sandbox.execute_script(script, language=language)

    def create_checkpoint(self, summary: str = "", snapshot_files: bool = False) -> Optional[Any]:
        """创建会话检查点（增强版 — 包含可选的文件快照和 git commit）
        
        参考 Cline 的 saveCheckpoint：
        - 消息快照（对话历史）— 始终执行
        - 文件快照（工作区文件内容）— snapshot_files=True 时执行
        - git commit hash — snapshot_files=True 且有 git 仓库时执行
        
        Args:
            summary: 检查点摘要
            snapshot_files: 是否快照工作区文件（较慢，手动检查点时建议开启）
        """
        if not HAS_CACHE:
            return None
        reloader = get_context_reloader()
        workspace_root = self.config.workspace_root or ""
        checkpoint = reloader.create_checkpoint(
            messages=self.messages,
            message_index=len(self.messages),
            total_tokens=estimate_messages_tokens(self.messages) if HAS_MODERN_PROMPT else 0,
            summary=summary,
            workspace_root=workspace_root,
            snapshot_files=snapshot_files,
        )
        reloader.save_checkpoint(checkpoint)
        logger.info(
            f"检查点已创建: {checkpoint.checkpoint_id}, "
            f"消息={checkpoint.total_messages}, "
            f"文件快照={len(checkpoint.file_snapshots)}, "
            f"git={checkpoint.git_commit_hash or 'N/A'}"
        )
        return checkpoint

    def restore_checkpoint(self, checkpoint_id: str, restore_type: str = "task") -> bool:
        """恢复会话检查点（增强版 — 支持三种恢复模式）
        
        参考 Cline 的 restoreCheckpoint：
        - "task": 只恢复对话历史（消息）
        - "workspace": 只恢复工作区文件
        - "taskAndWorkspace": 同时恢复对话和文件
        """
        if not HAS_CACHE:
            return False
        
        reloader = get_context_reloader()
        
        if restore_type in ("workspace", "taskAndWorkspace"):
            # 恢复工作区文件
            try:
                ws_ok = reloader.restore_workspace(checkpoint_id)
                if not ws_ok:
                    logger.warning(f"工作区恢复失败或无文件快照: {checkpoint_id}")
            except Exception as e:
                logger.error(f"工作区恢复异常: {e}")
        
        if restore_type in ("task", "taskAndWorkspace"):
            # 恢复对话历史
            self._cancelled = True
            if self.llm and hasattr(self.llm, 'cancel'):
                self.llm.cancel()
            self._chat_active.wait(timeout=5.0)
            
            messages = reloader.rollback_to_checkpoint(checkpoint_id)
            if messages:
                messages = sanitize_messages(messages)
                with self._messages_lock:
                    self.messages = messages
                mgr = getattr(self, '_tool_group_mgr', None)
                if mgr:
                    mgr.reset_session()
                self._instance_tool_schemas = None
                self._cancelled = False
                logger.info(f"检查点恢复成功: {checkpoint_id} (模式={restore_type})")
                return True
            self._cancelled = False
        
        return False

    @property
    def model_context_window(self) -> int:
        """获取当前模型的上下文窗口大小。
        
        优先级: ProviderConfig 手动设置 > ProviderConfig 已知模型 > model_cache > 默认值
        """
        # 优先从 ProviderConfig 获取有效上下文窗口
        if hasattr(self, 'llm') and hasattr(self.llm, 'config'):
            try:
                pc = self.llm.config
                if hasattr(pc, 'get_context_window'):
                    return pc.get_context_window()
                if pc.context_window > 0:
                    return pc.context_window
            except Exception:
                pass
        # 回退到 model_cache
        if HAS_CACHE:
            mc = get_model_cache()
            model_id = self.config.model_id or "gpt-4o"
            return mc.get_context_window(model_id)
        return 128000

    @property
    def model_can_reason(self) -> bool:
        """获取当前模型是否支持推理"""
        # 优先从 ProviderConfig 的 model_info 判断
        if hasattr(self, 'llm') and hasattr(self.llm, 'config'):
            try:
                info = self.llm.config.model_info
                if hasattr(info, 'is_reasoning_model'):
                    return info.is_reasoning_model
            except Exception:
                pass
        if HAS_CACHE:
            mc = get_model_cache()
            model_id = self.config.model_id or "gpt-4o"
            return mc.can_reason(model_id)
        return False
    
    @property
    def approval_manager(self):
        """获取审批管理器（如果可用）"""
        if HAS_HARNESS and self._harness:
            return self._harness.approval
        return None
    
    def register_approval_callback(self, callback):
        """注册审批回调函数"""
        if self.approval_manager:
            self.approval_manager.on_request(callback)

    def add_middleware(self, middleware: "AgentMiddleware"):
        """添加自定义中间件到管道"""
        if HAS_MIDDLEWARE and self._middleware_chain:
            self._middleware_chain.add(middleware)
            logger.info(f"已添加中间件: {middleware.name} (order={middleware.order})")
        else:
            logger.warning("中间件系统不可用，无法添加中间件")

    @property
    def middleware_chain(self) -> Optional["MiddlewareChain"]:
        """获取中间件链"""
        return self._middleware_chain


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
    multi_provider_manager = None

    # 尝试使用多提供商系统（MultiProviderManager 现在在 llm.py 中）
    try:
        provider_configs = config_manager.get_provider_configs_for_manager()
        if provider_configs:
            manager = MultiProviderManager(provider_configs)
            if manager.list_available_providers():
                multi_provider_manager = manager
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
                    def generate(self, prompt: str, system_prompt: str = None) -> str:
                        """简单的文本生成接口"""
                        messages = []
                        if system_prompt:
                            messages.append({"role": "system", "content": system_prompt})
                        messages.append({"role": "user", "content": prompt})
                        response = self.chat(messages)
                        return response.content
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
        auto_compact=False,
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

    agent = Agent(llm=llm, config=config, event_logger=event_logger_instance)
    
    if multi_provider_manager:
        agent._multi_provider = multi_provider_manager

    try:
        from .plugins import PluginManager
        plugin_mgr = PluginManager(plugins_dirs=[base_dir / "plugins"] if base_dir else [])
        plugin_mgr.discover_plugins()
        plugin_ctxs = plugin_mgr.load_all()
        for ctx in plugin_ctxs:
            for tool_reg in ctx.get_registered_tools():
                try:
                    from .tools import Tool
                    class _PluginTool(Tool):
                        name = tool_reg.name
                        description = tool_reg.schema.get("description", "")
                        parameters = tool_reg.schema.get("parameters", {})
                        def execute(self, **kwargs):
                            result = tool_reg.handler(**kwargs)
                            return str(result) if result is not None else ""
                    agent.tools.append(_PluginTool())
                    agent._instance_tool_schemas = None
                except Exception as e:
                    logger.warning(f"Plugin工具注册失败 {tool_reg.name}: {e}")
    except Exception as e:
        logger.debug(f"Plugin系统不可用: {e}")
    
    if base_dir:
        try:
            from .skill_system import Skill
            skills_dir = Path(base_dir) / "skills"
            if skills_dir.exists():
                discovered = 0
                for skill_subdir in sorted(skills_dir.iterdir()):
                    if not skill_subdir.is_dir():
                        continue
                    if skill_subdir.name.startswith(".") or skill_subdir.name.startswith("_"):
                        continue
                    skill_md = skill_subdir / "SKILL.md"
                    if not skill_md.exists():
                        continue
                    try:
                        skill_obj = Skill.from_skill_md(skill_subdir)
                        if skill_obj and skill_obj.name:
                            existing = config_manager.get_skill_config(skill_obj.name)
                            if not existing:
                                config_manager.add_skill_config(SkillConfig(
                                    name=skill_obj.name,
                                    description=skill_obj.description,
                                    type=skill_obj.category.value if hasattr(skill_obj.category, 'value') else str(skill_obj.category),
                                    enabled=skill_obj.enabled,
                                    metadata={
                                        "version": skill_obj.version,
                                        "author": skill_obj.author,
                                        "tags": skill_obj.tags,
                                        "allowed_tools": skill_obj.allowed_tools,
                                        "skill_dir": str(skill_subdir),
                                    },
                                ))
                            discovered += 1
                    except Exception as e:
                        logger.debug(f"技能发现跳过 {skill_subdir.name}: {e}")
                if discovered:
                    logger.info(f"从 skills/ 目录发现 {discovered} 个技能")
        except Exception as e:
            logger.debug(f"技能扫描不可用: {e}")
    
    return agent
