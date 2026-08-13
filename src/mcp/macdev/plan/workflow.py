"""plan.workflow：开发流程机器化（verify 完成门禁 / review 循环 / ledger 进度台账 / tdd 合规）。
从 plan_cli 原子重组；project_root 参数化（默认取 db 所在目录的父级）。
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from .db import PlanStore


# ─── review 循环状态机 ───

def cmd_review(store: PlanStore, task_id: int, action: str, findings: str = "") -> tuple:
    """review 循环：pending → review_requested → approved / needs_fix → fixed → review_requested"""
    conn = store.connect()
    row = conn.execute(
        "SELECT id, title, review_status, review_findings FROM tasks WHERE id = ?",
        (task_id,)).fetchone()
    if not row:
        conn.close()
        return 1, [f"[review] task id={task_id} 不存在"]
    tid, title, cur_status, cur_findings = row

    def _set(status: str, f: str = "") -> tuple:
        conn.execute("UPDATE tasks SET review_status=?, review_findings=? WHERE id=?",
                     (status, f, tid))
        conn.commit()
        conn.close()
        out = [f"[review] task={tid} '{title}' → {status}"]
        if f:
            out.append(f"[review] findings:\n{f}")
        return 0, out

    if action == "request":
        if cur_status == "approved":
            conn.close()
            return 0, [f"[review] task={tid} 已 approved，无需重新 request"]
        return _set("review_requested")
    if action == "approve":
        if cur_status == "approved":
            conn.close()
            return 0, [f"[review] task={tid} 已是 approved"]
        return _set("approved")
    if action == "reject":
        if not findings:
            conn.close()
            return 1, ["[review] reject 必须提供 --findings（Critical/Important/Minor）"]
        return _set("needs_fix", findings.replace("\\n", "\n").replace("\\t", "\t"))
    if action == "fix":
        if cur_status != "needs_fix":
            conn.close()
            return 1, [f"[review] task={tid} 状态是 {cur_status}，只有 needs_fix 才能 fix"]
        return _set("review_requested", cur_findings)
    conn.close()
    return 1, [f"[review] 未知 action: {action}"]


# ─── TDD 合规检查（db 版）───

def cmd_tdd_check(store: PlanStore) -> tuple:
    """TDD 合规（db 版）：test_missing / test_after_implement / test_unverifiable。"""
    conn = store.connect()
    rows = conn.execute(
        "SELECT t.id, t.title, s.id, s.ord, s.action, s.run, s.expected FROM tasks t "
        "LEFT JOIN steps s ON s.task_id = t.id ORDER BY t.id, s.ord").fetchall()
    conn.close()
    by_task: dict = {}
    for tid, title, sid, ord_, action, run, expected in rows:
        by_task.setdefault((tid, title), []).append((sid, ord_, action, run, expected))
    issues: list = []
    for (tid, title), steps in by_task.items():
        acts = [s[2] for s in steps if s[2]]
        if "implement" in acts and "test" not in acts:
            issues.append({"kind": "test_missing", "task": title})
        first_impl = next((i for i, a in enumerate(acts) if a == "implement"), None)
        first_test = next((i for i, a in enumerate(acts) if a == "test"), None)
        if first_impl is not None and first_test is not None and first_test > first_impl:
            issues.append({"kind": "test_after_implement", "task": title})
        for sid, ord_, action, run, expected in steps:
            if action == "test" and (not run or not expected):
                issues.append({"kind": "test_unverifiable", "task": title})
    if not issues:
        return 0, ["[tdd] ✅ 全部任务 TDD 合规（test 在 implement 前）"]
    out = []
    for i in issues:
        icon = {"test_missing": "🔴", "test_after_implement": "🟠", "test_unverifiable": "🟡"}[i["kind"]]
        out.append(f"  {icon} [{i['kind']}] {i['task']}")
    out.append(f"\n[tdd] {len(issues)} 项不合规")
    return 1, out


# ─── 完成门禁（verify）───

def cmd_verify(store: PlanStore, plan_id: int | None = None,
               project_root: Path | str = ".") -> tuple:
    """完成门禁（verification-before-completion）：聚合四类证据。
    (a) TDD 合规 (b) 静态缺陷已消失 (c) 测试文件存在 (d) 步骤完成 + review 通过。"""
    conn = store.connect()
    plan = conn.execute(
        "SELECT id, title, status FROM plans WHERE id = ?", (plan_id,)).fetchone() \
        if plan_id else None
    if plan_id and not plan:
        conn.close()
        return 1, [f"[verify] plan id={plan_id} 不存在"]
    tasks = conn.execute(
        "SELECT id, title, detail, files, req_ref, defect_ref, interfaces, status, review_status "
        "FROM tasks WHERE 1=1"
        + (" AND plan_id = ?" if plan_id else ""),
        (plan_id,) if plan_id else ()).fetchall()
    step_rows = conn.execute(
        "SELECT task_id, ord, action, run, expected, status FROM steps ORDER BY ord").fetchall()
    conn.close()

    current_ids = {d["id"] for d in store.load_defects()}
    steps_by_task: dict = {}
    for st in step_rows:
        steps_by_task.setdefault(st[0], []).append(st)

    failures: list = []
    scope_txt = f"plan={plan_id} '{plan[1]}'" if plan else "全部任务"

    for tid, title, _d, files, _req, defect_ref, _if, tstatus, review_status in tasks:
        steps = steps_by_task.get(tid, [])
        test_steps = [s for s in steps if s[2] == "test"]
        impl_steps = [s for s in steps if s[2] == "implement"]

        if impl_steps and not test_steps:
            failures.append((title, "TDD 违规：有 implement 但无 test（test_missing）"))
        if test_steps and impl_steps and steps.index(test_steps[0]) > steps.index(impl_steps[0]):
            failures.append((title, "TDD 违规：test 步骤排在 implement 之后（test_after_implement）"))

        if defect_ref:
            if defect_ref in current_ids:
                failures.append((title, f"静态缺陷 {defect_ref} 仍在报告中（未修复）"))
            test_files = [ln.split(":", 1)[1].strip() for ln in (files or "").splitlines()
                          if ln.strip().lower().startswith("test:")]
            if test_files and not all((Path(project_root) / tf).exists() for tf in test_files):
                failures.append((title, "任务声明的测试文件不存在: " + ", ".join(test_files)))

        if tstatus != "done":
            undone = [s for s in steps if s[5] != "done"]
            failures.append((title, f"任务状态 {tstatus}，{len(undone)} 个步骤未完成"))

        if review_status != "approved":
            failures.append((title, f"review 未通过（状态 {review_status}）——未批准的代码不得宣告完成"))

    if not tasks:
        failures.append(("(无任务)", "范围内没有任务"))

    out = [f"[verify] 完成门禁检查（{scope_txt}）— {len(tasks)} 个任务", ""]
    if not failures:
        out.append("  ✅ 全部通过：TDD 合规 · 缺陷清零 · 测试就位 · 步骤完成 · review 通过")
        out.append("  ✅ 可宣告完成（evidence: 见上方逐项证据）")
        return 0, out
    for title, msg in failures:
        out.append(f"  ❌ {title} — {msg}")
    out.append(f"\n[verify] {len(failures)} 项未通过 → 门禁拒绝，不得宣告完成。")
    out.append("        修复后重跑：python -m macdev audit && python -m macdev plan verify [--plan N]")
    return 1, out


# ─── 进度台账（ledger）───

def cmd_ledger(store: PlanStore, plan_id: int, out: Path | str = "") -> tuple:
    """进度台账：已完成任务标记 ✅（resume 跳过），未完成列出待办。"""
    conn = store.connect()
    plan = conn.execute("SELECT id, title, status FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        conn.close()
        return 1, [f"[ledger] plan id={plan_id} 不存在"]
    tasks = conn.execute(
        "SELECT id, title, status FROM tasks WHERE plan_id = ? ORDER BY id",
        (plan_id,)).fetchall()
    step_rows = conn.execute(
        "SELECT task_id, ord, action, status FROM steps ORDER BY ord").fetchall()
    conn.close()

    by_task: dict = {}
    for st in step_rows:
        by_task.setdefault(st[0], []).append(st)

    done_tasks, todo_tasks = [], []
    for tid, title, tstatus in tasks:
        steps = by_task.get(tid, [])
        all_done = tstatus == "done" and steps and all(s[3] == "done" for s in steps)
        if all_done:
            done_tasks.append((tid, title))
        else:
            undone = [f"#{s[1]} {s[2]}" for s in steps if s[3] != "done"]
            todo_tasks.append((tid, title, undone or ["(无步骤)"]))

    lines = [f"# 进度台账 Progress Ledger — {plan[1]}",
             "",
             f"> plan={plan_id} · 状态 {plan[2]} · 任务 {len(done_tasks)}/{len(tasks)} 完成 · "
             f"生成 {datetime.now().isoformat(timespec='seconds')}",
             "",
             "## 已完成（resume 时跳过）", ""]
    if done_tasks:
        for tid, title in done_tasks:
            lines.append(f"- [x] Task {tid}: {title}")
    else:
        lines.append("_（无）_")
    lines += ["", "## 待执行（resume 从第一个开始）", ""]
    for tid, title, undone in todo_tasks:
        mark = "- [ ]" if undone and undone != ["(无步骤)"] else "- [~]"
        lines.append(f"{mark} Task {tid}: {title}")
        for u in undone:
            lines.append(f"    - [ ] step {u}")
    lines.append("")

    out_path = Path(out) if out else Path(f"plan_{plan_id}_progress.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return 0, [f"[ledger] 进度台账 → {out_path}（完成 {len(done_tasks)}/{len(tasks)}）",
               "[ledger] resume 提示：从「待执行」第一个未完成 task 继续，不要重跑已完成的 ✅ 任务"], out_path
