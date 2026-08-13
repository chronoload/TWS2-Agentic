#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macdev 工作流定义 — 把 macdev 机器驱动开发库的流程改造成可编排工作流。

设计：
  - 每个工作流 = WorkflowDefinition（workflow_id + steps + entry_step + checkpoint_after）
  - 步骤全部为 TOOL 类型，config.tool_name="macdev"，通过工作流引擎的
    `_run_tool` 调用 MacdevTool（mcp/tools.py 已注册），subprocess 执行
    `python -m macdev ...`。
  - 步骤间依赖：args 中使用 {project}/{root}/{task}/{title} 等占位符，
    由引擎 `_render_string` 从 input_data 渲染；也可用 param_inputs
    （$input.x / $node.x.y / $var.x）做参数链。

工作流清单：
  wf_macdev_project_init  项目初始化（project init + list）
  wf_macdev_audit         静态接口审计闭环（audit + chain stats）
  wf_macdev_dev_cycle     完整开发闭环（init → audit → plan → patch → verify → log）
  wf_macdev_patch         自演化修复闭环（gen → apply → re-audit → verify）
  wf_macdev_log           经验沉淀（log add + list）
"""
from __future__ import annotations

from .workflow_engine import WorkflowDefinition, StepDefinition, StepType

# ─── 通用 TOOL 步骤构造器 ─────────────────────────────────────────

def _md_tool(step_id: str, name: str, subcommand: str, args: str,
             checkpoint: bool = False, param_inputs=None,
             param_outputs=None) -> StepDefinition:
    """构造一个 macdev TOOL 步骤。

    subcommand: 顶层命令（audit/plan/patch/log/requirement/dev/project/doc）
    args:       macdev 命令参数串（可含 {project} {root} {title} 等占位符）
    """
    return StepDefinition(
        step_id=step_id,
        name=name,
        step_type=StepType.TOOL,
        config={"tool_name": "macdev",
                "args": {"subcommand": subcommand, "args": args}},
        param_inputs=param_inputs,
        param_outputs=param_outputs,
    )


# ─── 1. 项目初始化 ────────────────────────────────────────────────

def macdev_project_init_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_macdev_project_init",
        name="macdev项目初始化",
        description="macdev 产物项目初始化：project init --name <name> 建 <name>-project/ 目录，随后列出已有项目",
        entry_step="init",
        checkpoint_after={"init"},
        steps=[
            _md_tool("init", "初始化产物目录", "project",
                     "init --name {project}"),
            _md_tool("list", "列出项目", "project",
                     "list"),
        ],
    )


# ─── 2. 静态接口审计闭环 ──────────────────────────────────────────

def macdev_audit_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_macdev_audit",
        name="macdev静态审计",
        description="macdev 静态接口审计：audit 跑全量扫描（亲属追逐依赖链 + 8维分析 + 4维扫描），产物收敛到 <name>-project/audit，随后定向查询 interface_chain.db",
        entry_step="run_audit",
        checkpoint_after={"run_audit"},
        steps=[
            _md_tool("run_audit", "运行审计", "audit",
                     "--task {task} --root {root} --project {project} --no-progress",
                     param_outputs=[
                         {"name": "audit_out", "path": "out", "type": "string"},
                         {"name": "ok", "path": "ok", "type": "string"},
                     ]),
            _md_tool("chain_stats", "查询审计统计", "audit",
                     "chain stats --db {db}"),
            _md_tool("chain_issues", "查询缺陷清单", "audit",
                     "chain issues --db {db} --count"),
        ],
    )


# ─── 3. 完整开发闭环（核心） ───────────────────────────────────────

def macdev_dev_cycle_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_macdev_dev_cycle",
        name="macdev开发闭环",
        description="macdev 完整开发闭环：project init → audit 审计 → plan 计划 → patch 修复 → verify 门禁 → log 沉淀。输入 project/title/root/task/plan_id",
        entry_step="init",
        checkpoint_after={"init", "audit", "plan_create", "patch_apply"},
        steps=[
            _md_tool("init", "初始化产物目录", "project",
                     "init --name {project}"),
            _md_tool("audit", "静态审计", "audit",
                     "--task {task} --root {root} --project {project} --no-progress"),
            _md_tool("plan_create", "创建开发计划", "plan",
                     "create --title {title} --goal {goal}"),
            _md_tool("plan_task", "添加任务", "plan",
                     "task add --plan {plan_id} --title {task_title} --detail {task_detail}"),
            _md_tool("patch_gen", "生成修复补丁", "patch",
                     "gen --db {project}-project/audit/interface_chain.db --root {root} --out patches"),
            _md_tool("patch_apply", "应用补丁", "patch",
                     "apply --dir patches --root {root}"),
            _md_tool("plan_verify", "完成门禁", "plan",
                     "verify --plan {plan_id} --root {root}"),
            _md_tool("log_add", "沉淀经验", "log",
                     "add --project {project} --category lessons --title {lesson_title} --body {lesson_body}"),
            _md_tool("log_list", "确认经验库", "log",
                     "list --project {project}"),
        ],
    )


# ─── 4. 自演化修复闭环 ────────────────────────────────────────────

def macdev_patch_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_macdev_patch",
        name="macdev自演化修复",
        description="macdev 自演化修复闭环：patch gen 从审计缺陷生成补丁 → apply 应用 → 重审计 → patch verify 对比补丁前后缺陷数。输入 project/root/task/db",
        entry_step="gen",
        checkpoint_after={"apply", "re_audit"},
        steps=[
            _md_tool("gen", "生成补丁脚本", "patch",
                     "gen --db {db} --root {root} --out patches"),
            _md_tool("apply", "应用补丁", "patch",
                     "apply --dir patches --root {root}"),
            _md_tool("re_audit", "重审计", "audit",
                     "--task {task} --root {root} --project {project} --no-progress"),
            _md_tool("verify", "补丁前后对比", "patch",
                     "verify --before {db} --after {project}-project/audit/interface_chain.db"),
            _md_tool("plugins", "列出修复插件", "patch",
                     "plugins"),
        ],
    )


# ─── 5. 经验沉淀 ──────────────────────────────────────────────────

def macdev_log_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_macdev_log",
        name="macdev经验沉淀",
        description="macdev 经验沉淀：log add 记录一条经验/教训/模式/决策，随后列出项目经验库。输入 project/category/title/body/tags",
        entry_step="add",
        steps=[
            _md_tool("add", "记录经验", "log",
                     "add --project {project} --category {category} --title {title} "
                     "--body {body} --tags {tags}"),
            _md_tool("list", "列出经验库", "log",
                     "list --project {project}"),
            _md_tool("export", "导出LOGS", "log",
                     "export --project {project} --out {project}-project/LOGS.md"),
        ],
    )


# ─── 注册表 ───────────────────────────────────────────────────────

MACDEV_WORKFLOWS: dict = {
    "wf_macdev_project_init": macdev_project_init_workflow(),
    "wf_macdev_audit": macdev_audit_workflow(),
    "wf_macdev_dev_cycle": macdev_dev_cycle_workflow(),
    "wf_macdev_patch": macdev_patch_workflow(),
    "wf_macdev_log": macdev_log_workflow(),
}


def register_macdev_workflows(registry: dict):
    """把 macdev 工作流注册进 WORKFLOW_REGISTRY 字典。"""
    registry.update(MACDEV_WORKFLOWS)
    return len(MACDEV_WORKFLOWS)


__all__ = [
    "macdev_project_init_workflow", "macdev_audit_workflow",
    "macdev_dev_cycle_workflow", "macdev_patch_workflow",
    "macdev_log_workflow", "MACDEV_WORKFLOWS", "register_macdev_workflows",
]
