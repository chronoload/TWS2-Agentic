"""plan.export：导出（writing-plans / table / JSON）+ 双轨自动刷新。"""
from __future__ import annotations
import csv
import json
from datetime import datetime
from pathlib import Path
from .db import PlanStore
from .commands import _status_icon, _resolve_req, _resolve_defect


def export_md(plan) -> str:
    """dataclass 版最小导出（Engine.run_plan export 用）。"""
    lines = [f"# {plan.title}", "", f"**Goal:** {plan.goal}", ""]
    for task in plan.tasks:
        lines.append(f"## {task.title}")
        for s in task.steps:
            box = "[x]" if s.status == "done" else "[ ]"
            lines.append(f"- {box} {s.text}")
        lines.append("")
    return "\n".join(lines)


def _render_writing_plans(plan, tasks, steps_by_task, req_map, defect_map) -> list:
    """对齐 writing-plans skill 的格式：头部 + Global Constraints + Task 文件清单 + checkbox 步骤。"""
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
    return lines


def _render_table(plan, tasks, steps_by_task, req_map, defect_map) -> list:
    lines = [f"# Plan: {plan[1]}",
             "",
             f"> 状态: **{plan[6]}** · 创建: {plan[7]} · 任务: {len(tasks)}",
             "",
             "## 目标",
             "",
             plan[2] or "（未填写）",
             "",
             "## 任务",
             "",
             "| # | 状态 | 标题 | 说明 | 关联需求 | 关联缺陷 | Review |",
             "|----|------|------|------|----------|----------|--------|"]
    for t in tasks:
        detail = t[2].replace("|", "\\|")[:100]
        defect_txt = _resolve_defect(t[5], defect_map)
        rev_txt = {"approved": "✅", "review_requested": "🔄",
                   "needs_fix": "❌", "pending": "⏳"}.get(t[8], t[8])
        lines.append(f"| {t[0]} | {t[7]} | `{t[1]}` | {detail} | {_resolve_req(t[4], req_map)} | {defect_txt} | {rev_txt} |")
    return lines


def export_plan(store: PlanStore, pid: int, out: Path | str = "", fmt: str = "writing-plans") -> tuple:
    """导出 plan → (exit_code, [lines], md_path, json_path)"""
    conn = store.connect()
    plan = conn.execute(
        "SELECT id, title, goal, arch, stack, global_constraints, status, created_at "
        "FROM plans WHERE id = ?", (pid,)).fetchone()
    if not plan:
        conn.close()
        return 1, [f"[export] plan id={pid} 不存在"], None, None
    tasks = conn.execute(
        "SELECT id, title, detail, files, req_ref, defect_ref, interfaces, status, "
        "review_status, review_findings FROM tasks WHERE plan_id = ? ORDER BY id",
        (pid,)).fetchall()
    step_rows = conn.execute(
        "SELECT id, task_id, ord, text, action, code, lang, run, expected, status "
        "FROM steps ORDER BY ord").fetchall()
    conn.close()
    steps_by_task: dict = {}
    for st in step_rows:
        steps_by_task.setdefault(st[1], []).append(st)

    req_map = store.req_status_map()
    defect_map = {d["id"]: d for d in store.load_defects()}
    lines = (_render_writing_plans(plan, tasks, steps_by_task, req_map, defect_map)
             if fmt == "writing-plans"
             else _render_table(plan, tasks, steps_by_task, req_map, defect_map))
    lines += ["", "---",
              f"自动生成: {datetime.now().isoformat(timespec='seconds')} 由 `macdev plan export`（format={fmt}）"]

    out_path = Path(out) if out else Path(f"PLAN_{plan[0]}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps({
        "plan": {"id": plan[0], "title": plan[1], "goal": plan[2], "arch": plan[3],
                 "stack": plan[4], "global_constraints": plan[5],
                 "status": plan[6], "created_at": plan[7]},
        "tasks": [{"id": t[0], "title": t[1], "detail": t[2], "files": t[3],
                   "req_ref": t[4], "defect_ref": t[5], "interfaces": t[6],
                   "status": t[7], "review_status": t[8], "review_findings": t[9],
                   "steps": [{"id": s[0], "ord": s[2], "text": s[3], "action": s[4],
                              "code": s[5], "lang": s[6], "run": s[7], "expected": s[8],
                              "status": s[9]} for s in steps_by_task.get(t[0], [])]}
                  for t in tasks],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0, [f"[export] {fmt} → {out_path}", f"[export] json → {json_path}"], out_path, json_path


def refresh_csv(store: PlanStore, out_dir: Path | str = "") -> Path:
    """汇总 plans.csv（全部 plan/task/step 明细，机器轨）。"""
    out_dir = Path(out_dir) if out_dir else store.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = store.connect()
    rows = conn.execute(
        "SELECT p.id, p.title, p.status, p.created_at, "
        "       t.id, t.title, t.status, "
        "       s.id, s.ord, s.text, s.status "
        "FROM plans p "
        "LEFT JOIN tasks t ON t.plan_id = p.id "
        "LEFT JOIN steps s ON s.task_id = t.id "
        "ORDER BY p.id, t.id, s.ord").fetchall()
    conn.close()
    csv_path = out_dir / "plans.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["plan_id", "plan_title", "plan_status", "created_at",
                    "task_id", "task_title", "task_status",
                    "step_id", "step_ord", "step_text", "step_status"])
        for r in rows:
            w.writerow(list(r))
    return csv_path


def refresh_plan(store: PlanStore, pid: int, out_dir: Path | str = "") -> tuple:
    """双轨自动刷新（对齐 requirement 约定）：变更后重写 PLAN_<pid>.md/.json + 汇总 plans.csv。
    db 为权威；md 人类轨、json/csv 机器轨，全部落在 out_dir（缺省 db 同目录）。"""
    out_dir = Path(out_dir) if out_dir else store.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    code, lines, md_path, json_path = export_plan(store, pid, out=out_dir / f"PLAN_{pid}.md")
    if code:
        return code, lines
    csv_path = refresh_csv(store, out_dir)
    return code, lines + [f"[plan] csv → {csv_path}"]
