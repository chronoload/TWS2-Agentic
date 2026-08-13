#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""worktree 工具包装 — 把 mcp/worktree.py 的任务工作树管理封装为 TS2 工具。

设计（参照 macdev_tools.py 的 MacdevTool 模式）：
  - 复用 mcp/tools.py 的 Tool 基类（schema/结构化结果/截断/搜索签名）。
  - 单个 WorktreeTool 覆盖 worktree.py 全部能力（create/remove/list），
    参数 = action + cwd/task_id/path，直接进程内调用（不 subprocess 二次包装）。
  - 安全：create/remove 调用 worktree.py 内置的校验（task_id 黑名单防路径穿越、
    git 可用性/仓库定位前置检查）。

注册：mcp/tools.py `get_tools()` 中 `from .worktree_tools import WorktreeTool;
all_tools.append(WorktreeTool())`（与 macdev 工具组同区块）。
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from .tools import Tool

MCP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = MCP_ROOT.parent

# 支持的 action 一览（与 worktree.py 函数一一对应）
ACTIONS = ("create", "remove", "list")


class WorktreeTool(Tool):
    name = "worktree"
    category = "development"
    keywords = ["worktree", "工作树", "任务隔离", "并行开发", "git", "检出",
                "分支", "隔离", "sandbox", "task"]
    description = ("管理 git 任务工作树（借鉴 Cline --worktree 模式）："
                   "为每个任务创建独立 git worktree（~/.ts2/worktrees/<task_id>/<label>，"
                   "基于 HEAD 分离检出），多任务并行开发互不污染工作区。"
                   "create=创建 / remove=移除 / list=列出。")
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作：create=为任务创建独立工作树 / remove=移除工作树 / list=列出全部工作树",
                "enum": list(ACTIONS),
            },
            "cwd": {
                "type": "string",
                "description": "工作目录（默认 TS2 项目根），用于定位 git 仓库",
            },
            "task_id": {
                "type": "string",
                "description": "[create] 自定义任务 ID（可空，自动生成 5 位随机 ID）；"
                               "含 / \\ .. 或控制字符会被拒绝（防路径穿越）",
            },
            "path": {
                "type": "string",
                "description": "[remove] 要移除的工作树路径（如 ~/.ts2/worktrees/abc12/TS2_813）",
            },
        },
        "required": ["action"],
    }
    model_hint = (
        "[何时使用] 需要为独立任务创建隔离开发环境、并行处理多个任务、"
        "或清理不再需要的任务工作树时。\n"
        "[参数说明]\n"
        "- action: create（创建）/ remove（移除）/ list（列出）\n"
        "- cwd: 工作目录，默认项目根（create 会在该 git 仓库下建工作树）\n"
        "- task_id: create 时可指定任务 ID（默认自动生成）\n"
        "- path: remove 时必填，工作树路径\n"
        "[注意] 工作树统一存放在 ~/.ts2/worktrees/<task_id>/<workspace_label>，"
        "删除失败会自动降级 --force。"
    )

    def __init__(self, project_root: str | Path = ""):
        self.project_root = Path(project_root) if project_root else PROJECT_ROOT

    def execute(self, action: str, cwd: str = "", task_id: str = "",
                path: str = "") -> str:
        try:
            from .worktree import (
                create_task_worktree, remove_worktree, list_worktrees,
            )
        except ImportError as e:
            return f"worktree 模块不可用: {e}"

        action = (action or "").strip().lower()
        if action not in ACTIONS:
            return f"错误：action 可选 {', '.join(ACTIONS)}"

        workdir = str(Path(cwd) if cwd else self.project_root)

        if action == "create":
            result = create_task_worktree(workdir, task_id=task_id)
            if not result.success:
                return f"[worktree create] 失败: {result.message}"
            return (f"[worktree create] ✅ {result.message}\n"
                    f"  task_id: {result.task_id}\n"
                    f"  路径:    {result.path}\n"
                    f"  仓库:    {result.repo_root}")

        if action == "remove":
            if not path:
                return "错误：remove 需要提供 path（工作树路径）"
            ok = remove_worktree(path)
            return f"[worktree remove] {'✅ 已移除' if ok else '❌ 移除失败'}: {path}"

        # list
        rows = list_worktrees(workdir)
        if not rows:
            return "[worktree list] 当前仓库无 worktree（仅主工作区）"
        lines = ["[worktree list] 当前仓库工作树：", "| 路径 | HEAD | 分支 | 分离 |",
                 "|------|------|------|------|"]
        for r in rows:
            head = (r.get("head") or "")[:12]
            branch = r.get("branch") or "—"
            detached = "是" if r.get("detached") else ""
            lines.append(f"| {r.get('path', '')} | {head} | {branch} | {detached} |")
        return "\n".join(lines)


def get_worktree_tools() -> List[Tool]:
    """获取 worktree 工具集（注册到 TS2 默认工具系统）。"""
    try:
        return [WorktreeTool()]
    except Exception:
        return []
