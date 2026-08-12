# 原子：cmd_tdd_check（原 plan_cli.py 第 944 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_tdd_check(args) -> int:
    """TDD 合规性检查（红-绿-重构闭环）：
       - test_missing        🔴 有 implement 步骤但无 test 步骤（RED 缺失）
       - test_after_implement 🟠 test 步骤排在首个 implement 之后（顺序违反）
       - test_unverifiable   🟡 test 步骤缺 run 或 expected（无法断言红/绿）
       - defect_no_test      🔴 绑定静态缺陷的任务无 test 步骤（缺陷修复必须测试驱动）
    """
    conn = _connect(args.db)
    scope_sql = "SELECT id, title, defect_ref FROM tasks WHERE 1=1"
    scope_params: list = []
    if args.task:
        scope_sql += " AND id = ?"
        scope_params.append(args.task)
    elif args.plan:
        scope_sql += " AND plan_id = ?"
        scope_params.append(args.plan)
    tasks = conn.execute(scope_sql, scope_params).fetchall()

    step_rows = conn.execute(
        "SELECT task_id, ord, action, run, expected FROM steps ORDER BY ord").fetchall()
    conn.close()

    steps_by_task: dict[int, list] = {}
    for st in step_rows:
        steps_by_task.setdefault(st[0], []).append(st)

    findings: list[tuple[str, int, str]] = []  # (kind, task_id, detail)
    for tid, title, defect_ref in tasks:
        steps = steps_by_task.get(tid, [])
        test_idxs = [i for i, s in enumerate(steps) if s[2] == "test"]
        impl_idxs = [i for i, s in enumerate(steps) if s[2] == "implement"]
        if impl_idxs and not test_idxs:
            findings.append(("test_missing", tid,
                             f"任务 '{title}' 有 implement 步骤但无 test 步骤（TDD 必须先写失败测试）"))
        if test_idxs and impl_idxs and min(test_idxs) > min(impl_idxs):
            findings.append(("test_after_implement", tid,
                             f"任务 '{title}' 的 test 步骤排在首个 implement 之后（应 Red→Green→Refactor）"))
        for i in test_idxs:
            s = steps[i]
            if not (s[3] and s[4]):
                findings.append(("test_unverifiable", tid,
                                 f"任务 '{title}' 的 test 步骤缺 run 或 expected（无法断言失败/通过）"))
        # 静态缺陷融合：绑定缺陷的任务必须有 test（修复必须先写回归测试再实现）
        if defect_ref and not test_idxs:
            findings.append(("defect_no_test", tid,
                             f"任务 '{title}' 绑定静态缺陷 {defect_ref} 但无 test 步骤"
                             "（缺陷修复必须测试驱动：先写失败测试，再修复实现）"))

    if not findings:
        print("[tdd] 全部任务符合 TDD 闭环（Red→Green→Refactor）✅")
        return 0
    for kind, tid, detail in findings:
        icon = {"test_missing": "🔴", "test_after_implement": "🟠",
                "test_unverifiable": "🟡", "defect_no_test": "🔴"}.get(kind, "⚠️")
        print(f"  {icon} [{kind}] task={tid} — {detail}")
    print(f"[tdd] 共 {len(findings)} 处不合规（任务范围: "
          + (f"plan={args.plan}" if args.plan else f"task={args.task}" if args.task else "全部"))
    return 1
