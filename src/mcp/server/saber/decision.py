"""
SaberSystem 决策生成层
- build_limited_context: 构建 ≤200 字受约束上下文（§11.4）
- generate_decision_point: I(P) 闸门 + 机会成本核算 + 防沉迷 + generator 注入

设计要点：
- Agent 建议职能按 I(P)=I₀·e^(-kP) 衰减；I(P)<0.1 时退役，不生成决策
- burned_out 时不生成决策（生命资本硬约束优先于建议）
- 防沉迷触发时返回受限决策，提示用户手动输入
- generator 可注入：默认规则生成，生产时可注入 LLM-backed generator
"""
from __future__ import annotations
import json
import logging
from typing import Any, Callable

from mcp.server.saber.models import Plan, Task, DecisionOption, DecisionPoint
from mcp.server.saber.life import LifeResource
from mcp.server.saber.agent import (
    AgentContributionLog, compute_intensity, should_block_for_anti_dependency,
)
from mcp.server.saber.opportunity_cost import assess_opportunity_cost

logger = logging.getLogger(__name__)

from mcp.llm import get_model_provider

# Agent 退役阈值（I(P) 低于此值不再生成建议）
INTENSITY_RETIREMENT_THRESHOLD = 0.1


def build_limited_context(plan: Plan, life: LifeResource,
                          git_diffs: list[str] | None = None,
                          working_files: list[str] | None = None) -> str:
    """构建 ≤500 字受约束上下文，供 Agent 决策使用

    包含 Plan 关键信息 + 生命资源状态 + git diff 区间 + 工作文件。
    让 Agent 在工作文件上下文内生成具体建议。
    """
    parts = [
        f"Plan:{plan.title}",
        f"层级:{plan.cognitive_focus.value}",
        f"进度:{plan.aggregated_progress:.0%}",
        f"注意力:{life.attention_capital.balance:.2f}",
        f"体能:{life.energy_level:.2f}",
        f"盈余:{life.waking_hours_surplus:.1f}h",
    ]
    if plan.tasks:
        todo = sum(1 for t in plan.tasks if t.status == "todo")
        doing = sum(1 for t in plan.tasks if t.status == "doing")
        done = sum(1 for t in plan.tasks if t.status == "done")
        parts.append(f"任务:待办{todo}/进行{doing}/完成{done}")
    if life.active_opportunities:
        parts.append(f"机遇:{len(life.active_opportunities)}个")
    if git_diffs:
        total = sum(len(d) for d in git_diffs)
        parts.append(f"git变更:{len(git_diffs)}个文件({total}行)")
        for i, d in enumerate(git_diffs[:3]):
            parts.append(f" diff{i+1}:{d[:200]}")
    if working_files:
        parts.append(f"工作文件:{','.join(working_files[:5])}")
    ctx = " | ".join(parts)
    return ctx[:500]


SABER_ADVISOR_SYSTEM_PROMPT = """你是一个战术决策助手，根据 Plan 上下文和生命资源状态，生成 2~3 个具体可执行的选项。
每个选项必须包含：
- description: 简短描述（10 字以内）
- rationale: 理由（20 字以内）
- estimated_impact: 预期影响
- confidence: 置信度 0.0~1.0
- attention_cost: 注意力消耗 0.0~0.5
- energy_cost: 体能消耗 0.0~0.5
- surplus_delta: 自由时间盈余变化（小时，负数表示消耗）
- tags: 标签列表 ["work","rest","explore","social"]
- action_payload: 执行动作（参考下方）

可用动作 action_payload.action:
- "create_tasks": 分解 Plan 为具体 Task，需含 titles（任务名列表）和 hours_per_task（每任务预计小时）
- "continue_plan": 继续推进当前 Plan
- "rest": 休息恢复，需含 minutes（分钟数）
- "switch_task": 切换到指定 task_id

生成 1~2 个 create_tasks 类的动作，将 Plan 分解为原子任务。
以 JSON 数组格式返回，不要额外说明。"""

def _llm_generator(context: str, intensity: float, life_vector: tuple,
                   plan: Plan | None = None,
                   git_diffs: list[str] | None = None,
                   working_files: list[str] | None = None) -> list[dict[str, Any]]:
    """LLM-backed 选项生成器，使用 TS2 MultiProviderManager"""
    provider = get_model_provider()
    if provider is None:
        raise RuntimeError("LLM 未配置，请检查 providers 配置")

    prompt = (
        f"当前上下文：{context}\n"
        f"Agent 强度：{intensity:.2f}\n"
        f"注意力余额：{life_vector[0]:.2f}\n"
        f"体能：{life_vector[1]:.2f}\n"
        f"情绪：{life_vector[2]:.2f}\n"
        f"请生成 2~5 个决策选项（JSON 数组），越多越好，覆盖工作和休息场景。"
    )
    try:
        resp = provider.chat(
            messages=[
                {"role": "system", "content": SABER_ADVISOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        options = json.loads(text)
        if isinstance(options, dict) and "options" in options:
            options = options["options"]
        return options
    except Exception as e:
        logger.warning(f"LLM generator 失败，回退规则生成: {e}")
        raise


SABER_PLAN_GENERATOR_PROMPT = """你是 SaberSystem 的战略规划助手。根据用户的目标（Goal），生成 2~4 个具体 Plan 方案。

每个 Plan 必须包含：
- title: 方案标题（15 字以内）
- description: 方案描述（50 字以内，说明具体做法）
- cognitive_focus: 认知层级（K=知识 C=概念 T=理论 S=技能 W=工作流）
- priority_weight: 优先级权重 0.0~1.0

生成要求：
1. 方案之间应有明显差异（不同策略方向）
2. cognitive_focus 要合理匹配方案内容
3. 整体权重之和应接近 1.0
以 JSON 数组格式返回，不要额外说明。"""


def generate_plans_for_goal(goal_title: str, goal_description: str,
                            goal_target_layer: str,
                            existing_plan_titles: list[str] | None = None
                            ) -> list[dict[str, Any]]:
    """使用 LLM 为目标生成 Plan 方案建议"""
    provider = get_model_provider()
    if provider is None:
        raise RuntimeError("LLM 未配置，请检查 providers 配置")

    existing_context = ""
    if existing_plan_titles:
        existing_context = f"\n已有 Plan：{'、'.join(existing_plan_titles)}（请避免重复）"

    prompt = (
        f"目标标题：{goal_title}\n"
        f"目标描述：{goal_description}\n"
        f"目标层级：{goal_target_layer}{existing_context}\n"
        f"请生成 2~4 个不同的 Plan 方案来实现此目标。"
    )
    try:
        resp = provider.chat(
            messages=[
                {"role": "system", "content": SABER_PLAN_GENERATOR_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        plans = json.loads(text)
        if isinstance(plans, dict) and "plans" in plans:
            plans = plans["plans"]
        if isinstance(plans, dict) and "options" in plans:
            plans = plans["options"]
        return plans
    except Exception as e:
        logger.warning(f"Plan 生成失败: {e}")
        raise


def _to_decision_option(raw: dict[str, Any]) -> DecisionOption:
    """dict 转 DecisionOption"""
    return DecisionOption(
        description=raw["description"],
        rationale=raw.get("rationale", ""),
        estimated_impact=raw.get("estimated_impact", ""),
        confidence=float(raw.get("confidence", 0.5)),
        action_payload=raw.get("action_payload", {}),
        attention_cost=float(raw.get("attention_cost", 0.0)),
        energy_cost=float(raw.get("energy_cost", 0.0)),
        missed_opportunities=raw.get("missed_opportunities", []),
        surplus_delta=float(raw.get("surplus_delta", 0.0)),
    )


def _default_generator(
    plan: Plan, life: LifeResource, alternatives: list[Task],
    anti_dependency: bool,
) -> list[dict[str, Any]]:
    """规则-based 默认选项生成器（不依赖 LLM）

    - 防沉迷触发时：生成"手动输入"选项，提示用户自主完成
    - 正常情况：生成"继续 Plan"与"休息恢复"两个选项
    """
    if anti_dependency:
        return [
            {
                "description": "手动输入前 3 个任务（自主完成，Agent 仅校验）",
                "rationale": "已连续多次无脑采纳，需自主实践以提升熟练度",
                "estimated_impact": "锻炼独立拆解能力",
                "confidence": 0.7,
                "action_payload": {"action": "manual_input", "count": 3},
                "attention_cost": 0.3,
                "energy_cost": 0.2,
                "missed_opportunities": [],
                "surplus_delta": -0.5,
            },
            {
                "description": "参考 Agent 草案但需手动修改后提交",
                "rationale": "在辅助与自主之间过渡",
                "estimated_impact": "半自主交付",
                "confidence": 0.5,
                "action_payload": {"action": "review_and_modify"},
                "attention_cost": 0.2,
                "energy_cost": 0.15,
                "missed_opportunities": [],
                "surplus_delta": -0.3,
            },
        ]

    # 生成自动拆解的任务名（基于 Plan 标题拆分思路）
    _suggested_tasks = [
        f"调研 {plan.title} 现状",
        f"制定 {plan.title} 实施方案",
        f"执行 {plan.title} 核心步骤",
    ] if not plan.tasks else []

    options = []
    if _suggested_tasks:
        options.append({
            "description": f"分解 Plan 为 3 个原子 Task",
            "rationale": f"Plan「{plan.title}」尚无任务，自动拆解为可执行步骤",
            "estimated_impact": "将目标转为可操作的任务列表",
            "confidence": 0.7,
            "action_payload": {"action": "create_tasks", "titles": _suggested_tasks, "hours_per_task": 1.0},
            "attention_cost": 0.1,
            "energy_cost": 0.1,
            "missed_opportunities": [],
            "surplus_delta": -0.3,
        })
    options.append({
        "description": f"继续推进 Plan：{plan.title}",
        "rationale": f"当前进度 {plan.aggregated_progress:.0%}，认知层级 {plan.cognitive_focus.value}",
        "estimated_impact": "推进 Plan 完成度",
        "confidence": 0.7,
        "action_payload": {"action": "continue_plan", "plan_id": plan.id},
        "attention_cost": 0.2,
        "energy_cost": 0.1,
        "missed_opportunities": [o.id for o in life.active_opportunities[:1]],
        "surplus_delta": -0.5,
    })
    options.append({
        "description": "休息 15 分钟恢复注意力资本",
        "rationale": f"注意力余额 {life.attention_capital.balance:.2f}，休息可存入资本",
        "estimated_impact": "提升后续产出质量",
        "confidence": 0.6,
        "action_payload": {"action": "rest", "minutes": 15},
        "attention_cost": 0.0,
        "energy_cost": 0.0,
        "missed_opportunities": [],
        "surplus_delta": 0.5,
    })
    if alternatives:
        alt = alternatives[0]
        options.append({
            "description": f"改做：{alt.title}",
            "rationale": "高紧迫度的替代任务",
            "estimated_impact": "抓住即将关闭的窗口",
            "confidence": 0.5,
            "action_payload": {"action": "switch_task", "task_id": alt.id},
            "attention_cost": 0.25,
            "energy_cost": 0.15,
            "missed_opportunities": [],
            "surplus_delta": -0.8 if alt.is_one_time_only else -0.3,
        })
    return options


def generate_decision_point(
    plan: Plan,
    life: LifeResource,
    proficiency: float,
    recent_logs: list[AgentContributionLog],
    alternatives: list[Task] | None = None,
    generator: Callable[..., list[dict[str, Any]]] | None = None,
    git_diffs: list[str] | None = None,
    working_files: list[str] | None = None,
) -> DecisionPoint | None:
    """生成决策点（§11.4）

    闸门顺序（生命优先于建议）：
    1. burned_out → 返回 None（推荐休息，不生成建议）
    2. I(P) < 0.1 → 返回 None（Agent 已退役）
    3. 防沉迷触发 → 返回受限决策（提示手动输入）

    generator 可注入：默认规则生成，生产时可注入 LLM-backed generator。
    git_diffs: 该 Plan 关联的 git diff 字符串列表。
    working_files: 工作文件路径列表。
    返回 None 表示不生成决策（agent_retired / burned_out）。
    """
    # 1. 生命资本硬约束优先
    if life.health.is_burned_out():
        return None

    # 2. I(P) 闸门——Agent 建议职能退役
    intensity = compute_intensity(proficiency)
    if intensity < INTENSITY_RETIREMENT_THRESHOLD:
        return None

    alternatives = alternatives or []
    context = build_limited_context(plan, life, git_diffs, working_files)
    life_vector = (
        life.attention_capital.balance,
        life.energy_level,
        life.mood_index,
    )

    # 3. 防沉迷检查
    anti_dependency = should_block_for_anti_dependency(recent_logs)

    # 4. 生成选项（LLM 失败则静默回退规则生成）
    if generator is not None:
        try:
            raw_options = generator(context, intensity, life_vector,
                                     plan=plan, git_diffs=git_diffs,
                                     working_files=working_files)
        except TypeError:
            # 兼容不接受额外 kwargs 的老式 generator
            raw_options = generator(context, intensity, life_vector)
        except Exception:
            logger.warning("LLM generator 失败，回退规则生成")
            raw_options = _default_generator(plan, life, alternatives, anti_dependency)
    else:
        raw_options = _default_generator(plan, life, alternatives, anti_dependency)

    # 5. 转为 DecisionOption + 机会成本核算
    options = [_to_decision_option(r) for r in raw_options[:6]]

    # 选项不足 2 个时补充默认选项
    if len(options) < 2:
        fallback = _default_generator(plan, life, alternatives, False)
        for r in fallback:
            if len(options) >= 2:
                break
            options.append(_to_decision_option(r))

    # 6. 机会成本展示
    opp_cost_shown: dict[str, str] = {}
    if alternatives:
        # 以第一个替代方案为 chosen，其余为 alternatives 评估
        chosen = alternatives[0]
        others = alternatives[1:] if len(alternatives) > 1 else []
        # 若仅 1 个替代方案，用 plan 的代表任务构造评估
        if not others and plan.tasks:
            others = plan.tasks[:2]
        assessment = assess_opportunity_cost(chosen, others)
        for opt in options:
            opp_cost_shown[opt.id] = assessment.level
    else:
        # 无替代方案时标注"无其他选择"
        for opt in options:
            opp_cost_shown[opt.id] = "low"

    return DecisionPoint(
        plan_id=plan.id,
        context_snapshot=context,
        options=options,
        agent_intensity=intensity,
        opportunity_cost_shown=opp_cost_shown,
    )
