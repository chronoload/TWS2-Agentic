#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""macdev 工具包装 — 把 macdev 机器驱动开发库包装为 TS2 默认工具（替换 plan_cli）。

设计：
  - 复用 mcp/tools.py 的 Tool 基类（schema/结构化结果/截断/搜索签名）。
  - 单个 MacdevTool 覆盖 macdev 全部顶级命令（audit/plan/patch/log/requirement/
    dev/project/doc），参数 = 顶层命令 + 参数串 + 可选 cwd / project。
  - 通过 subprocess 调用 `python -m macdev`（指向 mcp/macdev 拷贝版，脚本为唯一
    事实源），捕获 stdout/stderr 返回给 LLM，超时/异常兜底为人类可读消息。

注册：mcp/tools.py `get_tools()` 中 `from .macdev_tools import MacdevTool;
all_tools.append(MacdevTool())`；config 默认启用名单同步（替换 plan_cli）。
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List

from .tools import Tool

MCP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = MCP_ROOT.parent

# macdev 顶层命令（python -m macdev 的子命令组）
TOP_LEVEL_COMMANDS = ("audit", "plan", "patch", "log", "requirement", "dev",
                      "project", "doc")

# 支持 --project 产物收敛的顶层命令（plan/patch/project 走各自参数）
PROJECT_SUPPORTED = ("audit", "log", "requirement", "dev")

COMMAND_HELP = {
    "audit": "--task task.json --root . [--project <name>] 静态接口审计（亲属追逐依赖链 + 8维分析 + 4维扫描，双轨产物 INTERFACE_CHAIN.md + interface_chain.db + CSV）",
    "plan": "create --title ... / task add --plan <id> ... / step add --task <id> ... / verify --plan <id> / ledger / export / review / tdd check / openspec ...（开发流程机器化，变更自动刷新双轨产物）",
    "patch": "gen --db ... --root . / apply --dir patches/ --root . / verify --before ... --after ... / plugins（自演化修复闭环；bug 修复前先 systematic-debugging：复现→根因→假设→patch）",
    "log": "add --project <name> --category pitfalls --title ... / list [--scope project|pkg] / query --keyword ... / export（经验沉淀，随项目/随包双轨）",
    "requirement": "add --kind interface|path|file|spec --name ... / list / update / delete / export / align --root . / scan --req-dirs openspec（需求 CRUD + 规范接口对齐，双轨；--kind spec 替代外部 spec 文件——design 文档用 requirement 记录而非 docs/specs）",
    "dev": "map --target <目录> [--depth 3] / audit --target <目录>（学习/模仿目标项目：目录编排 + 架构了解）",
    "project": "init --name <name> [--git] / list / root --name <name>（产物目录约定 <name>-project/）",
    "doc": "[--out 路径] 自举生成使用/开发文档（AUDIT/PLAN/LOG/REQI/DEV 各 5 份）",
}


class MacdevTool(Tool):
    name = "macdev"
    category = "development"
    keywords = ["macdev", "audit", "审计", "接口链", "plan", "计划", "任务", "TDD",
                "verify", "review", "ledger", "log", "经验", "教训", "pitfall",
                "requirement", "需求", "align", "dev", "学习", "模仿", "架构",
                "project", "产物", "patch", "补丁", "自演化", "superpowers",
                "brainstorming", "grilling", "构思", "systematic-debugging", "调试",
                "subagent", "子技能", "spec", "writing-plans"]
    description = ("运行 macdev 机器驱动开发库命令（静态接口审计/开发流程机器化/经验沉淀/"
                   "需求对齐/学习模仿目标项目/产物目录/自演化补丁）。"
                   "它取代 plan_cli：plan 的 CRUD+verify+review+ledger+tdd+openspec 全在 plan 下，"
                   "audit 提供亲属追逐依赖链与 8 维分析，log 沉淀经验（随项目/随包），"
                   "requirement 维护结构化需求并对齐代码/端点（--kind spec 替代外部 spec 文件），"
                   "dev 学习模仿陌生项目。"
                   "整合 superpowers：任务先判定类型（构思→grilling/requirement spec / "
                   "bug→systematic-debugging→patch / 功能→plan TDD / 收尾→review→分支完成），"
                   "14 个子技能见 skills/macdev-skill/skills/（brainstorming/系统化调试/TDD/"
                   "writing-plans/verification/code-review/subagent/并行/分支收尾/worktrees 等）。"
                   "产物默认收敛到 <name>-project/（--project 或 env MACDEV_PROJECT）。")
    parameters = {
        "type": "object",
        "properties": {
            "subcommand": {
                "type": "string",
                "description": "macdev 顶层命令。常用：audit / plan / log / requirement / dev / "
                               "project / patch / doc",
                "enum": list(TOP_LEVEL_COMMANDS),
            },
            "args": {
                "type": "string",
                "description": "该命令的参数串（含其子命令与选项），空格分隔（多行内容用 \\n 转义）。"
                               "示例：plan create --title \"接入新端点\" / "
                               "plan task add --plan 20260811_x --title T1 --detail ... / "
                               "log list --scope pkg / dev map --target ../some-project",
                "example": "plan verify --plan 20260811_x",
            },
            "project": {
                "type": "string",
                "description": "产物目录名：产物收敛到 <name>-project/（audit/log/requirement/dev 支持；"
                               "缺省走 env MACDEV_PROJECT 或命令缺省位置）",
            },
            "cwd": {
                "type": "string",
                "description": "工作目录（默认 TS2 项目根），macdev 产物与相对路径基于此解析",
            },
        },
        "required": ["subcommand"],
    }
    model_hint = (
        "[何时使用] 审计项目架构/接口链、结构化维护开发计划、沉淀经验教训、管理需求并对齐代码、"
        "学习模仿陌生项目、收敛工作流产物。它取代了 plan_cli，plan 相关全部在 macdev plan 下。\n"
        "[流程编排（superpowers 整合）] 任务先判定类型再选纪律：\n"
        "- 构思/设计 → grilling（澄清→方案→批准）→ requirement add --kind spec 记录设计 → plan\n"
        "- bug/缺陷   → systematic-debugging（复现→根因→假设）→ patch gen/apply/verify\n"
        "- 功能实现   → plan（TDD：先失败测试后实现）→ verify 门禁\n"
        "- 收尾       → plan review → 分支完成\n"
        "14 个子技能：skills/macdev-skill/skills/（brainstorming/systematic-debugging/TDD/"
        "writing-plans/verification/code-review/subagent/parallel/branch/worktrees）\n"
        "[顶层命令速查]\n"
        "- audit: --task task.json --root . [--project <name>]  → INTERFACE_CHAIN.md + interface_chain.db\n"
        "- plan: create --title ... / task add --plan <id> --title ... / step add --task <id> --text ... /\n"
        "        verify --plan <id>（完成门禁）/ ledger / export / review / tdd check / openspec ...\n"
        "- log: add --project <name> --category pitfalls|lessons|patterns|decisions --title ... [--body]\n"
        "       list [--scope project|pkg] / query --keyword ... / export\n"
        "- requirement: add --kind interface|path|file|spec --name ... / list / align --root . / scan\n"
        "       （--kind spec 替代外部 spec 文件：design 用 requirement 双轨记录，禁止 docs/specs）\n"
        "- dev: map --target <目录>（目录编排）/ audit --target <目录>（架构了解）\n"
        "- project: init --name <name> [--git]（建 <name>-project/ 收纳全部产物）\n"
        "- patch: gen --db ... --root . / apply --dir ... / verify（自演化修复闭环）\n"
    )

    def __init__(self, project_root: str | Path = ""):
        self.project_root = Path(project_root) if project_root else PROJECT_ROOT

    def execute(self, subcommand: str, args: str = "", project: str = "",
                cwd: str = "") -> str:
        # 归一化：允许 "plan;create" 或 "plan create" 等分隔
        parts = subcommand.strip().replace(";", " ").split()
        if not parts or parts[0] not in TOP_LEVEL_COMMANDS:
            return f"错误：macdev 顶层命令，可选：{', '.join(TOP_LEVEL_COMMANDS)}"
        cmdline = [sys.executable, "-X", "utf8", "-m", "macdev", *parts]
        if args and args.strip():
            try:
                cmdline += shlex.split(args.strip())
            except ValueError as e:
                return f"参数解析失败：{e}（多行内容请用 \\n 转义，避免裸引号）"
        if project and parts[0] in PROJECT_SUPPORTED:
            cmdline += ["--project", project]
        env = dict(os.environ)
        # 确保 mcp/ 在 sys.path：python -m macdev 命中 mcp/macdev 拷贝版（唯一事实源）
        env["PYTHONPATH"] = str(MCP_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        workdir = str(Path(cwd) if cwd else self.project_root)
        try:
            r = subprocess.run(
                cmdline, capture_output=True, text=True,
                cwd=workdir, timeout=180, encoding="utf-8", env=env,
            )
        except subprocess.TimeoutExpired:
            return "执行超时（>180s）：audit 全量扫描可能较慢，请用 --project/--out 收敛，或用 dev audit --timeout 限制"
        except Exception as e:
            return f"执行失败：{e}"

        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode != 0:
            return f"退出码 {r.returncode}\n{out}\n{err}".strip() or "命令执行失败（无输出）"
        return out or err or "(命令执行成功，无输出)"


def get_macdev_tools() -> List[Tool]:
    """获取 macdev 工具集（注册到 TS2 默认工具系统，替换 plan_cli）。"""
    try:
        return [MacdevTool()]
    except Exception:
        return []
