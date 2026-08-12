from __future__ import annotations
from .model import Plan


def tdd_check(plan: Plan) -> list[dict]:
    """TDD 合规：test_missing（有 implement 无 test）/ test_after_implement / test_unverifiable。"""
    issues = []
    for task in plan.tasks:
        acts = [s.action for s in task.steps]
        if "implement" in acts and "test" not in acts:
            issues.append({"kind": "test_missing", "task": task.title})
        first_impl = next((i for i, a in enumerate(acts) if a == "implement"), None)
        first_test = next((i for i, a in enumerate(acts) if a == "test"), None)
        if first_impl is not None and first_test is not None and first_test > first_impl:
            issues.append({"kind": "test_after_implement", "task": task.title})
        for s in task.steps:
            if s.action == "test" and (not s.run or not s.expected):
                issues.append({"kind": "test_unverifiable", "task": task.title})
    return issues
