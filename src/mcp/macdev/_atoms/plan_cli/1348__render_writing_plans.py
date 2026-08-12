# 原子：_render_writing_plans（原 plan_cli.py 第 1348 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _render_writing_plans(plan, tasks, steps_by_task, req_map, defect_map) -> list:
    """对齐 writing-plans skill 的格式：头部 + Global Constraints + Task 文件清单/Interfaces + checkbox 步骤。"""
    # plan 行: (id, title, goal, arch, stack, global_constraints, status, created_at)
    title, goal, arch, stack = plan[1], plan[2], plan[3], plan[4]
    gcs, status, created = plan[5], plan[6], plan[7]
    lines = [f"# {title} Implementation Plan",
             "",
             "> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.",
             "",
             f"**Goal:** {goal or '（未填写）'}",
             "",
             f"**Architecture:** {arch or '（未填写）'}",
             "",
             f"**Tech Stack:** {stack or '（未填写）'}",
             "",
             f"**Status:** {status} · **Created:** {created} · **Tasks:** {len(tasks)}",
             ""]
    if gcs:
        lines += ["## Global Constraints", "",
                  "> 项目级硬约束，逐条抄录 spec——每个任务的实现与评审都必须遵守。", ""]
        for gc in gcs.splitlines():
            gc = gc.strip()
            if gc:
                lines.append(f"- {gc}")
        lines.append("")
    lines += ["---", ""]
    for i, t in enumerate(tasks, 1):
        # tasks 行: (id, title, detail, files, req_ref, defect_ref, interfaces, status, review_status, review_findings)
        tid, title_t, detail, files, req_ref, defect_ref, ifaces, tstatus, rv, rfind = t
        lines += [f"### Task {i}: {title_t} {_status_icon(tstatus)}", ""]
        if files:
            lines += ["**Files:**", ""]
            for fl in files.splitlines():
                fl = fl.strip()
                if fl:
                    lines.append(f"- {fl}")
            lines.append("")
        if ifaces:
            lines += ["**Interfaces:**", ""]
            for ln in ifaces.splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(f"- {ln}")
            lines.append("")
        if detail:
            lines += [detail, ""]
        if req_ref:
            lines += [f"**Requirement:** {_resolve_req(req_ref, req_map)}", ""]
        if defect_ref:
            lines += [f"**Static Defect:** {_resolve_defect(defect_ref, defect_map)}", ""]
        if rv:
            rv_txt = {"approved": "✅ approved", "review_requested": "🔄 审查中",
                      "needs_fix": "❌ 需修复", "pending": "⏳ 待审查"}.get(rv, rv)
            lines += [f"**Review:** {rv_txt}", ""]
        if rfind:
            lines += [f"**Findings:**", ""]
            for ln in rfind.splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(f"  - {ln}")
            lines.append("")
        steps = steps_by_task.get(tid, [])
        if steps:
            for j, st in enumerate(steps, 1):
                sid, stask, sord, stext, sact, scode, slang, srun, sexp, sstatus = st
                mark = "[x]" if sstatus == "done" else "[ ]"
                lines += [f"- {mark} **Step {j}: {stext}** ({sact})", ""]
                if scode:
                    lang = slang or "text"
                    lines += [f"```{lang}", scode, "```", ""]
                if srun:
                    lines += [f"Run: `{srun}`", ""]
                if sexp:
                    lines += [f"Expected: {sexp}", ""]
        else:
            lines += ["- [ ] _（本任务暂无步骤，待补充）_", ""]
        lines.append("")
    if req_map:
        lines += ["## 关联需求状态", "",
                  "> 来自 `requirements.db`（requirement_cli 维护）。未找到的条目已标记 ❌ missing。"]
    return lines
