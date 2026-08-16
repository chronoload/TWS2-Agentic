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
from .config import get_config_manager
# 状态机抽象：AgentState(阶段枚举) / AgentAction(动作枚举) / AgentStateMachine(迁移驱动)。
# 用于把 _chat_impl 的对话主循环拆分为显式阶段（见 _stage_prepare/_stage_llm_call/...），
# 各阶段通过迁移表 _TRANSITIONS 串联成可观察、可测试的状态流。
from .agent_state import AgentState, AgentAction, AgentStateMachine

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

logger = logging.getLogger(__name__)

# 全局 pending ask 池：供非 SSE 环境（WS2 Agent 等）的 ask_followup_question
# 挂起时注册问题，前端通过 /api/agent/ask/pending 轮询拉取并弹窗（与审批恢复同构）。
_GLOBAL_PENDING_ASKS: dict = {}


def list_global_pending_asks() -> list:
    """返回全局待回答 ask 列表 [{request_id, question, options}]（自动清理过期条目）"""
    import time as _t
    now = _t.time()
    items = []
    for rid, info in list(_GLOBAL_PENDING_ASKS.items()):
        if now - info.get("created_at", 0) > 320:
            _GLOBAL_PENDING_ASKS.pop(rid, None)
            continue
        items.append({
            "request_id": rid,
            "question": info.get("question", ""),
            "options": info.get("options", []) or [],
        })
    return items

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

    OpenAI API 要求：assistant 消息带 tool_calls 时，必须紧跟对应的 tool 响应消息
    （一个 assistant 可带多个 tool_calls，其后跟多条 tool 响应；中间不得插入
    user/system/其他 assistant 消息，也不允许 tool 出现在其 assistant 之前）。

    此函数处理以下情况：
    1. assistant 有 tool_calls 但缺少对应的 tool 响应 → 剔除该 tool_call（保留 content）
    2. 孤立的 tool 消息（无对应 assistant tool_call）→ 移除
    3. assistant 消息中 tool_call.id 为空 → 移除该无效 tool_call
    4. assistant 消息 content 为空且无有效 tool_calls → 移除（中途打断残留）
    5. 消息角色顺序异常（tool 出现在 assistant 之前 / 被其他消息隔开）→
       按【全局 id 配对】重建顺序：assistant(tool_calls) 后紧跟其所有 tool 响应
    """
    if not messages:
        return messages

    # 预处理：清理无效的 tool_calls 条目（id 为空/None）
    cleaned = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "assistant" and msg.get("tool_calls"):
            valid_tcs = []
            for tc in msg["tool_calls"]:
                tc_dict = tc if isinstance(tc, dict) else {}
                tc_id = tc_dict.get("id")
                if tc_id:  # 只保留有有效 id 的 tool_call
                    valid_tcs.append(tc)
                else:
                    logger.debug(f"sanitize: 移除无效 tool_call (id 为空, name={tc_dict.get('function', {}).get('name', '?')})")
            if valid_tcs:
                cleaned_msg = dict(msg)
                cleaned_msg["tool_calls"] = valid_tcs
                cleaned.append(cleaned_msg)
            else:
                # 所有 tool_calls 都无效，检查 content 是否有意义
                content = msg.get("content", "")
                if content and content.strip():
                    cleaned_msg = dict(msg)
                    cleaned_msg.pop("tool_calls", None)
                    cleaned.append(cleaned_msg)
                    logger.debug("sanitize: assistant 消息的 tool_calls 全部无效，降级为普通消息")
                else:
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

    # ── 全局 id 配对表 ──
    # assistant 的 tool_calls：id -> 消息索引（同一 assistant 可多 id）
    assistant_tc_ids: Dict[str, int] = {}
    for i, msg in enumerate(cleaned):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_dict = tc if isinstance(tc, dict) else {}
                tc_id = tc_dict.get("id")
                if tc_id and tc_id not in assistant_tc_ids:
                    assistant_tc_ids[tc_id] = i

    # tool 响应：id -> 有序索引列表（保留原有相对顺序）
    tool_msg_indices: Dict[str, List[int]] = {}
    for i, msg in enumerate(cleaned):
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            tool_msg_indices.setdefault(msg["tool_call_id"], []).append(i)

    consumed_tool_idx: set = set()

    # ── 按顺序重建：assistant(tool_calls) 后紧跟其 tool 响应 ──
    result: List[Dict[str, Any]] = []
    for i, msg in enumerate(cleaned):
        role = msg.get("role", "")

        # tool 消息：已被对应 assistant 消费则跳过；孤立（无对应 assistant）则移除
        if role == "tool":
            if i in consumed_tool_idx:
                continue
            tid = msg.get("tool_call_id", "")
            if tid not in assistant_tc_ids:
                logger.debug(f"santrize: 移除孤立 tool 消息 (tool_call_id={tid})")
                continue
            # 有 assistant 配对但顺序异常（assistant 尚未输出）——由 assistant 分支统一输出；
            # 此处直接跳过，避免 tool 出现在 assistant 之前。
            continue

        # assistant 带 tool_calls：保留【有 tool 响应】的 tool_call，并把响应紧跟其后
        if role == "assistant" and msg.get("tool_calls"):
            valid_tcs = []
            attached_tool_msgs: List[Dict[str, Any]] = []
            for tc in msg["tool_calls"]:
                tc_dict = tc if isinstance(tc, dict) else {}
                tc_id = tc_dict.get("id")
                if tc_id and tc_id in tool_msg_indices:
                    valid_tcs.append(tc)
                    # 依次取出该 tool_call 的所有 tool 响应（并行调用可多条）
                    for tidx in tool_msg_indices[tc_id]:
                        if tidx not in consumed_tool_idx:
                            attached_tool_msgs.append(cleaned[tidx])
                            consumed_tool_idx.add(tidx)
                else:
                    tool_name = tc_dict.get("function", {}).get("name", "unknown")
                    logger.debug(f"santrize: 剔除丢失响应的 tool_call (id={tc_id}, tool={tool_name})")

            if valid_tcs:
                out_msg = dict(msg)
                out_msg["tool_calls"] = valid_tcs
                result.append(out_msg)
                result.extend(attached_tool_msgs)
            else:
                # 全部 tool_call 丢失响应：降级为普通消息（保留 content）
                m = dict(msg)
                m.pop("tool_calls", None)
                result.append(m)
                logger.debug("santrize: 所有 tool_call 丢失响应，降级为普通消息")
            continue

        result.append(msg)

    return result


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


@dataclass
class _ChatRun:
    """一次 chat 运行（_chat_impl）的上下文载体

    在 _chat_impl 入口创建，贯穿整个状态机循环，把各阶段函数（_stage_*）
    需要的输入（用户输入、会话 ID、回调、限额）与累计的中间结果
    （轮次、token 统计、工具 schemas、最新 LLM 响应）集中放在一个对象里，
    避免为每个阶段函数引入大量显式参数。

    关键字段说明：
    - mw_ctx: 中间件上下文（MiddlewareContext），阶段函数据此接入中间件管道；
    - round_count: 当前轮次，受 config.max_rounds 限制；
    - total_prompt_tokens / total_completion_tokens: 本次运行累计 token；
    - last_actual_prompt_tokens: 上一轮 API 实际上报的 prompt token，
      供上下文预检与估算取较大值，避免低估；
    - tool_schemas: 当前轮发送给模型的工具 schemas；
    - llm_response: 最近一次 LLM 响应，供 TOOL_EXEC 阶段读取 tool_calls。
    """
    user_input: str = ""
    session_id: str = ""
    on_token: Optional[Callable] = None
    on_tool: Optional[Callable] = None
    on_tool_result: Optional[Callable] = None
    max_tool_tokens: int = 2000
    mw_ctx: Optional[Any] = None
    round_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    last_actual_prompt_tokens: int = 0
    tool_schemas: Optional[List[Dict]] = None
    llm_response: Optional[Any] = None


@dataclass
class _StageResult:
    """阶段函数（_stage_*）的返回值

    - action: 请求状态机执行的迁移动作，作为进入下一状态的键；
    - done:   是否已产出最终结果并终止本次 chat（True 时驱动器直接返回 result）；
    - result: done=True 时的最终回答文本。
    """
    action: Optional[AgentAction] = None
    done: bool = False
    result: str = ""


class Agent:
    def __init__(
        self,
        llm: Optional[LLM] = None,
        tools: Optional[List[Tool]] = None,
        config: Optional[AgentConfig] = None,
        event_logger: Optional[Any] = None,
        model_selector=None,
    ):
        self.config = config or AgentConfig()
        # 规范化 base_dir：调用方（app.py / 测试）可能传 str，
        # 统一转 Path，避免后续 base_dir / "data" 抛 str/str 类型错误
        if self.config.base_dir and not isinstance(self.config.base_dir, Path):
            self.config.base_dir = Path(self.config.base_dir)
        # 模式为单实例内存态：由调用方（server 端）按会话设置/恢复，不再从全局 config 加载
        self.llm = llm or SimulatorLLM()
        self._model_selector = model_selector
        self._event_logger = event_logger
        # ask 挂起：存当前未决的 ask 请求 id，用于 answer API 唤醒
        self._pending_ask = None
        # 当前已加载的工具组管理（用于状态查询）
        self._tool_group_mgr = None
        
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

        # 其余工具组（DataHub/GT/飞书/Lean4/Manim/MathLens/AutoResearch/Wolfram/
        # 服务端/多媒体/MCP远程服务）已统一在 get_tools() 中注册，
        # 见 tools.py:get_tools() 的 _record_tool_group 调用链

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
        self._awaiting_approval = False  # 待审批状态（审批机制置位 → 状态机 awaiting_approval）
        self._is_streaming = False  # 真实流式/运行状态：chat 开始置 True，结束置 False（app.py 6 处 getattr 依赖此字段）
        self._chat_epoch = 0  # chat 代际计数：cancel/reset 递增使旧线程 finally 不再复位状态机（防误清新 chat）
        self._active_session_id = ""  # 当前活跃会话 ID
        self._last_active_time = time_module.time()  # 最后活跃时间
        # 状态机：显式驱动 chat 主循环的阶段流转（见 _chat_impl 与 _stage_* 系列），
        # 状态从 IDLE 开始，每次 chat 在 _chat_impl 入口 reset 后复用。
        self._state_machine = AgentStateMachine()
        
        # 状态变更回调列表
        self._status_callbacks: List[Callable] = []

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
                    ))
                    self._coordinator.register_agent(AgentSpec(
                        role=AgentRole.TASK, name="task",
                        system_prompt="你是一个任务执行助手。按照指令完成特定任务。",
                    ))
                    self._coordinator.register_agent(AgentSpec(
                        role=AgentRole.RESEARCH, name="research",
                        system_prompt="你是一个研究助手。搜索、分析、总结信息。",
                    ))
                    self._coordinator.register_agent(AgentSpec(
                        role=AgentRole.REVIEW, name="review",
                        system_prompt="你是一个代码审查助手。审查代码质量和安全性。",
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

        # ── Agent 核心附件（agent_assistant 非 GUI 能力 → Agent 设计内建）──
        # debug_manager / metrics / conversation_history / plugin_manager(工具桥接)
        # / workflow_engine / git_searcher / kg_rag / load_rag / async_compact
        # / submit_workflow / resume_workflow / list_recoverable_workflows
        try:
            from .agent_core import attach_agent_core
            self._agent_core_injected = attach_agent_core(self, background=True)
            logger.info(f"Agent 核心附件注入完成: {self._agent_core_injected}")
        except Exception as e:
            logger.warning(f"Agent 核心附件注入失败（不影响主流程）: {e}")

    def register_context_injector(self, injector):
        """注册上下文注入器，在每次 chat() 调用时回调

        Args:
            injector: callable(agent, user_input) -> str，返回要注入的上下文文本
        """
        self._context_injectors.append(injector)

    def register_status_callback(self, callback: Callable):
        """注册状态变更回调，在 Agent 状态变化时调用

        Args:
            callback: callable(agent, event_type, **kwargs)
                event_type: 'chat_start', 'chat_end', 'tool_call', 'message_added'
        """
        self._status_callbacks.append(callback)

    def _notify_status(self, event_type: str, **kwargs):
        """通知状态变更"""
        for cb in self._status_callbacks:
            try:
                cb(self, event_type, **kwargs)
            except Exception as e:
                logger.debug(f"Status callback error: {e}")

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

        # 可取消：收到停止信号立即跳过压缩（避免长时命令后压缩吞掉 cancel，
        # 导致对话阻塞——用户点停止后压缩仍同步跑完才响应）
        if getattr(self, '_cancelled', False):
            logger.info("上下文压缩已跳过（收到取消信号）")
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
                # 压缩步骤间可取消：摘要/归档后若收到取消信号，跳过 auto_compact 重写
                # （压缩是同步多步操作，cancel 在步骤间也能响应，不吞停止）
                if getattr(self, '_cancelled', False):
                    logger.info("上下文压缩中断（收到取消信号），跳过 auto_compact")
                    return
                # 日志式归档：压缩前保存完整原始消息（供检查点回退时展开找回历史，多次压缩可还原）
                try:
                    if HAS_CACHE:
                        from .cache.context_reloader import get_context_reloader
                        _rel = get_context_reloader()
                        _arch = _rel.create_checkpoint(
                            messages=self.messages,
                            message_index=len(self.messages),
                            total_tokens=0,
                            summary=f"[pre-compact-archive] {reason or 'auto'}",
                            workspace_root="",
                            snapshot_files=False,
                        )
                        if _arch is not None:
                            _rel.save_checkpoint(_arch)
                            logger.info(
                                f"压缩前完整历史已归档: {_arch.checkpoint_id} "
                                f"({len(self.messages)} 条消息, {reason or 'auto'})"
                            )
                except Exception as e:
                    logger.debug(f"压缩前归档失败: {e}")
                original_count = len(self.messages)
                compacted, did_compact = auto_compact(self.messages, self.config.model_id or "gpt-4o", context_window_override=self.model_context_window, force=True)
                if did_compact:
                    # 双保险：压缩后再次 sanitize（tool 配对修复 + 空消息清理），
                    # 确保发给 API 的消息序列结构合法（auto_compact 已按轮分组保证
                    # user/assistant 交替，sanitize 兜底 tool_calls/tool 配对）
                    self.messages = sanitize_messages(compacted)
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
        on_sub_agent_event: Optional[Callable[[dict], None]] = None,
    ) -> str:
        # 并发 gate：同一实例已有 chat 运行中（_chat_active 被 clear）时拒绝重入，
        # 防止 SSE 断流/前端 fallback/多端并发导致的二次 chat 线程踩踏同一
        # messages/_cancelled/状态机（普通对话"老是被打断"根因③）。
        # 调用方（app.py 流式/非流式）会捕获异常并返回明确提示。
        if not self._chat_active.is_set():
            logger.warning(f"[Agent.chat] 拒绝重入：会话 '{session_id[:12] or 'default'}' 已有对话进行中（请先停止或等待完成）")
            raise RuntimeError("对话正在进行中，请稍候（或先停止当前生成）")
        self._cancelled = False  # 新对话，清除取消标志
        self._chat_epoch += 1  # 新代际：旧线程（若有）finally 不再复位本代状态机
        my_epoch = self._chat_epoch
        self._chat_active.clear()  # 标记 chat 正在进行
        self._is_streaming = True  # 标记运行中（前端流式状态依据）
        self._last_active_time = time_module.time()  # 更新最后活跃时间
        if session_id:
            self._active_session_id = session_id
        
        # 通知状态变更：chat_start
        self._notify_status('chat_start', session_id=self._active_session_id)
        
        # 子代理执行进度回调（本次对话期间有效，供 _execute_tool 转发到流式通道）
        self._current_sub_agent_cb = on_sub_agent_event
        try:
            result = self._chat_impl(
                user_input, on_token, on_tool, on_tool_result,
                max_tool_tokens, session_id,
            )
            return result
        finally:
            self._current_sub_agent_cb = None
            if self._chat_epoch == my_epoch:
                # 本代未被 cancel/reset 换代：正常复位状态机
                self._chat_active.set()  # 标记 chat 已结束
                self._is_streaming = False  # 标记运行结束
                self._last_active_time = time_module.time()  # 更新结束时间
                # 通知状态变更：chat_end
                self._notify_status('chat_end', session_id=self._active_session_id)
            else:
                # 已被 cancel/reset 换代：状态机已复位，不重复通知（防覆盖新 chat 状态）
                self._last_active_time = time_module.time()

    def _call_llm(self, messages, tools=None, on_token=None, session_id=""):
        """调用当前模型选择器，并把真实 Agent 会话 ID 传入。"""
        if self._model_selector is not None:
            return self._model_selector.chat(
                messages,
                tools=tools,
                on_token=on_token,
                session_id=session_id or None,
            )
        return self.llm.chat(messages, tools=tools, on_token=on_token)

    def _chat_impl(
        self,
        user_input: str,
        on_token: Optional[Callable[[str], None]] = None,
        on_tool: Optional[Callable[[str, Dict], None]] = None,
        on_tool_result: Optional[Callable[[str, str], None]] = None,
        max_tool_tokens: int = 2000,
        session_id: str = "",
    ) -> str:
        """状态机驱动的对话主流程（重构自旧版内联 while 循环）

        调度流程：
        1. 复位状态机到 IDLE，创建 _ChatRun 上下文，追加用户消息；
        2. 注入各类上下文（记忆 / 动态上下文 / 外部注入器），
           然后以 AgentAction.START 启动状态机（IDLE -> PREPARE）；
        3. 进入 while 循环，按当前状态分发到对应阶段函数：
             PREPARE       -> _stage_prepare        （中间件预处理 / 上下文压缩 / 工具激活）
             LLM_CALL      -> _stage_llm_call       （调用模型并解析结果）
             TOOL_EXEC     -> _stage_tool_exec      （执行模型请求的工具）
             CONTEXT_CHECK -> _stage_context_check  （工具执行后的上下文 / 轮次检查）
        4. 每个阶段返回 _StageResult：done=True 时返回最终结果并结束循环，
           否则按 action 迁移到下一状态继续；
        5. 运行异常时，若尚未处于终态，统一以 FAIL 迁移到 ERROR 后重抛。

        与旧 _chat_impl 的行为对应关系：
        - PREPARE       = 旧实现「循环前」的准备段；
        - LLM_CALL      = 旧实现「单轮内」的模型调用段；
        - TOOL_EXEC     = 旧实现「模型返回 tool_calls 后」的执行段；
        - CONTEXT_CHECK = 旧实现「工具执行后」的轮次 / 上下文检查段。
        审批（harness approval）、上下文压缩（_compress_and_save_to_memory）、
        检查点（checkpoint）等既有能力均保留在对应阶段函数中，行为不变。

        Returns:
            最终回答文本。
        """
        sm = self._state_machine
        # 复位到 IDLE，开始新一轮运行
        sm.reset()
        run = _ChatRun(
            user_input=user_input,
            session_id=session_id,
            on_token=on_token,
            on_tool=on_tool,
            on_tool_result=on_tool_result,
            max_tool_tokens=max_tool_tokens,
        )

        with self._messages_lock:
            self.messages.append({"role": "user", "content": user_input})

        if self._memory:
            try:
                memory_ctx = self._memory.get_memory_context(user_input)
                if memory_ctx and self.messages and self.messages[0].get("role") == "system":
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

        if self._context_injectors and self.messages and self.messages[0].get("role") == "system":
            for injector in self._context_injectors:
                try:
                    ctx = injector(self, user_input)
                    if ctx:
                        self._inject_to_system_prompt("EXTERNAL_CONTEXT", ctx)
                except Exception as e:
                    logger.debug(f"上下文注入失败: {e}")

        model_id = self.config.model_id or "gpt-4o"
        if HAS_MIDDLEWARE and self._middleware_chain:
            run.mw_ctx = MiddlewareContext(
                session_id=session_id,
                model_id=model_id,
            )

        # 启动状态机：IDLE -> PREPARE
        sm.transition(AgentAction.START)

        try:
            # 状态机主循环：非终态下按当前状态分发到对应阶段函数
            while not sm.state.is_terminal:
                state = sm.state
                if state is AgentState.PREPARE:
                    step = self._stage_prepare(run)
                elif state is AgentState.LLM_CALL:
                    step = self._stage_llm_call(run)
                elif state is AgentState.TOOL_EXEC:
                    step = self._stage_tool_exec(run)
                elif state is AgentState.CONTEXT_CHECK:
                    step = self._stage_context_check(run)
                else:
                    raise RuntimeError(f"状态机处于无法处理的非终态: {state}")
                if step.done:
                    # 阶段已产出最终结果：若尚未到达终态，先按 action 收敛到终态再返回
                    if not sm.state.is_terminal:
                        sm.transition(step.action)
                    return step.result
                # 阶段尚未结束：按返回的动作迁移到下一状态，进入下一轮循环
                sm.transition(step.action)
            raise RuntimeError(f"状态机意外进入终态: {sm.state}")
        except Exception:
            # 运行异常：若尚未处于终态，统一以 FAIL 迁移到 ERROR 后重抛
            if not sm.state.is_terminal:
                sm.transition(AgentAction.FAIL)
            raise

    def _stage_prepare(self, run: _ChatRun) -> _StageResult:
        """准备阶段（对应旧 _chat_impl 的「循环前」准备段）

        职责：
        - 中间件 run_before_agent 预处理（可改写消息）；若中间件拦截
          （返回 None），直接以 done=True + COMPLETE 结束本次 chat；
        - 对话开始时估算上下文占用，超过窗口 55% 自动压缩并保存记忆；
        - 按用户输入激活工具组（ToolGroupManager），并动态更新
          system prompt 中的 TOOL_USE 说明。

        输入: run（读取 run.user_input 用于工具组激活）。
        输出: _StageResult(action=PREPARE_DONE) 迁移到 LLM_CALL；
              若被中间件拦截则返回 done=True 的结果直接结束。

        与旧 _chat_impl 的对应：本阶段代码原先位于旧实现消息追加、
        上下文注入之后的循环体外，现原样迁移到独立阶段函数。
        """
        if HAS_MIDDLEWARE and self._middleware_chain and run.mw_ctx:
            processed = self._middleware_chain.run_before_agent(self.messages, run.mw_ctx)
            if processed is None:
                return _StageResult(done=True, action=AgentAction.COMPLETE, result="(中间件拦截：请求被阻止)")
            self.messages = processed

        if HAS_MODERN_PROMPT:
            est_tokens = self._estimate_message_tokens(self.messages)
            ctx_window = self.model_context_window
            # 对话刚开始就超 55%：先压缩再继续，避免后续轮次过早触硬限
            if est_tokens > ctx_window * 0.55:
                logger.info(
                    f"对话开始时上下文已使用 {est_tokens}/{ctx_window} tokens "
                    f"({est_tokens/ctx_window*100:.0f}%)，自动压缩+记忆保存"
                )
                self._compress_and_save_to_memory(reason="对话开始时上下文超出阈值")

        mgr = getattr(self, '_tool_group_mgr', None)
        if mgr and run.user_input:
            mgr.activate_for_query(run.user_input)

        self._update_tool_use_in_prompt()

        return _StageResult(action=AgentAction.PREPARE_DONE)

    def _stage_llm_call(self, run: _ChatRun) -> _StageResult:
        """LLM 调用阶段（对应旧 _chat_impl 的「单轮内」模型调用段）

        职责（每轮一次，总轮次受 config.max_rounds 限制）：
        - 轮次计数、取消检查、同步中间件 turn 计数；
        - 获取当前轮工具 schemas（动态过滤），并 sanitize 消息配对；
        - 上下文预检：以「估算 token 与 API 实际上报 token 的较大值」
          判断，超过硬限(85%)紧急压缩、超过软限(55%)预压缩；
        - 经中间件 run_wrap_model_call（或直接 _call_llm）调用模型，
          累计 prompt/completion token 统计；
        - 模型返回 tool_calls -> 追加 assistant 消息，返回 TOOL_CALLED
          迁移到 TOOL_EXEC；模型直接给出回答 -> 组装最终文本（含思考
          过程、技能自动创建）返回 done=True + COMPLETE 结束；
        - 收到取消信号（LLM cancelled / _cancelled）返回 CANCEL 结束。

        输入: run（使用 round_count/tool_schemas/on_token/session_id 等字段）。
        输出: _StageResult —— 完成类(done=True)直接结束，
              或 action=TOOL_CALLED 迁移到 TOOL_EXEC。

        保留的既有能力：上下文压缩（_compress_and_save_to_memory）、
        技能自动创建（_skill_creator）、中间件强制停止（force_stop）。
        """
        while run.round_count < self.config.max_rounds:
            run.round_count += 1
            if self._cancelled:
                logger.info("Agent 对话已被取消（外部 reset/session 切换），终止循环")
                return _StageResult(done=True, action=AgentAction.CANCEL, result="(已取消)")
            if run.mw_ctx:
                run.mw_ctx.turn_count = run.round_count

            tool_schemas = self._get_tool_schemas(run.user_input if run.round_count == 1 else "")
            run.tool_schemas = tool_schemas

            safe_messages = sanitize_messages(self.messages)

            if HAS_MODERN_PROMPT:
                est_tokens = self._estimate_message_tokens(safe_messages)
                ctx_window = self.model_context_window
                # 用估算值与 API 实际上报值的较大者判断，避免低估上下文占用
                if run.last_actual_prompt_tokens > 0:
                    effective_tokens = max(est_tokens, run.last_actual_prompt_tokens)
                else:
                    effective_tokens = est_tokens
                soft_limit = int(ctx_window * 0.55)
                hard_limit = int(ctx_window * 0.85)
                # 硬限：预测即将超窗，压缩后必须重新 sanitize 并清空旧上报值
                if effective_tokens > hard_limit:
                    logger.warning(
                        f"上下文预检 HIT HARD LIMIT: "
                        f"估算={est_tokens}, API={run.last_actual_prompt_tokens}, "
                        f"窗口={ctx_window} ({effective_tokens/ctx_window*100:.0f}%), "
                        f"紧急压缩"
                    )
                    self._compress_and_save_to_memory(reason="上下文预检触及硬限")
                    safe_messages = sanitize_messages(self.messages)
                    run.last_actual_prompt_tokens = 0
                elif effective_tokens > soft_limit:
                    logger.info(
                        f"上下文预检触发软限压缩: "
                        f"估算={est_tokens}, API={run.last_actual_prompt_tokens}, "
                        f"窗口={ctx_window} ({effective_tokens/ctx_window*100:.0f}%)"
                    )
                    self._compress_and_save_to_memory(reason="上下文预检触发软限压缩")
                    safe_messages = sanitize_messages(self.messages)
                    run.last_actual_prompt_tokens = 0

            if HAS_MIDDLEWARE and self._middleware_chain and run.mw_ctx:
                def _llm_handler(msgs):
                    return self._call_llm(
                        msgs,
                        tools=tool_schemas,
                        on_token=run.on_token,
                        session_id=run.session_id,
                    )
                response = self._middleware_chain.run_wrap_model_call(
                    safe_messages, _llm_handler, run.mw_ctx
                )
            else:
                # 无中间件：直接调用模型（_call_llm 会优先走模型选择器）
                response = self._call_llm(
                    safe_messages,
                    tools=tool_schemas,
                    on_token=run.on_token,
                    session_id=run.session_id,
                )

            run.total_prompt_tokens += response.prompt_tokens
            run.total_completion_tokens += response.completion_tokens
            if run.mw_ctx:
                run.mw_ctx.total_prompt_tokens = run.total_prompt_tokens
                run.mw_ctx.total_completion_tokens = run.total_completion_tokens

            # 记录 API 实际上报的 prompt token，供下一轮上下文预检参考
            run.last_actual_prompt_tokens = getattr(response, 'prompt_tokens', 0)

            if getattr(response, 'cancelled', False) or self._cancelled:
                logger.info("Agent 收到取消信号，终止对话循环")
                return _StageResult(done=True, action=AgentAction.CANCEL, result=response.content or "(已取消)")

            if HAS_MIDDLEWARE and self._middleware_chain and run.mw_ctx:
                mw_result = self._middleware_chain.run_after_model(response, self.messages, run.mw_ctx)
                if mw_result and mw_result.force_stop:
                    logger.warning(f"中间件强制停止: {mw_result.reason}")
                    return _StageResult(done=True, action=AgentAction.COMPLETE, result=f"(中间件停止: {mw_result.reason})")

            if not response.tool_calls:
                content = response.content or ""
                if not content.strip() and not response.reasoning_content:
                    logger.debug("跳过空 assistant 消息（无 tool_calls 且 content 为空）")
                    continue
                with self._messages_lock:
                    self.messages.append(response.message)
                if HAS_MIDDLEWARE and self._middleware_chain and run.mw_ctx:
                    self.messages = self._middleware_chain.run_after_agent(self.messages, run.mw_ctx)
                # 模型直接给出最终回答：组装返回文本（含思考过程）
                final = response.content or ""
                if response.reasoning_content:
                    final = f"💭 思考过程：\n{response.reasoning_content}\n\n---\n\n{final}"
                logger.info(
                    f"Agent 完成 (轮次={run.round_count}, "
                    f"prompt={run.total_prompt_tokens}, completion={run.total_completion_tokens})"
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
                return _StageResult(done=True, action=AgentAction.COMPLETE, result=final)

            with self._messages_lock:
                self.messages.append(response.message)
            # 模型请求了工具：保存响应供 TOOL_EXEC 阶段执行，迁移到 TOOL_EXEC
            run.llm_response = response
            return _StageResult(action=AgentAction.TOOL_CALLED)

        if HAS_MIDDLEWARE and self._middleware_chain and run.mw_ctx:
            self.messages = self._middleware_chain.run_after_agent(self.messages, run.mw_ctx)

        logger.warning(f"已达到最大轮次 ({self.config.max_rounds})")
        return _StageResult(done=True, action=AgentAction.COMPLETE, result="(已达到最大轮次)")

    def _stage_tool_exec(self, run: _ChatRun) -> _StageResult:
        """工具执行阶段（对应旧 _chat_impl 的「模型返回 tool_calls 后」执行段）

        职责：
        - 单工具调用走 _execute_tool（含审批、ask 挂起式追问、中间件、
          checkpoint 记录）；多个工具调用走 _execute_tools_parallel 并行执行；
        - 把每个工具结果作为 tool 消息追加进对话，并回填 checkpoint_hash
          （同时回写到对应 assistant tool_call 上）；
        - ask_followup_question 的返回结果会替换为实际用户答案
          （来自 _maybe_suspend_for_ask 挂起通道）；
        - 记录工具已使用（_mark_tool_used），activate_tool_group 后刷新
          TOOL_USE prompt；
        - 执行期间收到取消信号则返回 done=True + CANCEL 结束。

        输入: run（读取 llm_response.tool_calls，回调 run.on_tool/on_tool_result）。
        输出: _StageResult(action=TOOL_DONE) 迁移到 CONTEXT_CHECK。

        保留的既有能力：工具审批（harness approval）、ask 挂起式追问、
        自动对话检查点（_auto_conversation_checkpoint）。
        """
        response = run.llm_response
        if len(response.tool_calls) == 1:
            # 单工具：串行执行，便于处理 ask 答复替换与取消检查
            tc = response.tool_calls[0]
            if run.on_tool:
                run.on_tool(tc.name, tc.arguments)
            result = self._execute_tool(tc, max_tool_tokens=run.max_tool_tokens, mw_ctx=run.mw_ctx)
            # ask_followup_question 挂起返回后，把占位结果替换成真实用户答复
            if tc.name == "ask_followup_question":
                ans = self.get_last_ask_answer()
                if ans is not None:
                    result = f"用户答复: {ans}"
            cp_hash = self._get_last_checkpoint_hash()
            if run.on_tool_result:
                run.on_tool_result(tc.name, result)
            with self._messages_lock:
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                    "checkpoint_hash": cp_hash,
                })
            self._auto_conversation_checkpoint(tc.name, cp_hash)
            if cp_hash:
                for msg in reversed(self.messages):
                    if msg.get("role") == "assistant" and msg.get("tool_calls"):
                        for t in msg["tool_calls"]:
                            if isinstance(t, dict) and t.get("id") == tc.id:
                                t["checkpoint_hash"] = cp_hash
                                break
                        break
                    elif msg.get("tool_calls"):
                        for t in msg["tool_calls"]:
                            if hasattr(t, 'id') and t.id == tc.id:
                                if hasattr(t, 'checkpoint_hash'):
                                    t.checkpoint_hash = cp_hash
                                break
                        break
            self._mark_tool_used(tc.name)
            if tc.name == "activate_tool_group":
                self._update_tool_use_in_prompt()
            if self._cancelled:
                return _StageResult(done=True, action=AgentAction.CANCEL, result="(已取消)")
        else:
            # 多工具：并行执行，逐个追加 tool 消息并回填 checkpoint_hash
            results = self._execute_tools_parallel(
                response.tool_calls, run.on_tool, max_tool_tokens=run.max_tool_tokens, mw_ctx=run.mw_ctx
            )
            for tc, result in zip(response.tool_calls, results):
                cp_hash = self._get_last_checkpoint_hash()
                if run.on_tool_result:
                    run.on_tool_result(tc.name, result)
                with self._messages_lock:
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                        "checkpoint_hash": cp_hash,
                    })
                self._auto_conversation_checkpoint(tc.name, cp_hash)
                if cp_hash:
                    for msg in reversed(self.messages):
                        if msg.get("role") == "assistant" and msg.get("tool_calls"):
                            for t in msg["tool_calls"]:
                                if isinstance(t, dict) and t.get("id") == tc.id:
                                    t["checkpoint_hash"] = cp_hash
                                    break
                                elif hasattr(t, 'id') and t.id == tc.id:
                                    if hasattr(t, 'checkpoint_hash'):
                                        t.checkpoint_hash = cp_hash
                                    break
                            break
                self._mark_tool_used(tc.name)
                if tc.name == "activate_tool_group":
                    self._update_tool_use_in_prompt()
            if self._cancelled:
                return _StageResult(done=True, action=AgentAction.CANCEL, result="(已取消)")
        # 工具全部执行完成：迁移到 CONTEXT_CHECK 检查上下文与轮次
        return _StageResult(action=AgentAction.TOOL_DONE)

    def _stage_context_check(self, run: _ChatRun) -> _StageResult:
        """上下文检查阶段（对应旧 _chat_impl 的「工具执行后」检查段）

        职责：
        - 工具执行后估算上下文占用，超过窗口 65% 自动压缩并保存记忆，
          为新一轮 LLM 调用腾出空间；
        - 达到最大轮次则运行中间件 run_after_agent 并 done=True + COMPLETE 结束；
        - 否则返回 NEXT_ROUND，回到 LLM_CALL 开始新一轮。

        输入: run（读取 run.round_count 与最大轮次上限比较）。
        输出: _StageResult —— action=NEXT_ROUND 进入下一轮，
              或 done=True + COMPLETE 结束。
        """
        if HAS_MODERN_PROMPT and not self._cancelled:
            est_tokens = self._estimate_message_tokens(self.messages)
            ctx_window = self.model_context_window
            # 工具结果可能携带大量文本：超 65% 即压缩，避免下一轮触硬限
            # （收到取消信号则不压缩——压缩是同步多步操作，避免吞掉 cancel 造成阻塞）
            if est_tokens > ctx_window * 0.65:
                logger.warning(
                    f"上下文已使用 {est_tokens}/{ctx_window} tokens "
                    f"({est_tokens/ctx_window*100:.0f}%), 工具执行后自动压缩"
                )
                self._compress_and_save_to_memory(reason="工具执行后上下文超过 65%")

        if run.round_count >= self.config.max_rounds:
            if HAS_MIDDLEWARE and self._middleware_chain and run.mw_ctx:
                self.messages = self._middleware_chain.run_after_agent(self.messages, run.mw_ctx)
            logger.warning(f"已达到最大轮次 ({self.config.max_rounds})")
            return _StageResult(done=True, action=AgentAction.COMPLETE, result="(已达到最大轮次)")

        # 未达上限：进入下一轮（CONTEXT_CHECK -> LLM_CALL）
        return _StageResult(action=AgentAction.NEXT_ROUND)

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
                # 转发子代理执行进度到主流式通道（前端实时显示工具请求/进程）
                _sub_event_cb = getattr(self, '_current_sub_agent_cb', None)
                result = self._agent_tool(
                    agent=args.get("agent", ""),
                    prompt=args.get("prompt", ""),
                    context=args.get("context"),
                    on_event=_sub_event_cb,
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

            # ask_followup_question 挂起式：检查 _suspend_ask 标志，触发后挂起 turn。
            # 挂起返回后直接携带真实答案（单/多工具路径都正确，多工具并行不再依赖外部替换）
            if tool_call.name == "ask_followup_question":
                _ask_rid = self._maybe_suspend_for_ask(result)
                if _ask_rid is not None:
                    _ans = (getattr(self, "_last_ask_answers", None) or {}).pop(_ask_rid, None)
                    if _ans is None:
                        _ans = self.get_last_ask_answer() or "（用户未作答）"
                    import json as _json2
                    return _json2.dumps({"success": True, "answer": _ans, "suspended": "ask"}, ensure_ascii=False)

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
                        # 超时：保留 JSON 格式，但不设置 _cancelled，让结果注入循环
                        result_map[id(tc)] = f'{{"success":false,"error":"工具 {tc.name} 执行超时({timeout_per_tool}秒)"}}'
                    except Exception as e:
                        result_map[id(tc)] = f'{{"success":false,"error":"工具 {tc.name} 执行异常: {e}"}}'
            except concurrent.futures.TimeoutError:
                logger.warning(f"工具并行执行整体超时，为剩余工具填充超时结果")
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

    # ─── 模式 setter（单实例内存态，持久化由 server 端按会话负责）───
    def set_mode(self, mode: str) -> str:
        """设置本实例运行模式（act|plan）。返回归一化后的模式。"""
        mode = (mode or "act").strip().lower()
        if mode not in ("act", "plan"):
            mode = "act"
        self.config.mode = mode
        logger.info(f"Agent 模式已切换为 {mode}")
        return mode

    def get_mode(self) -> str:
        return getattr(self.config, "mode", "act") or "act"

    # ─── ask/answer 追问接口（供 server 端点调用）───
    def set_pending_ask(self, request_id: str) -> None:
        """标记当前 turn 挂起在 ask 问题上（支持并发多挂起：字典按 rid 区分）"""
        if getattr(self, "_pending_asks", None) is None:
            self._pending_asks = {}
        self._pending_asks[request_id] = True
        self._awaiting_approval = True

    def clear_pending_ask(self, request_id: Optional[str] = None) -> None:
        if getattr(self, "_pending_asks", None) is None:
            self._pending_asks = {}
        if request_id:
            self._pending_asks.pop(request_id, None)
        else:
            self._pending_asks.clear()
        if not self._pending_asks:
            self._awaiting_approval = False

    def get_pending_ask(self) -> Optional[str]:
        """返回任一挂起 rid（兼容旧调用）；answer 端点应优先用 has_pending_ask(rid)"""
        return next(iter(getattr(self, "_pending_asks", None) or {}), None)

    def has_pending_ask(self, request_id: str) -> bool:
        return request_id in (getattr(self, "_pending_asks", None) or {})

    def _maybe_suspend_for_ask(self, tool_result: str) -> Optional[str]:
        """ask_followup_question 调用后:挂起并等答案。返回挂起 rid（已答/超时后），None 表示非挂起。

        双通道：
        - 有 SSE ask 通道（_current_ask_sender，TS2 前端会话）→ 实时推送 ask 事件；
        - 无通道（WS2/隔离环境，sender=None）→ 问题存入全局 _GLOBAL_PENDING_ASKS 池，
          前端经 /api/agent/ask/pending 轮询拉取弹窗（复用 approval 恢复机制）。
        两条路径都 set_pending_ask + 阻塞等 answer API 唤醒（最长 300s）。
        答案按 rid 存 _last_ask_answers（并发多挂起互不覆盖），并同步单值 _last_ask_answer 兼容旧调用。
        """
        import json as _json
        import time as _t
        try:
            payload = _json.loads(tool_result)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        # _suspend_ask 在 ToolResult 的 data 里（to_json=asdict 扁平化）：
        #   {"success":true,"data":{"question":...,"options":[...],"_suspend_ask":true},"message":...}
        # 兼容顶层直传（WS2/其他通道可能的精简包装）。
        _data = payload.get("data") or {}
        if not (payload.get("_suspend_ask") or _data.get("_suspend_ask")):
            return None
        import uuid as _u
        rid = _u.uuid4().hex[:8]
        question = payload.get("question") or _data.get("question", "")
        options = payload.get("options") or _data.get("options") or []
        if not isinstance(options, list):
            options = []
        if getattr(self, "_last_ask_answers", None) is None:
            self._last_ask_answers = {}
        self.set_pending_ask(rid)
        sender = getattr(self, "_current_ask_sender", None)
        if sender is not None:
            try:
                sender({"type": "ask", "request_id": rid, "question": question, "options": options})
            except Exception:
                pass
        # 无论是否有 SSE 通道，都注册全局池（前端轮询兜底，双保险）。
        # 避免 WS2 等实例存在 _current_ask_sender 时只推 SSE、问题不进池，
        # 导致前端轮询 ask/pending 拉不到 → 不弹窗 → answer 匹配失败 → Agent 干等 300s。
        try:
            _GLOBAL_PENDING_ASKS[rid] = {
                "question": question,
                "options": options,
                "created_at": _t.time(),
                "agent": self,
            }
        except Exception:
            pass
        # 阻塞主线程（最长 300s），由 answer API 写入 _last_ask_answers[rid] 唤醒
        print(f"[ASK] {rid} 挂起等待答案 (sender={'有' if sender else '无'}, 全局池注册={'ok' if rid in _GLOBAL_PENDING_ASKS else 'FAIL'}, 实例id={id(self)})", flush=True)
        deadline = _t.time() + 300
        while _t.time() < deadline:
            if rid in self._last_ask_answers:
                print(f"[ASK] {rid} 读到答案 唤醒 (实例id={id(self)})", flush=True)
                break
            if not self._pending_asks.get(rid):
                print(f"[ASK] {rid} pending 已清 退出 (实例id={id(self)})", flush=True)
                break
            _t.sleep(0.1)
        answer = self._last_ask_answers.get(rid)
        if answer is None:
            answer = "（用户未作答）"
            print(f"[ASK] {rid} 300s 超时未作答 (实例id={id(self)})", flush=True)
        # 同步单值兼容旧调用（单工具串行路径）
        self._last_ask_answer = answer
        self.clear_pending_ask(rid)
        try:
            _GLOBAL_PENDING_ASKS.pop(rid, None)
        except Exception:
            pass
        return rid

    def get_last_ask_answer(self) -> Optional[str]:
        return getattr(self, "_last_ask_answer", None)

    def reset(self):
        """重置对话，等待当前 chat 完成后再清空"""
        # 设置取消标志，让正在运行的 chat 立即停止追加消息
        self._cancelled = True
        # 取消 LLM 调用
        if self.llm and hasattr(self.llm, 'cancel'):
            self.llm.cancel()
        # 等待当前 chat 完成（最多等 5 秒）
        self._chat_active.wait(timeout=5.0)
        # 换代 + 强制复位：chat 可能 wait 超时仍在运行，
        # 递增 _chat_epoch 使该线程 finally 不再复位状态机，
        # 并手动 set/False 确保本 reset 后处于空闲态。
        self._chat_epoch += 1
        self._chat_active.set()
        self._is_streaming = False
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
        """取消当前对话请求

        立即复位状态机（_chat_active.set / _is_streaming=False），
        并递增 _chat_epoch 使旧 chat 线程的 finally 不再复位状态机，
        避免「前端已复位、后端仍卡 running」以及「旧线程 finally 误清新 chat」。
        """
        self._cancelled = True
        if self.llm and hasattr(self.llm, 'cancel'):
            self.llm.cancel()
            logger.info("[Agent.cancel] 已发送取消信号")
        self._chat_epoch += 1  # 换代：旧 chat finally 不再复位
        self._chat_active.set()  # 立即标记为空闲
        self._is_streaming = False  # 立即标记非运行中
        self._notify_status('chat_cancelled', session_id=self._active_session_id)

    def _get_last_checkpoint_hash(self) -> str:
        """从 CheckpointMiddleware 获取最后一个 checkpoint hash

        优先返回 _last_checkpoint_id（每次工具调用都更新的 SQLite id，
        与 SSE tool_result / 前端一致），回退 git hash。
        否则中间步骤工具调用的 hash 为空 → 会话重载/诚实渲染后工具卡片
        checkpoint 丢失，无法恢复。
        """
        try:
            if HAS_MIDDLEWARE and self._middleware_chain:
                for mw in self._middleware_chain._middlewares:
                    from .middleware.shadow_checkpoint import CheckpointMiddleware
                    if isinstance(mw, CheckpointMiddleware):
                        cp_id = getattr(mw, '_last_checkpoint_id', 0)
                        if cp_id and cp_id > 0:
                            return str(cp_id)
                        return getattr(mw, '_last_hash', '') or ''
        except Exception:
            pass
        return ''

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

    def _auto_conversation_checkpoint(self, tool_name: str, sqlite_cp_hash: str) -> str:
        """通用流程自动创建对话快照（迁移自 agent_assistant 的每轮自动保存）

        每次工具调用后创建一个 ContextReloader 的 cp-* 消息快照，并将其 id
        回填到 SQLite checkpoints 记录的 conversation_checkpoint_id，使前端
        回退检查点时后端能恢复对话历史（restore API 按 SQLite id 反查 cp-*）。
        """
        try:
            if not HAS_CACHE:
                return ""
            sqlite_id = None
            if sqlite_cp_hash and str(sqlite_cp_hash).isdigit():
                sqlite_id = int(sqlite_cp_hash)
            step_info = f"#{sqlite_cp_hash}" if sqlite_id else ""
            cp = self.create_checkpoint(
                summary=f"{step_info} {tool_name or '对话'}",
                snapshot_files=False,
            )
            if cp is None:
                return ""
            cp_id = getattr(cp, "checkpoint_id", "") or str(cp)
            # 回填关联：SQLite 检查点 → ContextReloader 对话快照
            if sqlite_id and HAS_MIDDLEWARE and self._middleware_chain:
                try:
                    from .middleware.shadow_checkpoint import CheckpointMiddleware
                    for mw in self._middleware_chain._middlewares:
                        if isinstance(mw, CheckpointMiddleware) and getattr(mw, "fdb", None):
                            mw.fdb.update_conversation_checkpoint(sqlite_id, str(cp_id))
                            break
                except Exception:
                    pass
            return str(cp_id)
        except Exception as e:
            logger.debug(f"自动对话检查点创建失败: {e}")
            return ""

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
    model_selector = None

    try:
        from .model_selector import get_model_selector
        model_selector = get_model_selector()
    except Exception as e:
        logger.warning(f"模型选择器初始化失败，使用传统 LLM 路径：{e}")

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

    agent = Agent(
        llm=llm,
        config=config,
        event_logger=event_logger_instance,
        model_selector=model_selector,
    )
    
    if multi_provider_manager:
        agent._multi_provider = multi_provider_manager

    try:
        from .plugins import PluginManager
        plugin_mgr = PluginManager(plugins_dirs=[base_dir / "plugins"] if base_dir else [])
        plugin_mgr.discover_plugins()
        # 保存引用，供 API 层按需加载/激活插件（注入链路使用）
        agent._plugin_mgr = plugin_mgr
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
            # 技能发现来源：本地 skills/ + 市场 skills_market/
            scan_sources = ["skills", "skills_market"]
            total_discovered = 0
            for source_name in scan_sources:
                skills_dir = Path(base_dir) / source_name
                if not skills_dir.exists():
                    continue
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
                                        "market": (source_name == "skills_market"),
                                    },
                                ))
                            discovered += 1
                    except Exception as e:
                        logger.debug(f"技能发现跳过 {skill_subdir.name}: {e}")
                if discovered:
                    logger.info(f"从 {source_name}/ 目录发现 {discovered} 个技能")
                    total_discovered += discovered
        except Exception as e:
            logger.debug(f"技能扫描不可用: {e}")
    
    return agent
