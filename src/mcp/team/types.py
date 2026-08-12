"""团队编排模块的核心数据类型定义。

设计思路：
- 所有团队相关实体（成员配置、任务、运行记录、事件、消息、产物）都定义为轻量
  dataclass，便于通过 asdict 序列化，并在工具层与运行时层之间直接传递。
- ID 字段默认使用 uuid4 十六进制前 12 位，保证并发场景下全局唯一；时间字段默认
  取当前时间，减少调用方样板代码。
- 本模块是纯数据结构定义，不依赖任何执行器，方便各层复用、也便于单独测试。

与 Cline 的对应关系：Cline Teams 功能围绕 agent / task / run / outcome 等实体
建模，本模块即其中最小化的可移植数据类型版本。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TeamMemberConfig:
    """团队成员（Teammate）的配置描述。

    用于声明成员的身份、角色、系统提示词与执行约束，后续可转换为
    AgentTeam 的 AgentSpec（子代理规范）或运行时的成员字典。
    """

    # 成员唯一 ID，作为团队内寻址的标识
    agent_id: str = ""
    # 角色名，映射到子代理的 AgentRole（无法识别时回退为 CUSTOM）
    role: str = "teammate"
    # 系统提示词，决定该成员的行为基线
    system_prompt: str = ""
    # 成员类型：teammate / subagent
    kind: str = "teammate"
    # 单次任务允许的最大轮次上限
    max_turns: int = 20
    # 单次任务超时时间（秒），默认 30 分钟
    timeout_seconds: int = 1800
    # 允许使用的工具白名单；None 表示不限制
    allowed_tools: Optional[List[str]] = None
    # 禁止使用的工具黑名单
    denied_tools: Optional[List[str]] = None


@dataclass
class TeamRunRecord:
    """一次任务运行（run）的完整记录。

    生命周期：pending -> running -> completed / failed / cancelled，
    由 AgentTeamsRuntime 维护，工具层通过 run_id 查询或等待其结果。
    """

    # 运行唯一 ID，由运行时在提交时生成
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    # 执行该运行的成员 ID
    agent_id: str = ""
    # 交给该成员执行的任务消息
    message: str = ""
    # 当前状态：pending / running / completed / failed / cancelled
    status: str = "pending"
    # 成功后的结果文本
    result: Optional[str] = None
    # 失败时的错误信息
    error: Optional[str] = None
    # 创建时间戳
    created_at: float = field(default_factory=time.time)
    # 结束时间戳（完成/失败/取消时写入）
    completed_at: Optional[float] = None


@dataclass
class TeamTask:
    """共享的团队任务（task）描述。

    任务只描述"谁做什么、依赖哪些任务"，不直接执行；
    实际执行时由 submit_task 将其转为 TeamRunRecord 进入运行队列。
    """

    # 任务唯一 ID
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    # 负责该任务的成员 ID
    agent_id: str = ""
    # 任务内容
    message: str = ""
    # 依赖的任务 ID 列表，用于前置任务编排
    depends_on: List[str] = field(default_factory=list)


@dataclass
class TeamEvent:
    """团队运行时产生的轻量事件。

    通过 on_event 回调向外部（UI、日志系统等）广播状态变化，
    例如 TaskStart / TaskEnd / RunCompleted 等。
    """

    # 事件类型，如 TaskStart / TaskEnd / RunCompleted
    type: str = ""
    # 相关成员 ID
    agent_id: str = ""
    # 事件附加数据（消息、结果、错误等）
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Outcome:
    """团队协作产物（Outcome）。

    对应 Cline Teams 的产物沉淀机制：多成员以片段（fragment）分头贡献内容，
    经审查批准后整体定稿。生命周期：draft -> in_review -> finalized。
    """

    # 产物唯一 ID
    outcome_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    # 产物标题
    title: str = ""
    # 片段列表，每项包含内容/作者/审查状态等字段
    fragments: List[Dict[str, Any]] = field(default_factory=list)
    # 当前状态：draft / in_review / finalized
    status: str = "draft"
    # 负责该产物的成员 ID
    owner_agent_id: str = ""
    # 创建时间戳
    created_at: float = field(default_factory=time.time)
    # 最近更新时间戳（追加/审查/定稿时刷新）
    updated_at: float = field(default_factory=time.time)


@dataclass
class TeamMessage:
    """团队成员之间的邮箱消息。

    消息投递到收件人的邮箱队列（mailbox），读取后标记为已读；
    支持单播（send_message）与广播（broadcast）两种投递方式。
    """

    # 消息唯一 ID
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    # 收件人成员 ID
    to_agent_id: str = ""
    # 发件人成员 ID
    from_agent_id: str = ""
    # 消息正文
    content: str = ""
    # 发送时间戳
    created_at: float = field(default_factory=time.time)
    # 是否已被收件人读取
    read: bool = False
