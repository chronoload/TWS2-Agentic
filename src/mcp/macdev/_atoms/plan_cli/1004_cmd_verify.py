# 原子：cmd_verify（原 plan_cli.py 第 1004 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_verify(args) -> int:
    """完成门禁（verification-before-completion）：聚合检查 plan 是否可宣告完成。

    对齐 superpowers:verification-before-completion 的 Iron Law——
    「无新鲜验证证据不得宣告完成」。聚合四类证据：
      (a) TDD 合规：tdd check 结果（test/implement 顺序、缺测试等）
      (b) 静态缺陷：任务绑定的缺陷是否已在 extractor 报告中消失
      (c) 测试文件：绑定缺陷的任务是否有落盘的回归测试文件
      (d) 步骤完成：task 的步骤是否全部 done（executing 进度）
    任一失败 → 退出码 1（门禁拒绝）；全绿 → 0（可宣告完成）。
    """
    conn = _connect(args.db)
    plan = conn.execute(
        "SELECT id, title, status FROM plans WHERE id = ?", (args.plan,)).fetchone() \
        if args.plan else None
    if args.plan and not plan:
        print(f"[verify] plan id={args.plan} 不存在")
        conn.close()
        return 1
    tasks = conn.execute(
        "SELECT id, title, detail, files, req_ref, defect_ref, interfaces, status, review_status FROM tasks WHERE 1=1"
        + (" AND plan_id = ?" if args.plan else ""),
        (args.plan,) if args.plan else ()).fetchall()
    step_rows = conn.execute(
        "SELECT task_id, ord, action, run, expected, status FROM steps ORDER BY ord").fetchall()
    conn.close()

    current_ids = {d["id"] for d in _load_defects()}
    steps_by_task: dict[int, list] = {}
    for st in step_rows:
        steps_by_task.setdefault(st[0], []).append(st)

    failures: list[tuple[str, str]] = []
    scope_txt = f"plan={args.plan} '{plan[1]}'" if plan else "全部任务"

    # (a) TDD 合规 + (b) 缺陷 + (c) 测试文件 + (d) 步骤完成 + (e) review 门禁
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
            # 测试文件存在性：task files 中 Test: 行指向的文件
            test_files = [ln.split(":", 1)[1].strip() for ln in (files or "").splitlines()
                          if ln.strip().lower().startswith("test:")]
            if test_files and not all((PROJECT_ROOT / tf).exists() for tf in test_files):
                failures.append((title, "任务声明的测试文件不存在: " + ", ".join(test_files)))

        if tstatus != "done":
            undone = [s for s in steps if s[5] != "done"]
            failures.append((title, f"任务状态 {tstatus}，{len(undone)} 个步骤未完成"))

        if review_status != "approved":
            failures.append((title, f"review 未通过（状态 {review_status}）——未批准的代码不得宣告完成"))

    if not tasks:
        failures.append(("(无任务)", "范围内没有任务"))

    print(f"[verify] 完成门禁检查（{scope_txt}）— {len(tasks)} 个任务\n")
    if not failures:
        print("  ✅ 全部通过：TDD 合规 · 缺陷清零 · 测试就位 · 步骤完成 · review 通过")
        print("  ✅ 可宣告完成（evidence: 见上方逐项证据）")
        return 0
    for title, msg in failures:
        print(f"  ❌ {title} — {msg}")
    print(f"\n[verify] {len(failures)} 项未通过 → 门禁拒绝，不得宣告完成。")
    print("        修复后重跑：`python mcp/interface_chain_extractor.py && python mcp/plan_cli.py verify --plan N`")
    return 1
