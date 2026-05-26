from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable

from .persistence import MIN_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    CRON = "cron"
    INTERVAL = "interval"
    EVENT = "event"
    COURSE_SCHEDULE = "course_schedule"


@dataclass
class TriggerResult:
    should_fire: bool = False
    next_run_at: Optional[str] = None
    reason: str = ""


class CronTrigger:
    def __init__(self, cron_expr: str):
        self.cron_expr = cron_expr
        self._fields = cron_expr.strip().split()
        if len(self._fields) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expr}")

    def check(self, last_run_at: Optional[str] = None) -> TriggerResult:
        now = datetime.now()
        minute, hour, dom, month, dow = self._fields
        matched = True
        if minute != "*":
            matched = matched and now.minute == int(minute)
        if hour != "*":
            matched = matched and now.hour == int(hour)
        if dom != "*":
            matched = matched and now.day == int(dom)
        if month != "*":
            matched = matched and now.month == int(month)
        if dow != "*":
            matched = matched and now.weekday() == int(dow)

        if matched and last_run_at:
            try:
                last = datetime.fromisoformat(last_run_at)
                if (now - last).total_seconds() < MIN_INTERVAL_SECONDS:
                    return TriggerResult(
                        should_fire=False,
                        next_run_at=last_run_at,
                        reason="Minimum interval not reached",
                    )
            except (ValueError, TypeError):
                pass

        next_run = self._estimate_next(now)
        return TriggerResult(
            should_fire=matched,
            next_run_at=next_run,
            reason="Cron matched" if matched else "Cron not matched",
        )

    def _estimate_next(self, now: datetime) -> str:
        return (now + timedelta(hours=1)).isoformat()


class IntervalTrigger:
    def __init__(self, interval_seconds: int):
        self.interval_seconds = max(interval_seconds, MIN_INTERVAL_SECONDS)

    def check(self, last_run_at: Optional[str] = None) -> TriggerResult:
        now = datetime.now()
        if last_run_at is None:
            return TriggerResult(
                should_fire=True,
                next_run_at=(now + timedelta(seconds=self.interval_seconds)).isoformat(),
                reason="First run",
            )
        try:
            last = datetime.fromisoformat(last_run_at)
            elapsed = (now - last).total_seconds()
            if elapsed >= self.interval_seconds:
                return TriggerResult(
                    should_fire=True,
                    next_run_at=(now + timedelta(seconds=self.interval_seconds)).isoformat(),
                    reason=f"Interval elapsed ({elapsed:.0f}s >= {self.interval_seconds}s)",
                )
            return TriggerResult(
                should_fire=False,
                next_run_at=(last + timedelta(seconds=self.interval_seconds)).isoformat(),
                reason=f"Interval not elapsed ({elapsed:.0f}s < {self.interval_seconds}s)",
            )
        except (ValueError, TypeError):
            return TriggerResult(
                should_fire=True,
                next_run_at=(now + timedelta(seconds=self.interval_seconds)).isoformat(),
                reason="Invalid last_run_at",
            )


class EventTrigger:
    def __init__(self, event_pattern: str):
        self.event_pattern = event_pattern
        self._pending = False

    def notify_event(self, event_type: str):
        import fnmatch
        if fnmatch.fnmatch(event_type, self.event_pattern):
            self._pending = True

    def check(self, last_run_at: Optional[str] = None) -> TriggerResult:
        now = datetime.now()
        if self._pending:
            self._pending = False
            return TriggerResult(
                should_fire=True,
                next_run_at=(now + timedelta(hours=1)).isoformat(),
                reason="Event matched",
            )
        return TriggerResult(
            should_fire=False,
            next_run_at=None,
            reason="No matching event",
        )


class CourseScheduleTrigger:
    def __init__(self, schedule_config: Dict[str, Any]):
        self.schedule = schedule_config.get("schedule", [])
        self.remind_before_minutes = schedule_config.get("remind_before_minutes", 30)

    def check(self, last_run_at: Optional[str] = None) -> TriggerResult:
        now = datetime.now()
        current_day = now.weekday()
        current_time = now.hour * 60 + now.minute

        for entry in self.schedule:
            day = entry.get("day", -1)
            start_time_str = entry.get("start_time", "00:00")
            try:
                parts = start_time_str.split(":")
                start_minutes = int(parts[0]) * 60 + int(parts[1])
            except (ValueError, IndexError):
                continue

            remind_at = start_minutes - self.remind_before_minutes
            if day == current_day and remind_at <= current_time < start_minutes:
                if last_run_at:
                    try:
                        last = datetime.fromisoformat(last_run_at)
                        if (now - last).total_seconds() < MIN_INTERVAL_SECONDS:
                            return TriggerResult(
                                should_fire=False,
                                reason="Minimum interval not reached",
                            )
                    except (ValueError, TypeError):
                        pass
                return TriggerResult(
                    should_fire=True,
                    next_run_at=(now + timedelta(hours=2)).isoformat(),
                    reason=f"Course reminder: {entry.get('name', 'Unknown')}",
                )

        return TriggerResult(
            should_fire=False,
            next_run_at=None,
            reason="No course at this time",
        )


def create_trigger(trigger_type: TriggerType, config: Dict[str, Any]):
    if trigger_type == TriggerType.CRON:
        return CronTrigger(config.get("cron_expr", "0 * * * *"))
    elif trigger_type == TriggerType.INTERVAL:
        return IntervalTrigger(config.get("interval_seconds", 1800))
    elif trigger_type == TriggerType.EVENT:
        return EventTrigger(config.get("event_pattern", "*"))
    elif trigger_type == TriggerType.COURSE_SCHEDULE:
        return CourseScheduleTrigger(config)
    else:
        raise ValueError(f"Unknown trigger type: {trigger_type}")


__all__ = [
    "TriggerType", "TriggerResult",
    "CronTrigger", "IntervalTrigger", "EventTrigger", "CourseScheduleTrigger",
    "create_trigger",
]
