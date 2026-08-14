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

import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/loop", tags=["loop"])

_override_loop = None  # 测试注入点


class SubmitRequest(BaseModel):
    goal: str
    max_turns: Optional[int] = None
    auto_start: bool = True
    session_id: Optional[str] = None  # 会话级模式切换（决策A）：归属普通会话


class ControlRequest(BaseModel):
    action: str  # start / pause / resume / stop


class TaskMessageRequest(BaseModel):
    """审核介入：追加一条 user 消息（喂给 loop 下一回合）"""
    content: str


def _set_loop_for_test(loop):
    """测试专用：覆盖默认 loop 实例"""
    global _override_loop
    _override_loop = loop


# 会话上下文回调（spec id=4/5 装配）：{get(sid)->list, append(sid, msgs)}
# 由 app 层注入真实 agent 会话读写（同一上下文迭代器）；失败/未装配 → loop 退回独立上下文
_session_ctx = None


def _set_session_context(ctx):
    """注入会话上下文回调（app 启动时调用）。解耦：装配失败不影响普通对话。"""
    global _session_ctx
    _session_ctx = ctx


def _get_loop():
    """懒加载 AgentLoop 单例 + runner 注入（无 LLM 环境降级为 None runner）"""
    global _override_loop
    if _override_loop is not None:
        return _override_loop
    from ..harness.loop import get_agent_loop
    loop = get_agent_loop()
    # 装配会话上下文回调（同一上下文迭代器）：仅当未设置时注入，失败静默（解耦）
    if loop.session_context is None and _session_ctx:
        try:
            loop.session_context = _session_ctx
        except Exception:
            pass
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
                              auto_start=req.auto_start,
                              session_id=req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return {"task_id": task_id, "goal": req.goal}


@router.get("/tasks")
def loop_tasks_by_session(session: Optional[str] = None):
    """按会话查询 loop 任务（会话级模式切换：前端同流渲染时拉取归属会话的 loop 任务）"""
    loop = _get_loop()
    tasks = loop.list_tasks()
    if session is not None:
        tasks = [t for t in tasks if t.session_id == session]
    return {"tasks": [t.snapshot() for t in tasks]}


@router.get("/task/{task_id}")
def loop_task_detail(task_id: str):
    """任务详情（会话化）：meta + 完整消息流（前端像普通会话那样审核）"""
    loop = _get_loop()
    task = loop.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task.snapshot()


@router.post("/audit/{task_id}")
def loop_audit(task_id: str):
    """macdev 回审（交接第二轨，对抗性）：验证 handoff artifacts 断言。

    不采信模型自述——真实检查产出路径是否存在 + 源码文件可编译。
    解耦：独立端点，由前端/审核者主动触发，不阻塞 loop 主路径；
    失败仅反馈验证结果，不影响任务状态。
    """
    loop = _get_loop()
    task = loop.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    handoff = task.handoff or {}
    artifacts = list(handoff.get("artifacts") or [])
    verified, failed, skipped = [], [], []
    for a in artifacts:
        name, _, path = a.partition(": ")
        path = (path or "").strip()
        if not path:
            skipped.append(a)
            continue
        p = Path(path)
        if not p.is_absolute():
            # 相对路径：cwd 与项目根都试
            cwd_p = Path.cwd() / path
            root_p = Path(__file__).resolve().parent.parent.parent / path
            p = cwd_p if cwd_p.exists() else root_p
        if not p.exists():
            failed.append(f"{a}（文件不存在）")
            continue
        # 源码文件语法级验证（对抗性：能编译才算产出有效）
        ok = True
        if p.suffix == ".py":
            try:
                subprocess.run([__import__("sys").executable, "-m", "py_compile", str(p)],
                               capture_output=True, timeout=30, check=True)
            except Exception:
                ok = False
        elif p.suffix == ".js":
            try:
                subprocess.run(["node", "--check", str(p)],
                               capture_output=True, timeout=30, check=True)
            except Exception:
                ok = False
        if ok:
            verified.append(a)
        else:
            failed.append(f"{a}（语法检查未通过）")
    return {
        "task_id": task_id,
        "status": task.status.value,
        "handoff_status": handoff.get("status"),
        "verified": verified,
        "failed": failed,
        "skipped": skipped,
        "detail": "macdev 回审·对抗性验证：产出路径真实存在 + 源码可编译（不采信模型自述）",
    }


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
