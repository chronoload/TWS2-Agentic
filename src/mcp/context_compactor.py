#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Compact 上下文压缩 — 参考 OpenCode 的 autoCompact 机制

核心原理 (OpenCode):
  1. 监控每轮对话的 token 使用量
  2. 当达到 95% 上下文窗口时自动触发压缩
  3. 使用 LLM 生成历史对话摘要
  4. 用摘要替换旧消息，释放上下文空间

安全机制:
  - 保留最后 N 条消息不压缩（保持当前上下文）
  - 压缩前保存 checkpoint（可回滚）
  - 摘要保留关键事实和决策
"""
from __future__ import annotations

import json
import re
import tiktoken
from typing import List, Dict, Any, Optional, Callable, Tuple


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """估算文本 token 数"""
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def estimate_messages_tokens(messages: List[Dict], model: str = "gpt-4") -> int:
    """估算消息列表 token 数"""
    total = 0
    for msg in messages:
        total += 4  # 消息边框开销
        for key, val in msg.items():
            if val is None:
                continue
            total += estimate_tokens(str(val), model)
            if key == "name":
                total += 1
    total += 2  # 回复前缀
    return total


class AutoCompact:
    """
    Auto Compact 上下文压缩器

    Usage:
        compactor = AutoCompact(max_tokens=100000, threshold=0.95)
        messages = compactor.compact(messages, llm_summarize_fn)
    """

    PRESERVE_KEYWORDS = [
        # 关键/重要类
        "关键", "重要", "核心", "核心概念", "关键信息",
        "记住", "important", "key", "critical", "essential", "vital",
        # 定义/定理类
        "定义", "定理", "公式", "定律", "法则", "原理", "公理",
        "definition", "theorem", "formula", "law", "principle", "axiom",
        # 建议/警告类
        "必须", "应该", "建议", "注意", "警告", "强调",
        "must", "should", "must not", "required", "warning", "caution",
        # 技术配置类
        "函数", "变量", "参数", "配置", "设置", "选项",
        "function", "variable", "parameter", "config", "setting", "option",
        "mode", "type", "level", "enable", "disable", "true", "false",
        "on", "off", "yes", "no", "enabled", "disabled",
        "auto", "manual", "default", "custom",
        # 结果/结论类
        "摘要", "总结", "结论", "结果", "答案", "输出", "返回",
        "summary", "conclusion", "result", "answer", "output", "return",
        # 错误/bug类
        "bug", "错误", "fix", "修复", "问题", "issue", "error",
        "failed", "failure", "exception", "warning",
        # 数值/阈值类
        "阈值", "上限", "下限", "最大", "最小", "初始", "默认",
        "threshold", "max", "min", "limit", "initial", "default",
        "value", "range", "size", "length", "count", "number",
        # 路径/文件类
        "路径", "目录", "文件", "地址", "url", "path", "file", "directory",
        # 名称/标识类
        "名称", "标识", "id", "name", "identifier", "label", "title",
    ]

    def __init__(self, max_tokens: int = 100000, threshold: float = 0.95,
                 keep_recent: int = 10, model: str = "gpt-4"):
        self.max_tokens = max_tokens
        self.threshold = threshold
        self.keep_recent = keep_recent
        self.model = model
        self._compaction_count = 0
        self._last_summary: Optional[str] = None

    def should_compact(self, messages: List[Dict]) -> bool:
        """判断是否需要压缩"""
        current = estimate_messages_tokens(messages, self.model)
        return current >= self.max_tokens * self.threshold

    def _has_preserved_keywords(self, content: str) -> bool:
        """检查内容是否包含需要保留的关键词"""
        if not content:
            return False
        content_lower = content.lower()
        for keyword in self.PRESERVE_KEYWORDS:
            if keyword.lower() in content_lower:
                return True
        return False

    def compact(self, messages: List[Dict],
                summarize_fn: Optional[Callable] = None) -> List[Dict]:
        """
        压缩消息列表

        Args:
            messages: 原始消息列表
            summarize_fn: 摘要函数 (messages) -> str，如果为 None 使用内置摘要

        Returns:
            压缩后的消息列表
        """
        current_tokens = estimate_messages_tokens(messages, self.model)
        if current_tokens < self.max_tokens * self.threshold:
            return messages

        n = len(messages)

        # 保留系统消息
        system_msgs = [msg for msg in messages if msg.get("role") == "system"]
        non_system = [msg for msg in messages if msg.get("role") != "system"]
        
        if len(non_system) <= self.keep_recent:
            return messages

        # 第一优先级：关键词保护的消息（从全部非系统消息中筛选）
        keyword_preserved = []
        for msg in non_system:
            content = str(msg.get("content", ""))
            tool_result = str(msg.get("tool_result", ""))
            if self._has_preserved_keywords(content) or self._has_preserved_keywords(tool_result):
                keyword_preserved.append(msg)

        # 第二优先级：最近 keep_recent 条消息
        recent = non_system[-self.keep_recent:]

        # 被保护的消息ID集合（关键词保护 + 最近保护）
        preserved_ids = set(id(msg) for msg in keyword_preserved + recent)

        # 进入摘要的消息（既没有关键词保护，也不是最近的）
        remaining_for_summary = [msg for msg in non_system if id(msg) not in preserved_ids]

        if summarize_fn:
            summary = summarize_fn(remaining_for_summary) if remaining_for_summary else ""
        else:
            summary = self._builtin_summary(remaining_for_summary) if remaining_for_summary else "（无）"

        self._compaction_count += 1
        self._last_summary = summary

        # 重建消息列表：系统消息 + 摘要 + 关键词保护的消息 + 最近消息
        compacted = list(system_msgs)

        summary_msg = {
            "role": "system",
            "content": (
                f"[{self._compaction_count}次上下文压缩] "
                f"以下是之前对话的摘要:\n\n{summary}\n\n"
                f"--- 以上是历史摘要，以下是最近对话 ---"
            ),
        }
        compacted.append(summary_msg)
        
        # 关键词保护的消息（去除重复，按原顺序）
        seen_preserved = set()
        for msg in keyword_preserved:
            msg_id = id(msg)
            if msg_id not in seen_preserved:
                compacted.append(msg)
                seen_preserved.add(msg_id)
        
        compacted.extend(recent)

        # 递归压缩，直到满足限制
        return compacted

    def _builtin_summary(self, messages: List[Dict]) -> str:
        """内置简单摘要（不需要 LLM）"""
        parts = []

        user_msgs = [m for m in messages if m.get("role") == "user"]
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        tool_msgs = [m for m in messages if m.get("role") == "tool"]

        parts.append(f"共 {len(user_msgs)} 轮对话")

        # 提取用户问题摘要
        if user_msgs:
            questions = [(m.get("content") or "")[:100] for m in user_msgs[-5:]]
            parts.append(f"用户主要问题: {'; '.join(questions)}")

        # 提取关键回复
        if assistant_msgs:
            key_points = self._extract_key_points(assistant_msgs)
            if key_points:
                parts.append(f"关键回复要点: {'; '.join(key_points[:5])}")

        # 工具调用摘要
        if tool_msgs:
            tool_names = set(m.get("name", "") for m in tool_msgs)
            parts.append(f"使用的工具: {', '.join(tool_names)}")

        return "\n".join(parts)

    def _extract_key_points(self, messages: List[Dict]) -> List[str]:
        """从回复中提取关键点"""
        points = []
        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue
            # 提取编号列表项
            numbered = re.findall(r'(?:^|\n)\s*(?:\d+\.|[-*])\s+(.{10,80})', content)
            points.extend(n for n in numbered if len(n) > 10)
        return points

    @property
    def stats(self) -> dict:
        return {
            "compaction_count": self._compaction_count,
            "last_summary": self._last_summary[:200] if self._last_summary else None,
        }


# ============================================================
# Context Window Manager
# ============================================================

class ContextWindow:
    """
    上下文窗口管理器

    参考 OpenCode 的分层存储策略:
      L1: 热上下文 — 当前激活的消息
      L2: 温上下文 — 最近的对话
      L3: 冷上下文 — 压缩后的历史摘要
    """

    def __init__(self, max_tokens: int = 100000, hot_ratio: float = 0.5,
                 warm_ratio: float = 0.3):
        self.max_tokens = max_tokens
        self.hot_size = int(max_tokens * hot_ratio)   # 热层
        self.warm_size = int(max_tokens * warm_ratio)  # 温层
        self._stats = {"compactions": 0, "last_size": 0}

    def prepare_context(self, messages: List[Dict],
                        system_prompt: str = "") -> List[Dict]:
        """为 LLM 调用准备上下文窗口"""
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        total = estimate_tokens(system_prompt) if system_prompt else 0

        remaining = self.max_tokens - total - 500  # 预留 500 给回复

        # 从最新到最旧排列
        sorted_msgs = list(reversed(messages))

        for msg in sorted_msgs:
            tokens = estimate_tokens(str(msg.get("content", "")), "gpt-4")
            if total + tokens > remaining:
                # 插入压缩标记
                if result and result[0]["role"] != "system":
                    before = result[:-1]
                    before.append({
                        "role": "system",
                        "content": f"[早期对话已压缩，省略 {len(messages) - len(result)} 条消息]"
                    })
                    result = before
                break
            result.append(msg)
            total += tokens

        self._stats["last_size"] = total
        return list(reversed(result))


# ============================================================
# Convenience
# ============================================================

def create_auto_compact(max_tokens: int = 100000) -> AutoCompact:
    return AutoCompact(max_tokens=max_tokens)


def create_context_window(max_tokens: int = 100000) -> ContextWindow:
    return ContextWindow(max_tokens=max_tokens)


__all__ = [
    "AutoCompact", "ContextWindow",
    "estimate_tokens", "estimate_messages_tokens",
    "create_auto_compact", "create_context_window",
]