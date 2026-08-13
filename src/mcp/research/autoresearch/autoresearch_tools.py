import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...tools import Tool

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent / "skills"
SKILL_REGISTRY = None


def _get_skill_registry():
    global SKILL_REGISTRY
    if SKILL_REGISTRY is None:
        try:
            from .skill_registry import SkillRegistry
            SKILL_REGISTRY = SkillRegistry(
                builtin_dir=str(SKILLS_DIR),
                auto_match=True,
                max_skills_per_stage=3,
            )
        except Exception:
            SKILL_REGISTRY = None
    return SKILL_REGISTRY


class AutoResearchTopicInitTool(Tool):
    name = "autoresearch_topic_init"
    description = "初始化研究主题：分析研究问题、拆解子问题、确定研究范围"
    category = "autoresearch"
    keywords = ["研究", "选题", "拆解", "research", "topic", "decompose"]
    risk_level = "low"

    parameters = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "研究主题或问题描述",
            },
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "相关领域标签",
            },
        },
        "required": ["topic"],
    }

    def execute(self, topic: str = "", domains: list = None, **kwargs) -> str:
        domains = domains or []
        ctx = {
            "topic": topic,
            "domains": domains,
            "stage": "topic_init",
        }
        skills_prompt = _inject_skills(ctx)
        return json.dumps({
            "topic": topic,
            "domains": domains,
            "status": "initialized",
            "skills_prompt": skills_prompt[:2000],
        }, ensure_ascii=False)


class AutoResearchLitSearchTool(Tool):
    name = "autoresearch_lit_search"
    description = "文献搜索策略：制定搜索词、选择来源、收集并筛选文献"
    category = "autoresearch"
    keywords = ["文献", "搜索", "论文", "literature", "search", "paper", "arxiv"]
    risk_level = "low"

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询词",
            },
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "搜索来源: arxiv, semantic_scholar, web",
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数",
            },
        },
        "required": ["query"],
    }

    def execute(self, query: str = "", sources: list = None, max_results: int = 10, **kwargs) -> str:
        sources = sources or ["arxiv", "semantic_scholar"]
        ctx = {"query": query, "sources": sources, "stage": "literature_collect"}
        skills_prompt = _inject_skills(ctx)
        return json.dumps({
            "query": query,
            "sources": sources,
            "max_results": max_results,
            "status": "strategy_ready",
            "skills_prompt": skills_prompt[:2000],
        }, ensure_ascii=False)


class AutoResearchSynthesisTool(Tool):
    name = "autoresearch_synthesis"
    description = "知识综合：整合文献发现、识别研究空白、生成假设"
    category = "autoresearch"
    keywords = ["综合", "综述", "假设", "synthesis", "hypothesis", "gap"]
    risk_level = "low"

    parameters = {
        "type": "object",
        "properties": {
            "literature_summary": {
                "type": "string",
                "description": "文献综述摘要",
            },
            "gap_focus": {
                "type": "string",
                "description": "关注的空白领域",
            },
        },
        "required": ["literature_summary"],
    }

    def execute(self, literature_summary: str = "", gap_focus: str = "", **kwargs) -> str:
        ctx = {
            "literature_summary": literature_summary[:500],
            "gap_focus": gap_focus,
            "stage": "synthesis",
        }
        skills_prompt = _inject_skills(ctx)
        return json.dumps({
            "status": "synthesized",
            "gap_focus": gap_focus,
            "skills_prompt": skills_prompt[:2000],
        }, ensure_ascii=False)


class AutoResearchExpDesignTool(Tool):
    name = "autoresearch_exp_design"
    description = "实验设计：设计实验方案、选择指标、估算资源需求"
    category = "autoresearch"
    keywords = ["实验", "设计", "指标", "experiment", "design", "benchmark"]
    risk_level = "medium"

    parameters = {
        "type": "object",
        "properties": {
            "hypothesis": {
                "type": "string",
                "description": "待验证假设",
            },
            "experiment_mode": {
                "type": "string",
                "description": "实验模式: simulated, sandbox, docker",
            },
            "metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "评估指标列表",
            },
        },
        "required": ["hypothesis"],
    }

    def execute(self, hypothesis: str = "", experiment_mode: str = "simulated", metrics: list = None, **kwargs) -> str:
        metrics = metrics or ["primary_metric"]
        ctx = {
            "hypothesis": hypothesis[:500],
            "experiment_mode": experiment_mode,
            "metrics": metrics,
            "stage": "experiment_design",
        }
        skills_prompt = _inject_skills(ctx)
        return json.dumps({
            "hypothesis": hypothesis[:200],
            "experiment_mode": experiment_mode,
            "metrics": metrics,
            "status": "designed",
            "skills_prompt": skills_prompt[:2000],
        }, ensure_ascii=False)


class AutoResearchResultAnalysisTool(Tool):
    name = "autoresearch_result_analysis"
    description = "结果分析：分析实验数据、统计检验、决策建议"
    category = "autoresearch"
    keywords = ["分析", "结果", "统计", "analysis", "result", "decision"]
    risk_level = "medium"

    parameters = {
        "type": "object",
        "properties": {
            "experiment_results": {
                "type": "string",
                "description": "实验结果数据",
            },
            "metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "使用到的指标",
            },
        },
        "required": ["experiment_results"],
    }

    def execute(self, experiment_results: str = "", metrics: list = None, **kwargs) -> str:
        metrics = metrics or []
        ctx = {
            "experiment_results": experiment_results[:1000],
            "metrics": metrics,
            "stage": "result_analysis",
        }
        skills_prompt = _inject_skills(ctx)
        return json.dumps({
            "status": "analyzed",
            "skills_prompt": skills_prompt[:2000],
        }, ensure_ascii=False)


class AutoResearchQualityGateTool(Tool):
    name = "autoresearch_quality_gate"
    description = "质量门控：多维度评估研究质量（新颖性、严谨性、清晰度、影响力、实验充分性）"
    category = "autoresearch"
    keywords = ["质量", "评估", "评审", "quality", "review", "gate", "novelty"]
    risk_level = "low"

    parameters = {
        "type": "object",
        "properties": {
            "paper_content": {
                "type": "string",
                "description": "论文内容",
            },
            "dimensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "评估维度: novelty, rigor, clarity, impact, experiments",
            },
        },
        "required": ["paper_content"],
    }

    def execute(self, paper_content: str = "", dimensions: list = None, **kwargs) -> str:
        dimensions = dimensions or ["novelty", "rigor", "clarity", "impact", "experiments"]
        ctx = {
            "paper_content": paper_content[:2000],
            "dimensions": dimensions,
            "stage": "quality_gate",
        }
        skills_prompt = _inject_skills(ctx)
        return json.dumps({
            "status": "gated",
            "dimensions": dimensions,
            "skills_prompt": skills_prompt[:2000],
        }, ensure_ascii=False)


class AutoResearchSkillTool(Tool):
    name = "autoresearch_skill"
    description = "技能匹配：根据上下文自动匹配最佳研究技能并注入提示"
    category = "autoresearch"
    keywords = ["技能", "skill", "注入", "prompt", "匹配"]
    risk_level = "low"

    parameters = {
        "type": "object",
        "properties": {
            "context": {
                "type": "string",
                "description": "当前上下文描述",
            },
            "stage": {
                "type": "string",
                "description": "当前阶段名称",
            },
            "top_k": {
                "type": "integer",
                "description": "返回技能数量",
            },
        },
        "required": ["context"],
    }

    def execute(self, context: str = "", stage: str = "", top_k: int = 3, **kwargs) -> str:
        registry = _get_skill_registry()
        if registry is None:
            return json.dumps({"skills": [], "count": 0}, ensure_ascii=False)

        skills = registry.match(context, stage, top_k=top_k)
        prompt_injection = registry.export_for_prompt(skills)

        return json.dumps({
            "skills": [{"name": s.name, "description": s.description, "category": s.category} for s in skills],
            "count": len(skills),
            "prompt_injection": prompt_injection[:3000],
        }, ensure_ascii=False)


class AutoResearchListSkillsTool(Tool):
    name = "autoresearch_list_skills"
    description = "列出所有可用的研究技能及其分类"
    category = "autoresearch"
    keywords = ["列表", "技能", "可用", "list", "skills", "available"]
    risk_level = "low"

    parameters = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "按分类筛选: domain, experiment, tooling, writing",
            },
        },
        "required": [],
    }

    def execute(self, category: str = "", **kwargs) -> str:
        registry = _get_skill_registry()
        if registry is None:
            return json.dumps({"skills": [], "count": 0}, ensure_ascii=False)

        if category:
            skills = registry.list_by_category(category)
        else:
            skills = registry.list_all()

        result = {}
        for s in skills:
            cat = s.category
            if cat not in result:
                result[cat] = []
            result[cat].append({
                "name": s.name,
                "description": s.description,
                "applicable_stages": s.applicable_stages,
                "trigger_keywords": s.trigger_keywords,
            })

        return json.dumps({
            "skills_by_category": result,
            "total": len(skills),
        }, ensure_ascii=False)


def _inject_skills(ctx: dict) -> str:
    registry = _get_skill_registry()
    if registry is None:
        return ""

    context_text = json.dumps(ctx, ensure_ascii=False)
    stage = ctx.get("stage", "")
    skills = registry.match(context_text, stage, top_k=3)
    if not skills:
        return ""

    return registry.export_for_prompt(skills, max_chars=3000)


def get_autoresearch_tools() -> List[Tool]:
    if not SKILLS_DIR.exists():
        logger.warning("AutoResearch 技能目录不存在，跳过加载")
        return []

    try:
        _get_skill_registry()
    except Exception as e:
        logger.warning(f"AutoResearch 技能注册表初始化失败: {e}")
        return []

    return [
        AutoResearchTopicInitTool(),
        AutoResearchLitSearchTool(),
        AutoResearchSynthesisTool(),
        AutoResearchExpDesignTool(),
        AutoResearchResultAnalysisTool(),
        AutoResearchQualityGateTool(),
        AutoResearchSkillTool(),
        AutoResearchListSkillsTool(),
    ]