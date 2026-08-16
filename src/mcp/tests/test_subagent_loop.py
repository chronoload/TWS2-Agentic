"""子代理去轮次限制 + loop 防异常打断（TDD）"""
import sys
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.subagent.session import SessionAgent
from mcp.subagent.types import AgentRole, AgentSpec, SubAgentStatus


def _resp(content="", tool_calls=None):
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls or [],
        reasoning_content="",
        prompt_tokens=1,
        completion_tokens=1,
    )


def _tc(name="echo", args=None):
    return SimpleNamespace(id="c1", name=name, arguments=args or {})


class _FlakyLLM:
    """前 fail_before 次抛异常，之后正常返回"""

    def __init__(self, fail_before=0):
        self.fail_before = fail_before
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls <= self.fail_before:
            raise RuntimeError("boom-llm")
        return _resp(content="done")


class _ToolLoopLLM:
    """前 tool_rounds 轮返回 tool_calls，之后返回纯文本"""

    def __init__(self, tool_rounds=2):
        self.tool_rounds = tool_rounds
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls <= self.tool_rounds:
            return _resp(content="", tool_calls=[_tc()])
        return _resp(content="done")


class _AlwaysFailLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        raise RuntimeError("always-boom")


def _make_agent(llm, max_turns=0, max_retries=3, timeout=30):
    spec = AgentSpec(
        role=AgentRole.CODER, name="t", system_prompt="sys",
        max_turns=max_turns, max_retries=max_retries, timeout_seconds=timeout,
    )
    return SessionAgent(spec=spec, llm=llm)


# ---------- ① 无限轮次：不因轮次上限退出 ----------

def test_unlimited_turns_run_to_completion():
    """max_turns=0（无限）：连续工具轮次后正常完成，不因轮次截断"""
    llm = _ToolLoopLLM(tool_rounds=3)
    agent = _make_agent(llm, max_turns=0)
    result = agent.run("do it")
    assert result.status == SubAgentStatus.COMPLETED, f"应完成: {result.status} {result.error}"
    assert llm.calls >= 4, f"应跑完 3 轮工具+1 完成（至少 4 次 LLM），实际 {llm.calls}"


# ---------- ② loop 防异常打断：瞬时 LLM 异常恢复 ----------

def test_recovery_from_transient_llm_error():
    """前 2 次 LLM 异常 → 第 3 次成功 → completed（不失败不早退）"""
    llm = _FlakyLLM(fail_before=2)
    agent = _make_agent(llm, max_turns=0, max_retries=3)
    result = agent.run("do it")
    assert result.status == SubAgentStatus.COMPLETED, f"瞬时异常应恢复: {result.status} {result.error}"
    assert llm.calls == 3, f"应调用 3 次（2 次失败+1 成功），实际 {llm.calls}"


def test_exhausts_after_max_retries():
    """连续异常超过 max_retries → failed（防死循环）"""
    llm = _AlwaysFailLLM()
    agent = _make_agent(llm, max_turns=0, max_retries=2)
    result = agent.run("do it")
    assert result.status == SubAgentStatus.FAILED, f"连续异常应失败: {result.status}"
    assert llm.calls >= 3, f"应至少重试 3 次（1+2），实际 {llm.calls}"


# ---------- ③ 回归：有限轮次仍按轮次限制 ----------

def test_legacy_max_turns_still_limits():
    """max_turns=3：有限轮次仍按上限退出（向后兼容）"""
    llm = _ToolLoopLLM(tool_rounds=999)
    agent = _make_agent(llm, max_turns=3, max_retries=3)
    result = agent.run("do it")
    assert result.status == SubAgentStatus.COMPLETED
    assert llm.calls <= 4, f"有限轮次应截断（≤4 次），实际 {llm.calls}"


# ---------- ④ 轮次解耦：参数可设置，默认无限（配置轨/工具轨双轨） ----------

def test_subagent_config_default_infinite():
    """配置轨：SubagentConfig 默认 max_turns=0（无限，由 timeout 兜底）"""
    from mcp.subagent.types import SubagentConfig
    cfg = SubagentConfig(name="coder")
    assert cfg.max_turns == 0, f"配置轨默认应无限(0)，实际 {cfg.max_turns}"


def test_default_coordinator_preset_roles_infinite():
    """配置轨：预置角色 coder/task/research/review 默认无限（max_turns=0）"""
    from mcp.subagent.coordinator import create_default_coordinator
    coord = create_default_coordinator()
    for name in ("coder", "task", "research", "review"):
        spec = coord._specs.get(name)
        assert spec is not None, f"预置角色 {name} 应存在"
        assert spec.max_turns == 0, f"预置角色 {name} 应默认无限(0)，实际 {spec.max_turns}"


def test_tool_override_max_turns_limits():
    """工具轨：per-call max_turns 覆盖角色默认（传 3 → 3 轮截断，注册 spec 不变）"""
    from mcp.subagent.coordinator import create_default_coordinator
    coord = create_default_coordinator()
    llm = _ToolLoopLLM(tool_rounds=120)
    coord._agent_llms["coder"] = llm
    result = coord.run("coder", "do it", max_turns=3)
    assert result.status == SubAgentStatus.COMPLETED
    assert llm.calls <= 4, f"per-call max_turns=3 应截断（≤4 次），实际 {llm.calls}"
    assert coord._specs["coder"].max_turns == 0, "注册 spec 不应被覆盖（仍默认无限）"


def test_config_subagent_default_infinite():
    """配置轨：config.SubAgentConfig（配置文件默认源）max_turns 默认 0（无限）"""
    from mcp.config import SubAgentConfig as CfgSubAgentConfig
    cfg = CfgSubAgentConfig(role="coder", name="coder")
    assert cfg.max_turns == 0, f"配置轨默认应无限(0)，实际 {cfg.max_turns}"


# ---------- ⑤ 循环终止性：完成后/超时都能停止（不无限跑） ----------

def test_stops_exactly_after_completion():
    """无限轮次：3 轮工具 + 纯文本完成 → 恰好 4 次 LLM 调用后精确停止（不继续死循环）"""
    llm = _ToolLoopLLM(tool_rounds=3)
    agent = _make_agent(llm, max_turns=0)
    result = agent.run("do it")
    assert result.status == SubAgentStatus.COMPLETED
    assert llm.calls == 4, f"完成后应精确停止（3 工具轮+1 完成轮=4 次），实际 {llm.calls}"


def test_timeout_stops_infinite_tool_loop():
    """无限轮次 + 永不完成（永远返回工具调用）→ timeout 兜底停止（failed 超时，调用有界）"""
    llm = _ToolLoopLLM(tool_rounds=999999)
    agent = _make_agent(llm, max_turns=0, timeout=0.3)
    result = agent.run("do it")
    assert result.status == SubAgentStatus.FAILED, f"超时应失败: {result.status} {result.error}"
    assert "超时" in result.error, f"错误信息应含超时: {result.error}"
    # 终止性证明：若超时不生效，本测试将永远运行（tool_rounds=999999 永不完成）→ pytest 挂起。
    # 因此 status=FAILED(超时) 即证明循环已停止；上界仅为防极端（0.3s 纯模拟约 1.3 万次，留 75 倍余量）
    assert 0 < llm.calls < 10 ** 6, f"超时应限制调用次数（有界不无限跑），实际 {llm.calls}"
