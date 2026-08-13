"""
SaberSystem 机会成本评估框架
三层评估模型：精确层 + 区间层 + 场景层 + 最小后悔原则
核心：不返回单一数值，而是区间+场景描述，让用户自己做价值判断
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from mcp.server.saber.models import Task


class OpportunityCostType(Enum):
    """机会成本分类——放弃的类型"""
    TIME_LOSS = "time"           # 直接时间损失（精确）
    ATTENTION_LOSS = "attention" # 注意力资本消耗（精确）
    ENERGY_LOSS = "energy"       # 体能消耗（精确）
    OPPORTUNITY_MISS = "miss"    # 错失机遇（区间）
    REGRET_RISK = "regret"       # 后悔风险（区间）
    HEALTH_RISK = "health"       # 健康风险（区间）
    RELATION_RISK = "relation"   # 关系风险（区间)


CostLevel = Literal["low", "medium", "high", "very_high"]


@dataclass
class OpportunityCostAssessment:
    """机会成本评估结果——区间+场景，非单一数值"""
    level: CostLevel
    description: str
    components: list[dict]
    exact_costs: dict = field(default_factory=dict)


@dataclass
class RiskWarning:
    """高后悔风险警告"""
    level: Literal["high", "very_high"]
    message: str
    recommended_action: str = ""


def assess_single_alternative(chosen: Task, alt: Task) -> dict:
    """评估放弃单个替代方案的成本"""
    # 时间紧迫性：窗口剩余越少越紧迫
    if alt.time_window_remaining < 0.2:
        urgency = 1.0
    elif alt.time_window_remaining < 0.5:
        urgency = 0.7
    else:
        urgency = 0.4

    # 权重价值
    weight_value = alt.priority_weight

    # 可恢复性：错过后能否补回
    if alt.is_one_time_only:
        recoverability = 0.2
    elif alt.can_be_rescheduled:
        recoverability = 0.8
    else:
        recoverability = 0.5

    # 综合评估：紧迫 × 权重 × (1 - 可恢复性)
    raw_score = urgency * weight_value * (1 - recoverability)

    # 映射到区间
    if raw_score > 0.6:
        level: CostLevel = "very_high"
    elif raw_score > 0.4:
        level = "high"
    elif raw_score > 0.2:
        level = "medium"
    else:
        level = "low"

    return {
        "task": alt,
        "level": level,
        "urgency": urgency,
        "weight_value": weight_value,
        "recoverability": recoverability,
        "is_one_time": alt.is_one_time_only,
    }


def synthesize_level(components: list[dict]) -> CostLevel:
    """综合多个替代方案的成本等级——取最高"""
    levels = [c["level"] for c in components]
    priority = {"low": 0, "medium": 1, "high": 2, "very_high": 3}
    if not levels:
        return "low"
    return max(levels, key=lambda l: priority[l])


def generate_scenario_description(chosen: Task, components: list[dict]) -> str:
    """生成场景化自然语言描述"""
    level_desc = {
        "very_high": "将严重错过",
        "high": "将错过",
        "medium": "可能错过",
        "low": "可稍后补做",
    }
    parts = []
    for comp in components:
        alt = comp["task"]
        desc = level_desc.get(comp["level"], "将影响")
        if comp.get("is_one_time"):
            parts.append(f'{desc}一次难得的机会「{alt.title}」')
        else:
            parts.append(f'{desc}「{alt.title}」（权重 {comp["weight_value"]:.2f}）')

    hours = chosen.estimated_hours
    hours_str = f"{hours:g}h" if hours == int(hours) else f"{hours}h"
    if parts:
        return f"选择「{chosen.title}」将花费 {hours_str}，" + "；".join(parts) + "。"
    return f"选择「{chosen.title}」将花费 {hours_str}，无明显机会成本。"


def assess_opportunity_cost(
    chosen_task: Task,
    alternatives: list[Task],
) -> OpportunityCostAssessment:
    """
    评估选择当前任务的机会成本——不返回单一数值，而是区间+场景描述。
    三层评估：精确层（资源消耗）+ 区间层（低/中/高/极高）+ 场景层（自然语言）
    """
    if not alternatives:
        return OpportunityCostAssessment(
            level="low",
            description="无其他选择",
            components=[],
            exact_costs={
                "time_hours": chosen_task.estimated_hours,
                "attention_cost": chosen_task.attention_cost,
                "energy_cost": chosen_task.energy_requirement,
            },
        )

    # 1. 精确层：资源消耗
    time_cost = chosen_task.estimated_hours
    attention_cost = chosen_task.attention_cost
    energy_cost = chosen_task.energy_requirement

    # 2. 区间层：评估前两名替代方案
    top_alternatives = sorted(
        alternatives,
        key=lambda t: t.priority_weight * (1 - t.time_window_remaining),
        reverse=True,
    )[:2]

    cost_components = [assess_single_alternative(chosen_task, alt)
                       for alt in top_alternatives]

    # 3. 综合区间
    overall_level = synthesize_level(cost_components)

    # 4. 场景层：自然语言描述
    description = generate_scenario_description(chosen_task, cost_components)

    return OpportunityCostAssessment(
        level=overall_level,
        description=description,
        components=cost_components,
        exact_costs={
            "time_hours": time_cost,
            "attention_cost": attention_cost,
            "energy_cost": energy_cost,
        },
    )


def check_regret_risk(
    chosen_task: Task,
    alternatives: list[Task],
) -> RiskWarning | None:
    """
    最小后悔原则——检测高后悔风险。
    高后悔风险 = 高权重一次性机会即将关闭，且当前任务权重低于该机会。
    """
    regretful_alternatives = [
        alt for alt in alternatives
        if alt.priority_weight > 0.3              # 高权重
        and alt.is_one_time_only                   # 一次性机会
        and alt.time_window_remaining < 0.3        # 即将关闭
        and chosen_task.priority_weight < alt.priority_weight  # 权重低于替代
    ]

    if regretful_alternatives:
        worst = max(regretful_alternatives,
                    key=lambda a: a.priority_weight)
        return RiskWarning(
            level="high",
            message=(f"高后悔风险：选择「{chosen_task.title}」将错过"
                     f"高权重一次性机会「{worst.title}」"
                     f"（权重 {worst.priority_weight}）。"
                     f"该机会窗口即将关闭，错过后无法补回。"),
            recommended_action=(f"建议优先完成「{worst.title}」，"
                                f"或调整计划以同时容纳两者。"),
        )
    return None
