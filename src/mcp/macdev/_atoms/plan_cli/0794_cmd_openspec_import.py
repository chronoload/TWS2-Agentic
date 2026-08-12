# 原子：cmd_openspec_import（原 plan_cli.py 第 794 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_openspec_import(args) -> int:
    """openspec-propose 机器化：把 change 的 tasks.md checkbox 导入为 plan 的 task。

    解析 `- [ ] 1.1 描述` 为 tasks 表记录（分组标题并入标题），
    使 openspec 任务可纳入现有 plan 体系（tdd/verify/review/dispatch 全可用）。
    """
    code, out = _run_openspec("status", "--change", args.change, "--json", cwd=args.cwd)
    if code != 0:
        print(f"[openspec] status 失败: {out.strip()}")
        return 1
    data = _parse_openspec_json(out)
    root = data.get("changeRoot", "")
    tasks_md = Path(root) / "tasks.md"
    if not tasks_md.exists():
        print(f"[openspec] 未找到 tasks.md（{tasks_md}）——先跑 openspec-propose 生成 artifacts")
        return 1

    entries: list[tuple[str, str, bool]] = []  # (num, title, done)
    group = ""
    for line in tasks_md.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if line.startswith("## "):
            group = line[3:].strip()
            continue
        m = re.match(r"^\s*- \[( |x)\]\s+(\d+\.\d+)\s+(.*)$", line)
        if m:
            title = f"[{group}] {m.group(3)}" if group else m.group(3)
            entries.append((m.group(2), title, m.group(1) == "x"))
    if not entries:
        print(f"[openspec] tasks.md 无 checkbox 任务（{tasks_md}）")
        return 1

    conn = _connect(args.db)
    plan_id = args.plan
    if not plan_id:
        cur = conn.cursor()
        cur.execute("INSERT INTO plans(title, goal, status) VALUES (?,?, 'open')",
                    (f"openspec: {args.change}", data.get("changeName", args.change)))
        conn.commit()
        plan_id = cur.lastrowid
        print(f"[openspec] 已创建 plan id={plan_id}（title=openspec: {args.change}）")

    cur = conn.cursor()
    for num, title, done in entries:
        cur.execute("INSERT INTO tasks(plan_id, title, detail, status) VALUES (?,?,?,?)",
                    (plan_id, title, f"openspec 任务编号 {num}（change: {args.change}）",
                     "done" if done else "open"))
    conn.commit()
    conn.close()
    print(f"[openspec] 已导入 {len(entries)} 个任务到 plan {plan_id} "
          f"（含 {sum(1 for e in entries if e[2])} 已完成）")
    return 0
