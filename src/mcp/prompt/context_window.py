#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上下文窗口感知 — 参考 OpenClaw 的 context.ts 设计
模型特定的上下文窗口大小和消息压缩策略
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

from ..event_stream import emit as _emit_event

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
    "deepseek-chat": 1_000_000,
    "deepseek-reasoner": 1_000_000,
    "deepseek-v4-pro": 1_000_000,
    "deepseek-v4-flash": 1_000_000,
    "deepseek-v4": 1_000_000,
    "deepseek-v3": 1_000_000,
    "deepseek-r1": 1_000_000,
    "qwen-max": 32_768,
    "qwen-plus": 32_768,
    "qwen-turbo": 8_192,
}

DEFAULT_CONTEXT_WINDOW = 128_000
COMPACT_THRESHOLD_RATIO = 0.85

# 关键词保护列表（用于压缩时保留关键消息）
# 注意：必须只保留「语义强」的词。通用技术词（file/path/id/true/false/on/off/
# result/output/error 等）几乎出现在所有工具输出与代码内容里，命中率 100%，
# 会导致压缩时所有消息都被"保护"而形同虚设（历史上压缩从未生效的直接原因）。
PRESERVE_KEYWORDS_CONTEXT = [
    # 用户显式强调类
    "关键", "重要", "核心", "核心概念", "关键信息", "重点",
    "记住", "别忘了", "务必", "切记",
    "必须", "应该", "建议", "禁止", "注意", "警告", "强调",
    # 领域概念类
    "定义", "定理", "公式", "定律", "法则", "原理", "公理", "推论", "假设",
    # 决策/结论/修复类
    "摘要", "总结", "结论", "最终答案", "决定", "方案",
    "bug", "修复", "已修复", "问题定位", "根因", "失败原因",
    "important", "critical", "essential", "vital", "must", "required",
    "definition", "theorem", "formula", "law", "principle", "axiom",
    "summary", "conclusion", "decision", "root cause", "bug fix",
    "warning", "caution", "remember",
]

# 关键词保护的最大消息条数（超过后仅保留最近的，防止保护范围无限扩大导致压缩失效）
MAX_PRESERVED_KEYWORDS = 30


def has_preserved_keywords(content: str) -> bool:
    """检查内容是否包含需要保留的关键词"""
    if not content:
        return False
    content_lower = content.lower()
    for keyword in PRESERVE_KEYWORDS_CONTEXT:
        if keyword.lower() in content_lower:
            return True
    return False


def resolve_context_tokens(model_id: str, context_window_override: int = 0) -> int:
    """解析模型上下文窗口大小。
    
    优先级:
    1. context_window_override (来自 ProviderConfig)
    2. MODEL_CONTEXT_WINDOWS 硬编码表
    3. DEFAULT_CONTEXT_WINDOW
    """
    if context_window_override > 0:
        return context_window_override
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
        role = msg.get("role", "")
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
        # tool_calls 结构开销
        tool_calls = msg.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            for tc in tool_calls:
                tc_args = tc.get("arguments", "") if isinstance(tc, dict) else ""
                if isinstance(tc_args, dict):
                    import json
                    tc_args = json.dumps(tc_args)
                total += len(str(tc.get("name", ""))) + len(str(tc_args)) + 50
        # tool_call_id 开销
        if role == "tool" and msg.get("tool_call_id"):
            total += 20
    return total


def should_compact(messages: List[Dict[str, Any]],
                   model_id: str,
                   threshold_ratio: float = COMPACT_THRESHOLD_RATIO,
                   context_window_override: int = 0) -> bool:
    context_window = resolve_context_tokens(model_id, context_window_override)
    estimated = estimate_messages_tokens(messages)
    return estimated >= context_window * threshold_ratio


def generate_summary(messages: List[Dict[str, Any]],
                     max_summary_tokens: int = 2000) -> str:
    """生成更成熟的对话摘要，保留关键决策和上下文衔接"""
    user_messages = []
    assistant_decisions = []
    tool_calls = []
    tool_results_summary = []
    key_facts = []

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))

        if role == "user":
            # 保留用户的关键意图，不只是截断
            user_messages.append(content[:300] if len(content) > 300 else content)
        elif role == "assistant":
            # 提取助手的关键决策/结论
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    # 兼容两种 tool_calls 结构：
                    #   OpenAI 格式:  {"function": {"name": "xxx", ...}}
                    #   Anthropic 格式: {"name": "xxx", ...}
                    # 取不到 name 时回退到整个 tc 的字符串形式，避免显示 unknown
                    if isinstance(tc, dict):
                        tc_name = tc.get("name") or (tc.get("function") or {}).get("name") or str(tc)
                    else:
                        tc_name = str(tc)
                    tool_calls.append(tc_name)
            elif content:
                # 提取结论性语句（通常在末尾）
                lines = content.strip().split('\n')
                conclusion = lines[-1] if lines else content[:200]
                if len(conclusion) > 200:
                    conclusion = conclusion[:200]
                assistant_decisions.append(conclusion)
        elif role == "tool":
            # 工具结果摘要
            result_preview = content[:150] if len(content) > 150 else content
            tool_name = msg.get("name") or msg.get("tool_name") or "unknown"
            tool_results_summary.append(f"{tool_name}: {result_preview}")

    summary_parts = [
        f"=== 对话历史摘要（{len(messages)} 条消息）===",
        "",
        "## 用户意图",
    ]

    # 用户意图（最近5条优先）
    recent_intents = user_messages[-5:] if len(user_messages) > 5 else user_messages
    for i, intent in enumerate(recent_intents, 1):
        summary_parts.append(f"  {i}. {intent}")

    if tool_calls:
        unique_tools = list(dict.fromkeys(tool_calls))  # 保序去重
        summary_parts.append(f"\n## 工具调用（{len(tool_calls)} 次）")
        summary_parts.append(f"  使用: {', '.join(unique_tools[:15])}")

    # 关键结论（最近3条）
    if assistant_decisions:
        recent_decisions = assistant_decisions[-3:]
        summary_parts.append(f"\n## 关键结论")
        for d in recent_decisions:
            summary_parts.append(f"  - {d}")

    # 工具结果摘要（最近3条）
    if tool_results_summary:
        recent_results = tool_results_summary[-3:]
        summary_parts.append(f"\n## 工具结果")
        for r in recent_results:
            summary_parts.append(f"  - {r}")

    summary = "\n".join(summary_parts)
    return summary[:max_summary_tokens]


def auto_compact(
    messages: List[Dict[str, Any]],
    model_id: str,
    context_window_override: int = 0,
    force: bool = False,
) -> Tuple[List[Dict[str, Any]], bool]:
    if not force and not should_compact(messages, model_id, context_window_override=context_window_override):
        return messages, False

    logger.info(f"消息量接近上限，执行自动压缩 (模型: {model_id})")

    # 分离系统消息和非系统消息
    system_msgs = [msg for msg in messages if msg.get("role") == "system"]
    non_system = [msg for msg in messages if msg.get("role") != "system"]
    
    if len(non_system) <= 10:
        return messages, False

    # 第一优先级：关键词保护的消息（限最近 MAX_PRESERVED_KEYWORDS 条，
    # 防止宽泛命中导致所有消息都被保护、压缩失效）
    keyword_preserved = []
    for msg in reversed(non_system):
        content = str(msg.get("content", ""))
        tool_result = str(msg.get("tool_result", ""))
        if has_preserved_keywords(content) or has_preserved_keywords(tool_result):
            keyword_preserved.append(msg)
            if len(keyword_preserved) >= MAX_PRESERVED_KEYWORDS:
                break
    keyword_preserved.reverse()  # 恢复原始顺序

    # 第二优先级：最近消息
    recent = non_system[-10:]

    # 被保护的消息ID集合
    preserved_ids = set(id(msg) for msg in keyword_preserved + recent)

    # 确保tool_call和tool_result成对保留
    tool_call_ids_in_preserved = set()
    for msg in non_system:
        if id(msg) in preserved_ids:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_dict = tc if isinstance(tc, dict) else {}
                    tc_id = tc_dict.get("id")
                    if tc_id:
                        tool_call_ids_in_preserved.add(tc_id)
            if msg.get("role") == "tool" and msg.get("tool_call_id"):
                tool_call_ids_in_preserved.add(msg["tool_call_id"])

    for msg in non_system:
        if id(msg) not in preserved_ids:
            if msg.get("role") == "tool" and msg.get("tool_call_id") in tool_call_ids_in_preserved:
                preserved_ids.add(id(msg))
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_dict = tc if isinstance(tc, dict) else {}
                    if tc_dict.get("id") in tool_call_ids_in_preserved:
                        preserved_ids.add(id(msg))
                        break

    # 进入摘要的消息
    for_summary = [msg for msg in non_system if id(msg) not in preserved_ids]
    summary = generate_summary(for_summary) if for_summary else "（无重要对话内容）"

    compacted = list(system_msgs)
    
    compacted.append({
        "role": "system",
        "content": f"[对话历史摘要 - 保持消息格式完整性]\n{summary}"
    })

    # 添加关键词保护的消息（去重，按原顺序）
    seen_ids = set()
    for msg in keyword_preserved:
        if id(msg) not in seen_ids:
            compacted.append(msg)
            seen_ids.add(id(msg))

    # 添加最近消息
    for msg in recent:
        if id(msg) not in seen_ids:
            compacted.append(msg)
            seen_ids.add(id(msg))

    _emit_event("context.compacted", {
        "model_id": model_id,
        "before": len(messages),
        "after": len(compacted),
        "summarized": len(for_summary),
    })
    return compacted, True