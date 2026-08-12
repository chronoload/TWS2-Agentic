from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    name: str
    data: dict = field(default_factory=dict)


@dataclass
class Result:
    ok: bool = True
    data: dict = field(default_factory=dict)
    artifacts: list = field(default_factory=list)  # [(path, kind)]
    error: str = ""
