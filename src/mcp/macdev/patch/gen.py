"""patch.gen：从审计缺陷生成自演化补丁脚本（固化到 out_dir/*.py）。"""
from __future__ import annotations
import re
import sqlite3
from pathlib import Path
from ..core.types import Result
from .generators import build_patch
from .rules import strategy_for


def load_issues(db: Path | str) -> list:
    """从 interface_chain.db 各缺陷表归一化为 issue dict 列表。"""
    path = Path(db)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.text_factory = str
    issues: list = []
    try:
        for row in conn.execute("SELECT kind, attr, file, line, obj, default_value, detail "
                                "FROM defuse_issues"):
            kind, attr, file, line, obj, dv, detail = row
            issues.append({"kind": kind, "attr": attr or obj, "file": file,
                           "line": line or 0, "detail": detail})
        for row in conn.execute("SELECT kind, attr, file, line, detail FROM flag_lifecycle"):
            kind, attr, file, line, detail = row
            issues.append({"kind": kind, "attr": attr, "file": file,
                           "line": line or 0, "detail": detail})
        for row in conn.execute("SELECT 'missing_behavior', entry, file, detail "
                                "FROM behavior_issues"):
            kind, entry, file, detail = row
            issues.append({"kind": kind, "attr": entry, "file": file,
                           "line": 0, "detail": detail})
        for row in conn.execute("SELECT kind, fn, file, line, detail FROM merge_direction"):
            kind, fn, file, line, detail = row
            issues.append({"kind": kind, "attr": fn, "file": file,
                           "line": line or 0, "detail": detail})
        for row in conn.execute("SELECT kind, consumer, file, line, detail FROM id_source"):
            kind, consumer, file, line, detail = row
            issues.append({"kind": kind, "attr": consumer, "file": file,
                           "line": line or 0, "detail": detail})
        for row in conn.execute("SELECT kind, file, line, value FROM hardcoded"):
            kind, file, line, value = row
            issues.append({"kind": f"hardcoded_{kind}", "attr": "", "file": file,
                           "line": line or 0, "detail": value})
    finally:
        conn.close()
    return issues


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", s)[:60]


def _rel_to_root(file: str, root: Path) -> str:
    """绝对路径缺陷定位 → 相对 root（补丁脚本 file 字段用相对路径）。"""
    if not file:
        return ""
    p = Path(file)
    if p.is_absolute():
        try:
            return p.relative_to(root).as_posix()
        except ValueError:
            return file
    return file


def gen_patches(engine, db: Path | str, root: Path, out_dir: Path,
                rules: dict = None) -> Result:
    """逐缺陷生成补丁脚本并落盘 → Result（artifacts = 脚本路径列表）。
    生成器经 registry.create("patch.generator", strategy) 工厂装配（插件平级）。"""
    issues = load_issues(db)
    for issue in issues:
        issue["file"] = _rel_to_root(issue.get("file", ""), root)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for i, issue in enumerate(issues, 1):
        rule = strategy_for(issue["kind"], rules)
        try:
            generator = engine.registry.create("patch.generator", rule["strategy"])
            script = build_patch(issue, root, rules, generator=generator)
        except KeyError:
            script = build_patch(issue, root, rules)  # 缺省映射兜底
        except Exception:
            continue
        if not script.operations:
            continue
        fname = f"{i:04d}_{_safe_name(script.id)}.py"
        p = out_dir / fname
        p.write_text(script.to_py(root=str(root)), encoding="utf-8")
        artifacts.append(str(p))
    engine.bus.emit("patch.generated", {"issues": len(issues), "patches": len(artifacts)})
    return Result(ok=True, data={"issues": len(issues), "patches": len(artifacts)},
                  artifacts=artifacts)
