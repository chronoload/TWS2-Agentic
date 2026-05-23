#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上下文窗口感知 — 参考 OpenClaw 的 context.ts 设计
模型特定的上下文窗口大小和消息压缩策略
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_384,
    "claude-4-sonnet": 200_000,
    "claude-4-opus": 200_000,
    "claude-3.5-sonnet": 200_000,
    "claude-3.5-haiku": 200_000,
    "deepseek-v3": 128_000,
    "deepseek-r1": 128_000,
    "qwen-max": 32_768,
    "qwen-plus": 32_768,
    "qwen-turbo": 8_192,
}

DEFAULT_CONTEXT_WINDOW = 128_000
COMPACT_THRESHOLD_RATIO = 0.85


def resolve_context_tokens(model_id: str) -> int:
    model_lower = model_id.lower()
    for key, tokens in MODEL_CONTEXT_WINDOWS.items():
        if model_lower.startswith(key):
            return tokens
    return DEFAULT_CONTEXT_WINDOW


def estimate_message_tokens(content: str) -> int:
    if not content:
        return 0
    return max(1, len(content) // 4)


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_message_tokens(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    total += estimate_message_tokens(item["text"])
        reasoning = msg.get("reasoning_content", "")
        if reasoning:
            total += estimate_message_tokens(reasoning)
    return total


def should_compact(messages: List[Dict[str, Any]],
                   model_id: str,
                   threshold_ratio: float = COMPACT_THRESHOLD_RATIO) -> bool:
    context_window = resolve_context_tokens(model_id)
    estimated = estimate_messages_tokens(messages)
    return estimated >= context_window * threshold_ratio


def compact_messages(
    messages: List[Dict[str, Any]],
    model_id: str,
    keep_system: bool = True,
    keep_last: int = 6,
) -> List[Dict[str, Any]]:
    if not should_compact(messages, model_id):
        return messages

    result = []

    if keep_system and messages and messages[0].get("role") == "system":
        result.append(messages[0])
        messages = messages[1:]

    summary_index = -1
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and "摘要" in str(msg.get("content", "")):
            summary_index = i

    if summary_index > 0:
        summary = messages[summary_index]
        user_messages = [m for m in messages if m.get("role") == "user"]
        tool_messages = [m for m in messages if m.get("role") == "tool"]

        result.append(summary)

        recent_start = max(0, len(messages) - keep_last)
        for msg in messages[recent_start:]:
            if msg.get("role") != "system":
                result.append(msg)
    else:
        recent_start = max(0, len(messages) - keep_last)
        result.extend(messages[recent_start:])

    if result and result[0].get("role") != "system" and messages:
        sys_msg = next((m for m in messages if m.get("role") == "system"), None)
        if sys_msg:
            result.insert(0, sys_msg)

    return result


def generate_summary(messages: List[Dict[str, Any]],
                     max_summary_tokens: int = 2000) -> str:
    user_messages = []
    tool_calls = []
    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        if role == "user":
            user_messages.append(content[:200])
        elif role == "assistant":
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tool_calls.append(tc.get("name", "unknown"))

    summary_parts = [
        f"对话摘要（共 {len(messages)} 条消息）：",
        f"- 用户提出了 {len(user_messages)} 个问题",
    ]
    if tool_calls:
        unique_tools = list(set(tool_calls))
        summary_parts.append(f"- 调用了以下工具：{', '.join(unique_tools[:10])}")

    summary = "\n".join(summary_parts)
    return summary[:max_summary_tokens]


def auto_compact(
    messages: List[Dict[str, Any]],
    model_id: str,
) -> Tuple[List[Dict[str, Any]], bool]:
    if not should_compact(messages, model_id):
        return messages, False

    logger.info(f"消息量接近上限，执行自动压缩 (模型: {model_id})")

    summary = generate_summary(messages)

    compacted = [messages[0]] if messages and messages[0].get("role") == "system" else []
    compacted.append({
        "role": "assistant",
        "content": f"[系统自动摘要]\n{summary}"
    })

    for msg in messages[-6:]:
        if msg.get("role") != "system":
            compacted.append(msg)

    return compacted, True