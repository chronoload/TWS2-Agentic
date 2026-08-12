# 原子：cmd_export（原 plan_cli.py 第 1431 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_export(args) -> int:
    conn = _connect(args.db)
    plan = conn.execute(
        "SELECT id, title, goal, arch, stack, global_constraints, status, created_at FROM plans WHERE id = ?",
        (args.id,)).fetchone()
    if not plan:
        print(f"[export] plan id={args.id} 不存在")
        conn.close()
        return 1
    tasks = conn.execute(
        "SELECT id, title, detail, files, req_ref, defect_ref, interfaces, status, review_status, review_findings FROM tasks WHERE plan_id = ? ORDER BY id",
        (args.id,)).fetchall()
    steps_by_task = {}
    step_rows = conn.execute(
        "SELECT id, task_id, ord, text, action, code, lang, run, expected, status "
        "FROM steps ORDER BY ord").fetchall()
    conn.close()
    for st in step_rows:
        steps_by_task.setdefault(st[1], []).append(st)

    req_map = _req_status_map()
    defect_map = _defect_status_map()
    if args.format == "writing-plans":
        lines = _render_writing_plans(plan, tasks, steps_by_task, req_map, defect_map)
    else:
        lines = _render_table(plan, tasks, steps_by_task, req_map, defect_map)

    lines += ["", "---", f"自动生成: {datetime.now().isoformat(timespec='seconds')} 由 `plan_cli.py`（format={args.format}）"]

    out = Path(args.out) if args.out else DOCS_DIR / f"PLAN_{plan[0]}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    # 同时写 JSON 便于机器索引
    (out.with_suffix(".json")).write_text(json.dumps({
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

    print(f"[export] plan.{args.format}.md → {out}")
    print(f"[export] plan.json → {out.with_suffix('.json')}")
    return 0
