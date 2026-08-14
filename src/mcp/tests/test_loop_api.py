# -*- coding: utf-8 -*-
"""T4b: /api/loop/* 端点核心逻辑测试（直接调端点函数，规避 TestClient 版本兼容）

注：环境 starlette TestClient 与 httpx 不兼容（Client.__init__ app 参数），
端点函数是同步核心逻辑，直接调用等价覆盖（HTTP 层由 FastAPI 框架保证）。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.harness.loop import AgentLoop  # noqa: E402
from mcp.harness.turn import TurnResult, TurnStatus  # noqa: E402
from mcp.server.loop_api import (  # noqa: E402
    ControlRequest, SubmitRequest, _set_loop_for_test,
    loop_control, loop_state, loop_submit,
)


class FakeRunner:
    def run_turn(self, messages, tools=None, session_id=None):
        return TurnResult(
            id="t", status=TurnStatus.COMPLETED, content="完成", tool_calls=[],
        )


def test_state_empty():
    _set_loop_for_test(AgentLoop(runner=FakeRunner()))
    body = loop_state()
    assert "loop_status" in body
    assert body["tasks"] == []


def test_submit_then_state_shows_task():
    loop = AgentLoop(runner=FakeRunner())
    _set_loop_for_test(loop)
    body = loop_submit(SubmitRequest(goal="算个题"))
    tid = body["task_id"]
    assert tid
    loop.step()
    tasks = loop_state()["tasks"]
    assert tasks[0]["task_id"] == tid
    assert tasks[0]["status"] == "completed"


def test_control_pause():
    loop = AgentLoop(runner=FakeRunner())
    _set_loop_for_test(loop)
    loop.start()
    assert loop_control(ControlRequest(action="pause"))["loop_status"] == "paused"
    assert loop_control(ControlRequest(action="resume"))["loop_status"] == "running"
    assert loop_control(ControlRequest(action="stop"))["loop_status"] == "stopped"


def test_control_unknown_action():
    _set_loop_for_test(AgentLoop(runner=FakeRunner()))
    with pytest.raises(Exception):
        loop_control(ControlRequest(action="fly"))
