"""Agent 运行状态机（agent_state）

本模块为 Agent 的 chat 主循环提供一套显式的「有限状态机」抽象，
把原先 _chat_impl 中内联的 while 循环重构为：状态枚举（AgentState）+
动作枚举（AgentAction）+ 迁移表（_TRANSITIONS）+ 状态机类
（AgentStateMachine），使 Agent 的运行阶段（准备 / LLM 调用 / 工具执行 /
上下文检查）可观察、可测试、可扩展。

状态枚举（AgentState）：
    描述 Agent 一次 chat 运行当前所处的阶段。其中 COMPLETED / ERROR /
    CANCELLED 为终态（terminal），到达终态后状态机不再继续迁移；
    其余为活动状态，可在状态机中继续流转。

动作枚举（AgentAction）：
    描述「调用方希望状态机做什么」的意图。动作本身不含业务逻辑，
    只是查询迁移表的键；具体每个动作从哪个状态迁移到哪个状态，
    完全由迁移表 _TRANSITIONS 决定。

迁移表（_TRANSITIONS）：
    以 (当前状态, 动作) 为键、目标状态为值的字典。只显式声明业务上
    合法的迁移；未声明的 (状态, 动作) 组合在 transition() 中一律视为
    非法迁移并抛出 RuntimeError。

合法性校验思想：
    1) 迁移表集中声明合法迁移，未声明即非法——从根源上避免散落在
       各处的 if/else 产生不可达或矛盾的状态流；
    2) 模块加载时对每个非终态补充两条「通用迁移」：CANCEL -> CANCELLED、
       FAIL -> ERROR，保证任何非终态都能通过取消/失败收敛到终态，
       使异常路径与正常路径一样受迁移表约束（setdefault 不覆盖显式声明）。
"""

from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple


class AgentState(Enum):
    """Agent 运行状态枚举

    每个成员对应 chat 主循环的一个阶段；COMPLETED / ERROR / CANCELLED
    为终态（见 is_terminal），其余为活动状态，可在状态机中继续迁移。
    """
    # 空闲：无对话运行，状态机的初始状态（_chat_impl 每次 reset 的落点）
    IDLE = "idle"
    # 准备：中间件预处理、对话开始前的上下文压缩检查、工具组激活
    PREPARE = "prepare"
    # LLM 调用：组装消息并调用模型，解析模型是否请求工具
    LLM_CALL = "llm_call"
    # 工具执行：执行模型请求的一个或多个工具，并把结果回填对话
    TOOL_EXEC = "tool_exec"
    # 上下文检查：工具执行后检查轮次上限与上下文占用，决定是否进入下一轮
    CONTEXT_CHECK = "context_check"
    # 完成（终态）：正常产出最终回答
    COMPLETED = "completed"
    # 错误（终态）：运行期间抛出异常，统一以 FAIL 动作迁移进入
    ERROR = "error"
    # 已取消（终态）：外部取消 / reset / 会话切换等主动中断
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """该状态是否为终态（状态机运行到终态后不再继续迁移）"""
        return self in (
            AgentState.COMPLETED,
            AgentState.ERROR,
            AgentState.CANCELLED,
        )


class AgentAction(Enum):
    """状态迁移动作枚举

    动作本身不含业务逻辑，只是迁移表 _TRANSITIONS 的查询键；
    由各阶段函数（_stage_*）在阶段结束后返回，驱动状态机进入下一状态。
    """
    # 开始一次 chat 运行（IDLE -> PREPARE）
    START = "start"
    # 准备阶段完成（PREPARE -> LLM_CALL）
    PREPARE_DONE = "prepare_done"
    # 模型请求了工具（LLM_CALL -> TOOL_EXEC）
    TOOL_CALLED = "tool_called"
    # 工具执行完成（TOOL_EXEC -> CONTEXT_CHECK）
    TOOL_DONE = "tool_done"
    # 进入下一轮（TOOL_EXEC / CONTEXT_CHECK -> LLM_CALL）
    NEXT_ROUND = "next_round"
    # 完成，收敛到终态（-> COMPLETED）
    COMPLETE = "complete"
    # 取消，收敛到终态（-> CANCELLED，对非终态通用）
    CANCEL = "cancel"
    # 失败，收敛到终态（-> ERROR，对非终态通用）
    FAIL = "fail"


# 迁移表：键为 (当前状态, 动作)，值为迁移后的目标状态。
# 只显式声明业务上合法的迁移；非法组合在 transition() 中直接抛错。
# 主流程为一条环形链路：
#   IDLE --START--> PREPARE --PREPARE_DONE--> LLM_CALL
#   LLM_CALL --TOOL_CALLED--> TOOL_EXEC --TOOL_DONE--> CONTEXT_CHECK
#   CONTEXT_CHECK --NEXT_ROUND--> LLM_CALL（新一轮循环）
# 任一阶段均可通过 COMPLETE 提前收敛到 COMPLETED。
_TRANSITIONS: Dict[Tuple[AgentState, AgentAction], AgentState] = {
    (AgentState.IDLE, AgentAction.START): AgentState.PREPARE,
    (AgentState.PREPARE, AgentAction.PREPARE_DONE): AgentState.LLM_CALL,
    (AgentState.LLM_CALL, AgentAction.TOOL_CALLED): AgentState.TOOL_EXEC,
    (AgentState.LLM_CALL, AgentAction.COMPLETE): AgentState.COMPLETED,
    (AgentState.TOOL_EXEC, AgentAction.TOOL_DONE): AgentState.CONTEXT_CHECK,
    (AgentState.TOOL_EXEC, AgentAction.NEXT_ROUND): AgentState.LLM_CALL,
    (AgentState.TOOL_EXEC, AgentAction.COMPLETE): AgentState.COMPLETED,
    (AgentState.CONTEXT_CHECK, AgentAction.NEXT_ROUND): AgentState.LLM_CALL,
    (AgentState.CONTEXT_CHECK, AgentAction.COMPLETE): AgentState.COMPLETED,
    (AgentState.PREPARE, AgentAction.COMPLETE): AgentState.COMPLETED,
}

# 合法性校验 / 通用迁移补充：
# 对每个非终态补充 CANCEL -> CANCELLED、FAIL -> ERROR 两条迁移
# （setdefault 不覆盖已在上面显式声明的条目），
# 保证任何非终态都能通过取消/失败收敛到终态。
for _state in AgentState:
    if _state.is_terminal:
        continue
    _TRANSITIONS.setdefault((_state, AgentAction.CANCEL), AgentState.CANCELLED)
    _TRANSITIONS.setdefault((_state, AgentAction.FAIL), AgentState.ERROR)


class AgentStateMachine:
    """Agent 有限状态机

    持有当前状态，对外提供 transition()（按动作迁移）、reset()（复位）、
    add_listener()（注册状态变更监听）。状态发生变更时通过 _notify()
    依次调用所有监听器；单个监听器抛出的异常会被吞掉，不干扰状态机本身。
    """

    def __init__(self, initial_state: AgentState = AgentState.IDLE):
        """初始化状态机

        Args:
            initial_state: 初始状态，默认 IDLE（空闲）。
        """
        self.on_state_change: List[
            Callable[[AgentState, AgentState, Optional[AgentAction]], None]
        ] = []
        self._state = initial_state

    @property
    def state(self) -> AgentState:
        """返回当前状态"""
        return self._state

    def reset(self, state: AgentState = AgentState.IDLE) -> None:
        """无条件复位状态机到指定状态

        Args:
            state: 复位到的目标状态，默认 IDLE。
        """
        old_state = self._state
        self._state = state
        if old_state != state:
            self._notify(old_state, state, None)

    def transition(self, action: AgentAction) -> AgentState:
        """按动作执行一次状态迁移

        在迁移表 _TRANSITIONS 中查找 (当前状态, 动作)；若未声明则视为
        非法迁移，抛出 RuntimeError。

        Args:
            action: 要执行的迁移动作（可为 AgentAction 或其值字符串）。

        Returns:
            迁移后的新状态。

        Raises:
            RuntimeError: 迁移表未声明该 (状态, 动作) 组合。
        """
        if not isinstance(action, AgentAction):
            action = AgentAction(action)
        next_state = _TRANSITIONS.get((self._state, action))
        if next_state is None:
            raise RuntimeError(
                f"非法状态迁移: {self._state.name} --{action.name}--> ?"
            )
        old_state = self._state
        self._state = next_state
        self._notify(old_state, next_state, action)
        return next_state

    def add_listener(
        self,
        callback: Callable[[AgentState, AgentState, Optional[AgentAction]], None],
    ) -> Callable:
        """注册状态变更监听器

        回调签名: callback(old_state, new_state, action)。
        action 为 None 表示由 reset() 触发的直接复位，而非正常迁移。

        Returns:
            传入的 callback 本身，便于调用方保存/注销。
        """
        self.on_state_change.append(callback)
        return callback

    def _notify(
        self,
        old_state: AgentState,
        new_state: AgentState,
        action: Optional[AgentAction],
    ) -> None:
        """向所有监听器广播一次状态变更

        单个监听器抛出的异常会被捕获并忽略，避免回调异常阻断状态机运行。
        """
        for cb in self.on_state_change:
            try:
                cb(old_state, new_state, action)
            except Exception:
                pass
