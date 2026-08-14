# -*- coding: utf-8 -*-
"""AgentLoop HTTP API（FastAPI APIRouter）

端点：
  GET  /api/loop/state    → {loop_status, tasks: [snapshot...]}
  POST /api/loop/submit   → {goal, max_turns?} → {task_id}
  POST /api/loop/control  → {action: start|pause|resume|stop} → {loop_status}

设计：_get_loop() 懒加载单例 + runner 注入（无 runner 时用 model_selector 装配）；
测试可通过 _set_loop_for_test() 注入假 loop（模块级覆盖）。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/loop", tags=["loop"])

_override_loop = None  # 测试注入点


class SubmitRequest(BaseModel):
    goal: str
    max_turns: Optional[int] = None
    auto_start: bool = True


class ControlRequest(BaseModel):
    action: str  # start / pause / resume / stop


class TaskMessageRequest(BaseModel):
    """审核介入：追加一条 user 消息（喂给 loop 下一回合）"""
    content: str


def _set_loop_for_test(loop):
    """测试专用：覆盖默认 loop 实例"""
    global _override_loop
    _override_loop = loop


def _get_loop():
    """懒加载 AgentLoop 单例 + runner 注入（无 LLM 环境降级为 None runner）"""
    global _override_loop
    if _override_loop is not None:
        return _override_loop
    from ..harness.loop import get_agent_loop
    loop = get_agent_loop()
    if loop.runner is None:
        try:
            from ..harness.runner import HarnessRunner
            from ..model_selector import get_model_selector
            loop.set_runner(
                HarnessRunner(use_model_selector=True,
                              _model_selector=get_model_selector())
            )
        except Exception:
            pass
    return loop


@router.get("/state")
def loop_state():
    loop = _get_loop()
    return {
        "loop_status": loop.status.value,
        "tasks": [t.snapshot() for t in loop.list_tasks()],
    }


@router.post("/submit")
def loop_submit(req: SubmitRequest):
    loop = _get_loop()
    try:
        task_id = loop.submit(goal=req.goal, max_turns=req.max_turns,
                              auto_start=req.auto_start)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return {"task_id": task_id, "goal": req.goal}


@router.get("/task/{task_id}")
def loop_task_detail(task_id: str):
    """任务详情（会话化）：meta + 完整消息流（前端像普通会话那样审核）"""
    loop = _get_loop()
    task = loop.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task.snapshot()


@router.post("/task/{task_id}/message")
def loop_task_message(task_id: str, req: TaskMessageRequest):
    """审核介入（决策③C）：插入 user 消息，喂给 loop 下一回合"""
    loop = _get_loop()
    try:
        task = loop.intervene(task_id, req.content)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "task_id": task_id, "pending_input": task.pending_input}


@router.post("/control")
def loop_control(req: ControlRequest):
    loop = _get_loop()
    action = req.action
    if action == "start":
        loop.start()
    elif action == "pause":
        loop.pause()
    elif action == "resume":
        loop.resume()
    elif action == "stop":
        loop.stop()
    else:
        raise HTTPException(status_code=400, detail=f"未知动作: {action}")
    return {"loop_status": loop.status.value}
