from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..tools import Tool

logger = logging.getLogger(__name__)


class GTValidateTool(Tool):
    name = "gt_validate"
    description = "验证证明/代码的完整性和安全性，检查 EVOLVE 标记完整性、定理声明不变性、环境利用等"
    model_hint = "[何时使用] 需要用 EVOLVE 范式批量修改证明代码后验证完整性时。\n[参数说明]\n- original_code: 修改前的原始 Lean 代码\n- candidate_code: 修改后的候选 Lean 代码\n- final: 是否最终严格验证"
    parameters = {
        "type": "object",
        "properties": {
            "original_code": {"type": "string", "description": "【必填】修改前的原始 Lean 代码文本"},
            "candidate_code": {"type": "string", "description": "【必填】经过 EVOLVE 修改后的候选 Lean 代码文本"},
            "final": {"type": "boolean", "description": "是否为最终严格验证模式（更严格的检查，默认 false）", "default": False},
        },
        "required": ["original_code", "candidate_code"],
    }
    category = "gt"
    keywords = ["validate", "proof", "lean", "verify", "check"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        from .gt_core import GTValidator
        original = kwargs.get("original_code", "")
        candidate = kwargs.get("candidate_code", "")
        final = kwargs.get("final", False)
        validator = GTValidator()
        result = validator.validate_candidate(original, candidate, final=final)
        return json.dumps({
            "accepted": result.accepted,
            "status": result.status,
            "reason": result.reason,
            "repair_hint": result.repair_hint,
        }, ensure_ascii=False, indent=2)


class GTRateTool(Tool):
    name = "gt_rate"
    description = "对证明草图进行评分，检测策略性缺陷和未验证声明"
    model_hint = "[何时使用] 需要评估 Lean 证明草图的质量和完整性时。\n[参数说明]\n- sketch: Lean 证明草图的代码文本\n- target_statement: 目标定理声明（可选，用于验证覆盖度）"
    parameters = {
        "type": "object",
        "properties": {
            "sketch": {"type": "string", "description": "【必填】Lean 证明草图的代码文本"},
            "target_statement": {"type": "string", "description": "目标定理声明文本（可选，不提供则自动推断）"},
        },
        "required": ["sketch"],
    }
    category = "gt"
    keywords = ["rate", "score", "rank", "evaluate", "proof"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        from .gt_core import GTRater
        sketch = kwargs.get("sketch", "")
        target = kwargs.get("target_statement")
        rater = GTRater()
        result = rater.rate(sketch, target_statement=target)
        return json.dumps({
            "score": result.score,
            "summary": result.summary,
            "critical_flaws": result.critical_flaws,
            "gap_quality": result.gap_quality,
        }, ensure_ascii=False, indent=2)


class GTGapLedgerTool(Tool):
    name = "gt_gap_ledger"
    description = "分析代码中的未解决问题(gaps)，生成结构化的 Gap Ledger 报告"
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要分析的代码"},
            "allowed_references": {
                "type": "array",
                "items": {"type": "string"},
                "description": "允许引用的定理列表",
                "default": [],
            },
        },
        "required": ["code"],
    }
    category = "gt"
    keywords = ["gap", "ledger", "holes", "sorry", "admit", "missing"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        from .gt_core import extract_gap_ledger, detect_unverified_claims
        code = kwargs.get("code", "")
        allowed = kwargs.get("allowed_references", [])
        ledger = extract_gap_ledger(code)
        claims = detect_unverified_claims(code, allowed_references=allowed)
        return json.dumps({
            "gap_ledger": ledger,
            "unverified_claims": claims,
            "has_holes": bool(claims or "sorry" in code or "admit" in code),
        }, ensure_ascii=False, indent=2)


class GTAssumptionAuditTool(Tool):
    name = "gt_assumption_audit"
    description = "审计几何/拓扑假设，检测常见的假设缺失或过强问题（如 Poincaré 对偶性、紧性条件等）"
    model_hint = "[何时使用] 需要审核数学证明中的假设完整性时，特别是几何/拓扑相关。\n[参数说明]\n- text: 包含代码和上下文的完整证明文本"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "【必填】要审计的完整证明文本（包含 Lean 代码和上下文说明）"},
        },
        "required": ["text"],
    }
    category = "gt"
    keywords = ["audit", "assumption", "hypothesis", "poincare", "compact", "orient"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        from .gt_core import audit_hypotheses
        text = kwargs.get("text", "")
        audit_text, warnings, status = audit_hypotheses(text)
        return json.dumps({
            "audit": audit_text,
            "warnings": warnings,
            "status_override": status,
        }, ensure_ascii=False, indent=2)


class GTSearchReplaceTool(Tool):
    name = "gt_search_replace"
    description = "在代码中执行精确的搜索替换操作，用于修复证明中的局部问题"
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "【必填】要查看的原始 Lean 代码"},
            "search": {"type": "string", "description": "要搜索的文本"},
            "replace": {"type": "string", "description": "【必填】替换后的新文本"},
        },
        "required": ["code", "search", "replace"],
    }
    category = "gt"
    keywords = ["search", "replace", "patch", "edit", "fix"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        from .gt_core import apply_search_replace
        code = kwargs.get("code", "")
        search = kwargs.get("search", "")
        replace = kwargs.get("replace", "")
        try:
            result = apply_search_replace(code, search, replace)
            return json.dumps({"success": True, "result": result}, ensure_ascii=False)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


class GTEvolveTool(Tool):
    name = "gt_evolve"
    description = "在 EVOLVE 标记区域内替换第一个 sorry/admit 占位符"
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "包含 EVOLVE 标记的代码"},
            "replacement": {"type": "string", "description": "替换 sorry/admit 的代码片段"},
        },
        "required": ["code", "replacement"],
    }
    category = "gt"
    keywords = ["evolve", "sorry", "admit", "hole", "fill", "replace"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        from .gt_core import replace_first_hole_inside_evolve
        code = kwargs.get("code", "")
        replacement = kwargs.get("replacement", "")
        result, changed = replace_first_hole_inside_evolve(code, replacement)
        return json.dumps({
            "result": result,
            "changed": changed,
        }, ensure_ascii=False, indent=2)


class GTWorkflowRunTool(Tool):
    name = "gt_workflow_run"
    description = "运行完整的 GT 工作流（basic 或 evolution 模式），自动执行假设审计、变异、验证、评分"
    parameters = {
        "type": "object",
        "properties": {
            "source_code": {"type": "string", "description": "原始证明/代码"},
            "context": {"type": "string", "description": "附加上下文信息（可选，用于工作流传递）", "default": ""},
            "mode": {"type": "string", "description": "工作流模式: basic 或 evolution", "default": "basic", "enum": ["basic", "evolution"]},
            "allowed_references": {
                "type": "array",
                "items": {"type": "string"},
                "description": "允许引用的定理列表",
                "default": [],
            },
            "forbidden_assumptions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "禁止使用的假设列表",
                "default": [],
            },
        },
        "required": ["source_code"],
    }
    category = "gt"
    keywords = ["workflow", "run", "prove", "evolution", "basic", "agent"]
    risk_level = "high"

    def execute(self, **kwargs) -> str:
        from .gt_workflow import GTWorkflowStep
        source = kwargs.get("source_code", "")
        context = kwargs.get("context", "")
        mode = kwargs.get("mode", "basic")
        allowed = kwargs.get("allowed_references", [])
        forbidden = kwargs.get("forbidden_assumptions", [])

        step = GTWorkflowStep(mode=mode)
        result = step.execute(
            source_code=source,
            context=context,
            allowed_references=allowed,
            forbidden_assumptions=forbidden,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)


class GTResearchTool(Tool):
    name = "gt_research"
    description = "使用 LLM 驱动的研究服务，对几何/拓扑问题进行形式化、分解和审计"
    parameters = {
        "type": "object",
        "properties": {
            "problem": {"type": "string", "description": "研究问题描述"},
            "domain_context": {"type": "string", "description": "领域上下文（可选）", "default": ""},
            "mode": {"type": "string", "description": "研究模式: plan 或 reason", "default": "plan"},
            "model": {"type": "string", "description": "使用的模型名称", "default": "gpt-4.1"},
            "base_url": {"type": "string", "description": "API base URL", "default": ""},
            "api_key": {"type": "string", "description": "API key（可选，默认从环境变量读取）", "default": ""},
        },
        "required": ["problem"],
    }
    category = "gt"
    keywords = ["research", "study", "formalize", "audit", "llm"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        from .research_service import GTResearchService, ResearchRequest
        from .model_client import ModelConfig
        problem = kwargs.get("problem", "")
        domain_context = kwargs.get("domain_context", "")
        mode = kwargs.get("mode", "plan")
        model = kwargs.get("model", "gpt-4.1")
        base_url = kwargs.get("base_url", "")
        api_key = kwargs.get("api_key", "") or None

        config = ModelConfig.from_env()
        if model:
            config = ModelConfig(
                provider=config.provider,
                model=model,
                base_url=base_url or config.base_url,
                api_key=api_key or config.api_key,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )

        service = GTResearchService()
        request = ResearchRequest(
            problem=problem,
            domain_context=domain_context,
            mode=mode,
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
        )
        response = service.research(request)
        return json.dumps(response.to_dict(), ensure_ascii=False, indent=2)


class GTCompileTool(Tool):
    name = "gt_compile"
    description = "使用 Lean 编译器检查代码是否能通过编译"
    model_hint = "[何时使用] 需要检查 Lean 代码是否能通过编译器（无语法/类型错误）时。\n[参数说明]\n- code: 要检查的 Lean 代码"
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "【必填】要检查的完整 Lean 代码文本"},
        },
        "required": ["code"],
    }
    category = "gt"
    keywords = ["compile", "lean", "check", "build"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        from .compiler import LeanCompiler
        code = kwargs.get("code", "")
        compiler = LeanCompiler()
        feedback = compiler.check_code(code)
        return json.dumps({
            "compiles": feedback.compiles,
            "checked": feedback.checked,
            "output": feedback.output,
        }, ensure_ascii=False, indent=2)


def get_gt_tools() -> List[Tool]:
    return [
        GTValidateTool(),
        GTRateTool(),
        GTGapLedgerTool(),
        GTAssumptionAuditTool(),
        GTSearchReplaceTool(),
        GTEvolveTool(),
        GTWorkflowRunTool(),
        GTResearchTool(),
        GTCompileTool(),
    ]
