"""project.commands：产物目录初始化解析。

约定：`<name>-project/` 为唯一产物目录，内含 `.macdev-project`（记录 name）。
命令返回 (code, lines)（与 plan/log 同约定）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

MARKER = ".macdev-project"


def project_dir(name: str, base: Path = None) -> Path:
    base = base or Path.cwd()
    return base / f"{name}-project"


def cmd_init(name: str, git: bool = False, base: str = "") -> tuple:
    base_path = Path(base) if base else Path.cwd()
    target = project_dir(name, base_path)
    target.mkdir(parents=True, exist_ok=True)
    (target / MARKER).write_text(name, encoding="utf-8")
    # 标准产物子目录（audit 固定在此覆写）
    (target / "audit").mkdir(exist_ok=True)
    out = [f"[project] initialized → {target}"]
    if git:
        if not (target / ".git").exists():
            r = subprocess.run(["git", "init"], cwd=str(target),
                               capture_output=True, text=True)
            out.append(r.stdout.strip() or r.stderr.strip())
        else:
            out.append(f"[project] {target} 已是 git 仓库")
    out.append("约定：audit → audit/（重跑覆写）；plan → plans.db；log → logs.db + LOGS.md")
    return 0, out


def cmd_list(base: str = "") -> tuple:
    base_path = Path(base) if base else Path.cwd()
    found = sorted(p for p in base_path.glob("*-project")
                   if p.is_dir() and (p / MARKER).exists())
    if not found:
        return 0, ["[project] 无已初始化产物目录（先 python -m macdev project init --name <n>）"]
    out = ["| 产物目录 | 项目名 |", "|----------|--------|"]
    for p in found:
        name = (p / MARKER).read_text(encoding="utf-8").strip() or p.name
        out.append(f"| {p.name} | {name} |")
    return 0, out


def cmd_root(name: str, base: str = "") -> tuple:
    target = project_dir(name, Path(base) if base else Path.cwd())
    return 0, [str(target)]
