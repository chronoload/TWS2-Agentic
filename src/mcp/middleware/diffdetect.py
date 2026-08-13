#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 输出中的 unified diff 自动检测 — 参考 Crush diffdetect

当 LLM 在回复中直接输出 unified diff 格式（而不是调用 apply_diff 工具），
diffdetect 可以自动识别并提取，转为结构化的文件修改操作。

检测信号：
- @@ ... @@: hunk 头
- --- a/path / +++ b/path: 文件头
- diff --git a/... b/...: git 头

使用场景：
1. after_agent 中间件中检测 LLM 回复
2. 自动将 diff 转为 apply_diff 工具调用
3. 在检查点中记录 diff 来源
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DiffSignal:
    """扫描 LLM 输出中的 unified diff 标记（参考 Crush diffdetect.Inspect）"""
    has_hunk: bool = False
    has_file_header: bool = False
    has_git_header: bool = False


@dataclass
class DiffHunk:
    """单个 diff hunk"""
    old_start: int = 0
    old_count: int = 0
    new_start: int = 0
    new_count: int = 0
    lines: List[str] = field(default_factory=list)


@dataclass
class DiffBlock:
    """一个文件的完整 diff 块"""
    old_path: str = ""
    new_path: str = ""
    hunks: List[DiffHunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        """提取目标文件路径（优先 new_path，去掉 a/ 前缀）"""
        p = self.new_path or self.old_path
        if p.startswith("b/"):
            p = p[2:]
        elif p.startswith("a/"):
            p = p[2:]
        return p


def inspect(content: str) -> DiffSignal:
    """扫描内容中的 unified diff 标记（参考 Crush diffdetect.Inspect）"""
    signal = DiffSignal()
    for line in content.split("\n"):
        if line.startswith("@@"):
            signal.has_hunk = True
        if line.startswith("--- ") or line.startswith("+++ "):
            signal.has_file_header = True
        if line.startswith("diff --git "):
            signal.has_git_header = True
    return signal


def is_unified_diff(content: str) -> bool:
    """判断内容是否包含 unified diff（参考 Crush diffdetect.IsUnifiedDiff）"""
    s = inspect(content)
    # git header + file header = 标准 git diff
    # hunk + file header = 简化 unified diff
    return (s.has_git_header and s.has_file_header) or \
           (s.has_hunk and s.has_file_header)


def extract_diff_blocks(content: str) -> List[DiffBlock]:
    """从 LLM 输出中提取所有 diff 块

    支持两种格式：
    1. git diff 格式: diff --git a/X b/X \\n --- a/X \\n +++ b/X \\n @@...
    2. 简化 unified diff: --- a/X \\n +++ b/X \\n @@...

    Returns:
        [DiffBlock(...), ...]
    """
    blocks: List[DiffBlock] = []
    current: Optional[DiffBlock] = None
    current_hunk: Optional[DiffHunk] = None

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # diff --git a/X b/Y → 新块开始
        m = re.match(r'^diff --git (?:a/)?(\S+) (?:b/)?(\S+)', line)
        if m:
            if current and current.hunks:
                blocks.append(current)
            current = DiffBlock(old_path=m.group(1), new_path=m.group(2))
            current_hunk = None
            i += 1
            continue

        # --- a/path → 文件头
        m = re.match(r'^--- (?:a/)?(.+)', line)
        if m:
            if current is None:
                current = DiffBlock()
            current.old_path = m.group(1)
            i += 1
            continue

        # +++ b/path → 文件头
        m = re.match(r'^\+\+\+ (?:b/)?(.+)', line)
        if m:
            if current is None:
                current = DiffBlock()
            current.new_path = m.group(1)
            i += 1
            continue

        # @@ -old_start,old_count +new_start,new_count @@ → hunk 头
        m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
        if m and current is not None:
            if current_hunk and current_hunk.lines:
                current.hunks.append(current_hunk)
            current_hunk = DiffHunk(
                old_start=int(m.group(1)),
                old_count=int(m.group(2) or "1"),
                new_start=int(m.group(3)),
                new_count=int(m.group(4) or "1"),
            )
            i += 1
            continue

        # hunk 内容行（+/-/空格开头）
        if current_hunk is not None and (line.startswith("+") or line.startswith("-") or line.startswith(" ") or line == ""):
            # 避免收集非 diff 内容（如代码块结束标记 ```）
            if line.startswith("```"):
                i += 1
                continue
            current_hunk.lines.append(line)
            i += 1
            continue

        # 非_diff 行 → 如果当前块有 hunks，结束当前块
        if current and current_hunk and current_hunk.lines:
            current.hunks.append(current_hunk)
            current_hunk = None

        # 如果遇到非 diff 行且当前块已完成
        if current and current.hunks and not line.startswith(("+", "-", " ", "@@", "---", "+++", "diff")):
            blocks.append(current)
            current = None

        i += 1

    # 收尾
    if current_hunk and current_hunk.lines:
        if current is None:
            current = DiffBlock()
        current.hunks.append(current_hunk)
    if current and current.hunks:
        blocks.append(current)

    return blocks


def diff_blocks_to_tool_args(blocks: List[DiffBlock]) -> List[dict]:
    """将 diff 块转为 apply_diff 工具参数

    Returns:
        [{"path": "...", "diff": "..."}, ...]
    """
    results = []
    for block in blocks:
        if not block.hunks:
            continue

        # 重建 diff 文本
        diff_lines = []
        if block.old_path:
            diff_lines.append(f"--- a/{block.old_path}")
        if block.new_path:
            diff_lines.append(f"+++ b/{block.new_path}")

        for hunk in block.hunks:
            header = f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
            diff_lines.append(header)
            diff_lines.extend(hunk.lines)

        results.append({
            "path": block.path,
            "diff": "\n".join(diff_lines),
        })

    return results
