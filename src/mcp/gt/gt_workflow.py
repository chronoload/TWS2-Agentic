from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .assumption_audit import audit_gt_hypotheses
from .compiler import LeanCompiler
from .gap_ledger import default_gap_ledger, detect_unverified_claims, extract_gap_ledger
from .gt_core import (
    GTValidator, GTRater, PopulationDB, PUcbSampler, GoalCache,
    ValidationResult, RatedSketch,
    has_lean_holes, render_gap_ledger, infer_gaps_from_sketch,
    replace_first_hole_inside_evolve, apply_search_replace,
)
from .prover_subagent import GTProverSubagent, ProverStep
from .schemas import AttemptSummary, GTProblem, GTResult

logger = logging.getLogger(__name__)


class GTWorkflowMode(Enum):
    BASIC = "basic"
    EVOLUTION = "evolution"


@dataclass
class GTBasicConfig:
    num_provers: int = 8
    max_episodes: int = 200
    max_search_replace_per_episode: int = 60
    compile_after_each_edit: bool = True
    allow_sorry_in_intermediate: bool = True
    allow_sorry_in_final: bool = False


@dataclass
class GTEvolutionConfig:
    num_provers: int = 10
    elite_pool_size: int = 64
    p_ucb_exploration_c: float = 0.2
    num_raters: int = 3
    rater_match_size: int = 7
    goal_cache: bool = True


class GTWorkflowStep:
    """GT Agent 工作流步骤，可嵌入 TS2 WorkflowEngine。

    支持两种模式:
    - basic: 单次 prover 变异 + 验证
    - evolution: 种群进化搜索 (PopulationDB + P-UCB)
    """

    def __init__(
        self,
        *,
        mode: str = "basic",
        basic_config: Optional[GTBasicConfig] = None,
        evolution_config: Optional[GTEvolutionConfig] = None,
        validator: Optional[GTValidator] = None,
        rater: Optional[GTRater] = None,
        compiler: Optional[LeanCompiler] = None,
        prover: Optional[GTProverSubagent] = None,
        llm: Any = None,
        output_root: str = "gt_agent_runs",
    ) -> None:
        self.mode = GTWorkflowMode(mode)
        self.basic_config = basic_config or GTBasicConfig()
        self.evolution_config = evolution_config or GTEvolutionConfig()
        self.compiler = compiler or LeanCompiler()
        self.validator = validator or GTValidator(self.compiler)
        self.rater = rater or GTRater()
        self.prover = prover or GTProverSubagent(self.validator, self.compiler)
        self.llm = llm
        self.output_root = Path(output_root)
        self._goal_cache = GoalCache(enabled=self.evolution_config.goal_cache)

    def execute(
        self,
        source_code: str,
        context: str = "",
        allowed_references: Optional[List[str]] = None,
        forbidden_assumptions: Optional[List[str]] = None,
        abort_check: Any = None,
    ) -> Dict[str, Any]:
        allowed_references = allowed_references or []
        forbidden_assumptions = forbidden_assumptions or []

        audit_text, audit_warnings, audit_status = audit_gt_hypotheses(source_code + "\n" + context)

        if audit_status:
            return self._build_result(
                status=audit_status,
                final_code=source_code,
                summary=AttemptSummary(
                    status=audit_status,
                    main_idea="The supplied statement appears to miss required hypotheses.",
                    remaining_gaps=audit_warnings,
                ),
                gap_ledger=default_gap_ledger(audit_warnings[0] if audit_warnings else "Audit failed", lean_status="not attempted"),
                audit=audit_text,
                rater_report=self.rater.rank([source_code])[1],
            )

        is_lean = source_code.strip().startswith(("import ", "theorem ", "lemma ", "namespace ", "open ", "example ", "--"))
        if not is_lean:
            claims = detect_unverified_claims(source_code + "\n" + context, allowed_references)
            gaps = (
                default_gap_ledger(f"Unverified literature claim: {', '.join(claims)}", lean_status="natural-language only")
                if claims
                else default_gap_ledger("Natural-language problem has not been formalized.")
            )
            return self._build_result(
                status="PARTIAL",
                final_code=source_code,
                summary=AttemptSummary(
                    status="PARTIAL",
                    main_idea="Produced a conservative natural-language audit; no formal theorem was modified.",
                    remaining_gaps=claims or ["Formal statement is missing."],
                ),
                gap_ledger=gaps,
                audit=audit_text,
                rater_report=self.rater.rank([source_code])[1],
            )

        if self.mode == GTWorkflowMode.EVOLUTION:
            return self._run_evolution(
                source_code, context, allowed_references, forbidden_assumptions,
                audit_text, abort_check,
            )
        else:
            return self._run_basic(
                source_code, context, allowed_references, forbidden_assumptions,
                audit_text, abort_check,
            )

    def _run_basic(
        self,
        source_code: str,
        context: str,
        allowed_references: List[str],
        forbidden_assumptions: List[str],
        audit_text: str,
        abort_check: Any,
    ) -> Dict[str, Any]:
        step = self.prover.mutate(source_code, source_code)

        if self.llm and not step.changed:
            candidate_code, changed = self._llm_mutate(source_code, source_code)
            if changed:
                validation = self.validator.validate_candidate(source_code, candidate_code, final=False)
                if validation.accepted:
                    lean_fb = self.compiler.check_code(candidate_code)
                    step = ProverStep(
                        code=candidate_code,
                        changed=True,
                        validation=validation,
                        lean_feedback=lean_fb,
                        summary=AttemptSummary(
                            status="PARTIAL",
                            main_idea="Applied LLM-proposed search-replace patch.",
                            lean_feedback=lean_fb.output,
                        ),
                    )

        final_validation = self.validator.validate_candidate(source_code, step.code, final=True)
        status = "PROVED" if final_validation.accepted and not has_lean_holes(step.code) else "PARTIAL"

        if status != "PROVED" and final_validation.reason:
            step.summary.remaining_gaps.append(final_validation.reason)
            if final_validation.lean_feedback and hasattr(final_validation.lean_feedback, 'output') and final_validation.lean_feedback.output:
                step.summary.lean_feedback = final_validation.lean_feedback.output

        step.summary.status = status
        gap_ledger = extract_gap_ledger(step.code) if status != "PROVED" else "# GT Gap Ledger\n\nNo open gaps recorded.\n"
        if status != "PROVED" and "No open gaps recorded" in gap_ledger:
            gap_ledger = default_gap_ledger("; ".join(step.summary.remaining_gaps) or "Proof remains uncertified.")

        result = self._build_result(
            status=status,
            final_code=step.code,
            summary=step.summary,
            gap_ledger=gap_ledger,
            audit=audit_text,
            rater_report=self.rater.rank([step.code])[1],
        )

        self._write_result_to_disk(result, suffix=".lean")
        return result

    def _run_evolution(
        self,
        source_code: str,
        context: str,
        allowed_references: List[str],
        forbidden_assumptions: List[str],
        audit_text: str,
        abort_check: Any,
    ) -> Dict[str, Any]:
        population = PopulationDB(elite_pool_size=self.evolution_config.elite_pool_size)
        population.initialize(source_code)
        sampler = PUcbSampler(self.evolution_config.p_ucb_exploration_c)

        max_episodes = self.basic_config.max_episodes
        for episode in range(max_episodes):
            if abort_check and abort_check():
                break

            parent = sampler.sample(population.entries())
            step = self.prover.mutate(source_code, parent.code)

            if not step.validation.accepted:
                if self.llm:
                    candidate_code, changed = self._llm_mutate(source_code, parent.code)
                    if changed:
                        validation = self.validator.validate_candidate(source_code, candidate_code, final=False)
                        if validation.accepted:
                            rated = self.rater.rate(candidate_code)
                            population.add(candidate_code, score=rated.score, metadata={"mode": "evolution-llm", "episode": episode})
                continue

            rated = self.rater.rate(step.code)
            if step.validation.accepted:
                population.add(step.code, score=rated.score, metadata={"mode": "evolution", "episode": episode})

            final_validation = self.validator.validate_candidate(source_code, step.code, final=True)
            if final_validation.accepted and not has_lean_holes(step.code):
                result = self._build_result(
                    status="PROVED",
                    final_code=step.code,
                    summary=AttemptSummary(
                        status="PROVED",
                        main_idea=f"Evolution found a proof after {episode + 1} episodes.",
                        closed_lemmas=["No proof holes remain."],
                    ),
                    gap_ledger="# GT Gap Ledger\n\nNo open gaps recorded.\n",
                    audit=audit_text,
                    rater_report=self.rater.rank([entry.code for entry in population.entries()])[1],
                )
                self._write_result_to_disk(result, suffix=".lean")
                return result

        best = population.best()
        final_validation = self.validator.validate_candidate(source_code, best.code, final=True)
        status = "PROVED" if final_validation.accepted and not has_lean_holes(best.code) else "PARTIAL"

        remaining_gaps: List[str] = []
        if status != "PROVED" and final_validation.reason:
            remaining_gaps.append(final_validation.reason)

        summary = AttemptSummary(
            status=status,
            main_idea=f"Evolution mode completed with best score {best.score:.1f} after {max_episodes} episodes.",
            remaining_gaps=remaining_gaps or ["Evolution adapter completed without full proof."],
        )

        result = self._build_result(
            status=status,
            final_code=best.code,
            summary=summary,
            gap_ledger=extract_gap_ledger(best.code) if status != "PROVED" else "# GT Gap Ledger\n\nNo open gaps recorded.\n",
            audit=audit_text,
            rater_report=self.rater.rank([entry.code for entry in population.entries()])[1],
        )
        self._write_result_to_disk(result, suffix=".lean")
        return result

    def _llm_mutate(self, original_code: str, parent_code: str) -> tuple:
        try:
            gap_ledger = extract_gap_ledger(parent_code)
            prompt = (
                "You are a proof assistant. Given the following code with gaps, "
                "propose a search-replace patch to fill the next gap.\n\n"
                f"Current code:\n```\n{parent_code}\n```\n\n"
                f"Gap analysis:\n{gap_ledger}\n\n"
                "Respond with a JSON object with 'search' and 'replace' keys."
            )
            messages = [
                {"role": "system", "content": "You are a proof assistant that proposes minimal search-replace patches."},
                {"role": "user", "content": prompt},
            ]
            response = self.llm.chat(messages)
            content = response.content if hasattr(response, 'content') else str(response)

            try:
                patch = json.loads(content)
                if "search" in patch and "replace" in patch:
                    new_code = apply_search_replace(parent_code, patch["search"], patch["replace"])
                    return new_code, True
            except (json.JSONDecodeError, ValueError):
                pass

            return parent_code, False
        except Exception as e:
            logger.debug(f"LLM mutate failed: {e}")
            return parent_code, False

    def _build_result(
        self,
        *,
        status: str,
        final_code: str,
        summary: AttemptSummary,
        gap_ledger: str,
        audit: str,
        rater_report: str,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "final_code": final_code,
            "summary": {
                "status": summary.status,
                "main_idea": summary.main_idea,
                "closed_lemmas": summary.closed_lemmas,
                "remaining_gaps": summary.remaining_gaps,
                "lean_feedback": summary.lean_feedback,
                "rater_criticism": summary.rater_criticism,
            },
            "gap_ledger": gap_ledger,
            "assumption_audit": audit,
            "rater_report": rater_report,
        }

    def _write_result_to_disk(self, result: Dict[str, Any], suffix: str = ".lean") -> None:
        try:
            import time
            run_dir = self.output_root / f"run_{int(time.time())}"
            run_dir.mkdir(parents=True, exist_ok=True)

            formal_path = run_dir / ("final.lean" if suffix == ".lean" else "final.md")
            formal_path.write_text(result["final_code"], encoding="utf-8")

            summary_path = run_dir / "summary.md"
            summary_path.write_text(_render_summary(result), encoding="utf-8")

            gap_path = run_dir / "gap_ledger.md"
            gap_path.write_text(result["gap_ledger"], encoding="utf-8")

            audit_path = run_dir / "assumption_audit.md"
            audit_path.write_text(result["assumption_audit"], encoding="utf-8")

            rater_path = run_dir / "rater_report.md"
            rater_path.write_text(result["rater_report"], encoding="utf-8")

            result_path = run_dir / "result.json"
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            result["output_dir"] = str(run_dir)
        except Exception as e:
            logger.debug(f"Failed to write result to disk: {e}")


def _render_summary(result: Dict[str, Any]) -> str:
    summary = result.get("summary", {})
    closed = "\n".join(f"- {item}" for item in summary.get("closed_lemmas", [])) or "- None"
    gaps = "\n".join(f"- {item}" for item in summary.get("remaining_gaps", [])) or "- None"
    return "\n".join(
        [
            "# GT Agent Result",
            "",
            "## Status",
            result.get("status", "UNKNOWN"),
            "",
            "## Proof strategy",
            summary.get("main_idea", "Not recorded."),
            "",
            "## Closed components",
            closed,
            "",
            "## Remaining gaps",
            gaps,
            "",
            "## Geometry/topology assumption audit",
            "See assumption_audit.md.",
            "",
            "## Next executable steps",
            summary.get("lean_feedback", "Provide a precise local lemma and run Lean validation."),
            "",
        ]
    )
