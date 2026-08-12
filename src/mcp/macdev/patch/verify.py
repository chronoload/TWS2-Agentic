"""patch.verify：自演化闭环验证——应用补丁后重跑审计，比较缺陷集合是否收敛。"""
from __future__ import annotations
from pathlib import Path
from ..core.types import Result
from .gen import load_issues


def count_issues(db: Path | str) -> dict:
    """当前审计缺陷计数（按维度）。"""
    issues = load_issues(db)
    counter: dict = {}
    for i in issues:
        counter[i["kind"]] = counter.get(i["kind"], 0) + 1
    return counter


def verify_patches(engine, db_before: Path | str, db_after: Path | str,
                   expected_kinds: tuple = ()) -> Result:
    """比较补丁前后的缺陷集合。
    db_after 为空或不存在 → 提示需重跑 audit 后再验。"""
    before = count_issues(db_before)
    if not Path(db_after).exists():
        return Result(ok=False,
                      data={"before": before},
                      error="db_after 不存在：请先重跑 audit 生成新 interface_chain.db 再 verify")
    after = count_issues(db_after)
    total_before = sum(before.values())
    total_after = sum(after.values())
    converged = total_after <= total_before
    engine.bus.emit("patch.verified", {"before": total_before, "after": total_after,
                                       "converged": converged})
    return Result(ok=converged, data={"before": before, "after": after,
                                      "total_before": total_before,
                                      "total_after": total_after})
