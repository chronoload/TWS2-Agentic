# 原子：cmd_openspec_export（原 plan_cli.py 第 848 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_openspec_export(args) -> int:
    """openspec-apply-change 机器化：把 plan 的 task 完成状态回写 tasks.md checkbox。

    按 detail 中的「openspec 任务编号 N.M」匹配 checkbox，任务 done → `- [x]`，
    使 openspec status 反映真实 apply 进度。
    """
    code, out = _run_openspec("status", "--change", args.change, "--json", cwd=args.cwd)
    if code != 0:
        print(f"[openspec] status 失败: {out.strip()}")
        return 1
    data = _parse_openspec_json(out)
    root = data.get("changeRoot", "")
    tasks_md = Path(root) / "tasks.md"
    if not tasks_md.exists():
        print(f"[openspec] 未找到 tasks.md（{tasks_md}）——无 checkbox 可回写")
        return 1

    conn = _connect(args.db)
    rows = conn.execute(
        "SELECT id, title, status, detail FROM tasks WHERE plan_id = ?", (args.plan,)).fetchall()
    conn.close()
    # 编号 → task 完成状态
    num_done: dict[str, bool] = {}
    for _tid, _title, status, detail in rows:
        m = re.search(r"openspec 任务编号 (\d+\.\d+)", detail or "")
        if m:
            num_done[m.group(1)] = (status == "done")

    lines = tasks_md.read_text(encoding="utf-8").splitlines()
    changed = 0
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)- \[( |x)\]\s+(\d+\.\d+)", line)
        if m and m.group(3) in num_done:
            mark = "x" if num_done[m.group(3)] else " "
            # 只替换 checkbox 标记，保留编号与描述
            new_line = line[:m.start(2)] + mark + line[m.end(2):]
            if new_line != line:
                lines[i] = new_line
                changed += 1
    tasks_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[openspec] 已回写 tasks.md：{changed} 行 checkbox 更新（plan={args.plan} → change={args.change}）")
    return 0
