"""团队编排（Team）子模块的公共入口。

设计思路：把"多代理协作"能力拆分为三个关注点，各自独立可测试：
- agent_team：面向会话内子代理的高级封装（AgentTeam），基于子代理
  Coordinator / SessionAgent 直接驱动真实 LLM 子代理协同完成任务；
- team_runtime：轻量级运行时（AgentTeamsRuntime），提供成员管理、任务队列、
  消息邮箱、使命日志与产物（Outcome）生命周期，执行器可注入，便于测试与复用；
- team_tools：把运行时能力包装为 team_* 系列工具，供 LLM 通过工具调用编排团队。

与 Cline 的对应关系：Cline 的 Teams 功能允许主代理动态创建/删除 Teammate、
并行派发任务、查看运行状态、成员间收发消息并沉淀协作产物；
本模块即该能力的移植实现，工具命名与 Cline 保持一致。

这里只导出稳定的公共 API，模块内部实现细节不对外暴露。
"""

from .agent_team import AgentTeam
from .team_runtime import AgentTeamsRuntime
from .team_tools import TEAM_TOOL_NAMES, create_team_tools, get_team_tools

__all__ = [
    "AgentTeam",
    "AgentTeamsRuntime",
    "TEAM_TOOL_NAMES",
    "create_team_tools",
    "get_team_tools",
]
