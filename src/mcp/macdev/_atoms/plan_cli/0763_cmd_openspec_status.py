# 原子：cmd_openspec_status（原 plan_cli.py 第 763 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_openspec_status(args) -> int:
    """openspec-explore 机器化：change 的 artifacts 完成度 + tasks.md checkbox 进度。"""
    code, out = _run_openspec("status", "--change", args.change, "--json", cwd=args.cwd)
    if code != 0:
        print(f"[openspec] status 失败: {out.strip()}")
        return 1
    data = _parse_openspec_json(out)
    if not data:
        print(f"[openspec] change '{args.change}' 不存在")
        return 1
    print(f"[openspec] change: {data.get('changeName', args.change)}  "
          f"schema: {data.get('schemaName', '?')}  complete: {data.get('isComplete', False)}")
    for a in data.get("artifacts", []) or []:
        st = a.get("status", "?")
        icon = "✅" if st == "done" else ("🕓" if st == "ready" else "⛔")
        missing = f" (缺: {', '.join(a.get('missingDeps', []) or [])})" if a.get("missingDeps") else ""
        print(f"  {icon} {a.get('id')}: {st}{missing}")
    root = data.get("changeRoot", "")
    tasks_md = Path(root) / "tasks.md"
    if tasks_md.exists():
        done = total = 0
        for line in tasks_md.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*- \[( |x)\]\s+\d+\.\d+", line)
            if m:
                total += 1
                if m.group(1) == "x":
                    done += 1
        print(f"[openspec] tasks: {done}/{total} 完成")
    return 0
