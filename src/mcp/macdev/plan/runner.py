from __future__ import annotations
from ..core.types import Result
from .model import Plan
from .tdd import tdd_check
from .export import export_md


def run_plan(engine, plan: Plan, action: str, out_dir) -> Result:
    if action == "tdd":
        issues = tdd_check(plan)
        engine.bus.emit("plan.state.changed", {"action": "tdd", "issues": len(issues)})
        return Result(ok=len(issues) == 0, data={"issues": issues})
    if action == "export":
        md = export_md(plan)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "PLAN.md"
        p.write_text(md, encoding="utf-8")
        engine.bus.emit("plan.state.changed", {"action": "export", "file": str(p)})
        return Result(ok=True, artifacts=[str(p)])
    return Result(ok=False, error=f"未知 action: {action}")
