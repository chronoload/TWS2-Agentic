"""团队工具的 MCP 工具层封装（team_* 系列，共 18 个）。

设计思路：
- 把 AgentTeamsRuntime 的全部能力（成员管理、任务队列、邮箱、日志、产物）逐一
  包装成标准 Tool 子类，LLM 通过工具调用即可编排团队，无需直接触碰运行时对象。
- 每个工具构造时绑定一个具体 runtime；为了支持"不传 runtime"的便捷用法，
  模块维护一个模块级单例 _default_runtime，首次调用时惰性创建。

与 Cline 的对应关系：工具名与 Cline Teams 的 team_* 工具一一对应
（见测试中的 CLINE_TEAM_TOOL_NAMES），便于迁移与兼容。
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from ..tools import Tool
from .team_runtime import AgentTeamsRuntime

# 全部 18 个团队工具的名字清单，用于注册与校验
TEAM_TOOL_NAMES = [
    "team_spawn_teammate",
    "team_shutdown_teammate",
    "team_status",
    "team_task",
    "team_run_task",
    "team_cancel_run",
    "team_list_runs",
    "team_await_runs",
    "team_send_message",
    "team_broadcast",
    "team_read_mailbox",
    "team_mission_log",
    "team_cleanup",
    "team_create_outcome",
    "team_attach_outcome_fragment",
    "team_review_outcome_fragment",
    "team_finalize_outcome",
    "team_list_outcomes",
]

# 模块级单例 runtime：调用 get_team_tools() 不带参数时惰性创建并复用
_default_runtime: Optional[AgentTeamsRuntime] = None


def set_runtime(runtime: AgentTeamsRuntime):
    """设置模块级单例 runtime，供后续无参调用 get_team_tools() 复用。"""
    global _default_runtime
    _default_runtime = runtime


def _serialize(value: Any) -> Any:
    """把 dataclass 转为普通字典，其他值原样返回（供 JSON 序列化）。"""
    if is_dataclass(value):
        return asdict(value)
    return value


def _split_ids(raw: Any) -> List[str]:
    """把工具入参解析为 ID 字符串列表。

    兼容两种输入：已切分的 list，或逗号分隔的字符串；
    过滤空项，避免空字符串进入依赖/运行 ID 列表。
    """
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [x.strip() for x in str(raw or "").split(",") if x.strip()]


class TeamSpawnTeammateTool(Tool):
    """注册一个新的团队成员（对应 Cline 的 team_spawn_teammate）。"""

    name = "team_spawn_teammate"
    description = "注册一个新的团队成员（Teammate）。参数: agent_id(必填), role, system_prompt, kind。"
    risk_level = "medium"
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "成员唯一 ID"},
            "role": {"type": "string", "description": "成员角色描述", "default": "teammate"},
            "system_prompt": {"type": "string", "description": "系统提示词", "default": ""},
            "kind": {"type": "string", "description": "成员类型: teammate/subagent", "default": "teammate"},
        },
        "required": ["agent_id"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, agent_id: str, role: str = "teammate", system_prompt: str = "", kind: str = "teammate", **kwargs) -> str:
        """执行注册动作并返回 JSON 结果（agent_id + spawned 状态）。"""
        self._runtime.add_member(agent_id, role=role, kind=kind, system_prompt=system_prompt)
        return json.dumps({"agent_id": agent_id, "status": "spawned"}, ensure_ascii=False)


class TeamShutdownTeammateTool(Tool):
    """移除一个团队成员（对应 Cline 的 team_shutdown_teammate）。"""

    name = "team_shutdown_teammate"
    description = "移除一个团队成员（Teammate）。参数: agent_id。"
    risk_level = "high"
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "要移除的成员 ID"},
        },
        "required": ["agent_id"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, agent_id: str, **kwargs) -> str:
        """执行移除动作并返回 JSON 结果（agent_id + stopped 状态）。"""
        self._runtime.remove_member(agent_id)
        return json.dumps({"agent_id": agent_id, "status": "stopped"}, ensure_ascii=False)


class TeamStatusTool(Tool):
    """查看团队整体状态快照（成员/任务/邮箱/日志/产物统计）。"""

    name = "team_status"
    description = "查看团队状态：成员列表、运行中/排队任务、未读邮箱消息数、mission log 条数与产物统计。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, **kwargs) -> str:
        """返回 get_snapshot() 的 JSON 序列化结果。"""
        return json.dumps(self._runtime.get_snapshot(), ensure_ascii=False)


class TeamTaskTool(Tool):
    """创建共享团队任务（TeamTask），仅登记任务不执行。"""

    name = "team_task"
    description = "创建共享的团队任务（TeamTask）。参数: agent_id, message, depends_on(逗号分隔的任务ID列表)。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "负责该任务的成员 ID"},
            "message": {"type": "string", "description": "任务内容"},
            "depends_on": {"type": "string", "description": "依赖的其他任务ID，逗号分隔", "default": ""},
        },
        "required": ["agent_id", "message"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, agent_id: str, message: str, depends_on: Any = "", **kwargs) -> str:
        """创建任务；depends_on 经 _split_ids 解析后传入，返回 task_id。"""
        task = self._runtime.create_task(agent_id, message, depends_on=_split_ids(depends_on))
        return json.dumps(
            {"task_id": task.task_id, "agent_id": task.agent_id, "status": "created"},
            ensure_ascii=False,
        )


class TeamRunTaskTool(Tool):
    """提交任务到运行队列执行（返回 run_id）。"""

    name = "team_run_task"
    description = "提交一个任务到团队队列执行，返回 run_id。参数: agent_id, message, depends_on(逗号分隔的 run_id 列表)。"
    risk_level = "medium"
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "执行该任务的成员 ID"},
            "message": {"type": "string", "description": "任务内容"},
            "depends_on": {"type": "string", "description": "依赖的其他 run_id，逗号分隔", "default": ""},
        },
        "required": ["agent_id", "message"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, agent_id: str, message: str, depends_on: Any = "", **kwargs) -> str:
        """提交运行并返回 JSON（run_id + queued 状态）。"""
        run_id = self._runtime.submit_task(agent_id, message, depends_on=_split_ids(depends_on))
        return json.dumps({"run_id": run_id, "agent_id": agent_id, "status": "queued"}, ensure_ascii=False)


class TeamCancelRunTool(Tool):
    """取消一个排队或运行中的 run。"""

    name = "team_cancel_run"
    description = "取消一个排队的团队任务运行。参数: run_id。"
    risk_level = "medium"
    parameters = {
        "type": "object",
        "properties": {
            "run_id": {"type": "string", "description": "要取消的 run_id"},
        },
        "required": ["run_id"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, run_id: str, **kwargs) -> str:
        """取消 run 并返回其最新状态。"""
        run = self._runtime.cancel_run(run_id)
        return json.dumps({"run_id": run.run_id, "status": run.status}, ensure_ascii=False)


class TeamListRunsTool(Tool):
    """列出团队运行记录，可按成员过滤。"""

    name = "team_list_runs"
    description = "列出团队任务运行记录。参数: agent_id(可选，按成员过滤)。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "按成员 ID 过滤", "default": ""},
        },
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, agent_id: str = "", **kwargs) -> str:
        """列出 run 记录，dataclass 先 _serialize 转字典再 JSON 序列化。"""
        runs = self._runtime.list_runs(agent_id)
        return json.dumps({"runs": [_serialize(r) for r in runs]}, ensure_ascii=False)


class TeamAwaitRunsTool(Tool):
    """阻塞等待指定 run 完成；不传 run_ids 时等待全部。"""

    name = "team_await_runs"
    description = "阻塞等待指定的 run 完成（run_ids 逗号分隔）。不带参数时等待所有 run 完成。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "run_ids": {"type": "string", "description": "要等待的 run_id 列表，逗号分隔", "default": ""},
        },
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, run_ids: Any = "", **kwargs) -> str:
        """等待 run 结束并返回全部相关记录（含结果/状态）。"""
        ids = _split_ids(run_ids)
        if ids:
            runs = self._runtime.await_runs(ids)
        else:
            runs = self._runtime.await_all_runs()
        return json.dumps({"runs": [_serialize(r) for r in runs]}, ensure_ascii=False)


class TeamSendMessageTool(Tool):
    """给指定成员发送邮箱消息（单播）。"""

    name = "team_send_message"
    description = "给某个团队成员发送邮箱消息。参数: to(收件人), from(发件人), content。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "收件人 agent_id"},
            "from": {"type": "string", "description": "发件人 agent_id"},
            "content": {"type": "string", "description": "消息内容"},
        },
        "required": ["to", "from", "content"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, to: str = "", content: str = "", **kwargs) -> str:
        """发送消息；"from" 是 Python 关键字，须从 kwargs 中取出。"""
        from_agent_id = kwargs.pop("from", "")
        message = self._runtime.send_message(to, from_agent_id, content)
        return json.dumps({"id": message.message_id, "to_agent_id": message.to_agent_id}, ensure_ascii=False)


class TeamBroadcastTool(Tool):
    """向除发件人外的所有成员广播消息。"""

    name = "team_broadcast"
    description = "给除自己外的所有团队成员广播消息。参数: from(发件人), content。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "from": {"type": "string", "description": "发件人 agent_id"},
            "content": {"type": "string", "description": "广播内容"},
        },
        "required": ["from", "content"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, content: str = "", **kwargs) -> str:
        """广播消息并返回投递数量（不含发件人自己）。"""
        from_agent_id = kwargs.pop("from", "")
        messages = self._runtime.broadcast(from_agent_id, content)
        return json.dumps({"delivered": len(messages)}, ensure_ascii=False)


class TeamReadMailboxTool(Tool):
    """读取成员邮箱消息（读取后标记为已读）。"""

    name = "team_read_mailbox"
    description = "读取指定成员的邮箱消息（读取后标记为已读）。参数: agent_id。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "要读取邮箱的成员 ID"},
        },
        "required": ["agent_id"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, agent_id: str, **kwargs) -> str:
        """读取邮箱并返回消息列表 JSON。"""
        messages = self._runtime.read_mailbox(agent_id)
        return json.dumps({"messages": [_serialize(m) for m in messages]}, ensure_ascii=False)


class TeamMissionLogTool(Tool):
    """维护使命日志：append 追加一条，read 返回全部。"""

    name = "team_mission_log"
    description = "维护团队使命日志。action=append 时追加一条（需 content），action=read 时返回全部日志。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "append 或 read", "default": "append"},
            "content": {"type": "string", "description": "追加的日志内容（action=append 时需要）", "default": ""},
            "agent_id": {"type": "string", "description": "写入日志的成员 ID", "default": ""},
        },
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, action: str = "append", content: str = "", agent_id: str = "", **kwargs) -> str:
        """按 action 分派：read 返回全部日志，否则追加一条。"""
        if action == "read":
            return json.dumps({"entries": self._runtime.read_mission_log()}, ensure_ascii=False)
        entry = self._runtime.append_mission_log(content, agent_id=agent_id)
        return json.dumps({"id": entry["id"], "status": "appended"}, ensure_ascii=False)


class TeamCleanupTool(Tool):
    """清理已结束的 run 记录，可加时间门槛。"""

    name = "team_cleanup"
    description = "清理团队运行记录（仅清理已完成/失败/取消的 run）。参数: older_than_seconds(可选)。"
    risk_level = "medium"
    parameters = {
        "type": "object",
        "properties": {
            "older_than_seconds": {"type": "integer", "description": "仅清理早于该时间(秒)的完成记录", "default": None},
        },
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, older_than_seconds: Any = None, **kwargs) -> str:
        """清理记录并返回移除数量。"""
        seconds = int(older_than_seconds) if older_than_seconds else None
        removed = self._runtime.cleanup(older_than_seconds=seconds)
        return json.dumps({"status": "cleaned", "removed_runs": removed}, ensure_ascii=False)


class TeamCreateOutcomeTool(Tool):
    """创建一份协作产物（Outcome）。"""

    name = "team_create_outcome"
    description = "创建一份团队协作产物（Outcome）。参数: title, owner_agent_id。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "产物标题"},
            "owner_agent_id": {"type": "string", "description": "负责该产物的成员 ID"},
        },
        "required": ["title", "owner_agent_id"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, title: str, owner_agent_id: str = "", **kwargs) -> str:
        """创建产物并返回其 ID 与初始状态。"""
        outcome = self._runtime.create_outcome(title, owner_agent_id=owner_agent_id)
        return json.dumps({"outcome_id": outcome.outcome_id, "status": outcome.status}, ensure_ascii=False)


class TeamAttachOutcomeFragmentTool(Tool):
    """向产物追加一个片段。"""

    name = "team_attach_outcome_fragment"
    description = "向产物追加一个片段。参数: outcome_id, content, author_agent_id。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "outcome_id": {"type": "string", "description": "产物 ID"},
            "content": {"type": "string", "description": "片段内容"},
            "author_agent_id": {"type": "string", "description": "作者成员 ID", "default": ""},
        },
        "required": ["outcome_id", "content"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, outcome_id: str, content: str, author_agent_id: str = "", **kwargs) -> str:
        """追加片段并返回 fragment_id。"""
        fragment = self._runtime.attach_outcome_fragment(outcome_id, content, author_agent_id=author_agent_id)
        return json.dumps({"fragment_id": fragment["fragment_id"], "status": "attached"}, ensure_ascii=False)


class TeamReviewOutcomeFragmentTool(Tool):
    """审查产物片段（approve/reject）。"""

    name = "team_review_outcome_fragment"
    description = "审查产物片段。参数: outcome_id, fragment_id, status(approve|reject), comment(可选)。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "outcome_id": {"type": "string", "description": "产物 ID"},
            "fragment_id": {"type": "string", "description": "片段 ID"},
            "status": {"type": "string", "description": "approve 或 reject"},
            "comment": {"type": "string", "description": "审查意见", "default": ""},
        },
        "required": ["outcome_id", "fragment_id", "status"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, outcome_id: str, fragment_id: str, status: str, comment: str = "", **kwargs) -> str:
        """审查片段并返回其最新审查状态。"""
        fragment = self._runtime.review_outcome_fragment(outcome_id, fragment_id, status, comment=comment)
        return json.dumps({"fragment_id": fragment["fragment_id"], "status": fragment["review_status"]}, ensure_ascii=False)


class TeamFinalizeOutcomeTool(Tool):
    """定稿产物（要求至少一个已批准片段）。"""

    name = "team_finalize_outcome"
    description = "定稿一份产物（要求至少有一个已批准的片段）。参数: outcome_id。"
    risk_level = "medium"
    parameters = {
        "type": "object",
        "properties": {
            "outcome_id": {"type": "string", "description": "产物 ID"},
        },
        "required": ["outcome_id"],
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, outcome_id: str, **kwargs) -> str:
        """定稿产物并返回最终状态。"""
        outcome = self._runtime.finalize_outcome(outcome_id)
        return json.dumps({"outcome_id": outcome.outcome_id, "status": outcome.status}, ensure_ascii=False)


class TeamListOutcomesTool(Tool):
    """列出团队产物，可按状态过滤。"""

    name = "team_list_outcomes"
    description = "列出团队产物。参数: status(可选: draft/in_review/finalized)。"
    risk_level = "low"
    parameters = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "按状态过滤", "default": ""},
        },
    }

    def __init__(self, runtime: AgentTeamsRuntime):
        self._runtime = runtime

    def execute(self, status: str = "", **kwargs) -> str:
        """列出产物并返回 JSON。"""
        outcomes = self._runtime.list_outcomes(status)
        return json.dumps({"outcomes": [_serialize(o) for o in outcomes]}, ensure_ascii=False)


# 全部工具类注册表：get_team_tools 据此批量实例化
_TEAM_TOOL_CLASSES = [
    TeamSpawnTeammateTool,
    TeamShutdownTeammateTool,
    TeamStatusTool,
    TeamTaskTool,
    TeamRunTaskTool,
    TeamCancelRunTool,
    TeamListRunsTool,
    TeamAwaitRunsTool,
    TeamSendMessageTool,
    TeamBroadcastTool,
    TeamReadMailboxTool,
    TeamMissionLogTool,
    TeamCleanupTool,
    TeamCreateOutcomeTool,
    TeamAttachOutcomeFragmentTool,
    TeamReviewOutcomeFragmentTool,
    TeamFinalizeOutcomeTool,
    TeamListOutcomesTool,
]


def get_team_tools(runtime: Optional[AgentTeamsRuntime] = None) -> List[Tool]:
    """返回绑定了指定（或单例）runtime 的 18 个团队工具实例列表。

    Args:
        runtime: 要绑定的运行时；为 None 时使用（或惰性创建）模块级单例。

    Returns:
        List[Tool]: 全部 team_* 工具的实例列表。
    """
    global _default_runtime
    if runtime is None:
        if _default_runtime is None:
            _default_runtime = AgentTeamsRuntime()
        runtime = _default_runtime
    set_runtime(runtime)
    return [tool_cls(runtime) for tool_cls in _TEAM_TOOL_CLASSES]


def create_team_tools(runtime: Optional[AgentTeamsRuntime] = None) -> List[Tool]:
    """创建团队工具的别名入口，行为与 get_team_tools 完全一致。"""
    return get_team_tools(runtime)
