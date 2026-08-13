from __future__ import annotations

import re
import math
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .compiler import LeanCompiler, LeanFeedback

EVOLVE_START_RE = re.compile(r"EVOLVE-(?:BLOCK|VALUE)-START")
EVOLVE_END_RE = re.compile(r"EVOLVE-(?:BLOCK|VALUE)-END")
THEOREM_RE = re.compile(r"^\s*(?:theorem|lemma)\s+([A-Za-z0-9_'.]+)\b", re.MULTILINE)


GAP_TYPES = {"routine", "technical", "strategic", "library-missing", "conjectural"}


@dataclass
class Gap:
    identifier: str
    statement: str
    gap_type: str = "technical"
    depends_on: List[str] = field(default_factory=list)
    why_needed: str = ""
    current_evidence: str = ""
    lean_status: str = "not formalized"
    risk: str = ""
    next_step: str = ""

    def to_markdown(self) -> str:
        depends = ", ".join(self.depends_on) if self.depends_on else "None"
        return "\n".join([
            f"## Gap {self.identifier}",
            f"Statement: {self.statement}",
            f"Type: {self.gap_type}",
            f"Depends on: {depends}",
            f"Why needed: {self.why_needed or 'Not recorded.'}",
            f"Current evidence: {self.current_evidence or 'Not recorded.'}",
            f"Lean status: {self.lean_status}",
            f"Risk: {self.risk or 'Not recorded.'}",
            f"Next step: {self.next_step or 'Not recorded.'}",
        ])


@dataclass
class ValidationResult:
    accepted: bool
    status: str
    reason: str = ""
    repair_hint: str = ""
    lean_feedback: Any = None
    details: Dict[str, object] = field(default_factory=dict)

    def to_rejection_json(self) -> Dict[str, str]:
        return {
            "status": "REJECTED",
            "reason": self.reason,
            "repair_hint": self.repair_hint,
        }


@dataclass
class RatedSketch:
    index: int
    score: float
    summary: str
    critical_flaws: List[str] = field(default_factory=list)
    gap_quality: str = ""


@dataclass
class PopulationEntry:
    id: int
    code: str
    score: float = 0.0
    visits: int = 0
    wins: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AttemptSummary:
    status: str = "PARTIAL"
    main_idea: str = ""
    closed_lemmas: List[str] = field(default_factory=list)
    remaining_gaps: List[str] = field(default_factory=list)
    lean_feedback: str = ""
    rater_criticism: str = ""

    def to_markdown(self, index: Optional[int] = None) -> str:
        heading = f"Attempt {index}" if index is not None else "Attempt"
        closed = "\n".join(f"- {item}" for item in self.closed_lemmas) or "- None"
        gaps = "\n".join(f"- {item}" for item in self.remaining_gaps) or "- None"
        return "\n".join([
            heading,
            f"Status: {self.status}",
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
        ])


EVOLVE_START_RE = re.compile(r"EVOLVE-(?:BLOCK|VALUE)-START")
EVOLVE_END_RE = re.compile(r"EVOLVE-(?:BLOCK|VALUE)-END")
THEOREM_RE = re.compile(r"^\s*(?:theorem|lemma)\s+([A-Za-z0-9_'.]+)\b", re.MULTILINE)


def render_gap_ledger(gaps: List[Gap]) -> str:
    if not gaps:
        return "# GT Gap Ledger\n\nNo open gaps recorded.\n"
    return "# GT Gap Ledger\n\n" + "\n\n".join(gap.to_markdown() for gap in gaps) + "\n"


def default_gap_ledger(reason: str, lean_status: str = "not checked") -> str:
    return render_gap_ledger([
        Gap(
            identifier="G1",
            statement=reason,
            gap_type="technical",
            why_needed="The agent cannot certify PROVED until this item is closed.",
            lean_status=lean_status,
            risk="May hide a real hypothesis or formalization mismatch.",
            next_step="State the missing lemma precisely and check it independently.",
        )
    ])


def extract_gap_ledger(text: str) -> str:
    marker = "# GT Gap Ledger"
    if marker in text:
        return text[text.index(marker):].strip()
    lean_marker = "GT_GAP_LEDGER:"
    if lean_marker in text:
        return text[text.index(lean_marker):].strip()
    gaps = infer_gaps_from_sketch(text)
    return render_gap_ledger(gaps)


def infer_gaps_from_sketch(text: str) -> List[Gap]:
    gaps: List[Gap] = []
    if re.search(r"\bsorry\b|\badmit\b", text):
        gaps.append(Gap(
            identifier="G1",
            statement="Proof contains unresolved sorry/admit placeholder.",
            gap_type="technical",
            why_needed="Final output cannot contain unchecked proof holes.",
            lean_status="open",
            risk="The placeholder may contain the core theorem.",
            next_step="Replace the placeholder with a smaller checked lemma or proof.",
        ))
    fake_claims = detect_unverified_claims(text, allowed_references=[])
    for index, claim in enumerate(fake_claims, start=len(gaps) + 1):
        gaps.append(Gap(
            identifier=f"G{index}",
            statement=f"Unverified literature claim: {claim}",
            gap_type="library-missing",
            why_needed="The proof cannot rely on unnamed or unsupplied external theorems.",
            current_evidence="Claim was detected in the input but not in allowed references.",
            lean_status="unformalized",
            risk="May be fabricated or may require stronger hypotheses.",
            next_step="Provide an exact statement and either a formal theorem name or user-supplied reference.",
        ))
    return gaps


def detect_unverified_claims(text: str, allowed_references: Optional[List[str]] = None) -> List[str]:
    allowed = {item.lower() for item in (allowed_references or [])}
    claims: List[str] = []
    theorem_pattern = re.compile(
        r"([A-Z][A-Za-z]+(?:[-\u2013\u2014][A-Z][A-Za-z]+)*(?:\s+[A-Z][A-Za-z]+(?:[-\u2013\u2014][A-Z][A-Za-z]+)*)*\s+(?:compactness\s+)?theorem)"
    )
    for match in theorem_pattern.finditer(text):
        claim = match.group(1).strip()
        if claim.lower() not in allowed:
            claims.append(claim)
    return sorted(set(claims))


def detect_bad_gaps(text: str, target_statement: Optional[str] = None) -> List[str]:
    findings: List[str] = []
    if re.search(r"lemma\s+main_hidden_gap\b[\s\S]*?:=\s*by\s*\n\s*sorry", text):
        findings.append("lemma main_hidden_gap hides the main argument behind sorry")
    if target_statement:
        escaped = re.escape(target_statement.strip())
        if re.search(rf"lemma\s+\w+\s*:\s*{escaped}\s*:=\s*by\s*\n\s*sorry", text):
            findings.append("gap lemma restates the target theorem")
    if re.search(r"standard theorem", text, re.IGNORECASE) and "exact statement" not in text:
        findings.append("gap invokes an unverified standard theorem without an exact statement")
    return findings


def has_lean_holes(code: str) -> bool:
    return re.search(r"\bsorry\b|\badmit\b", code) is not None


def audit_hypotheses(text: str) -> tuple:
    """Return (markdown_audit, warnings, status_override)."""
    warnings: List[str] = []
    lowered = text.lower()

    if "poincare duality" in lowered or "poincar" in lowered:
        if "non-compact" in lowered or "noncompact" in lowered:
            warnings.append(
                "Poincare duality on non-compact manifolds needs compact-support, "
                "closed-manifold, or finite-type hypotheses; the supplied statement is too strong."
            )
        if "orient" not in lowered:
            warnings.append("Poincare duality usually needs orientability or twisted coefficients.")
        if "boundary" in lowered and "relative" not in lowered:
            warnings.append("Manifolds with boundary require relative/cohomology-with-compact-support variants.")

    if "compactness theorem" in lowered and re.search(r"[A-Z][A-Za-z]+[- ][A-Z][A-Za-z]+", text):
        warnings.append("Named compactness theorem is not verified unless supplied as an allowed reference.")

    status_override = "MISFORMALIZED" if any("too strong" in warning for warning in warnings) else None
    lines = [
        "# Hypothesis audit",
        "",
        "## Category and objects",
        "Not fully specified." if not text.strip() else "Derived from the supplied problem text/sketch.",
        "",
        "## Hypothesis warnings",
    ]
    lines.extend(f"- {warning}" for warning in warnings)
    if not warnings:
        lines.append("- No obvious hypothesis issue detected by the local audit.")
    lines.extend([
        "",
        "## Required manual checks",
        "- category and morphisms",
        "- equivalence relation",
        "- compactness and finite-type assumptions",
        "- basepoints and orientations",
        "- boundary terms and signs",
        "- functoriality/naturality",
        "- local-to-global steps",
    ])
    return "\n".join(lines) + "\n", warnings, status_override


class GTValidator:
    """Multi-layer validator for proof sketches."""

    forbidden_final_patterns = (
        (re.compile(r"\bsorry\b"), "final output contains sorry"),
        (re.compile(r"\badmit\b"), "final output contains admit"),
        (re.compile(r"^\s*axiom\b", re.MULTILINE), "final output declares an axiom"),
        (re.compile(r"\bunsafe\b"), "final output contains unsafe"),
        (re.compile(r"set_option\s+maxHeartbeats\s+0"), "final output disables maxHeartbeats"),
        (re.compile(r"by\s+native_decide"), "final output uses by native_decide"),
    )

    environment_exploit_patterns = (
        re.compile(r"set_option\s+maxHeartbeats\s+0"),
        re.compile(r"^\s*axiom\b", re.MULTILINE),
        re.compile(r"\bunsafe\b"),
    )

    def __init__(self, compiler: Any = None, *, allow_import_changes: bool = False, require_compile: bool = True) -> None:
        if compiler is None:
            from .compiler import LeanCompiler
            compiler = LeanCompiler()
        self.compiler = compiler
        self.allow_import_changes = allow_import_changes
        self.require_compile = require_compile

    def validate_candidate(
        self,
        original_code: str,
        candidate_code: str,
        *,
        final: bool = False,
    ) -> ValidationResult:
        checks = [
            self.check_marker_integrity(original_code, candidate_code),
            self.check_theorem_statement_unchanged(original_code, candidate_code),
            self.check_namespace_preserved(original_code, candidate_code),
            self.check_imports_unchanged(original_code, candidate_code),
            self.check_environment_exploit(candidate_code),
        ]
        if final:
            checks.append(self.check_forbidden_final_tokens(candidate_code))

        for result in checks:
            if not result.accepted:
                return result

        if final and self.require_compile:
            feedback = self.compiler.check_code(candidate_code)
            if not feedback.checked:
                return ValidationResult(
                    False, "REJECTED",
                    "Lean compile check could not be run",
                    "install Lean or inject a compiler adapter before accepting a final proof",
                    feedback,
                )
            if not feedback.compiles:
                return ValidationResult(
                    False, "REJECTED",
                    "final Lean compile failed",
                    "repair the Lean errors before returning PROVED",
                    feedback,
                )
            return ValidationResult(True, "ACCEPTED", lean_feedback=feedback)

        return ValidationResult(True, "ACCEPTED")

    def final_accepts(self, original_code: str, candidate_code: str) -> bool:
        return self.validate_candidate(original_code, candidate_code, final=True).accepted

    def integrity_failed(self, original_code: str, candidate_code: str) -> bool:
        return not self.validate_candidate(original_code, candidate_code, final=False).accepted

    def check_marker_integrity(self, original_code: str, candidate_code: str) -> ValidationResult:
        if _outside_evolve_text(original_code) != _outside_evolve_text(candidate_code):
            return ValidationResult(
                False, "REJECTED",
                "theorem statement changed outside EVOLVE markers",
                "revert theorem signature and only add helper lemmas inside EVOLVE-BLOCK",
            )
        return ValidationResult(True, "ACCEPTED")

    def check_theorem_statement_unchanged(self, original_code: str, candidate_code: str) -> ValidationResult:
        original = _theorem_headers_without_evolve(original_code)
        candidate = _theorem_headers_without_evolve(candidate_code)
        if original != candidate:
            return ValidationResult(
                False, "REJECTED",
                "theorem statement changed outside EVOLVE markers",
                "restore the original theorem or lemma signature",
            )
        return ValidationResult(True, "ACCEPTED")

    def check_imports_unchanged(self, original_code: str, candidate_code: str) -> ValidationResult:
        if self.allow_import_changes:
            return ValidationResult(True, "ACCEPTED")
        if _imports(original_code) != _imports(candidate_code):
            return ValidationResult(
                False, "REJECTED",
                "imports changed",
                "keep imports unchanged unless the run configuration explicitly allows it",
            )
        return ValidationResult(True, "ACCEPTED")

    def check_namespace_preserved(self, original_code: str, candidate_code: str) -> ValidationResult:
        if _namespaces(original_code) != _namespaces(candidate_code):
            return ValidationResult(
                False, "REJECTED",
                "namespace declarations changed",
                "preserve the original namespace structure",
            )
        return ValidationResult(True, "ACCEPTED")

    def check_environment_exploit(self, code: str) -> ValidationResult:
        for pattern in self.environment_exploit_patterns:
            if pattern.search(code):
                return ValidationResult(
                    False, "REJECTED",
                    "environment exploit or forbidden declaration detected",
                    "remove unsafe options, axioms, and unsafe declarations",
                )
        return ValidationResult(True, "ACCEPTED")

    def check_forbidden_final_tokens(self, code: str) -> ValidationResult:
        for pattern, reason in self.forbidden_final_patterns:
            if pattern.search(code):
                return ValidationResult(
                    False, "REJECTED",
                    reason,
                    "replace the placeholder or forbidden construct with a checked proof",
                )
        return ValidationResult(True, "ACCEPTED")


class GTRater:
    """Deterministic local rater for proof sketches."""

    def rate(self, sketch: str, *, index: int = 1, target_statement: Optional[str] = None) -> RatedSketch:
        flaws: List[str] = []
        score = 100.0

        bad_gaps = detect_bad_gaps(sketch, target_statement)
        if bad_gaps:
            flaws.extend(f"Bad strategic gap: {item}" for item in bad_gaps)
            score -= 35 * len(bad_gaps)

        claims = detect_unverified_claims(sketch, allowed_references=[])
        if claims:
            flaws.extend(f"Unverified claim: {claim}" for claim in claims)
            score -= 15 * len(claims)

        if has_lean_holes(sketch):
            score -= 10
        if re.search(r"\bcompact\b|\borient|\bboundary|\btransvers", sketch, re.IGNORECASE):
            score += 5
        if "# GT Gap Ledger" in sketch or "GT_GAP_LEDGER" in sketch:
            score += 8

        gap_quality = "bad strategic gaps detected" if bad_gaps else "no bad strategic gap detected locally"
        summary = "Sketch exposes some auditable structure." if not flaws else "Sketch has policy violations."
        return RatedSketch(index, score, summary, flaws, gap_quality)

    def rank(self, sketches: List[str]) -> tuple:
        rated = [self.rate(sketch, index=index) for index, sketch in enumerate(sketches, start=1)]
        rated.sort(key=lambda item: item.score, reverse=True)
        decision = " > ".join(str(item.index) for item in rated)
        report_lines = ["# GTRater Report", ""]
        for item in rated:
            flaws = "\n".join(f"- {flaw}" for flaw in item.critical_flaws) or "- None detected locally."
            report_lines.extend([
                f"## Sketch {item.index}",
                f"Score: {item.score:.1f}",
                f"Summary: {item.summary}",
                "Critical flaw analysis:",
                flaws,
                f"Gap quality analysis: {item.gap_quality}",
                "",
            ])
        report_lines.append(f"<decision>{decision}</decision>")
        return rated, "\n".join(report_lines) + "\n"


class PopulationDB:
    """In-memory population database for evolution mode."""

    def __init__(self, elite_pool_size: int = 64) -> None:
        self.elite_pool_size = elite_pool_size
        self._next_id = 1
        self._entries: List[PopulationEntry] = []

    def initialize(self, initial_sketch: str) -> PopulationEntry:
        self._entries.clear()
        self._next_id = 1
        return self.add(initial_sketch, score=0.0, metadata={"origin": "initial"})

    def add(self, code: str, *, score: float = 0.0, metadata: Optional[Dict[str, Any]] = None) -> PopulationEntry:
        entry = PopulationEntry(self._next_id, code, score=score, metadata=metadata or {})
        self._next_id += 1
        self._entries.append(entry)
        self._entries.sort(key=lambda item: item.score, reverse=True)
        del self._entries[self.elite_pool_size:]
        return entry

    def entries(self) -> List[PopulationEntry]:
        return list(self._entries)

    def best(self) -> PopulationEntry:
        if not self._entries:
            raise ValueError("population is empty")
        return max(self._entries, key=lambda item: item.score)


class PUcbSampler:
    """P-UCB (Upper Confidence Bound) sampler for population-based search."""

    def __init__(self, exploration_c: float = 0.2) -> None:
        self.exploration_c = exploration_c

    def sample(self, entries: List[PopulationEntry]) -> PopulationEntry:
        if not entries:
            raise ValueError("cannot sample an empty population")
        total_visits = sum(entry.visits for entry in entries) + 1

        def value(entry: PopulationEntry) -> float:
            exploitation = entry.score
            exploration = self.exploration_c * math.sqrt(math.log(total_visits + 1) / (entry.visits + 1))
            return exploitation + exploration

        selected = max(entries, key=value)
        selected.visits += 1
        return selected


class GoalCache:
    """Cache for repeated goal/feedback strings."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._cache: Dict[str, str] = {}

    def get(self, key: str) -> Optional[str]:
        if not self.enabled:
            return None
        return self._cache.get(key)

    def set(self, key: str, value: str) -> None:
        if self.enabled:
            self._cache[key] = value


def replace_first_hole_inside_evolve(code: str, replacement: str) -> tuple:
    lines = code.splitlines(keepends=True)
    inside = False
    for index, line in enumerate(lines):
        if EVOLVE_START_RE.search(line):
            inside = True
        if inside and re.search(r"\b(sorry|admit)\b", line):
            indent = re.match(r"\s*", line).group(0)
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f"{indent}{replacement}{newline}"
            return "".join(lines), True
        if EVOLVE_END_RE.search(line):
            inside = False
    return code, False


def apply_search_replace(code: str, search: str, replace: str) -> str:
    if search not in code:
        raise ValueError("search text not found")
    return code.replace(search, replace, 1)


def _outside_evolve_text(code: str) -> str:
    lines = code.splitlines()
    out: List[str] = []
    inside = False
    for line in lines:
        if EVOLVE_START_RE.search(line):
            inside = True
            out.append(line)
            continue
        if EVOLVE_END_RE.search(line):
            inside = False
            out.append(line)
            continue
        if not inside:
            out.append(line.rstrip())
    return "\n".join(out).strip()


def _imports(code: str) -> List[str]:
    return [line.strip() for line in code.splitlines() if line.strip().startswith("import ")]


def _namespaces(code: str) -> List[str]:
    return [
        line.strip()
        for line in code.splitlines()
        if line.strip().startswith("namespace ") or line.strip().startswith("end ")
    ]


def _theorem_headers_without_evolve(code: str) -> List[str]:
    return [line.strip() for line in _outside_evolve_text(code).splitlines() if THEOREM_RE.match(line)]
