"""
SaberSystem 质量审核模型
双层质量：硬质量（System 确定性）+ 软质量（Agent 客观审核）
含透支惩罚、申诉机制、质量影响传导
关键：Agent 审核职能永不衰减（与建议职能正交）
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from mcp.server.saber.life import LifeResource


@dataclass
class QualityScore:
    """交付物质量分——双层结构"""
    plan_id: str
    artifact_path: str
    hard_quality: float                     # 0~1，System 确定性计算
    soft_quality: float                     # 0~1，Agent 客观审核
    composite_score: float                  # hard × 0.5 + soft × 0.5
    attention_overdraft_penalty: float      # 0.7~1.0
    final_score: float                      # composite × penalty
    id: str = field(default_factory=lambda: str(uuid4()))
    hard_metrics: dict = field(default_factory=dict)
    soft_metrics: dict = field(default_factory=dict)
    audit_rationale: str = ""
    audited_at: datetime = field(default_factory=datetime.now)
    appeal_status: str = "none"  # none | pending | re_audited | resolved
    re_audit_score: float | None = None
    consecutive_high_quality: int = 0


@dataclass
class AuditAppeal:
    """用户对软质量审核的申诉"""
    quality_score_id: str
    user_reason: str
    id: str = field(default_factory=lambda: str(uuid4()))
    submitted_at: datetime = field(default_factory=datetime.now)
    re_audit_temperature: float = 0.3  # 二次审核温度（不同于首次）
    re_audit_score: float | None = None
    final_soft_quality: float | None = None  # 首次与二次的均值
    resolved_at: datetime | None = None
    appeal_status: str = "pending"


def compute_hard_quality(
    satisfaction_rate: float,
    metrics: dict[str, float],
) -> tuple[float, dict]:
    """
    硬质量 = 约束满足率 × 0.5 + 量化指标加权均值 × 0.5
    纯数学，不可申诉
    """
    normalized_metrics = {k: max(0.0, min(1.0, v)) for k, v in metrics.items()}
    metrics_mean = (sum(normalized_metrics.values()) / len(normalized_metrics)
                    if normalized_metrics else 0.0)
    hard_quality = satisfaction_rate * 0.5 + metrics_mean * 0.5
    return hard_quality, normalized_metrics


def compute_overdraft_penalty(life: LifeResource) -> float:
    """
    注意力透支惩罚系数：0.7~1.0
    每次透支扣 0.1，下限 0.7。不可申诉。
    """
    cap = life.attention_capital
    if not cap.is_overdrawn():
        return 1.0
    penalty = max(0.7, 1.0 - cap.overdraft_count * 0.1)
    return penalty


def compute_final_score(composite: float, penalty: float) -> float:
    """最终质量分 = 综合分 × 惩罚系数"""
    return composite * penalty


def audit_soft_quality(
    dimensions: dict[str, float],
    life: LifeResource,
    hard_quality: float,
) -> dict:
    """
    Agent 客观审核软质量——5 维度拆分 + 低温度采样
    dimensions: {readability, depth, originality, alignment, maintainability}
    返回 {soft_quality, rationale, penalty}
    """
    # 软质量 = 5 维度均值
    soft_quality = (sum(dimensions.values()) / len(dimensions)
                    if dimensions else 0.0)

    # 注意力透支惩罚
    penalty = compute_overdraft_penalty(life)

    # 生成审核理由
    rationale_parts = [f"硬质量 {hard_quality:.2f}",
                       f"软质量 {soft_quality:.2f}"]
    if penalty < 1.0:
        rationale_parts.append(
            f"⚠️ 注意力透支惩罚 ×{penalty}"
            f"（连续透支 {life.attention_capital.overdraft_count} 次）"
        )
    rationale = " ｜ ".join(rationale_parts)

    return {
        "soft_quality": soft_quality,
        "rationale": rationale,
        "penalty": penalty,
    }


def apply_quality_impact(
    final_score: float,
    estimated_surplus: float,
    consecutive_high_quality: int,
) -> dict:
    """
    质量影响传导——质量分影响三件事：
    1. 盈余结算倍率（0.5x~1.5x）
    2. 信任分更新（外部处理）
    3. 连续 3 次高质量触发权重重分配建议
    """
    # 盈余倍率：final_score=0 → 0.5x，final_score=1 → 1.5x
    surplus_multiplier = 0.5 + final_score
    actual_surplus = estimated_surplus * surplus_multiplier

    # 连续 3 次高质量（final_score > 0.85）触发重分配建议
    reweight_suggested = (final_score > 0.85 and consecutive_high_quality >= 3)

    return {
        "surplus_multiplier": surplus_multiplier,
        "actual_surplus": actual_surplus,
        "reweight_suggested": reweight_suggested,
    }
