# -*- coding: utf-8 -*-
"""AgentLoop T1(P0) 测试：loop 确定性 + 完成语义 + 状态机 + 串行 FIFO

用 FakeRunner 替代真实 HarnessRunner（确定性脚本驱动），
使 AgentLoop 核心逻辑（step）可同步、可断言地测试。
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.harness.loop import AgentLoop, LoopStatus, TaskStatus  # noqa: E402
from mcp.harness.turn import TurnResult, TurnStatus  # noqa: E402


class FakeRunner:
    """确定性 fake runner：按脚本依次返回预定义回合结果。

    每个脚本项 = (tool_calls, content)；调用顺序即回合顺序。
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = []  # 每次 run_turn 收到的 messages

    def run_turn(self, messages, tools=None, session_id=None):
        self.calls.append(list(messages))
        tool_calls, content = self.script.pop(0)
        return TurnResult(
            id=f"turn-{len(self.calls)}",
            status=TurnStatus.COMPLETED,
            content=content,
            tool_calls=list(tool_calls),
        )


def make_loop(runner, **kw):
    return AgentLoop(runner=runner, **kw)


# ── 1) 完成语义：一回合无 tool_calls → completed, turn_count=1 ──
def test_task_completes_when_no_tool_calls():
    runner = FakeRunner([([], "最终答案")])
    loop = make_loop(runner)
    task_id = loop.submit("计算 1+1", auto_start=False)
    assert loop.step() == task_id
    task = loop.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result == "最终答案"
    assert task.turn_count == 1
    assert len(runner.calls) == 1


# ── 2) 多回合：先 tool_calls 后无 tool_calls → completed, turn_count=2 ──
def test_task_runs_multiple_turns_until_done():
    runner = FakeRunner(
        [
            ([{"name": "calculate", "arguments": "1+1"}], ""),
            ([], "结果是 2"),
        ]
    )
    loop = make_loop(runner)
    task_id = loop.submit("算一下", auto_start=False)
    assert loop.step() == task_id
    task = loop.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.turn_count == 2
    # 第二轮 messages 应包含 assistant 与 tool 回合（历史被拼接）
    assert len(runner.calls[1]) >= 3


# ── 3) 串行 FIFO：先提交先完成 ──
def test_fifo_order():
    runner = FakeRunner([([], "A"), ([], "B")])
    loop = make_loop(runner)
    id_a = loop.submit("任务A", auto_start=False)
    id_b = loop.submit("任务B", auto_start=False)
    assert loop.step() == id_a
    assert loop.get_task(id_a).status == TaskStatus.COMPLETED
    assert loop.get_task(id_b).status == TaskStatus.PENDING
    assert loop.step() == id_b
    assert loop.get_task(id_b).status == TaskStatus.COMPLETED


# ── 4) 状态机：paused 不 drain，resume 恢复 ──
def test_pause_resume():
    runner = FakeRunner([([], "x")])
    loop = make_loop(runner)
    loop.pause()
    task_id = loop.submit("t", auto_start=False)
    assert loop.step() is None  # paused 时 step 不处理
    assert loop.get_task(task_id).status == TaskStatus.PENDING
    loop.resume()
    assert loop.step() == task_id
    assert loop.get_task(task_id).status == TaskStatus.COMPLETED


# ── 5) 停止：stop 后 step 不再处理 ──
def test_stop_halts_processing():
    runner = FakeRunner([([], "x")])
    loop = make_loop(runner)
    loop.start()
    try:
        loop.stop()
        task_id = loop.submit("t2", auto_start=False)
        assert loop.step() is None  # stopped 后不处理
        assert loop.get_task(task_id).status == TaskStatus.PENDING
    finally:
        loop.stop()


# ══════════════ T2(P1): 防失控 + 广播 + middleware 横切 ══════════════

class InfiniteToolRunner:
    """永不自然完成：每回合都返回 tool_calls，用于预算测试"""

    def run_turn(self, messages, tools=None, session_id=None):
        return TurnResult(
            id="t", status=TurnStatus.COMPLETED, content="",
            tool_calls=[{"name": "loop", "arguments": "{}"}],
        )


# ── 6) max_turns 预算：用尽 → HALTED ──
def test_max_turns_budget_halted():
    runner = InfiniteToolRunner()
    loop = make_loop(runner, max_turns=3)
    task_id = loop.submit("循环任务", max_turns=3, auto_start=False)
    assert loop.step() == task_id
    task = loop.get_task(task_id)
    assert task.status == TaskStatus.HALTED
    assert task.turn_count == 3
    assert "max_turns" in (task.error or "")


# ── 7) 时长预算：max_duration 超时 → HALTED ──
def test_max_duration_budget_halted():
    class SlowRunner:
        def run_turn(self, messages, tools=None, session_id=None):
            time.sleep(0.05)
            return TurnResult(
                id="t", status=TurnStatus.COMPLETED, content="",
                tool_calls=[{"name": "slow", "arguments": "{}"}],
            )

    loop = make_loop(SlowRunner(), max_turns=100, max_duration_seconds=0.08)
    task_id = loop.submit("慢任务", max_turns=100, auto_start=False)
    assert loop.step() == task_id
    task = loop.get_task(task_id)
    assert task.status == TaskStatus.HALTED
    assert "max_duration" in (task.error or "")


# ── 8) EventBus 广播：started / completed / halted ──
def test_event_broadcast_completed_and_halted():
    from mcp.automation.event_bus import EventBus

    bus = EventBus()
    events = []
    bus.subscribe("agent_loop.*", lambda e: events.append(e.event_type))

    loop = make_loop(FakeRunner([([], "ok")]), event_bus=bus)
    loop.submit("任务", auto_start=False)
    loop.step()
    assert "agent_loop.task_started" in events
    assert "agent_loop.task_completed" in events

    events.clear()
    loop2 = make_loop(InfiniteToolRunner(), max_turns=2, event_bus=bus)
    loop2.submit("任务2", max_turns=2)
    loop2.step()
    assert "agent_loop.task_halted" in events


# ── 9) MiddlewareChain 横切被调用 ──
def test_middleware_chain_invoked():
    from mcp.middleware.base import AgentMiddleware, MiddlewareResult
    from mcp.middleware.chain import MiddlewareChain

    class CountingMW(AgentMiddleware):
        name = "counting"
        order = 1

        def __init__(self):
            self.before = 0
            self.after = 0

        def before_agent(self, messages, context):
            self.before += 1
            return MiddlewareResult()

        def after_agent(self, messages, context):
            self.after += 1
            return MiddlewareResult()

    mw = CountingMW()
    chain = MiddlewareChain()
    chain.add(mw)
    loop = make_loop(FakeRunner([([], "x")]), middleware_chain=chain)
    loop.submit("m", auto_start=False)
    loop.step()
    assert mw.before >= 1
    assert mw.after >= 1


# ── 8) 提交即自主（修复：submit 自动启动后台线程，任务不再永久 pending）──
def test_submit_auto_starts_background_execution():
    import time
    runner = FakeRunner([([], "自动完成")])
    loop = make_loop(runner)
    task_id = loop.submit("自动任务", max_turns=2)  # 默认 auto_start=True
    time.sleep(1.0)  # 等后台线程 drain 队列
    task = loop.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result == "自动完成"
    assert len(runner.calls) == 1

# ── 9) 状态机守卫：PAUSED 时 auto_start 不启动执行（任务保持 pending）──
def test_submit_auto_start_respects_paused():
    runner = FakeRunner([([], "x")])
    loop = make_loop(runner)
    loop.start()   # 先 RUNNING
    loop.pause()   # 再 PAUSED（pause 仅在 RUNNING→PAUSED 生效）
    task_id = loop.submit("t", auto_start=True)  # PAUSED 下不启动执行
    assert loop.get_task(task_id).status == TaskStatus.PENDING


# ── 10) 会话化：任务执行后消息流被记录（user goal → assistant 回合 → tool）──
def test_task_records_message_flow():
    """loop 会话化（决策①A）：LoopTask.messages 记录完整消息流，snapshot 暴露"""
    runner = FakeRunner([
        ([{"name": "calc", "arguments": "1+1"}], ""),
        ([], "结果是 2"),
    ])
    loop = make_loop(runner)
    task_id = loop.submit("计算", max_turns=5, auto_start=False)
    loop.step()
    task = loop.get_task(task_id)
    msgs = task.messages
    # 第一回合：user goal + assistant(tool_calls) + tool 结果
    assert msgs[0]["role"] == "user" and "计算" in msgs[0]["content"]
    assert msgs[1]["role"] == "assistant" and msgs[1]["tool_calls"]
    assert msgs[2]["role"] == "tool"
    # 第二回合：assistant 无 tool_calls → 完成
    assert msgs[-1]["role"] == "assistant" and "结果是 2" in msgs[-1]["content"]
    # 每条消息带 ts
    assert all("ts" in m for m in msgs)
    # snapshot 暴露 messages
    snap = task.snapshot()
    assert "messages" in snap and len(snap["messages"]) == len(msgs)


# ── 11) 会话级模式切换：session_id 关联 + 每回合 turn 事件 ──
def test_submit_with_session_id():
    runner = FakeRunner([([], "完成")])
    loop = make_loop(runner)
    task_id = loop.submit("目标", session_id="sess-1", auto_start=False)
    task = loop.get_task(task_id)
    assert task.session_id == "sess-1"
    assert task.snapshot()["session_id"] == "sess-1"


def test_turn_event_emitted_per_round():
    from mcp.automation.event_bus import EventBus

    bus = EventBus()
    events = []
    bus.subscribe("agent_loop.*", lambda e: events.append(e.event_type))
    runner = FakeRunner([([], "完成")])
    loop = make_loop(runner, event_bus=bus)
    task_id = loop.submit("目标", session_id="sess-1", auto_start=False)
    loop.step()
    assert "agent_loop.turn" in events



# ── 12) 交接笔记（handoff）：终态生成结构化接力笔记（loop 交接 + macdev 回审双轨）──
def test_task_generates_handoff():
    runner = FakeRunner([
        ([{"name": "write_file", "arguments": '{"path": "x.py"}'}], ""),
        ([], "完成：已写入 x.py"),
    ])
    loop = make_loop(runner)
    task_id = loop.submit("写文件", auto_start=False)
    loop.step()
    task = loop.get_task(task_id)
    h = task.handoff
    assert h is not None
    assert h["goal"] == "写文件"
    assert h["status"] == "completed"
    assert h["turns"] == 2
    assert h["summary"] == "完成：已写入 x.py"
    # artifacts 从 write_file 调用提取 path 断言
    assert any("x.py" in a for a in h["artifacts"])
    # decisions 含工具名
    assert "write_file" in h["decisions"]
    # 无错误 → open_issues 为空
    assert h["open_issues"] == []
    # snapshot 暴露 handoff
    assert task.snapshot()["handoff"]["status"] == "completed"


# ── 13) 上下文共享改造（spec id=4）：同一上下文迭代器 ──
def test_loop_uses_session_context_when_available():
    """有 session_id 且注入会话回调 → 回合上下文 = 会话历史 + goal，结果回写会话"""

    class FakeSessionCtx:
        def __init__(self):
            self.history = [
                {"role": "user", "content": "之前聊过的内容"},
                {"role": "assistant", "content": "之前回复"},
            ]
            self.appended = []

        def get(self, sid):
            return list(self.history)

        def append(self, sid, msgs):
            self.appended.append((sid, list(msgs)))

    ctx = FakeSessionCtx()
    runner = FakeRunner([([], "完成")])
    loop = make_loop(runner, session_context=ctx)
    task_id = loop.submit("新目标", session_id="sess-1", auto_start=False)
    loop.step()
    # 回合上下文以会话历史开头（同一上下文），goal 追加在后
    first_call = runner.calls[0]
    assert first_call[0]["content"] == "之前聊过的内容"
    assert any(m.get("content") == "新目标" for m in first_call)
    # 结果回写会话（同一上下文迭代器：回合产物写回共享流）
    assert len(ctx.appended) >= 1
    assert ctx.appended[0][0] == "sess-1"
    # 无 session_id 时保持独立上下文（兼容旧用法）
    runner2 = FakeRunner([([], "ok")])
    loop2 = make_loop(runner2, session_context=ctx)
    tid2 = loop2.submit("独立任务", auto_start=False)
    loop2.step()
    assert runner2.calls[0][0]["content"] == "独立任务"

    # 无 session_id 时保持独立上下文（兼容旧用法）
    runner2 = FakeRunner([([], "ok")])
    loop2 = make_loop(runner2, session_context=ctx)
    tid2 = loop2.submit("独立任务", auto_start=False)
    loop2.step()
    assert runner2.calls[0][0]["content"] == "独立任务"


def test_session_mode_task_messages_are_loop_only():
    """session 模式下 task.messages 只记录 loop 自身回合（goal + 回合产出），
    不含普通对话历史——前端同流显示不被污染、去重指针不漂移（吞消息/闪烁根因，1:1 对齐单例）"""

    class FakeSessionCtx:
        def __init__(self):
            self.history = [
                {"role": "user", "content": "普通对话1"},
                {"role": "assistant", "content": "普通回复1"},
            ]
            self.appended = []

        def get(self, sid):
            return list(self.history)

        def append(self, sid, msgs):
            self.appended.append((sid, list(msgs)))

    ctx = FakeSessionCtx()
    runner = FakeRunner([([], "完成")])
    loop = make_loop(runner, session_context=ctx)
    task_id = loop.submit("新目标", session_id="sess-1", auto_start=False)
    loop.step()
    task = loop.get_task(task_id)
    msgs = task.messages
    # 起始是 goal（user），不含普通对话消息
    assert msgs[0]["role"] == "user" and msgs[0]["content"] == "新目标"
    assert not any(m["content"] == "普通对话1" for m in msgs)
    assert not any(m["content"] == "普通回复1" for m in msgs)
    # 回合产出（assistant）在流中
    assert any(m["role"] == "assistant" for m in msgs)
    # 回写仅含回合产出增量（不含普通对话/不含 goal 重复）
    assert ctx.appended
    assert all("普通对话1" not in str(x) and "普通回复1" not in str(x) for _, x in ctx.appended)
