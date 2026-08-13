"""plan 能力插件（开发流程）。"""
from .model import Plan, Task, Step
from .runner import run_plan


def register(registry) -> None:
    registry.register("plan.runner", "default", run_plan)
