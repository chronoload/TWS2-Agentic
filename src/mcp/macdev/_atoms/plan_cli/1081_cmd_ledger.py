# 原子：cmd_ledger（原 plan_cli.py 第 1081 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_ledger(args) -> int:
    """进度台账（executing-plans / subagent-driven-development 的 ledger 机器化）。

    skill 要求进度写入 ledger 文件（.superpowers/sdd/progress.md），防 context
    压缩后丢失位置。本命令把 plan 的执行进度渲染为 ledger：
      - 已完成任务（status=done + 步骤全 done）标记 ✅，未完成的列出待办
      - 输出到 --out（默认 <plan>-progress.md），可被 git 追踪
    """
    conn = _connect(args.db)
    plan = conn.execute(
        "SELECT id, title, status FROM plans WHERE id = ?", (args.plan,)).fetchone()
    if not plan:
        print(f"[ledger] plan id={args.plan} 不存在")
        conn.close()
        return 1
    tasks = conn.execute(
        "SELECT id, title, status FROM tasks WHERE plan_id = ? ORDER BY id",
        (args.plan,)).fetchall()
    step_rows = conn.execute(
        "SELECT task_id, ord, action, status FROM steps ORDER BY ord").fetchall()
    conn.close()

    by_task: dict[int, list] = {}
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
             f"> plan={args.plan} · 状态 {plan[2]} · 任务 {len(done_tasks)}/{len(tasks)} 完成 · 生成 {datetime.now().isoformat(timespec='seconds')}",
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

    out = Path(args.out) if args.out else DOCS_DIR / f"plan_{args.plan}_progress.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ledger] 进度台账 → {out}（完成 {len(done_tasks)}/{len(tasks)}）")
    print("[ledger] resume 提示：从「待执行」第一个未完成 task 继续，不要重跑已完成的 ✅ 任务")
    return 0
