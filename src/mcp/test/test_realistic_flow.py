#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TS2 Agent 真实场景端到端测试

模拟完整的 Agent 对话流程，包括：
1. 多轮工具调用循环（assistant → tool → assistant → tool → ...）
2. API 返回空 tool_call_id 的模拟
3. 跨轮次的消息链完整性验证
4. sanitize_messages 前后对比

运行方式：
  python TS2/mcp/test_realistic_flow.py
  python TS2/mcp/test_realistic_flow.py --debug   # 显示详细调试日志
"""

import json
import sys
import os
import logging

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置日志
logging.basicConfig(
    level=logging.DEBUG if '--debug' in sys.argv else logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

from mcp._sanitize import sanitize_messages
from mcp.llm import LLMResponse, ToolCall, _safe_tool_id, _safe_parse_args


def print_messages(label, messages):
    """格式化打印消息列表"""
    print(f"\n{'='*60}")
    print(f" {label}")
    print(f"{'='*60}")
    for i, m in enumerate(messages):
        role = m.get("role", "?")
        content = m.get("content", "")
        tc = m.get("tool_calls", "N/A")
        tcid = m.get("tool_call_id", "N/A")
        content_preview = content[:50] if content else "(empty)"
        print(f"  [{i}] {role:12s} content={content_preview!r}")
        if tc != "N/A" and tc:
            for j, t in enumerate(tc):
                tid = t.get("id", "?") if isinstance(t, dict) else "?"
                tname = t.get("function", {}).get("name", "?") if isinstance(t, dict) else "?"
                print(f"       tool_call[{j}]: id={tid!r} name={tname!r}")
        if tcid != "N/A":
            print(f"       tool_call_id={tcid!r}")


def validate_tool_call_chain(messages, label):
    """验证 tool 消息和 assistant tool_calls 的匹配关系"""
    errors = []
    for i, m in enumerate(messages):
        if m.get("role") == "tool":
            tcid = m.get("tool_call_id", "")
            found = False
            for j in range(i-1, -1, -1):
                prev = messages[j]
                if prev.get("role") == "assistant":
                    prev_tcs = prev.get("tool_calls", [])
                    if prev_tcs:
                        for ptc in prev_tcs:
                            if isinstance(ptc, dict) and ptc.get("id") == tcid:
                                found = True
                                break
                    if found:
                        break
            if not found:
                errors.append(f"Tool msg [{i}] tcid={tcid!r} has NO matching assistant with tool_calls!")
    
    if errors:
        print(f"\n  !! [{label}] {len(errors)} validation error(s):")
        for e in errors:
            print(f"     {e}")
    else:
        print(f"\n  OK [{label}] All tool messages have matching assistant tool_calls")
    
    return len(errors) == 0


# ============================================================
# 场景 1: 标准多轮工具调用（正常 ID）
# ============================================================

def scenario_1_normal_ids():
    """场景 1: 标准多轮工具调用，所有 ID 都正常"""
    print(f"\n{'#'*60}")
    print(f"# 场景 1: 标准多轮工具调用（正常 ID）")
    print(f"{'#'*60}")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the weather in Beijing and Shanghai?"},
    ]
    
    # === 第 1 轮: assistant 返回 2 个工具调用 ===
    tc1 = ToolCall(id="call_weather_bj", name="get_weather", arguments={"city": "Beijing"})
    tc2 = ToolCall(id="call_weather_sh", name="get_weather", arguments={"city": "Shanghai"})
    resp1 = LLMResponse(content="", tool_calls=[tc1, tc2])
    messages.append(resp1.message)
    
    # 工具结果
    messages.append({"role": "tool", "tool_call_id": "call_weather_bj", "content": "Sunny, 25°C"})
    messages.append({"role": "tool", "tool_call_id": "call_weather_sh", "content": "Rainy, 20°C"})
    
    # === 第 2 轮: assistant 再返回 1 个工具调用 ===
    tc3 = ToolCall(id="call_air_quality", name="get_air_quality", arguments={"city": "Beijing"})
    resp2 = LLMResponse(content="", tool_calls=[tc3])
    messages.append(resp2.message)
    
    # 工具结果
    messages.append({"role": "tool", "tool_call_id": "call_air_quality", "content": "AQI: 85"})
    
    # === 第 3 轮: assistant 最终回答 ===
    resp3 = LLMResponse(content="Beijing: Sunny 25°C, AQI 85. Shanghai: Rainy 20°C.")
    messages.append(resp3.message)
    
    print_messages("清洗前", messages)
    validate_tool_call_chain(messages, "清洗前")
    
    cleaned = sanitize_messages(messages)
    
    print_messages("清洗后", cleaned)
    validate_tool_call_chain(cleaned, "清洗后")
    
    # 验证
    assert len(cleaned) == 8, f"消息数量错误: {len(cleaned)} (期望 8)"
    assert cleaned[2]["tool_calls"][0]["id"] == "call_weather_bj", "第 1 个 tool_call id 被修改"
    assert cleaned[2]["tool_calls"][1]["id"] == "call_weather_sh", "第 2 个 tool_call id 被修改"
    assert cleaned[5]["tool_calls"][0]["id"] == "call_air_quality", "第 3 个 tool_call id 被修改"
    assert cleaned[3]["tool_call_id"] == "call_weather_bj", "tool_call_id 不匹配"
    assert cleaned[4]["tool_call_id"] == "call_weather_sh", "tool_call_id 不匹配"
    assert cleaned[6]["tool_call_id"] == "call_air_quality", "tool_call_id 不匹配"
    assert "tool_calls" not in cleaned[7], "最终回答不应有 tool_calls"
    
    print(f"\n  [PASS] 场景 1 通过")


# ============================================================
# 场景 2: API 返回空 tool_call_id（真实 bug 场景）
# ============================================================

def scenario_2_empty_ids():
    """场景 2: API 返回空 tool_call_id（真实 bug 场景）"""
    print(f"\n{'#'*60}")
    print(f"# 场景 2: API 返回空 tool_call_id（真实 bug 场景）")
    print(f"{'#'*60}")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Search for information about quantum computing."},
    ]
    
    # === 第 1 轮: assistant 返回 2 个工具调用，ID 为空（模拟 API bug） ===
    # 模拟 _process_stream 中 _safe_tool_id 未被调用的情况
    assistant_msg_1 = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "",  # 空 ID！
                "type": "function",
                "function": {"name": "search_web", "arguments": '{"q": "quantum computing basics"}'}
            },
            {
                "id": "",  # 空 ID！
                "type": "function",
                "function": {"name": "search_papers", "arguments": '{"q": "quantum computing 2024"}'}
            },
        ]
    }
    messages.append(assistant_msg_1)
    
    # 工具结果（tool_call_id 也为空，模拟 Agent.chat() 中的行为）
    messages.append({"role": "tool", "tool_call_id": "", "content": "Quantum computing uses qubits..."})
    messages.append({"role": "tool", "tool_call_id": "", "content": "Paper 1: ... Paper 2: ..."})
    
    # === 第 2 轮: assistant 再返回 1 个工具调用，ID 也为空 ===
    assistant_msg_2 = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "",  # 空 ID！
                "type": "function",
                "function": {"name": "summarize", "arguments": '{"topic": "quantum computing"}'}
            },
        ]
    }
    messages.append(assistant_msg_2)
    
    # 工具结果
    messages.append({"role": "tool", "tool_call_id": "", "content": "Summary: Quantum computing is..."})
    
    # === 第 3 轮: assistant 最终回答 ===
    messages.append({"role": "assistant", "content": "Here's what I found about quantum computing..."})
    
    print_messages("清洗前（空 ID）", messages)
    validate_tool_call_chain(messages, "清洗前")
    
    cleaned = sanitize_messages(messages)
    
    print_messages("清洗后（UUID 已生成）", cleaned)
    validate_tool_call_chain(cleaned, "清洗后")
    
    # 验证
    assert len(cleaned) == 8, f"消息数量错误: {len(cleaned)} (期望 8)"
    
    # 第 1 轮: 2 个空 ID → 2 个 UUID
    tc1_ids = [tc["id"] for tc in cleaned[2]["tool_calls"]]
    assert len(tc1_ids) == 2, f"第 1 轮 tool_calls 数量错误: {len(tc1_ids)}"
    for tid in tc1_ids:
        assert tid.startswith("call_"), f"空 ID 未生成 UUID: {tid!r}"
        assert len(tid) == 17, f"UUID 长度错误: {tid} ({len(tid)})"
    assert tc1_ids[0] != tc1_ids[1], f"两个 UUID 重复: {tc1_ids}"
    
    # 第 1 轮 tool 消息的 tool_call_id 应该匹配 assistant 的 tool_calls
    assert cleaned[3]["tool_call_id"] == tc1_ids[0], \
        f"tool[3] tool_call_id {cleaned[3]['tool_call_id']!r} 不匹配 assistant tc[0] id {tc1_ids[0]!r}"
    assert cleaned[4]["tool_call_id"] == tc1_ids[1], \
        f"tool[4] tool_call_id {cleaned[4]['tool_call_id']!r} 不匹配 assistant tc[1] id {tc1_ids[1]!r}"
    
    # 第 2 轮: 1 个空 ID → 1 个 UUID
    tc2_ids = [tc["id"] for tc in cleaned[5]["tool_calls"]]
    assert len(tc2_ids) == 1, f"第 2 轮 tool_calls 数量错误: {len(tc2_ids)}"
    assert tc2_ids[0].startswith("call_"), f"空 ID 未生成 UUID: {tc2_ids[0]!r}"
    
    # 第 2 轮 tool 消息的 tool_call_id 应该匹配 assistant 的 tool_calls
    assert cleaned[6]["tool_call_id"] == tc2_ids[0], \
        f"tool[6] tool_call_id {cleaned[6]['tool_call_id']!r} 不匹配 assistant tc[0] id {tc2_ids[0]!r}"
    
    # 所有 UUID 必须唯一
    all_ids = tc1_ids + tc2_ids
    assert len(all_ids) == len(set(all_ids)), f"UUID 不唯一: {all_ids}"
    
    # 最终回答不应有 tool_calls
    assert "tool_calls" not in cleaned[7], "最终回答不应有 tool_calls"
    
    print(f"\n  [PASS] 场景 2 通过")


# ============================================================
# 场景 3: 混合场景 - 部分 ID 正常，部分为空
# ============================================================

def scenario_3_mixed_ids():
    """场景 3: 混合场景 - 部分 ID 正常，部分为空"""
    print(f"\n{'#'*60}")
    print(f"# 场景 3: 混合场景 - 部分 ID 正常，部分为空")
    print(f"{'#'*60}")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Compare weather and news."},
    ]
    
    # assistant 返回 3 个工具调用：2 个空 ID + 1 个正常 ID
    assistant_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "",  # 空 ID
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Beijing"}'}
            },
            {
                "id": "call_news_fixed",  # 正常 ID
                "type": "function",
                "function": {"name": "get_news", "arguments": '{"topic": "tech"}'}
            },
            {
                "id": "",  # 空 ID
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Shanghai"}'}
            },
        ]
    }
    messages.append(assistant_msg)
    
    # 工具结果（tool_call_id 都为空）
    messages.append({"role": "tool", "tool_call_id": "", "content": "Sunny, 25°C"})
    messages.append({"role": "tool", "tool_call_id": "", "content": "Tech news: AI advances..."})
    messages.append({"role": "tool", "tool_call_id": "", "content": "Rainy, 20°C"})
    
    # 最终回答
    messages.append({"role": "assistant", "content": "Beijing is sunny, Shanghai is rainy, and tech news..."})
    
    print_messages("清洗前（混合 ID）", messages)
    validate_tool_call_chain(messages, "清洗前")
    
    cleaned = sanitize_messages(messages)
    
    print_messages("清洗后", cleaned)
    validate_tool_call_chain(cleaned, "清洗后")
    
    # 验证
    assert len(cleaned) == 7, f"消息数量错误: {len(cleaned)} (期望 7)"
    
    tc_ids = [tc["id"] for tc in cleaned[2]["tool_calls"]]
    assert len(tc_ids) == 3, f"tool_calls 数量错误: {len(tc_ids)}"
    
    # 第 1 个: 空 ID → UUID
    assert tc_ids[0].startswith("call_"), f"空 ID 未生成 UUID: {tc_ids[0]!r}"
    # 第 2 个: 正常 ID → 保持不变
    assert tc_ids[1] == "call_news_fixed", f"正常 ID 被修改: {tc_ids[1]!r}"
    # 第 3 个: 空 ID → UUID
    assert tc_ids[2].startswith("call_"), f"空 ID 未生成 UUID: {tc_ids[2]!r}"
    # 两个 UUID 必须不同
    assert tc_ids[0] != tc_ids[2], f"两个 UUID 重复: {tc_ids}"
    
    # tool 消息的 tool_call_id 应该按顺序匹配
    assert cleaned[3]["tool_call_id"] == tc_ids[0], f"tool[3] 不匹配 tc[0]"
    assert cleaned[4]["tool_call_id"] == tc_ids[1], f"tool[4] 不匹配 tc[1]"
    assert cleaned[5]["tool_call_id"] == tc_ids[2], f"tool[5] 不匹配 tc[2]"
    
    print(f"\n  [PASS] 场景 3 通过")


# ============================================================
# 场景 4: 跨轮次消息链 - 模拟 Agent.chat() 的完整循环
# ============================================================

def scenario_4_agent_loop():
    """场景 4: 模拟 Agent.chat() 的完整循环"""
    print(f"\n{'#'*60}")
    print(f"# 场景 4: 模拟 Agent.chat() 的完整循环")
    print(f"{'#'*60}")
    
    # 模拟 Agent.chat() 中的消息构建过程
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Research quantum computing and summarize."},
    ]
    
    # === 第 1 轮: LLM 返回工具调用 ===
    # 模拟 _process_stream 的输出（ToolCall 对象）
    tc_round1 = [
        ToolCall(id="call_q1", name="search_web", arguments={"q": "quantum computing overview"}),
        ToolCall(id="call_q2", name="search_web", arguments={"q": "quantum computing applications"}),
    ]
    resp1 = LLMResponse(content="", tool_calls=tc_round1)
    messages.append(resp1.message)
    
    # 执行工具，追加结果
    messages.append({"role": "tool", "tool_call_id": "call_q1", "content": "Quantum computing uses qubits..."})
    messages.append({"role": "tool", "tool_call_id": "call_q2", "content": "Applications: cryptography, drug discovery..."})
    
    # === 第 2 轮: LLM 再次返回工具调用（模拟 Agent 循环） ===
    tc_round2 = [
        ToolCall(id="call_q3", name="summarize", arguments={"text": "quantum computing overview and applications"}),
    ]
    resp2 = LLMResponse(content="", tool_calls=tc_round2)
    messages.append(resp2.message)
    
    # 执行工具
    messages.append({"role": "tool", "tool_call_id": "call_q3", "content": "Summary: Quantum computing is a revolutionary technology..."})
    
    # === 第 3 轮: LLM 返回最终回答 ===
    resp3 = LLMResponse(content="Quantum computing is a revolutionary technology that uses qubits...")
    messages.append(resp3.message)
    
    # === 第 4 轮: 用户追问 ===
    messages.append({"role": "user", "content": "What are the main challenges?"})
    
    # === 第 5 轮: LLM 返回工具调用（跨轮次） ===
    tc_round3 = [
        ToolCall(id="call_q4", name="search_web", arguments={"q": "quantum computing challenges"}),
    ]
    resp4 = LLMResponse(content="", tool_calls=tc_round3)
    messages.append(resp4.message)
    
    # 执行工具
    messages.append({"role": "tool", "tool_call_id": "call_q4", "content": "Challenges: decoherence, error correction, scalability..."})
    
    # === 第 6 轮: LLM 最终回答 ===
    resp5 = LLMResponse(content="The main challenges in quantum computing are decoherence, error correction, and scalability.")
    messages.append(resp5.message)
    
    print_messages("清洗前（完整 Agent 循环）", messages)
    validate_tool_call_chain(messages, "清洗前")
    
    cleaned = sanitize_messages(messages)
    
    print_messages("清洗后", cleaned)
    validate_tool_call_chain(cleaned, "清洗后")
    
    # 验证
    assert len(cleaned) == 12, f"消息数量错误: {len(cleaned)} (期望 12)"
    
    # 第 1 轮: 2 个工具调用
    assert cleaned[2]["tool_calls"][0]["id"] == "call_q1"
    assert cleaned[2]["tool_calls"][1]["id"] == "call_q2"
    assert cleaned[3]["tool_call_id"] == "call_q1"
    assert cleaned[4]["tool_call_id"] == "call_q2"
    
    # 第 2 轮: 1 个工具调用
    assert cleaned[5]["tool_calls"][0]["id"] == "call_q3"
    assert cleaned[6]["tool_call_id"] == "call_q3"
    
    # 第 3 轮: 最终回答，无 tool_calls
    assert "tool_calls" not in cleaned[7]
    
    # 第 4 轮: 用户追问
    assert cleaned[8]["role"] == "user"
    
    # 第 5 轮: 1 个工具调用
    assert cleaned[9]["tool_calls"][0]["id"] == "call_q4"
    assert cleaned[10]["tool_call_id"] == "call_q4"
    
    # 第 6 轮: 最终回答
    assert "tool_calls" not in cleaned[11]
    
    print(f"\n  [PASS] 场景 4 通过")


# ============================================================
# 场景 5: 模拟真实 API 返回的流式 chunk 构建过程
# ============================================================

def scenario_5_streaming_chunks():
    """场景 5: 模拟真实 API 返回的流式 chunk 构建过程"""
    print(f"\n{'#'*60}")
    print(f"# 场景 5: 模拟真实 API 返回的流式 chunk 构建过程")
    print(f"{'#'*60}")
    
    # 模拟 OpenAIProvider._process_stream() 中的 tc_map 构建
    # 模拟流式 chunk 逐步构建 tool_call
    
    tc_map = {}
    
    # Chunk 1: 开始第 1 个 tool_call（只有 index，没有 id）
    tc_map[0] = {"id": "", "name": "", "args": ""}
    
    # Chunk 2: 第 1 个 tool_call 的 id 来了（但可能是空的！）
    tc_map[0]["id"] = ""  # 模拟 API 返回空 id
    
    # Chunk 3: 第 1 个 tool_call 的 name
    tc_map[0]["name"] = "get_weather"
    
    # Chunk 4: 第 1 个 tool_call 的 arguments 开始
    tc_map[0]["args"] = '{"city": "'
    
    # Chunk 5: 第 1 个 tool_call 的 arguments 继续
    tc_map[0]["args"] += 'Beijing"}'
    
    # Chunk 6: 开始第 2 个 tool_call
    tc_map[1] = {"id": "", "name": "", "args": ""}
    
    # Chunk 7: 第 2 个 tool_call 的 id（也是空的）
    tc_map[1]["id"] = ""
    
    # Chunk 8: 第 2 个 tool_call 的 name
    tc_map[1]["name"] = "get_news"
    
    # Chunk 9: 第 2 个 tool_call 的 arguments
    tc_map[1]["args"] = '{"topic": "tech"}'
    
    # 模拟 _process_stream 中的解析逻辑
    tool_calls = []
    for idx in sorted(tc_map):
        raw = tc_map[idx]
        args = _safe_parse_args(raw.get("args", ""))
        tool_id = _safe_tool_id(raw.get("id", ""))
        tool_calls.append(ToolCall(id=tool_id, name=raw.get("name", ""), arguments=args))
    
    print(f"\n  流式解析结果:")
    for i, tc in enumerate(tool_calls):
        print(f"    tc[{i}]: id={tc.id!r} name={tc.name!r} args={tc.arguments}")
    
    # 验证 _safe_tool_id 为空 ID 生成了 UUID
    assert tool_calls[0].id.startswith("call_"), f"空 ID 未生成 UUID: {tool_calls[0].id!r}"
    assert tool_calls[1].id.startswith("call_"), f"空 ID 未生成 UUID: {tool_calls[1].id!r}"
    assert tool_calls[0].id != tool_calls[1].id, f"两个 UUID 重复"
    
    # 构建完整消息链
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Get weather and news."},
    ]
    
    # assistant 消息（使用流式解析后的 ToolCall）
    resp = LLMResponse(content="", tool_calls=tool_calls)
    messages.append(resp.message)
    
    # 工具结果（tool_call_id 使用 ToolCall 的 id）
    messages.append({"role": "tool", "tool_call_id": tool_calls[0].id, "content": "Sunny, 25°C"})
    messages.append({"role": "tool", "tool_call_id": tool_calls[1].id, "content": "Tech news: AI..."})
    
    # 最终回答
    messages.append({"role": "assistant", "content": "Weather is sunny, news is about AI."})
    
    print_messages("清洗前（流式构建）", messages)
    validate_tool_call_chain(messages, "清洗前")
    
    cleaned = sanitize_messages(messages)
    
    print_messages("清洗后", cleaned)
    validate_tool_call_chain(cleaned, "清洗后")
    
    # 验证
    assert len(cleaned) == 6, f"消息数量错误: {len(cleaned)} (期望 6)"
    assert cleaned[2]["tool_calls"][0]["id"] == tool_calls[0].id, "tool_call id 被修改"
    assert cleaned[2]["tool_calls"][1]["id"] == tool_calls[1].id, "tool_call id 被修改"
    assert cleaned[3]["tool_call_id"] == tool_calls[0].id, "tool_call_id 不匹配"
    assert cleaned[4]["tool_call_id"] == tool_calls[1].id, "tool_call_id 不匹配"
    
    print(f"\n  [PASS] 场景 5 通过")


# ============================================================
# 场景 6: 极端情况 - 空 tool_calls 列表 + 空 tool_call_id
# ============================================================

def scenario_6_edge_cases():
    """场景 6: 极端情况 - 空 tool_calls 列表 + 空 tool_call_id"""
    print(f"\n{'#'*60}")
    print(f"# 场景 6: 极端情况 - 空 tool_calls 列表 + 空 tool_call_id")
    print(f"{'#'*60}")
    
    # 场景 6a: assistant 有 tool_calls: []，后面有 tool 消息
    print(f"\n  --- 场景 6a: tool_calls: [] + 有 tool 消息跟随 ---")
    msgs_a = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "tool", "content": "result", "tool_call_id": "call_123"},
    ]
    cleaned_a = sanitize_messages(msgs_a)
    assert "tool_calls" in cleaned_a[2], "有 tool 消息跟随时应保留 tool_calls"
    assert cleaned_a[2]["tool_calls"] == [], "tool_calls 应为空列表"
    print(f"    [OK] tool_calls: [] 被保留")
    
    # 场景 6b: assistant 有 tool_calls: []，后面没有 tool 消息
    print(f"\n  --- 场景 6b: tool_calls: [] + 无 tool 消息跟随 ---")
    msgs_b = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "", "tool_calls": []},
    ]
    cleaned_b = sanitize_messages(msgs_b)
    assert "tool_calls" not in cleaned_b[2], "无 tool 消息跟随时应移除 tool_calls"
    print(f"    [OK] tool_calls: [] 被移除")
    
    # 场景 6c: 多个 tool 消息，tool_call_id 都为空，前面有 assistant 带空 tool_call id
    print(f"\n  --- 场景 6c: 多个空 tool_call_id + 空 assistant tool_call id ---")
    msgs_c = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "", "type": "function", "function": {"name": "tool_a", "arguments": "{}"}},
            {"id": "", "type": "function", "function": {"name": "tool_b", "arguments": "{}"}},
        ]},
        {"role": "tool", "content": "result_a", "tool_call_id": ""},
        {"role": "tool", "content": "result_b", "tool_call_id": ""},
    ]
    cleaned_c = sanitize_messages(msgs_c)
    tc_ids = [tc["id"] for tc in cleaned_c[0]["tool_calls"]]
    assert len(tc_ids) == 2, f"tool_calls 数量错误: {len(tc_ids)}"
    assert tc_ids[0].startswith("call_"), f"空 ID 未生成 UUID: {tc_ids[0]!r}"
    assert tc_ids[1].startswith("call_"), f"空 ID 未生成 UUID: {tc_ids[1]!r}"
    assert tc_ids[0] != tc_ids[1], f"UUID 重复: {tc_ids}"
    assert cleaned_c[1]["tool_call_id"] == tc_ids[0], f"tool[1] 不匹配 tc[0]"
    assert cleaned_c[2]["tool_call_id"] == tc_ids[1], f"tool[2] 不匹配 tc[1]"
    print(f"    [OK] 空 tool_call_id 正确匹配 UUID")
    
    # 场景 6d: tool 消息在 assistant 之前（异常顺序）
    print(f"\n  --- 场景 6d: tool 消息在 assistant 之前（异常顺序）---")
    msgs_d = [
        {"role": "tool", "content": "result", "tool_call_id": ""},
        {"role": "assistant", "content": "response"},
    ]
    cleaned_d = sanitize_messages(msgs_d)
    # tool 消息没有前面的 assistant 可匹配，应该生成 UUID fallback
    assert cleaned_d[0]["tool_call_id"].startswith("call_"), \
        f"无 assistant 匹配时应生成 UUID: {cleaned_d[0]['tool_call_id']!r}"
    print(f"    [OK] 无 assistant 匹配时生成 UUID fallback")
    
    print(f"\n  [PASS] 场景 6 通过")


# ============================================================
# 主函数
# ============================================================

def main():
    print(f"{'='*60}")
    print(f" TS2 Agent 真实场景端到端测试")
    print(f"{'='*60}")
    
    scenarios = [
        ("场景 1: 标准多轮工具调用（正常 ID）", scenario_1_normal_ids),
        ("场景 2: API 返回空 tool_call_id（真实 bug 场景）", scenario_2_empty_ids),
        ("场景 3: 混合场景 - 部分 ID 正常，部分为空", scenario_3_mixed_ids),
        ("场景 4: 模拟 Agent.chat() 的完整循环", scenario_4_agent_loop),
        ("场景 5: 模拟真实 API 返回的流式 chunk 构建过程", scenario_5_streaming_chunks),
        ("场景 6: 极端情况 - 空 tool_calls 列表 + 空 tool_call_id", scenario_6_edge_cases),
    ]
    
    passed = 0
    failed = 0
    
    for name, func in scenarios:
        try:
            func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n  !! {name}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print(f" 结果: {passed} 通过, {failed} 失败")
    print(f"{'='*60}")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
