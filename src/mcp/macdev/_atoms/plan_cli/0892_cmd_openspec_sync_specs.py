# 原子：cmd_openspec_sync_specs（原 plan_cli.py 第 892 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_openspec_sync_specs(args) -> int:
    """openspec-sync-specs 机器化：delta specs → requirements 条目。

    解析 change 的 specs/**/*.md（ADDED/MODIFIED/REMOVED/RENAMED Requirements），
    调用 requirement_cli 写入 requirements.db（kind=spec，source=openspec）。
    """
    root = _openspec_change_root(args.change, args.cwd)
    if not root:
        print(f"[openspec] change '{args.change}' 不存在")
        return 1
    specs_dir = Path(root) / "specs"
    if not specs_dir.exists():
        print(f"[openspec] 无 delta specs（{specs_dir}）")
        return 0

    req_exe = ["python", str(MCP_ROOT / "requirement_cli.py")]
    added = modded = removed = renamed = 0
    for f in sorted(specs_dir.rglob("*.md")):
        text = f.read_text(encoding="utf-8")
        section = ""
        for line in text.splitlines():
            if line.startswith("## "):
                section = line[3:].strip()
            if "Requirements" not in section:
                continue
            if line.startswith("### Requirement:"):
                name = line.split(":", 1)[1].strip()
                rel = f"{f.parent.name}/{f.name}"
                if "ADDED" in section:
                    subprocess.run(req_exe + ["add", "--kind", "spec", "--name", name,
                                              "--detail", f"openspec change={args.change} ({rel})"],
                                   capture_output=True, text=True)
                    added += 1
                elif "MODIFIED" in section:
                    subprocess.run(req_exe + ["add", "--kind", "spec", "--name", name,
                                              "--detail", f"openspec MODIFIED change={args.change} ({rel})"],
                                   capture_output=True, text=True)
                    modded += 1
                elif "REMOVED" in section:
                    subprocess.run(req_exe + ["add", "--kind", "spec", "--name", name,
                                              "--detail", f"openspec REMOVED change={args.change} ({rel})"],
                                   capture_output=True, text=True)
                    removed += 1
                elif "RENAMED" in section:
                    subprocess.run(req_exe + ["add", "--kind", "spec", "--name", name,
                                              "--detail", f"openspec RENAMED change={args.change} ({rel})"],
                                   capture_output=True, text=True)
                    renamed += 1
    print(f"[openspec] sync-specs 完成：ADDED={added} MODIFIED={modded} REMOVED={removed} RENAMED={renamed}")
    return 0
