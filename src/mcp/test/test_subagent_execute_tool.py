#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TS2 Agent._execute_tool sub_agent 分支流式 token 转发集成测试

验证：
1. Agent 调用 sub_agent 工具时，构造的 on_token 回调会把 token 以
   {"event":"token","token":...} 事件转发到 _current_sub_agent_cb
2. on_token 转发失败不抛异常、不中断
3. _current_sub_agent_cb 为 None 时 on_token 回调不崩溃
"""

import json
import logging
import sys
import os

logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp.subagent.coordinator import Coordinator
from mcp.subagent.types import AgentRole, AgentSpec


class _FakeLLM:
    """模拟 LLM：流式 token + 单轮回答"""
    def __init__(self, tokens=None):
        self.tokens = tokens or ["流", "式", "t", "o", "k", "e", "n"]

    def chat(self, messages, tools=None, on_token=None, **kwargs):
        if on_token:
            for t in self.tokens:
                on_token(t)
        return _FakeResponse(content="".join(self.tokens))


class _FakeResponse:
    def __init__(self, content=""):
        self.content = content
        self.tool_calls = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_content = ""


class _FakeToolCall:
    def __init__(self, name="sub_agent", arguments=None):
        self.name = name
        self.arguments = arguments or {"agent": "coder", "prompt": "hi"}


class _MiniAgent:
    """最小 Agent 桩：复用 Agent._execute_tool 的 sub_agent 分支逻辑"""
    def __init__(self, coordinator, sub_event_cb=None):
        self._agent_tool = coordinator  # 这里用 Coordinator 的 run 语义近似
        self._current_sub_agent_cb = sub_event_cb
        self._event_logger = None
        self._middleware_chain = None
        self._harness = None

    def _execute_tool(self, tool_call):
        # 复刻 Agent._execute_tool 的 sub_agent 分支（仅核心转发逻辑）
        args = tool_call.arguments or {}
        _sub_event_cb = self._current_sub_agent_cb
        events = []

        def _capture(e):
            events.append(e)
            if _sub_event_cb:
                _sub_event_cb(e)

        def _sub_token_cb(tok):
            if _sub_event_cb is not None:
                try:
                    _sub_event_cb({"event": "token", "token": tok})
                except Exception:
                    pass

        # 模拟 coordinator.run 转发 on_token
        self._agent_tool.run(
            args.get("agent", ""),
            args.get("prompt", ""),
            on_event=_capture,
            on_token=_sub_token_cb,
        )
        return json.dumps({"__sub_agent__": True, "content": "ok"}), events


def _make_coordinator():
    co = Coordinator(llm=_FakeLLM())
    co.register_agent(AgentSpec(name="coder", role=AgentRole.CODER, system_prompt="t", timeout_seconds=60))
    return co


PASS = 0
FAIL = 0
ERRORS = []


def test(name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            global PASS, FAIL
            try:
                func(*args, **kwargs)
                PASS += 1
                print(f"  [PASS] {name}")
            except Exception as e:
                FAIL += 1
                msg = f"  [FAIL] {name}: {type(e).__name__}: {e}"
                print(msg)
                ERRORS.append(msg)
        return wrapper
    return decorator


@test("_execute_tool sub_agent 分支：on_token 转发 token 事件到 _current_sub_agent_cb")
def test_execute_tool_forwards_token():
    co = _make_coordinator()
    received = []
    agent = _MiniAgent(co, sub_event_cb=lambda e: received.append(e))
    tc = _FakeToolCall(arguments={"agent": "coder", "prompt": "hi"})
    agent._execute_tool(tc)
    # 应收到 token 事件（每 token 一个）
    token_events = [e for e in received if e.get("event") == "token"]
    assert token_events, "未收到任何 token 事件"
    # 拼接 token 应等于完整内容
    joined = "".join(e["token"] for e in token_events)
    assert joined == "流式token", f"token 拼接错误: {joined!r}"


@test("_execute_tool 分支：_current_sub_agent_cb 为 None 时 on_token 不崩溃")
def test_execute_tool_no_cb():
    co = _make_coordinator()
    agent = _MiniAgent(co, sub_event_cb=None)  # 无回调
    tc = _FakeToolCall(arguments={"agent": "coder", "prompt": "hi"})
    # 不应崩溃
    agent._execute_tool(tc)


@test("_execute_tool 分支：on_token 转发失败不中断")
def test_execute_tool_token_error_silent():
    co = _make_coordinator()
    def _boom(e):
        raise RuntimeError("回调失败")
    agent = _MiniAgent(co, sub_event_cb=_boom)
    tc = _FakeToolCall(arguments={"agent": "coder", "prompt": "hi"})
    # 不应崩溃
    agent._execute_tool(tc)


def main():
    print("=" * 60)
    print("Agent._execute_tool sub_agent 流式转发测试")
    print("=" * 60)
    test_execute_tool_forwards_token()
    test_execute_tool_no_cb()
    test_execute_tool_token_error_silent()
    print("=" * 60)
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    if ERRORS:
        for e in ERRORS:
            print(" ", e)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
