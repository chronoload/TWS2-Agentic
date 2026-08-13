from __future__ import annotations
from .model import Plan


class PlanState:
    @staticmethod
    def next(plan: Plan) -> str:
        if plan.status == "done":
            return "archived"
        if any(t.status == "in_progress" for t in plan.tasks):
            return "active"
        if all(t.status == "done" for t in plan.tasks) and plan.tasks:
            return "done"
        return "ready"
