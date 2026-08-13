"""Engine 薄门面：只做装配与调度，无业务逻辑。"""
from __future__ import annotations
from pathlib import Path
from .registry import Registry
from .bus import EventBus
from .types import Result


class Engine:
    def __init__(self, registry: Registry, bus: EventBus) -> None:
        self.registry = registry
        self.bus = bus

    def run_audit(self, task, out_dir: Path) -> Result:
        from ..audit.runner import run_audit
        return run_audit(self, task, out_dir)

    def run_plan(self, plan, action: str, out_dir=None) -> Result:
        from ..plan.runner import run_plan
        return run_plan(self, plan, action, out_dir)
