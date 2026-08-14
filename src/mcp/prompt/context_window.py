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


def _group_rounds(non_system: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[List[Dict[str, Any]]]]:
    """把非 system 消息按「轮」分组：每轮从 user 消息开始，到下一个 user 之前结束。

    轮 = 完整对话回合（user → assistant(可带 tool_calls) → tool(可选) → assistant 回复）。
    以轮为单位挑选保留，可从根本上保证压缩输出满足 OpenAI/Anthropic 消息顺序约束
    （user/assistant 交替、tool 紧跟 assistant(tool_calls)、非 system 首条为 user）。

    返回 (leading_orphans, rounds)：
    - leading_orphans：开头无 user 前缀的孤立消息（异常截断历史，应并入摘要）
    - rounds：按 user 边界切分的轮列表
    """
    leading: List[Dict[str, Any]] = []
    rounds: List[List[Dict[str, Any]]] = []
    cur: Optional[List[Dict[str, Any]]] = None
    for msg in non_system:
        if msg.get("role") == "user":
            if cur is not None:
                rounds.append(cur)
            cur = [msg]
        else:
            if cur is None:
                leading.append(msg)  # 无 user 前缀的孤儿（异常历史）
            else:
                cur.append(msg)
    if cur is not None:
        rounds.append(cur)
    return leading, rounds


def _ensure_valid_sequence(compacted: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """收尾结构保证（自包含，不依赖 agent.sanitize_messages 避免循环 import）。

    按轮分组已保证常规场景合法；此函数兜底异常历史（如原始消息即 user→user）：
    1. 相邻 user 消息合并（内容不丢，用换行连接）
    2. 非 system 首条若是 assistant/tool（异常孤儿）→ 并入最近一条 system 摘要
    tool 配对由调用方 sanitize_messages 兜底（agent 对话循环每轮已调用）。
    """
    result: List[Dict[str, Any]] = []
    for msg in compacted:
        if msg.get("role") == "user" and result and result[-1].get("role") == "user":
            prev = result[-1]
            prev_content = str(prev.get("content", ""))
            cur_content = str(msg.get("content", ""))
            prev["content"] = f"{prev_content}\n\n{cur_content}" if prev_content else cur_content
            continue
        result.append(msg)

    first_idx = next((i for i, m in enumerate(result) if m.get("role") != "system"), None)
    if first_idx is not None and result[first_idx].get("role") in ("assistant", "tool"):
        orphan = result.pop(first_idx)
        orphan_content = str(orphan.get("content", ""))
        if orphan_content:
            for m in reversed(result):
                if m.get("role") == "system":
                    m["content"] = f"{m.get('content', '')}\n\n[被压缩的孤立消息] {orphan_content[:2000]}"
                    break
    return result


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

    # ── 按「轮」分组（轮 = user 起始到下一个 user 前的完整回合）──
    # 以轮为单位挑选保留，保证输出满足 API 消息顺序约束
    # （user/assistant 交替、tool 紧跟 assistant(tool_calls)、非 system 首条为 user）。
    leading_orphans, rounds = _group_rounds(non_system)

    # 第一优先级：关键词命中的轮（倒序扫描，限制保留消息总数防压缩失效）
    keyword_rounds: List[List[Dict[str, Any]]] = []
    kept_msgs = 0
    for rnd in reversed(rounds):
        if kept_msgs >= MAX_PRESERVED_KEYWORDS:
            break
        if any(
            has_preserved_keywords(str(m.get("content", ""))) or
            has_preserved_keywords(str(m.get("tool_result", "")))
            for m in rnd
        ):
            keyword_rounds.append(rnd)
            kept_msgs += len(rnd)
    keyword_rounds.reverse()  # 恢复原始顺序

    # 第二优先级：最近消息所属的轮（保持对话连续性）
    recent_rounds: List[List[Dict[str, Any]]] = []
    recent_msgs = 0
    for rnd in reversed(rounds):
        if recent_msgs >= 10:
            break
        recent_rounds.append(rnd)
        recent_msgs += len(rnd)
    recent_rounds.reverse()

    # 被保护的轮（去重，按原顺序）
    preserved_rounds: List[List[Dict[str, Any]]] = []
    seen_round_ids = set()
    for rnd in keyword_rounds + recent_rounds:
        rnd_id = id(rnd)
        if rnd_id not in seen_round_ids:
            preserved_rounds.append(rnd)
            seen_round_ids.add(rnd_id)

    # 进入摘要的消息：未保留轮 + 前导孤儿（无 user 前缀的异常历史）
    preserved_msg_ids = {id(m) for rnd in preserved_rounds for m in rnd}
    for_summary = [m for m in non_system if id(m) not in preserved_msg_ids]
    summary = generate_summary(for_summary) if for_summary else "（无重要对话内容）"

    compacted = list(system_msgs)

    compacted.append({
        "role": "system",
        "content": f"[对话历史摘要 - 保持消息格式完整性]\n{summary}"
    })

    # 按原顺序展开被保护的轮
    for rnd in preserved_rounds:
        compacted.extend(rnd)

    # 收尾结构保证（兜底异常历史：相邻 user / 孤立 assistant 开头）
    compacted = _ensure_valid_sequence(compacted)

    _emit_event("context.compacted", {
        "model_id": model_id,
        "before": len(messages),
        "after": len(compacted),
        "summarized": len(for_summary),
    })
    return compacted, True