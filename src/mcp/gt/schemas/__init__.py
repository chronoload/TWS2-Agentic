from __future__ import annotations

from dataclasses import field
from typing import Any, Literal

GTStatus = Literal["PROVED", "PARTIAL", "MISFORMALIZED", "COUNTEREXAMPLE", "BLOCKED"]


from dataclasses import dataclass


@dataclass
class AttemptSummary:
    status: str = ""
    main_idea: str = ""
    closed_lemmas: list[str] = field(default_factory=list)
    remaining_gaps: list[str] = field(default_factory=list)
    lean_feedback: str = ""
    rater_criticism: str = ""
    elo: int | None = None

    def to_markdown(self, index: int | None = None) -> str:
        heading = f"Attempt {index}" if index is not None else "Attempt"
        closed = "\n".join(f"- {item}" for item in self.closed_lemmas) or "- None"
        gaps = "\n".join(f"- {item}" for item in self.remaining_gaps) or "- None"
        return "\n".join(
            [
                heading,
                f"Status: {self.status}",
                f"Elo: {self.elo if self.elo is not None else 'unrated'}",
                "Main idea:",
                self.main_idea or "Not recorded.",
                "Closed lemmas:",
                closed,
                "Remaining gaps:",
                gaps,
                "Rater criticism:",
                self.rater_criticism or "Not rated.",
                "Lean feedback:",
                self.lean_feedback or "No Lean feedback.",
            ]
        )


@dataclass
class GTProblem:
    problem_path: str = ""
    mode: str = "basic"
    context_path: str | None = None
    allowed_references: list[str] = field(default_factory=list)
    forbidden_assumptions: list[str] = field(default_factory=list)

    @classmethod
    def from_path(
        cls,
        problem_path: str,
        mode: str = "basic",
        context_path: str | None = None,
    ) -> "GTProblem":
        return cls(
            problem_path=problem_path,
            mode=mode,
            context_path=context_path,
        )


@dataclass
class GTResult:
    status: str = ""
    formal_artifact: str = ""
    natural_language_summary: str = ""
    gap_ledger: str = ""
    assumption_audit: str = ""
    rater_report: str = ""

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        data = asdict(self)
        return {key: str(value) for key, value in data.items()}
