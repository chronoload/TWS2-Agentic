"""流水线编排引擎：管理 Batch 生命周期、分发 agent 命令、Gate 判定"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ._base import Config, setup_logging

logger = setup_logging()


class PipelineState(Enum):
    IDLE = "idle"
    ARCHITECT = "architect"
    WRITING = "writing"
    REVIEWING = "reviewing"
    GATE = "gate"
    COMPLETE = "complete"


class BatchStatus(Enum):
    PENDING = "pending"
    WRITING = "writing"
    WRITTEN = "written"
    REVIEWING = "reviewing"
    PASSED = "passed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class DispatchCommand:
    action: str  # "write" | "review" | "research" | "debug_compile"
    role: str  # "writer" | "fact_reviewer" | "coherence_reviewer" | ...
    prompt_file: str
    prompt_context: dict
    output_paths: list[str]
    options: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "action": self.action,
            "role": self.role,
            "prompt_file": self.prompt_file,
            "prompt_context": self.prompt_context,
            "output_paths": self.output_paths,
            "options": self.options,
        }, ensure_ascii=False, indent=2)


@dataclass
class GateResult:
    passed: bool
    failed_reviewers: list[str] = field(default_factory=list)
    retry_needed: bool = False
    stop_needed: bool = False
    details: dict = field(default_factory=dict)


@dataclass
class Batch:
    id: str
    lessons: list[str]
    dependencies: list[str] = field(default_factory=list)
    status: BatchStatus = BatchStatus.PENDING
    review_results: dict = field(default_factory=dict)
    retry_count: int = 0
    framework_path: str = ""
    rmd_paths: list[str] = field(default_factory=list)

    def add_review_result(self, reviewer: str, result: dict) -> None:
        self.review_results[reviewer] = result


@dataclass
class Pipeline:
    state: PipelineState = PipelineState.IDLE
    batches: list[Batch] = field(default_factory=list)
    project_name: str = ""

    def get_batch(self, batch_id: str) -> Batch | None:
        for b in self.batches:
            if b.id == batch_id:
                return b
        return None

    def get_writable_batches(self) -> list[Batch]:
        """获取可写的 batch（依赖已满足或无依赖）"""
        written = {b.id for b in self.batches if b.status in (BatchStatus.WRITTEN, BatchStatus.PASSED)}
        return [b for b in self.batches if b.status == BatchStatus.PENDING and all(d in written for d in b.dependencies)]

    def get_reviewable_batches(self) -> list[Batch]:
        """获取可审查的 batch（已写完）"""
        return [b for b in self.batches if b.status == BatchStatus.WRITTEN]


class Orchestrator:
    """流水线编排器"""

    def __init__(self, config: Config):
        self.config = config
        self.max_retry = config.get("pipeline.max_retry", 3)

    def create_pipeline(self, lessons: list[str]) -> Pipeline:
        """根据课时列表创建 pipeline（按 batch_size 分批）"""
        batch_min, batch_max = config_get_batch_size(self.config)
        pipeline = Pipeline(project_name=self.config.get("content.project.name", ""))

        # 简单分批（后续 dependency.py 可优化）
        batch_num = 0
        for i in range(0, len(lessons), batch_max):
            batch_lessons = lessons[i : i + batch_max]
            batch_id = f"B{batch_num}"
            batch = Batch(id=batch_id, lessons=batch_lessons)
            pipeline.batches.append(batch)
            batch_num += 1

        return pipeline

    def dispatch_architect(self, lessons: list[str]) -> DispatchCommand:
        """生成 Architect 分发命令"""
        return DispatchCommand(
            action="write",
            role="architect",
            prompt_file="core/prompts/architect.md",
            prompt_context={
                "project_name": self.config.get("content.project.name", ""),
                "lessons": lessons,
                "reference_lesson": self.config.get("content.reference.lesson", ""),
                "reference_lines": self.config.get("content.reference.lines", 0),
                "quality_standards_path": "core/quality/quality-standards.md",
                "re_kctsw_path": "core/quality/re-kctsw.md",
                "narrative_philosophy": self.config.get("content.narrative.philosophy", "re-kctsw"),
                "section_order": self.config.get("content.narrative.section_order", []),
                "output_dir": "frameworks/",
            },
            output_paths=[],
        )

    def dispatch_writer(self, batch: Batch) -> DispatchCommand:
        """生成 Writer 分发命令"""
        return DispatchCommand(
            action="write",
            role="writer",
            prompt_file="core/prompts/writer.md",
            prompt_context={
                "project_name": self.config.get("content.project.name", ""),
                "reference_lesson_path": self.config.get("content.reference.lesson", ""),
                "reference_lines": self.config.get("content.reference.lines", 0),
                "quality_standards_path": "core/quality/quality-standards.md",
                "re_kctsw_path": "core/quality/re-kctsw.md",
                "framework_path": batch.framework_path,
                "lessons": batch.lessons,
                "section_order": self.config.get("content.narrative.section_order", []),
                "header_format": self.config.get("content.narrative.header_format", ""),
                "output_dir": self.config.get("content.structure.dir_pattern", "."),
            },
            output_paths=batch.rmd_paths,
            options={"max_retry": self.max_retry},
        )

    def dispatch_reviewers(self, batch: Batch) -> list[DispatchCommand]:
        """生成 5 个并发 reviewer 分发命令"""
        reviewers = [
            ("fact_reviewer", "fact-reviewer.md"),
            ("coherence_reviewer", "coherence-reviewer.md"),
            ("necessity_reviewer", "necessity-reviewer.md"),
            ("continuity_reviewer", "continuity-reviewer.md"),
            ("debugger_compiler", "debugger-compiler.md"),
        ]
        commands = []
        for role, prompt_file in reviewers:
            cmd = DispatchCommand(
                action="review" if role != "debugger_compiler" else "debug_compile",
                role=role,
                prompt_file=f"core/prompts/{prompt_file}",
                prompt_context={
                    "project_name": self.config.get("content.project.name", ""),
                    "rmd_paths": batch.rmd_paths,
                    "framework_path": batch.framework_path,
                    "reference_lesson_path": self.config.get("content.reference.lesson", ""),
                    "quality_standards_path": "core/quality/quality-standards.md",
                    "fail_thresholds_path": "core/quality/fail-thresholds.md",
                },
                output_paths=[],
            )
            commands.append(cmd)
        return commands

    def evaluate_gate(self, batch: Batch) -> GateResult:
        """汇总 review 结果，判定 PASS/FAIL/RETRY"""
        failed = []
        for reviewer, result in batch.review_results.items():
            status = result.get("status", "UNKNOWN")
            if status == "FAIL":
                failed.append(reviewer)

        if not failed:
            return GateResult(passed=True)

        # 检查是否超过重试次数
        if batch.retry_count >= self.max_retry:
            return GateResult(
                passed=False,
                failed_reviewers=failed,
                stop_needed=True,
                details={"retry_count": batch.retry_count, "max_retry": self.max_retry},
            )

        return GateResult(
            passed=False,
            failed_reviewers=failed,
            retry_needed=True,
            details={"retry_count": batch.retry_count},
        )

    def record_review(self, batch: Batch, reviewer: str, result: dict) -> None:
        """记录 reviewer 结果"""
        batch.add_review_result(reviewer, result)
        batch.status = BatchStatus.REVIEWING

    def advance_batch(self, batch: Batch, gate: GateResult) -> None:
        """根据 Gate 结果推进 batch 状态"""
        if gate.passed:
            batch.status = BatchStatus.PASSED
        elif gate.stop_needed:
            batch.status = BatchStatus.STOPPED
        else:
            batch.retry_count += 1
            batch.status = BatchStatus.PENDING  # 回到待写状态
            batch.review_results.clear()


def config_get_batch_size(config: Config) -> tuple[int, int]:
    """获取 batch 大小范围"""
    bs = config.get("pipeline.batch_size", [3, 6])
    if isinstance(bs, list) and len(bs) >= 2:
        return bs[0], bs[1]
    return 3, 6
