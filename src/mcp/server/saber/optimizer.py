"""
SaberSystem 多目标资源分配优化器
优先级评分 = 权重 × 紧迫度 × 健康匹配度 × 认知层级增益
按 Softmax 比例分配有限清醒小时与注意力，保留 20% 余量
含权重失衡检测（理想偏航警告）
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from mcp.server.saber.models import Plan, CognitiveLayer
from mcp.server.saber.life import LifeResource


@dataclass
class ImbalanceWarning:
    """理想偏航警告"""
    level: str  # high | medium
    message: str
    recommended_action: str = ""


def compute_urgency(plan: Plan) -> float:
    """
    紧迫度——距 deadline 越近越紧迫，0~1
    30 天以上 → ~0.1；1 天 → ~0.9；逾期 → 1.0
    """
    if plan.maturity_deadline is None:
        return 0.3  # 无截止日 → 默认低紧迫
    now = datetime.now()
    delta_days = (plan.maturity_deadline - now).total_seconds() / 86400
    if delta_days <= 0:
        return 1.0  # 逾期
    # 指数衰减：1 天 → 0.9，7 天 → 0.5，30 天 → 0.1
    urgency = max(0.0, min(1.0, 1.0 - delta_days / 30))
    return urgency


def compute_health_match(plan: Plan, life: LifeResource) -> float:
    """
    健康匹配度——Plan 所需体能与当前体能的匹配
    高能耗 Plan + 疲惫 user → 低匹配
    低能耗 Plan + 任何 user → 高匹配
    """
    if plan.energy_cost <= 0:
        return 1.0
    # 匹配度 = user 体能 / Plan 需求，封顶 1.0
    match = life.energy_level / plan.energy_cost
    return max(0.0, min(1.0, match))


def compute_cognitive_gain(plan: Plan) -> float:
    """
    认知层级增益——该 Plan 对 Ideal 的认知层级增益
    WORKFLOW 层（最高）→ 1.0；KNOWLEDGE 层（最低）→ 0.4
    """
    gain_map = {
        CognitiveLayer.KNOWLEDGE: 0.4,
        CognitiveLayer.CONCEPT: 0.6,
        CognitiveLayer.THEORY: 0.7,
        CognitiveLayer.SKILL: 0.85,
        CognitiveLayer.WORKFLOW: 1.0,
    }
    return gain_map.get(plan.cognitive_focus, 0.5)


def plan_priority_score(plan: Plan, life: LifeResource) -> float:
    """
    Plan 优先级 = 权重 × 紧迫度 × 健康匹配度 × 认知层级增益
    系统按此分数对活跃 Plan 排序，分配清醒小时与注意力。
    """
    weight = plan.priority_weight
    urgency = compute_urgency(plan)
    health_match = compute_health_match(plan, life)
    layer_gain = compute_cognitive_gain(plan)
    return weight * urgency * health_match * layer_gain


def allocate_life_resources(
    active_plans: list[Plan],
    life: LifeResource,
) -> dict[str, dict]:
    """
    在多个活跃 Plan 间分配今日剩余的清醒小时与注意力。
    使用加权比例分配，保留 20% 余量供休息/意外。
    """
    if not active_plans:
        return {}

    scores = {p.id: plan_priority_score(p, life) for p in active_plans}
    total_score = sum(scores.values())
    if total_score <= 0:
        # 全零分时平均分配
        ratio = 1.0 / len(active_plans)
        return {
            p.id: {
                "waking_hours": life.waking_hours_surplus * 0.8 * ratio,
                "attention_budget": life.attention_capital.balance * 0.8 * ratio,
                "priority_score": 0.0,
            }
            for p in active_plans
        }

    # 保留 20% 余量
    available_hours = life.waking_hours_surplus * 0.8
    available_attention = life.attention_capital.balance * 0.8

    allocation = {}
    for p in active_plans:
        ratio = scores[p.id] / total_score
        allocation[p.id] = {
            "waking_hours": available_hours * ratio,
            "attention_budget": available_attention * ratio,
            "priority_score": scores[p.id],
        }
    return allocation


def check_weight_imbalance(
    active_plans: list[Plan],
    actual_allocation: dict[str, float],
    window_days: int = 7,
) -> ImbalanceWarning | None:
    """
    权重失衡检测（理想偏航）：
    - 高权重 Goal（>0.3）收到 <5% 资源 → 警告
    - 低权重 Goal（<0.2）独占 >70% 资源 → 警告
    """
    for plan in active_plans:
        alloc = actual_allocation.get(plan.id, 0.0)
        if plan.priority_weight > 0.3 and alloc < 0.05:
            return ImbalanceWarning(
                level="high",
                message=(f"高权重目标（权重 {plan.priority_weight}）已 "
                         f"{window_days} 天未投入资源，你的理想正在偏航。"
                         f"建议本周至少分配 2h。"),
                recommended_action=f"建议优先为「{plan.title}」分配资源",
            )
        if plan.priority_weight < 0.2 and alloc > 0.7:
            return ImbalanceWarning(
                level="medium",
                message=(f"低权重目标「{plan.title}」"
                         f"（权重 {plan.priority_weight}）独占了 "
                         f"{alloc*100:.0f}% 资源，是否需要重新评估理想权重？"),
                recommended_action="建议调整 Goal 权重或 Plan 优先级",
            )
    return None
