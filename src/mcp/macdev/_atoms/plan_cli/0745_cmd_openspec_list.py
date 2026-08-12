# 原子：cmd_openspec_list（原 plan_cli.py 第 745 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_openspec_list(args) -> int:
    """openspec-explore 机器化：列出 changes（只读查询）。"""
    code, out = _run_openspec("list", "--json", cwd=args.cwd)
    if code != 0:
        print(f"[openspec] list 失败: {out.strip()}")
        return 1
    data = _parse_openspec_json(out)
    changes = data.get("changes", []) or []
    if not changes:
        print("[openspec] (无 active changes)")
        return 0
    for c in changes:
        name = c.get("name") or c.get("changeName") or ""
        schema = c.get("schemaName") or ""
        print(f"- {name}  (schema: {schema})")
    return 0
