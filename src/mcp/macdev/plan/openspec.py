"""plan.openspec：openspec CLI 桥接（list/status/import/export/sync-specs）。
从 plan_cli 原子重组；openspec 可执行与 requirement 写入命令均可配置（零 TS2 特化）。
"""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path


def _openspec_exe() -> str:
    """定位 openspec CLI（优先 PATH，找不到时用裸名让 subprocess 报错）。"""
    return shutil.which("openspec") or "openspec"


def _run_openspec(*cmd: str, cwd: str = "") -> tuple:
    """运行 openspec CLI，返回 (exit_code, stdout)。"""
    try:
        r = subprocess.run([_openspec_exe(), *cmd], capture_output=True, text=True,
                           cwd=cwd or ".", timeout=60, encoding="utf-8")
        return r.returncode, (r.stdout or "")
    except Exception as e:
        return 1, f"openspec 调用失败: {e}"


def _parse_openspec_json(out: str) -> dict:
    try:
        return json.loads(out)
    except Exception:
        return {}


def _openspec_change_root(change: str, cwd: str = "") -> str:
    code, out = _run_openspec("list", "--json", cwd=cwd)
    if code != 0:
        return ""
    data = _parse_openspec_json(out)
    for c in data.get("changes", []) or []:
        if c.get("name") == change:
            return c.get("root") or c.get("directory") or ""
    return ""


def cmd_list(cwd: str = "") -> tuple:
    """列出 changes（只读查询）。"""
    code, out = _run_openspec("list", "--json", cwd=cwd)
    if code != 0:
        return 1, [f"[openspec] list 失败: {out.strip()}"]
    changes = _parse_openspec_json(out).get("changes", []) or []
    if not changes:
        return 0, ["[openspec] (无 active changes)"]
    return 0, [f"- {c.get('name') or c.get('changeName') or ''}  (schema: {c.get('schemaName') or ''})"
               for c in changes]


def cmd_status(change: str, cwd: str = "") -> tuple:
    """change 状态（只读查询）。"""
    code, out = _run_openspec("status", change, cwd=cwd)
    if code != 0:
        return 1, [f"[openspec] status 失败: {out.strip()}"]
    return 0, (out.strip().splitlines() or ["[openspec] (无输出)"])


def cmd_import(change: str, cwd: str = "") -> tuple:
    """导入/应用 change。"""
    code, out = _run_openspec("import", change, cwd=cwd)
    if code != 0:
        return 1, [f"[openspec] import 失败: {out.strip()}"]
    return 0, (out.strip().splitlines() or ["[openspec] import 完成"])


def cmd_export(change: str, cwd: str = "") -> tuple:
    """导出 change 为文档。"""
    code, out = _run_openspec("export", change, cwd=cwd)
    if code != 0:
        return 1, [f"[openspec] export 失败: {out.strip()}"]
    return 0, (out.strip().splitlines() or ["[openspec] export 完成"])


def cmd_sync_specs(change: str, cwd: str = "", req_cli: str = "") -> tuple:
    """openspec-sync-specs：delta specs → requirements 条目。
    req_cli：写入 requirements 的命令模板（如 "python requirement_cli.py"），为空则仅统计。"""
    root = _openspec_change_root(change, cwd)
    if not root:
        return 1, [f"[openspec] change '{change}' 不存在"]
    specs_dir = Path(root) / "specs"
    if not specs_dir.exists():
        return 0, [f"[openspec] 无 delta specs（{specs_dir}）"]

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
                status = ("ADDED" if "ADDED" in section else "MODIFIED" if "MODIFIED" in section
                          else "REMOVED" if "REMOVED" in section else "RENAMED" if "RENAMED" in section else "")
                if status == "ADDED":
                    added += 1
                elif status == "MODIFIED":
                    modded += 1
                elif status == "REMOVED":
                    removed += 1
                elif status == "RENAMED":
                    renamed += 1
                if req_cli and status in ("ADDED", "MODIFIED", "REMOVED", "RENAMED"):
                    import shlex
                    subprocess.run([*shlex.split(req_cli), "add", "--kind", "spec", "--name", name,
                                    "--detail", f"openspec {status} change={change} ({rel})"],
                                   capture_output=True, text=True)
    return 0, [f"[openspec] sync-specs 完成：ADDED={added} MODIFIED={modded} "
               f"REMOVED={removed} RENAMED={renamed}" +
               ("" if req_cli else "（未配置 --req-cli，仅统计）")]
