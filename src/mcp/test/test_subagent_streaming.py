#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TS2 子代理流式输出测试

测试覆盖：
1. _emit_token 静默吞异常（on_token 抛异常不崩溃、不中断）
2. _call_llm 把 on_token 传给 llm.chat（仅当设置了 on_token）
3. _call_llm 未设置 on_token 时不传 on_token 参数（兼容旧 LLM）
4. 完整链路：SessionAgent.run 通过 on_token 转发 token 到回调
5. Coordinator.run / AgentTool.__call__ 的 on_token 参数透传
"""

import json
import logging
import sys
import os

logging.basicConfig(level=logging.CRITICAL, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# 添加项目路径（项目根 = mcp 的父目录，即本文件上两级）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp.subagent.session import SessionAgent
from mcp.subagent.coordinator import Coordinator
from mcp.subagent.agent_tool import AgentTool
from mcp.subagent.types import AgentRole, AgentSpec

PASS = 0
FAIL = 0
ERRORS = []


def test(name):
    """测试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            global PASS, FAIL
            try:
                func(*args, **kwargs)
                PASS += 1
                print(f"  [PASS] {name}")
            except AssertionError as e:
                FAIL += 1
                msg = f"  [FAIL] {name}: {e}"
                print(msg)
                ERRORS.append(msg)
            except Exception as e:
                FAIL += 1
                msg = f"  [FAIL] {name} (异常): {type(e).__name__}: {e}"
                print(msg)
                ERRORS.append(msg)
        return wrapper
    return decorator


class _FakeLLM:
    """模拟 LLM：记录收到的 on_token，并模拟流式调用 on_token"""
    def __init__(self, tokens=None):
        self.tokens = tokens or ["你", "好", "世", "界"]
        self.received_on_token = None
        self.received_kwargs = {}

    def chat(self, messages, tools=None, on_token=None, **kwargs):
        self.received_on_token = on_token
        self.received_kwargs = {"on_token": on_token, "tools": tools}
        # 模拟 LLM 流式：逐 token 调用 on_token
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


def _make_agent(on_token=None, on_event=None):
    spec = AgentSpec(
        name="test",
        role=AgentRole.CODER,
        system_prompt="test",
        timeout_seconds=60,
    )
    return SessionAgent(spec=spec, llm=_FakeLLM(), on_token=on_token, on_event=on_event)


@test("_emit_token 转发 token 到 on_token 回调")
def test_emit_token_forward():
    received = []
    agent = _make_agent(on_token=lambda t: received.append(t))
    agent._emit_token("a")
    agent._emit_token("b")
    assert received == ["a", "b"], f"on_token 未收到全部 token: {received}"


@test("_emit_token 静默吞异常，不崩溃")
def test_emit_token_silent():
    def _boom(t):
        raise RuntimeError("on_token 转发失败")
    agent = _make_agent(on_token=_boom)
    # 不应抛异常
    agent._emit_token("x")
    # on_token 为 None 时也不崩溃
    agent2 = _make_agent(on_token=None)
    agent2._emit_token("x")


@test("_call_llm 把 on_token 传给 llm.chat（设置了 on_token 时）")
def test_call_llm_passes_on_token():
    fake = _FakeLLM()
    spec = AgentSpec(name="test", role=AgentRole.CODER, system_prompt="t", timeout_seconds=60)
    agent = SessionAgent(spec=spec, llm=fake, on_token=lambda t: None)
    agent._call_llm()
    assert fake.received_kwargs.get("on_token") is not None, "on_token 未传给 llm.chat"
    # on_token 应该是 agent._emit_token（绑定方法）
    assert fake.received_kwargs["on_token"] == agent._emit_token


@test("_call_llm 未设置 on_token 时不传 on_token 参数（兼容旧 LLM）")
def test_call_llm_no_on_token():
    fake = _FakeLLM()
    spec = AgentSpec(name="test", role=AgentRole.CODER, system_prompt="t", timeout_seconds=60)
    agent = SessionAgent(spec=spec, llm=fake, on_token=None)
    agent._call_llm()
    assert fake.received_kwargs.get("on_token") is None, "on_token 应为 None"


@test("完整链路：SessionAgent.run 流式转发 token 到回调")
def test_full_chain_stream():
    received_tokens = []
    fake = _FakeLLM(tokens=["流", "式", "输", "出"])
    spec = AgentSpec(name="test", role=AgentRole.CODER, system_prompt="t", timeout_seconds=60)
    agent = SessionAgent(spec=spec, llm=fake, on_token=lambda t: received_tokens.append(t))
    result = agent.run("hello")
    # LLM 流式 token 应全部转发到 on_token
    assert received_tokens == ["流", "式", "输", "出"], f"流式 token 转发不完整: {received_tokens}"
    assert result.content == "流式输出", f"结果内容错误: {result.content!r}"


@test("Coordinator.run 透传 on_token 到 SessionAgent")
def test_coordinator_passes_on_token():
    co = Coordinator(llm=_FakeLLM())
    co.register_agent(AgentSpec(name="coder", role=AgentRole.CODER, system_prompt="t", timeout_seconds=60))
    received = []
    co.run("coder", "hello", on_token=lambda t: received.append(t))
    assert received, "Coordinator.run 未透传 on_token（无 token 收到）"


@test("AgentTool.__call__ 透传 on_token")
def test_agent_tool_passes_on_token():
    co = Coordinator(llm=_FakeLLM())
    co.register_agent(AgentSpec(name="coder", role=AgentRole.CODER, system_prompt="t", timeout_seconds=60))
    tool = AgentTool(co)
    received = []
    result = tool("coder", "hello", on_token=lambda t: received.append(t))
    assert received, "AgentTool 未透传 on_token（无 token 收到）"
    # 返回结构化 JSON
    data = json.loads(result)
    assert data.get("__sub_agent__") is True


@test("on_token 转发失败不中断子代理 run（不触发 loop 重试）")
def test_on_token_error_does_not_interrupt():
    fake = _FakeLLM(tokens=["a", "b", "c"])
    spec = AgentSpec(name="test", role=AgentRole.CODER, system_prompt="t", timeout_seconds=60)
    def _boom(t):
        raise RuntimeError("转发失败")
    agent = SessionAgent(spec=spec, llm=fake, on_token=_boom)
    # 不应崩溃，且能正常完成
    result = agent.run("hello")
    assert result.content == "abc", f"on_token 异常导致子代理 run 中断: {result.content!r}"


def main():
    global PASS, FAIL
    print("=" * 60)
    print("子代理流式输出测试")
    print("=" * 60)
    test_emit_token_forward()
    test_emit_token_silent()
    test_call_llm_passes_on_token()
    test_call_llm_no_on_token()
    test_full_chain_stream()
    test_coordinator_passes_on_token()
    test_agent_tool_passes_on_token()
    test_on_token_error_does_not_interrupt()
    print("=" * 60)
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    if ERRORS:
        print("失败详情:")
        for e in ERRORS:
            print(" ", e)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
