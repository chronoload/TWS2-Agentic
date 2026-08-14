# -*- coding: utf-8 -*-
"""T4a: ws2_loop_* 后端工具测试（提交/列表/控制/注册）"""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.harness.loop import AgentLoop, TaskStatus  # noqa: E402
from mcp.harness.turn import TurnResult, TurnStatus  # noqa: E402
from mcp.ws2_tools import (  # noqa: E402
    SubmitLoopTaskTool, LoopTaskListTool, LoopControlTool,
)


class FakeRunner:
    def run_turn(self, messages, tools=None, session_id=None):
        return TurnResult(
            id="t", status=TurnStatus.COMPLETED, content="完成", tool_calls=[],
        )


def _parse(res):
    return json.loads(res) if isinstance(res, str) else res


def test_submit_returns_task_id_and_runs():
    loop = AgentLoop(runner=FakeRunner())
    tool = SubmitLoopTaskTool(loop_engine=loop)
    res = _parse(tool.execute(goal="跑个任务"))
    assert res["success"] is True
    assert res["data"]["task_id"]
    tid = res["data"]["task_id"]
    loop.step()
    task = loop.get_task(tid)
    assert task.status == TaskStatus.COMPLETED


def test_list_shows_tasks():
    loop = AgentLoop(runner=FakeRunner())
    tid = loop.submit("任务1")
    loop.step()
    tool = LoopTaskListTool(loop_engine=loop)
    res = _parse(tool.execute())
    assert res["success"] is True
    tasks = res["data"]["tasks"]
    assert len(tasks) >= 1
    assert tasks[0]["task_id"] == tid
    assert tasks[0]["status"] == "completed"


def test_control_pause_resume_stop():
    loop = AgentLoop(runner=FakeRunner())
    ctl = LoopControlTool(loop_engine=loop)
    loop.start()  # IDLE → RUNNING（pause 仅在 RUNNING 生效，状态机语义）
    res = _parse(ctl.execute(action="pause"))
    assert res["success"] is True
    assert loop.status.value == "paused"
    res = _parse(ctl.execute(action="resume"))
    assert loop.status.value == "running"
    res = _parse(ctl.execute(action="stop"))
    assert loop.status.value == "stopped"


def test_tools_registered():
    from mcp.ws2_tools import get_ws2_tools

    tools = get_ws2_tools()
    names = [t.name for t in tools]
    assert "ws2_loop_submit" in names
    assert "ws2_loop_list" in names
    assert "ws2_loop_control" in names
