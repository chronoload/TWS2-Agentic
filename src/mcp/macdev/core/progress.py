"""扫描进度与超时预算（自演化：全量扫描友好，避免长时间无输出/无上限）。"""
from __future__ import annotations
import time


class ScanBudget:
    """进度打印 + 超时截断子集汇报。

    用法：
        budget = ScanBudget(total, label, interval=100, timeout=0)
        for f in files:
            budget.tick()
            if budget.expired():
                break   # 超时 → 截断为已处理子集，结果仍可汇报
    超时后 budget.truncated=True，runner 据此输出子集汇报并 emit 事件。
    多阶段复用：每个阶段前调用 budget.reset(total, label) 重新计数。
    """

    def __init__(self, total: int, label: str = "scan", interval: int = 100,
                 timeout: int = 0, quiet: bool = False):
        self.interval = interval
        self.quiet = quiet
        self.deadline = time.monotonic() + timeout if timeout > 0 else None
        self.total = max(total, 1)
        self.label = label
        self.done = 0
        self.truncated = False
        self._done_report = False

    def reset(self, total: int = 0, label: str = "") -> None:
        self.total = max(total or self.total, 1)
        if label:
            self.label = label
        self.done = 0
        self.truncated = False
        self._done_report = False

    def tick(self, n: int = 1) -> None:
        self.done += n
        if self.quiet:
            return
        shown = min(self.done, self.total)
        if shown >= self.total:
            if not self._done_report:
                self._done_report = True
                print(f"[macdev audit] {self.label}: {shown}/{self.total}", flush=True)
        elif shown % self.interval == 0:
            print(f"[macdev audit] {self.label}: {shown}/{self.total}", flush=True)

    def expired(self) -> bool:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.truncated = True
            return True
        return False

    def summary(self) -> dict:
        return {"label": self.label, "scanned": min(self.done, self.total),
                "total": self.total, "truncated": self.truncated}
