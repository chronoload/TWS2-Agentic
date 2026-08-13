from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Step:
    text: str
    action: str = "other"   # test | implement | run | commit | other
    code: str = ""
    lang: str = ""
    run: str = ""
    expected: str = ""
    status: str = "pending"
    ord: int = 0


@dataclass
class Task:
    id: int
    plan_id: int
    title: str
    status: str = "pending"   # pending | in_progress | done
    steps: list = field(default_factory=list)
    defect: str = ""
    req: str = ""


@dataclass
class Plan:
    id: int
    title: str
    goal: str = ""
    status: str = "open"      # open | active | done | archived
    tasks: list = field(default_factory=list)
