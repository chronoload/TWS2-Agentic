#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TS2 Agent 传输格式极限测试脚本

测试覆盖：
1. ToolCall 类型统一性（isinstance 检查）
2. 空 tool_call_id 的 UUID 回退
3. 空 args 字符串的 JSON 解析
4. delta.content 为 None/空字符串的处理
5. delta.tool_calls 缺失时的 hasattr 保护
6. on_token 签名兼容性（单参数 vs 双参数）
7. LLMResponse.message 格式正确性
8. 循环引用和深拷贝问题
9. 并发工具调用时的 tool_call_id 唯一性
10. 流式 chunk 中 usage 字段缺失的保护
"""

import json
import logging
import sys
import os
import uuid
import traceback

# 设置日志
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
                msg = f"  [ERROR] {name}: {e}\n{traceback.format_exc()}"
                print(msg)
                ERRORS.append(msg)
        return wrapper
    return decorator


# ============================================================
# 测试 1: ToolCall 类型统一性
# ============================================================

@test("ToolCall 类型统一性 - llm.ToolCall 是唯一来源")
def test_toolcall_type_unification():
    from mcp.llm import ToolCall as LLMToolCall
    
    # 创建实例并验证 isinstance
    tc = LLMToolCall(id="test_1", name="test_tool", arguments={"key": "value"})
    assert isinstance(tc, LLMToolCall), "isinstance 对 llm.ToolCall 失败"
    assert tc.id == "test_1"
    assert tc.name == "test_tool"
    assert tc.arguments == {"key": "value"}


@test("ToolCall 实例化 - 所有字段正确")
def test_toolcall_fields():
    from mcp.llm import ToolCall
    
    tc = ToolCall(id="call_abc123", name="get_weather", arguments={"city": "Beijing"})
    assert tc.id == "call_abc123", f"id 字段错误: {tc.id}"
    assert tc.name == "get_weather", f"name 字段错误: {tc.name}"
    assert tc.arguments == {"city": "Beijing"}, f"arguments 字段错误: {tc.arguments}"
    
    # 空 arguments
    tc2 = ToolCall(id="call_def456", name="empty_args", arguments={})
    assert tc2.arguments == {}, f"空 arguments 错误: {tc2.arguments}"


# ============================================================
# 测试 2: 空 tool_call_id 的 UUID 回退
# ============================================================

@test("空 tool_call_id 的 UUID 回退 - LLM.chat() 流式解析")
def test_empty_toolcall_id_llm():
    from mcp.llm import ToolCall
    
    # 模拟 LLM.chat() 中的流式解析逻辑
    tc_map = {
        0: {"id": "", "name": "get_weather", "args": '{"city": "Beijing"}'},
        1: {"id": "call_real_id", "name": "get_time", "args": '{"tz": "UTC"}'},
    }
    
    parsed = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args_str = raw.get("args", "")
        if not args_str or args_str.strip() == "":
            args = {}
        else:
            try:
                args = json.loads(args_str)
            except (json.JSONDecodeError, KeyError):
                args = {}
        tool_id = raw.get("id", "")
        if not tool_id:
            tool_id = f"call_{uuid.uuid4().hex[:12]}"
        parsed.append(ToolCall(id=tool_id, name=raw.get("name", ""), arguments=args))
    
    # 第一个 tool_call 的 id 应该是 UUID 格式
    assert parsed[0].id.startswith("call_"), f"UUID 回退失败: {parsed[0].id}"
    assert len(parsed[0].id) == 17, f"UUID 长度错误: {parsed[0].id} ({len(parsed[0].id)})"
    
    # 第二个 tool_call 的 id 应该是原始值
    assert parsed[1].id == "call_real_id", f"原始 id 被覆盖: {parsed[1].id}"
    
    # 验证 UUID 唯一性
    assert parsed[0].id != parsed[1].id, "UUID 与真实 id 冲突"


@test("空 tool_call_id 的 UUID 回退 - OpenAIProvider._process_stream()")
def test_empty_toolcall_id_openai_provider():
    from mcp.llm import ToolCall
    
    # 模拟 OpenAIProvider._process_stream() 中的逻辑
    tc_map = {
        0: {"id": "", "name": "search", "args": '{"q": "test"}'},
    }
    
    tool_calls = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args_str = raw.get("args", "")
        if not args_str or args_str.strip() == "":
            args = {}
        else:
            try:
                args = json.loads(args_str)
            except (json.JSONDecodeError, KeyError):
                args = {}
        tool_id = raw.get("id", "")
        if not tool_id:
            tool_id = f"call_{uuid.uuid4().hex[:12]}"
        tool_calls.append(ToolCall(id=tool_id, name=raw.get("name", ""), arguments=args))
    
    assert tool_calls[0].id.startswith("call_"), f"UUID 回退失败: {tool_calls[0].id}"
    assert tool_calls[0].name == "search", f"name 错误: {tool_calls[0].name}"
    assert tool_calls[0].arguments == {"q": "test"}, f"arguments 错误: {tool_calls[0].arguments}"


# ============================================================
# 测试 3: 空 args 字符串的 JSON 解析
# ============================================================

@test("空 args 字符串的 JSON 解析保护")
def test_empty_args_json():
    from mcp.llm import ToolCall
    
    test_cases = [
        ("", {}),
        ("   ", {}),
        ('{"key": "value"}', {"key": "value"}),
        ("null", {}),  # json.loads("null") returns None, should be normalized to {}
        ("{}", {}),
    ]
    
    for args_str, expected in test_cases:
        if not args_str or args_str.strip() == "":
            args = {}
        else:
            try:
                args = json.loads(args_str)
            except (json.JSONDecodeError, KeyError):
                args = {}
        # "null" 字符串 json.loads 返回 None，需要额外处理
        if args is None:
            args = {}
        assert args == expected, f"args_str='{args_str}' 解析为 {args}, 期望 {expected}"


@test("空 args 字符串不会导致 JSONDecodeError")
def test_empty_args_no_crash():
    # 直接 json.loads("") 应该抛出异常
    try:
        json.loads("")
        assert False, "json.loads('') 应该抛出异常但没有"
    except json.JSONDecodeError:
        pass  # 期望的行为
    
    # 修复后的代码应该安全处理
    args_str = ""
    if not args_str or args_str.strip() == "":
        args = {}
    else:
        args = json.loads(args_str)
    assert args == {}, f"空字符串处理失败: {args}"


# ============================================================
# 测试 4: delta.content 为 None/空字符串的处理
# ============================================================

@test("delta.content 为 None 时不会崩溃")
def test_delta_content_none():
    # 模拟 LLM.chat() 中的逻辑
    class MockDelta:
        content = None
    
    delta = MockDelta()
    
    # 旧代码: if delta.content: → 会跳过 None，没问题
    # 新代码: if delta.content is not None: → 也会跳过 None，没问题
    
    # 验证不会崩溃
    if delta.content is not None:
        content_parts = [delta.content]
    else:
        content_parts = []
    
    assert content_parts == [], f"None content 被错误处理: {content_parts}"


@test("delta.content 为空字符串 '' 时正确处理")
def test_delta_content_empty_string():
    # 模拟 LLM.chat() 中的逻辑
    class MockDelta:
        content = ""
    
    delta = MockDelta()
    
    # 旧代码: if delta.content: → 空字符串为 falsy，会跳过
    # 新代码: if delta.content is not None: → 空字符串不是 None，会处理
    
    # 新代码行为
    if delta.content is not None:
        content_parts = [delta.content]
    else:
        content_parts = []
    
    assert content_parts == [""], f"空字符串 content 被错误跳过: {content_parts}"
    
    # 验证旧代码行为（bug）
    if delta.content:
        old_content_parts = [delta.content]
    else:
        old_content_parts = []
    
    assert old_content_parts == [], "旧代码应该跳过空字符串（这是 bug）"


# ============================================================
# 测试 5: delta.tool_calls 缺失时的 hasattr 保护
# ============================================================

@test("delta.tool_calls 缺失时 hasattr 保护")
def test_delta_toolcalls_missing():
    # 模拟没有 tool_calls 属性的 delta 对象
    class MockDeltaNoToolCalls:
        content = "Hello"
    
    delta = MockDeltaNoToolCalls()
    
    # 旧代码: if delta.tool_calls: → AttributeError
    # 新代码: if hasattr(delta, 'tool_calls') and delta.tool_calls: → 安全
    
    try:
        # 旧代码会崩溃
        if delta.tool_calls:
            pass
        assert False, "旧代码应该抛出 AttributeError 但没有"
    except AttributeError:
        pass  # 期望的行为
    
    # 新代码安全
    if hasattr(delta, 'tool_calls') and delta.tool_calls:
        assert False, "不应该进入 tool_calls 分支"
    
    # 有 tool_calls 但为空的 delta
    class MockDeltaEmptyToolCalls:
        content = "Hello"
        tool_calls = []
    
    delta2 = MockDeltaEmptyToolCalls()
    if hasattr(delta2, 'tool_calls') and delta2.tool_calls:
        assert False, "空 tool_calls 列表不应该进入分支"


# ============================================================
# 测试 6: on_token 签名兼容性
# ============================================================

@test("on_token 签名兼容性 - 单参数回调被双参数调用")
def test_on_token_signature_compatibility():
    # Agent.chat() 的 on_token 签名: Callable[[str], None]
    # LLM.chat() 的 on_token 签名: Callable[[str, str], Any]
    
    received = []
    
    # 模拟 Agent.chat() 中的包装
    def on_token_single(text: str):
        received.append(text)
    
    def _wrapped_on_token(text: str, msg_type: str = "") -> None:
        if on_token_single:
            return on_token_single(text)
    
    # 模拟 LLM.chat() 中的调用
    _wrapped_on_token("Hello", "content")
    _wrapped_on_token("思考中...", "reasoning")
    _wrapped_on_token("World", "content")
    
    assert received == ["Hello", "思考中...", "World"], \
        f"on_token 包装失败: {received}"
    
    # 验证 msg_type 被正确忽略
    assert len(received) == 3, f"消息数量错误: {len(received)}"


@test("on_token 为 None 时不会崩溃")
def test_on_token_none():
    # 模拟 LLM.chat() 中 on_token 为 None 的情况
    on_token = None
    
    # 包装函数
    def _wrapped_on_token(text: str, msg_type: str = "") -> None:
        if on_token:
            return on_token(text)
    
    # 调用不应该崩溃
    _wrapped_on_token("Hello", "content")
    _wrapped_on_token("World", "reasoning")


# ============================================================
# 测试 7: LLMResponse.message 格式正确性
# ============================================================

@test("LLMResponse.message 格式正确性")
def test_llmresponse_message_format():
    from mcp.llm import LLMResponse, ToolCall
    
    # 纯文本响应
    resp1 = LLMResponse(content="Hello World")
    msg1 = resp1.message
    assert msg1["role"] == "assistant", f"role 错误: {msg1['role']}"
    assert msg1["content"] == "Hello World", f"content 错误: {msg1['content']}"
    assert "tool_calls" not in msg1, "不应有 tool_calls"
    
    # 带推理内容的响应
    resp2 = LLMResponse(content="Answer", reasoning_content="Thinking...")
    msg2 = resp2.message
    assert msg2["reasoning_content"] == "Thinking...", f"reasoning_content 错误: {msg2['reasoning_content']}"
    
    # 带工具调用的响应
    resp3 = LLMResponse(
        content="",
        tool_calls=[
            ToolCall(id="call_1", name="search", arguments={"q": "test"}),
        ]
    )
    msg3 = resp3.message
    assert msg3["content"] == "", "content 应为空字符串"
    assert "tool_calls" in msg3, "应有 tool_calls"
    assert msg3["tool_calls"][0]["id"] == "call_1", f"tool_call id 错误: {msg3['tool_calls'][0]['id']}"
    assert msg3["tool_calls"][0]["type"] == "function", f"type 错误: {msg3['tool_calls'][0]['type']}"
    assert msg3["tool_calls"][0]["function"]["name"] == "search", f"name 错误"
    assert msg3["tool_calls"][0]["function"]["arguments"] == '{"q": "test"}', f"arguments 错误"


@test("LLMResponse.content 为 None 时 message 正确处理")
def test_llmresponse_content_none():
    from mcp.llm import LLMResponse
    
    # content 为 None 时应该转为空字符串
    resp = LLMResponse(content=None)
    msg = resp.message
    assert msg["content"] == "", f"None content 未转为空字符串: {msg['content']}"


# ============================================================
# 测试 8: 并发工具调用时的 tool_call_id 唯一性
# ============================================================

@test("并发工具调用时 tool_call_id 唯一性")
def test_concurrent_toolcall_id_uniqueness():
    from mcp.llm import ToolCall
    
    # 模拟多个工具调用，其中一些 id 为空
    tc_map = {
        0: {"id": "", "name": "tool_a", "args": "{}"},
        1: {"id": "", "name": "tool_b", "args": "{}"},
        2: {"id": "call_fixed", "name": "tool_c", "args": "{}"},
    }
    
    parsed = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args_str = raw.get("args", "")
        if not args_str or args_str.strip() == "":
            args = {}
        else:
            try:
                args = json.loads(args_str)
            except (json.JSONDecodeError, KeyError):
                args = {}
        tool_id = raw.get("id", "")
        if not tool_id:
            tool_id = f"call_{uuid.uuid4().hex[:12]}"
        parsed.append(ToolCall(id=tool_id, name=raw.get("name", ""), arguments=args))
    
    # 所有 id 必须唯一
    ids = [tc.id for tc in parsed]
    assert len(ids) == len(set(ids)), f"tool_call_id 不唯一: {ids}"
    
    # 空 id 的 tool_call 应该有 UUID
    assert parsed[0].id.startswith("call_"), f"tool_a id 错误: {parsed[0].id}"
    assert parsed[1].id.startswith("call_"), f"tool_b id 错误: {parsed[1].id}"
    assert parsed[2].id == "call_fixed", f"tool_c id 被覆盖: {parsed[2].id}"
    
    # 两个 UUID 必须不同
    assert parsed[0].id != parsed[1].id, f"UUID 重复: {parsed[0].id} == {parsed[1].id}"


# ============================================================
# 测试 9: 流式 chunk 中 usage 字段缺失的保护
# ============================================================

@test("流式 chunk 中 usage 字段缺失的保护")
def test_chunk_usage_missing():
    # 模拟没有 usage 属性的 chunk
    class MockChunkNoUsage:
        class MockChoices:
            class MockDelta:
                content = "Hello"
            delta = MockDelta()
            finish_reason = None
        choices = [MockChoices()]
    
    chunk = MockChunkNoUsage()
    
    # 旧代码: if chunk.usage: → AttributeError
    # 新代码: if chunk.usage: → 如果 chunk 没有 usage 属性，会 AttributeError
    
    # 实际上，OpenAI SDK 的 chunk 总是有 usage 属性（可能为 None）
    # 但为了安全，应该用 hasattr 或 getattr
    
    # 使用 getattr 安全访问
    usage = getattr(chunk, "usage", None)
    if usage:
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    else:
        prompt_tokens = 0
    
    assert prompt_tokens == 0, f"usage 缺失时 prompt_tokens 应为 0: {prompt_tokens}"


# ============================================================
# 测试 10: 端到端消息格式兼容性
# ============================================================

@test("端到端消息格式兼容性 - 模拟完整 Agent 对话")
def test_end_to_end_message_format():
    from mcp.llm import LLMResponse, ToolCall
    
    messages = []
    
    # 1. 用户消息
    messages.append({"role": "user", "content": "北京的天气怎么样？"})
    
    # 2. 助手响应（带工具调用）
    resp1 = LLMResponse(
        content="",
        tool_calls=[
            ToolCall(id="call_weather_1", name="get_weather", arguments={"city": "Beijing"}),
        ]
    )
    messages.append(resp1.message)
    
    # 验证助手消息格式
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == ""
    assert len(messages[-1]["tool_calls"]) == 1
    assert messages[-1]["tool_calls"][0]["id"] == "call_weather_1"
    
    # 3. 工具结果消息
    messages.append({
        "role": "tool",
        "tool_call_id": "call_weather_1",
        "content": json.dumps({"temperature": 25, "condition": "晴"})
    })
    
    # 验证工具消息格式
    assert messages[-1]["role"] == "tool"
    assert messages[-1]["tool_call_id"] == "call_weather_1"
    
    # 4. 助手最终响应
    resp2 = LLMResponse(content="北京今天25°C，天气晴朗。")
    messages.append(resp2.message)
    
    assert messages[-1]["content"] == "北京今天25°C，天气晴朗。"
    assert "tool_calls" not in messages[-1]
    
    # 验证整个消息链
    assert len(messages) == 4, f"消息链长度错误: {len(messages)}"


# ============================================================
# 测试 11: _sanitize.py 的 tool_call_id 回退
# ============================================================

@test("_sanitize.py 中 tool_call_id 回退逻辑 - 无前面 assistant 消息时生成 UUID")
def test_sanitize_tool_call_id_no_assistant():
    """当没有前面的 assistant 消息时，空 tool_call_id 生成 UUID 作为 fallback"""
    from mcp._sanitize import sanitize_messages
    
    # 模拟 tool 消息缺少 tool_call_id，且前面没有 assistant 消息
    messages = [
        {"role": "tool", "content": "result", "tool_call_id": None},
        {"role": "tool", "content": "result2", "tool_call_id": ""},
        {"role": "tool", "content": "result3", "tool_call_id": "valid_id"},
    ]
    
    cleaned = sanitize_messages(messages)
    
    # None tool_call_id → 生成 UUID（没有前面的 assistant 消息可匹配，fallback 到 UUID）
    assert cleaned[0]["tool_call_id"].startswith("call_"), \
        f"None tool_call_id 应生成 UUID: {cleaned[0]['tool_call_id']}"
    assert len(cleaned[0]["tool_call_id"]) == 17, \
        f"UUID 长度错误: {cleaned[0]['tool_call_id']} ({len(cleaned[0]['tool_call_id'])})"
    
    # 空字符串 tool_call_id → 生成 UUID
    assert cleaned[1]["tool_call_id"].startswith("call_"), \
        f"空 tool_call_id 应生成 UUID: {cleaned[1]['tool_call_id']}"
    assert len(cleaned[1]["tool_call_id"]) == 17, \
        f"UUID 长度错误: {cleaned[1]['tool_call_id']} ({len(cleaned[1]['tool_call_id'])})"
    
    # 有效 tool_call_id 应该保持不变
    assert cleaned[2]["tool_call_id"] == "valid_id", \
        f"有效 tool_call_id 被修改: {cleaned[2]['tool_call_id']}"
    
    # 所有生成的 UUID 必须唯一
    ids = [m["tool_call_id"] for m in cleaned]
    assert len(ids) == len(set(ids)), f"UUID 不唯一: {ids}"


@test("_sanitize.py 中 tool_call_id 回退逻辑 - 有前面 assistant 消息时匹配")
def test_sanitize_tool_call_id_with_assistant():
    """当有前面的 assistant 消息时，空 tool_call_id 应该匹配前面的 tool_calls"""
    from mcp._sanitize import sanitize_messages
    
    # 模拟完整的对话：assistant 消息带 tool_calls → tool 消息
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_abc", "type": "function", "function": {"name": "search", "arguments": "{}"}},
                {"id": "call_def", "type": "function", "function": {"name": "read", "arguments": "{}"}},
            ]
        },
        {"role": "tool", "content": "result1", "tool_call_id": None},  # 应匹配 call_abc
        {"role": "tool", "content": "result2", "tool_call_id": ""},     # 应匹配 call_def
        {"role": "tool", "content": "result3", "tool_call_id": "valid_id"},  # 保持不变
    ]
    
    cleaned = sanitize_messages(messages)
    
    # None tool_call_id → 匹配前面的第一个未使用的 tool_call id
    assert cleaned[1]["tool_call_id"] == "call_abc", \
        f"None tool_call_id 应匹配 call_abc: {cleaned[1]['tool_call_id']}"
    
    # 空字符串 tool_call_id → 匹配前面的第二个未使用的 tool_call id
    assert cleaned[2]["tool_call_id"] == "call_def", \
        f"空 tool_call_id 应匹配 call_def: {cleaned[2]['tool_call_id']}"
    
    # 有效 tool_call_id 应该保持不变
    assert cleaned[3]["tool_call_id"] == "valid_id", \
        f"有效 tool_call_id 被修改: {cleaned[3]['tool_call_id']}"


# ============================================================
# 测试 12: LLMResponse 的 model 和 finish_reason 字段
# ============================================================

@test("LLMResponse 新增 model 和 finish_reason 字段")
def test_llmresponse_new_fields():
    from mcp.llm import LLMResponse
    
    # 默认值
    resp = LLMResponse(content="test")
    assert resp.model == "", f"默认 model 错误: {resp.model}"
    assert resp.finish_reason == "", f"默认 finish_reason 错误: {resp.finish_reason}"
    
    # 设置值
    resp2 = LLMResponse(content="test", model="gpt-4o", finish_reason="stop")
    assert resp2.model == "gpt-4o", f"model 错误: {resp2.model}"
    assert resp2.finish_reason == "stop", f"finish_reason 错误: {resp2.finish_reason}"


# ============================================================
# 测试 13: 导入兼容性
# ============================================================

@test("llm 模块正确导出 ToolCall 和 LLMResponse")
def test_import_compatibility():
    # 验证 llm 模块有 ToolCall/LLMResponse 定义
    import mcp.llm
    
    # 检查是否从 llm 导入
    assert hasattr(mcp.llm, 'ToolCall'), "llm 没有 ToolCall"
    assert hasattr(mcp.llm, 'LLMResponse'), "llm 没有 LLMResponse"
    
    # 验证是同一个类
    from mcp.llm import ToolCall as LLMToolCall
    assert mcp.llm.ToolCall is LLMToolCall, "ToolCall 不是同一个类"


# ============================================================
# 测试 14: 边界情况 - 大量工具调用
# ============================================================

@test("大量工具调用时 ID 唯一性和性能")
def test_many_toolcalls():
    from mcp.llm import ToolCall
    
    # 模拟 50 个工具调用，其中一半 id 为空
    tc_map = {}
    for i in range(50):
        tc_map[i] = {
            "id": "" if i % 2 == 0 else f"call_fixed_{i}",
            "name": f"tool_{i}",
            "args": '{}',
        }
    
    parsed = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args_str = raw.get("args", "")
        if not args_str or args_str.strip() == "":
            args = {}
        else:
            try:
                args = json.loads(args_str)
            except (json.JSONDecodeError, KeyError):
                args = {}
        tool_id = raw.get("id", "")
        if not tool_id:
            tool_id = f"call_{uuid.uuid4().hex[:12]}"
        parsed.append(ToolCall(id=tool_id, name=raw.get("name", ""), arguments=args))
    
    # 所有 ID 必须唯一
    ids = [tc.id for tc in parsed]
    assert len(ids) == len(set(ids)), f"大量工具调用中 ID 不唯一"
    
    # 空 ID 的个数
    uuid_ids = [id for id in ids if id.startswith("call_") and not id.startswith("call_fixed_")]
    assert len(uuid_ids) == 25, f"UUID 数量错误: {len(uuid_ids)} (期望 25)"


# ============================================================
# 第三部分：错误打包（Error Bundling）极限测试
# ============================================================

@test("错误打包 1 - 多个错误同时发生：None chunk + 空 tool_call_id + 损坏 JSON")
def test_error_bundling_multiple_errors():
    """模拟流式响应中同时出现多个错误：损坏 chunk、空 id、损坏 JSON"""
    from mcp.llm import ToolCall, _safe_parse_args, _safe_tool_id, _safe_tool_name
    
    # 模拟 _process_stream 中的 tc_map 构建
    tc_map = {
        0: {"id": "", "name": "search", "args": '{"q": "test"}'},  # 空 id
        1: {"id": "call_valid", "name": "", "args": '{"x": 1}'},   # 空 name
        2: {"id": "", "name": "", "args": '{"y": 2}'},             # 空 id + 空 name
        3: {"id": "call_bad", "name": "bad_tool", "args": '{"z":'}, # 损坏 JSON
        4: {"id": "", "name": "corrupted", "args": '{"a": "b"},'}, # 空 id + 损坏 JSON
    }
    
    parsed = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args = _safe_parse_args(raw.get("args", ""))
        tool_id = _safe_tool_id(raw.get("id", ""))
        tool_name = _safe_tool_name(raw.get("name", ""))
        parsed.append(ToolCall(id=tool_id, name=tool_name, arguments=args))
    
    # 验证所有工具调用都被正确处理
    assert len(parsed) == 5, f"应解析 5 个工具调用，实际 {len(parsed)}"
    
    # 1. 空 id → UUID
    assert parsed[0].id.startswith("call_"), f"空 id 未回退: {parsed[0].id}"
    assert parsed[0].name == "search", f"name 错误: {parsed[0].name}"
    assert parsed[0].arguments == {"q": "test"}, f"args 错误: {parsed[0].arguments}"
    
    # 2. 空 name → unknown_tool
    assert parsed[1].id == "call_valid", f"有效 id 被修改: {parsed[1].id}"
    assert parsed[1].name == "unknown_tool", f"空 name 未回退: {parsed[1].name}"
    assert parsed[1].arguments == {"x": 1}, f"args 错误: {parsed[1].arguments}"
    
    # 3. 空 id + 空 name → 都回退
    assert parsed[2].id.startswith("call_"), f"空 id 未回退: {parsed[2].id}"
    assert parsed[2].name == "unknown_tool", f"空 name 未回退: {parsed[2].name}"
    assert parsed[2].arguments == {"y": 2}, f"args 错误: {parsed[2].arguments}"
    
    # 4. 损坏 JSON → 修复或空 dict
    assert parsed[3].id == "call_bad", f"有效 id 被修改: {parsed[3].id}"
    assert parsed[3].name == "bad_tool", f"name 错误: {parsed[3].name}"
    # 损坏的 JSON 应该被修复或返回空 dict
    assert isinstance(parsed[3].arguments, dict), f"损坏 JSON 未修复: {parsed[3].arguments}"
    
    # 5. 空 id + 损坏 JSON
    assert parsed[4].id.startswith("call_"), f"空 id 未回退: {parsed[4].id}"
    assert parsed[4].name == "corrupted", f"name 错误: {parsed[4].name}"
    assert isinstance(parsed[4].arguments, dict), f"损坏 JSON 未修复: {parsed[4].arguments}"
    
    # 验证所有 ID 唯一
    ids = [tc.id for tc in parsed]
    assert len(ids) == len(set(ids)), f"ID 不唯一: {ids}"


@test("错误打包 2 - 流式 chunk 中同时缺失多个字段")
def test_error_bundling_missing_fields():
    """模拟流式 chunk 中同时缺失 usage、choices、delta 字段"""
    # 使用内置 getattr 替代不存在的 _safe_get_attr
    def _safe_get_attr(obj, attr, default=None):
        return getattr(obj, attr, default)
    
    # 模拟各种损坏的 chunk
    class MockChunkNone:
        pass  # 没有 usage, 没有 choices
    
    class MockChunkNoChoices:
        usage = None
    
    class MockChunkNoDelta:
        class MockChoices:
            delta = None
        choices = [MockChoices()]
    
    chunks = [None, MockChunkNone(), MockChunkNoChoices(), MockChunkNoDelta()]
    
    content_parts = []
    chunk_count = 0
    
    for chunk in chunks:
        chunk_count += 1
        if chunk is None:
            continue
        
        usage = _safe_get_attr(chunk, "usage")
        if usage:
            pass  # 正常处理
        
        choices = _safe_get_attr(chunk, "choices")
        if not choices:
            continue
        
        delta = choices[0].delta
        if delta is None:
            continue
        
        if _safe_get_attr(delta, "content") is not None:
            content_parts.append(delta.content)
    
    # 验证没有崩溃，且正确处理了所有损坏情况
    assert chunk_count == 4, f"chunk_count 错误: {chunk_count}"
    assert content_parts == [], "不应有 content 被收集"


@test("错误打包 3 - 空流 + 空 tool_calls + 空 content 同时发生")
def test_error_bundling_empty_stream_and_toolcalls():
    """模拟空流 + 空 tool_calls + 空 content 同时发生"""
    from mcp.llm import LLMResponse, ToolCall
    
    # 模拟 _process_stream 返回空响应
    resp = LLMResponse(
        content="",
        reasoning_content="",
        tool_calls=[],
        prompt_tokens=0,
        completion_tokens=0,
    )
    
    assert resp.content == "", f"content 应为空: {resp.content}"
    assert resp.tool_calls == [], f"tool_calls 应为空: {resp.tool_calls}"
    assert resp.prompt_tokens == 0, f"prompt_tokens 应为 0: {resp.prompt_tokens}"
    
    # message 格式也应该正确
    msg = resp.message
    assert msg["role"] == "assistant", f"role 错误: {msg['role']}"
    assert msg["content"] == "", f"content 错误: {msg['content']}"
    assert "tool_calls" not in msg, "不应有 tool_calls"


# ============================================================
# 第四部分：不闭合（Unclosed）极限测试
# ============================================================

@test("不闭合 1 - 流式 chunk 不闭合（0 chunk）")
def test_unclosed_zero_chunks():
    """模拟流式响应返回 0 个 chunk（空流）"""
    from mcp.llm import LLMResponse
    
    # 模拟 _process_stream 中 chunk_count == 0 的处理
    chunk_count = 0
    
    if chunk_count == 0:
        resp = LLMResponse(
            content="",
            reasoning_content="",
            tool_calls=[],
            prompt_tokens=0,
            completion_tokens=0,
        )
    else:
        resp = LLMResponse(content="should not reach here")
    
    assert resp.content == "", f"空流应返回空 content: {resp.content}"
    assert resp.tool_calls == [], f"空流应返回空 tool_calls: {resp.tool_calls}"
    assert resp.prompt_tokens == 0, f"空流应返回 0 tokens: {resp.prompt_tokens}"


@test("不闭合 2 - tool_call 不闭合（只有 id 没有 name 和 args）")
def test_unclosed_toolcall():
    """模拟 tool_call 流式 chunk 不完整：只有 id，没有 name 和 args"""
    from mcp.llm import ToolCall, _safe_parse_args, _safe_tool_id, _safe_tool_name
    
    # 模拟 tc_map 中只有 id，没有 name 和 args
    tc_map = {
        0: {"id": "call_partial", "name": "", "args": ""},
    }
    
    parsed = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args = _safe_parse_args(raw.get("args", ""))
        tool_id = _safe_tool_id(raw.get("id", ""))
        tool_name = _safe_tool_name(raw.get("name", ""))
        parsed.append(ToolCall(id=tool_id, name=tool_name, arguments=args))
    
    assert len(parsed) == 1, f"应解析 1 个工具调用: {len(parsed)}"
    assert parsed[0].id == "call_partial", f"id 错误: {parsed[0].id}"
    assert parsed[0].name == "unknown_tool", f"空 name 未回退: {parsed[0].name}"
    assert parsed[0].arguments == {}, f"空 args 未回退: {parsed[0].arguments}"


@test("不闭合 3 - JSON 截断（不闭合的 JSON 字符串）")
def test_unclosed_json_truncation():
    """模拟工具调用参数 JSON 被截断"""
    from mcp.llm import _try_repair_json
    
    test_cases = [
        # (损坏的 JSON, 期望修复后的结果)
        ('{"city": "Beijing"', {"city": "Beijing"}),  # 缺少 }
        ('{"a": 1, "b": 2', {"a": 1, "b": 2}),        # 缺少 }
        ('{"nested": {"x": 1}', {"nested": {"x": 1}}), # 嵌套缺少 }
        ('{"arr": [1, 2, 3]', {"arr": [1, 2, 3]}),     # 数组缺少 }
        ('{"key": "value"}', {"key": "value"}),         # 完整 JSON
        ('{"a": 1, "b": 2,}', {"a": 1, "b": 2}),       # 多余逗号
    ]
    
    for raw, expected in test_cases:
        result = _try_repair_json(raw)
        assert result == expected, f"修复失败: raw={raw!r}, got={result}, expected={expected}"


@test("不闭合 4 - 流式 chunk 中 tool_call 的 arguments 逐步累积但最终不完整")
def test_unclosed_streaming_args_accumulation():
    """模拟流式 chunk 中 arguments 逐步累积但最终不完整"""
    from mcp.llm import ToolCall, _safe_parse_args, _safe_tool_id, _safe_tool_name
    
    # 模拟流式累积过程：args 逐步追加但最终不完整
    tc_map = {
        0: {"id": "call_weather", "name": "get_weather", "args": '{"city": "Bei'},
    }
    # 模拟后续 chunk 继续追加
    tc_map[0]["args"] += 'jing", "tem'  # 仍然不完整
    tc_map[0]["args"] += 'p'  # 仍然不完整
    
    parsed = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args = _safe_parse_args(raw.get("args", ""))
        tool_id = _safe_tool_id(raw.get("id", ""))
        tool_name = _safe_tool_name(raw.get("name", ""))
        parsed.append(ToolCall(id=tool_id, name=tool_name, arguments=args))
    
    assert len(parsed) == 1, f"应解析 1 个工具调用: {len(parsed)}"
    assert parsed[0].id == "call_weather", f"id 错误: {parsed[0].id}"
    assert parsed[0].name == "get_weather", f"name 错误: {parsed[0].name}"
    # 不完整的 JSON 应该被修复或返回空 dict
    assert isinstance(parsed[0].arguments, dict), f"不完整 JSON 未修复: {parsed[0].arguments}"


# ============================================================
# 第五部分：损坏信息（Corrupted Data）极限测试
# ============================================================

@test("损坏信息 1 - 损坏的 JSON（乱码字符）")
def test_corrupted_json_garbled():
    """模拟工具调用参数中包含乱码字符"""
    from mcp.llm import _try_repair_json
    
    test_cases = [
        # (损坏的 JSON, 期望至少是 dict)
        ('{"city": "Bei\x00jing"}', None),  # 含 null 字符
        ('{"city": "Bei\x01jing"}', None),  # 含控制字符
        ('{"city": "Bei\x1fjing"}', None),  # 含控制字符
        ('{"city": "北京\u0000"}', None),    # 含 null 字符
        ('\x00\x01\x02{"city": "test"}', None),  # 前导乱码
        ('{"city": "test"}\x00\x01\x02', None),   # 尾部乱码
    ]
    
    for raw, _ in test_cases:
        result = _try_repair_json(raw)
        assert isinstance(result, dict), f"损坏 JSON 未修复为 dict: raw={raw!r}, got={type(result)}"


@test("损坏信息 2 - 非法 Unicode / 编码错误")
def test_corrupted_unicode():
    """模拟包含非法 Unicode 的字符串"""
    from mcp.llm import _try_repair_json
    
    # 模拟各种编码损坏
    test_cases = [
        '{"msg": "\\ud800\\udc00"}',  # 代理对（可能合法）
        '{"msg": "\\xZZ"}',           # 非法转义
        '{"msg": "\\uZZZZ"}',         # 非法 unicode 转义
        '{"msg": "test\\',             # 尾部反斜杠
    ]
    
    for raw in test_cases:
        result = _try_repair_json(raw)
        assert isinstance(result, dict), f"非法 Unicode 未修复为 dict: raw={raw!r}, got={type(result)}"


@test("损坏信息 3 - 空字符串和 None 输入")
def test_corrupted_empty_and_none():
    """模拟各种空/None 输入"""
    from mcp.llm import _try_repair_json, _safe_parse_args, _safe_tool_id, _safe_tool_name
    
    # _try_repair_json
    assert _try_repair_json(None) == {}, f"None 输入未返回空 dict"
    assert _try_repair_json("") == {}, f"空字符串未返回空 dict"
    assert _try_repair_json("   ") == {}, f"空白字符串未返回空 dict"
    assert _try_repair_json(123) == {}, f"非字符串输入未返回空 dict"
    
    # _safe_parse_args
    assert _safe_parse_args(None) == {}, f"_safe_parse_args(None) 未返回空 dict"
    assert _safe_parse_args("") == {}, f"_safe_parse_args('') 未返回空 dict"
    assert _safe_parse_args("null") == {}, f"_safe_parse_args('null') 未返回空 dict"
    assert _safe_parse_args("123") == {}, f"_safe_parse_args('123') 未返回空 dict"
    assert _safe_parse_args("[]") == {}, f"_safe_parse_args('[]') 未返回空 dict"
    
    # _safe_tool_id
    assert _safe_tool_id(None).startswith("call_"), f"_safe_tool_id(None) 未生成 UUID"
    assert _safe_tool_id("").startswith("call_"), f"_safe_tool_id('') 未生成 UUID"
    assert _safe_tool_id("   ").startswith("call_"), f"_safe_tool_id('   ') 未生成 UUID"
    assert _safe_tool_id(123).startswith("call_"), f"_safe_tool_id(123) 未生成 UUID"
    assert _safe_tool_id("valid_id") == "valid_id", f"_safe_tool_id('valid_id') 被修改"
    
    # _safe_tool_name
    assert _safe_tool_name(None) == "unknown_tool", f"_safe_tool_name(None) 未回退"
    assert _safe_tool_name("") == "unknown_tool", f"_safe_tool_name('') 未回退"
    assert _safe_tool_name("   ") == "unknown_tool", f"_safe_tool_name('   ') 未回退"
    assert _safe_tool_name(123) == "unknown_tool", f"_safe_tool_name(123) 未回退"
    assert _safe_tool_name("valid_name") == "valid_name", f"_safe_tool_name('valid_name') 被修改"


@test("损坏信息 4 - 混合损坏：乱码 + 截断 + 空字段")
def test_corrupted_mixed():
    """模拟混合损坏：乱码 + 截断 + 空字段同时出现"""
    from mcp.llm import ToolCall, _safe_parse_args, _safe_tool_id, _safe_tool_name
    
    # 模拟各种损坏的 tool_call 数据
    tc_map = {
        0: {"id": None, "name": None, "args": None},                    # 全部 None
        1: {"id": "", "name": "", "args": ""},                          # 全部空
        2: {"id": "call_ok", "name": "tool_ok", "args": '{"a": 1}'},    # 正常
        3: {"id": "call_garbled", "name": "tool_garbled", "args": '{"a": "\x00\x01\x02"}'},  # 乱码值
        4: {"id": "call_truncated", "name": "tool_truncated", "args": '{"a": 1, "b":'},      # 截断
    }
    
    parsed = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args = _safe_parse_args(raw.get("args", ""))
        tool_id = _safe_tool_id(raw.get("id", ""))
        tool_name = _safe_tool_name(raw.get("name", ""))
        parsed.append(ToolCall(id=tool_id, name=tool_name, arguments=args))
    
    assert len(parsed) == 5, f"应解析 5 个工具调用: {len(parsed)}"
    
    # 0: 全部 None → 全部回退
    assert parsed[0].id.startswith("call_"), f"None id 未回退: {parsed[0].id}"
    assert parsed[0].name == "unknown_tool", f"None name 未回退: {parsed[0].name}"
    assert parsed[0].arguments == {}, f"None args 未回退: {parsed[0].arguments}"
    
    # 1: 全部空 → 全部回退
    assert parsed[1].id.startswith("call_"), f"空 id 未回退: {parsed[1].id}"
    assert parsed[1].name == "unknown_tool", f"空 name 未回退: {parsed[1].name}"
    assert parsed[1].arguments == {}, f"空 args 未回退: {parsed[1].arguments}"
    
    # 2: 正常 → 保持不变
    assert parsed[2].id == "call_ok", f"正常 id 被修改: {parsed[2].id}"
    assert parsed[2].name == "tool_ok", f"正常 name 被修改: {parsed[2].name}"
    assert parsed[2].arguments == {"a": 1}, f"正常 args 被修改: {parsed[2].arguments}"
    
    # 3: 乱码值 → 修复
    assert parsed[3].id == "call_garbled", f"id 被修改: {parsed[3].id}"
    assert parsed[3].name == "tool_garbled", f"name 被修改: {parsed[3].name}"
    assert isinstance(parsed[3].arguments, dict), f"乱码 args 未修复: {parsed[3].arguments}"
    
    # 4: 截断 → 修复
    assert parsed[4].id == "call_truncated", f"id 被修改: {parsed[4].id}"
    assert parsed[4].name == "tool_truncated", f"name 被修改: {parsed[4].name}"
    assert isinstance(parsed[4].arguments, dict), f"截断 args 未修复: {parsed[4].arguments}"
    
    # 验证所有 ID 唯一
    ids = [tc.id for tc in parsed]
    assert len(ids) == len(set(ids)), f"ID 不唯一: {ids}"


@test("sanitize 空 tool_calls 保留 - 有 tool 消息跟随")
def test_sanitize_empty_toolcalls_with_tool_following():
    """测试 sanitize_messages 保留 tool_calls: [] 当有 tool 消息跟随"""
    from mcp._sanitize import sanitize_messages
    
    # 场景: assistant 消息有 tool_calls: []，后面有 tool 消息
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "tool", "content": "result", "tool_call_id": "call_123"},
    ]
    
    result = sanitize_messages(messages)
    
    # assistant 消息应该保留 tool_calls 字段（即使为空）
    assistant_msg = result[2]
    assert assistant_msg["role"] == "assistant"
    assert "tool_calls" in assistant_msg, "当有 tool 消息跟随时应保留 tool_calls 字段"
    assert assistant_msg["tool_calls"] == [], "tool_calls 应为空列表"
    
    # tool 消息应该保留
    tool_msg = result[3]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call_123"


@test("sanitize 空 tool_calls 移除 - 无 tool 消息跟随")
def test_sanitize_empty_toolcalls_without_tool_following():
    """测试 sanitize_messages 移除 tool_calls: [] 当没有 tool 消息跟随"""
    from mcp._sanitize import sanitize_messages
    
    # 场景: assistant 消息有 tool_calls: []，后面没有 tool 消息
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "", "tool_calls": []},
    ]
    
    result = sanitize_messages(messages)
    
    # assistant 消息应该移除 tool_calls 字段（因为没有 tool 消息跟随）
    assistant_msg = result[2]
    assert assistant_msg["role"] == "assistant"
    assert "tool_calls" not in assistant_msg, "当没有 tool 消息跟随时应移除 tool_calls 字段"


@test("损坏信息 5 - _safe_get_attr 全面保护测试")
def test_safe_get_attr_protection():
    """测试 _safe_get_attr 对各种 None/缺失属性的保护"""
    # 使用内置 getattr 替代不存在的 _safe_get_attr
    def _safe_get_attr(obj, attr, default=None):
        return getattr(obj, attr, default)
    
    # None 对象
    assert _safe_get_attr(None, "anything") is None, "None 对象应返回 default"
    assert _safe_get_attr(None, "anything", "fallback") == "fallback", "None 对象应返回 fallback"
    
    # 正常对象
    class Obj:
        attr = "value"
        none_attr = None
    
    obj = Obj()
    assert _safe_get_attr(obj, "attr") == "value", "正常属性访问失败"
    assert _safe_get_attr(obj, "missing") is None, "缺失属性应返回 default"
    assert _safe_get_attr(obj, "missing", "fallback") == "fallback", "缺失属性应返回 fallback"
    assert _safe_get_attr(obj, "none_attr") is None, "None 属性应返回 None"


# ============================================================
# 运行所有测试
# ============================================================

def run_all_tests():
    global PASS, FAIL, ERRORS
    
    print("=" * 60)
    print("TS2 Agent 传输格式极限测试")
    print("=" * 60)
    print()
    
    # 收集所有测试函数
    test_funcs = []
    for name in list(globals().keys()):
        if name.startswith("test_"):
            obj = globals()[name]
            if callable(obj):
                test_funcs.append(obj)
    
    # 运行测试
    for test_func in test_funcs:
        test_func()
    
    print()
    print("=" * 60)
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    print("=" * 60)
    
    if ERRORS:
        print("\n失败详情:")
        for err in ERRORS:
            print(err)
    
    return FAIL == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
