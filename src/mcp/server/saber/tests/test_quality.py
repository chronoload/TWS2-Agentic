"""
SaberSystem 质量审核模型测试
双层质量：硬质量（System 确定性）+ 软质量（Agent 客观审核）
含透支惩罚、申诉机制、质量影响传导
"""
import pytest
from mcp.server.saber.quality import (
    QualityScore,
    AuditAppeal,
    compute_hard_quality,
    compute_overdraft_penalty,
    compute_final_score,
    apply_quality_impact,
    audit_soft_quality,
)
from mcp.server.saber.models import CognitiveLayer, Plan, Constraint
from mcp.server.saber.life import LifeResource, AttentionCapital


def make_plan_with_constraints(constraint_passed=True):
    """测试辅助：构造含约束的 Plan"""
    plan = Plan(title="测试", description="", goal_id="g1",
                cognitive_focus=CognitiveLayer.W, priority_weight=0.6)
    plan.constraints = [
        Constraint(plan_id=plan.id, type="file_exists",
                   target="output.md", operator="exists",
                   value=True, must_hold=True),
    ]
    plan._test_constraint_passed = constraint_passed  # 测试钩子
    return plan


class TestQualityScore:
    """质量分数据结构"""

    def test_create_quality_score(self):
        qs = QualityScore(
            plan_id="p1", artifact_path="output.md",
            hard_quality=0.8, soft_quality=0.7,
            composite_score=0.75,
            attention_overdraft_penalty=1.0,
            final_score=0.75,
        )
        assert qs.plan_id == "p1"
        assert qs.hard_quality == 0.8
        assert qs.soft_quality == 0.7

    def test_composite_is_half_half(self):
        """综合分 = 硬质量 × 0.5 + 软质量 × 0.5"""
        qs = QualityScore(
            plan_id="p1", artifact_path="x",
            hard_quality=0.8, soft_quality=0.6,
            composite_score=0.0,  # 待计算
            attention_overdraft_penalty=1.0,
            final_score=0.0,
        )
        qs.composite_score = 0.8 * 0.5 + 0.6 * 0.5
        assert qs.composite_score == pytest.approx(0.7)


class TestComputeHardQuality:
    """硬质量——System 确定性计算"""

    def test_all_constraints_passed(self):
        """所有约束通过 → 高硬质量"""
        plan = make_plan_with_constraints(constraint_passed=True)
        # mock 约束核验
        constraints = plan.constraints
        # 假设全部通过
        hard_q, metrics = compute_hard_quality(
            satisfaction_rate=1.0,
            metrics={"test_coverage": 0.9, "lint_score": 0.95},
        )
        assert hard_q > 0.9

    def test_partial_constraints_passed(self):
        """部分约束通过 → 中等硬质量"""
        hard_q, _ = compute_hard_quality(
            satisfaction_rate=0.5,
            metrics={"test_coverage": 0.5, "lint_score": 0.5},
        )
        assert hard_q == pytest.approx(0.5, abs=0.05)


class TestOverdraftPenalty:
    """注意力透支惩罚"""

    def test_no_penalty_when_not_overdrawn(self):
        """未透支 → 无惩罚（1.0）"""
        life = LifeResource(user_id="u1")
        life.attention_capital = AttentionCapital(balance=0.5)
        penalty = compute_overdraft_penalty(life)
        assert penalty == 1.0

    def test_penalty_when_overdrawn(self):
        """透支一次 → 惩罚 0.9"""
        life = LifeResource(user_id="u1")
        life.attention_capital = AttentionCapital(balance=-0.3, overdraft_count=1)
        penalty = compute_overdraft_penalty(life)
        assert penalty == pytest.approx(0.9)

    def test_penalty_capped_at_0_7(self):
        """惩罚下限 0.7（即使透支多次）"""
        life = LifeResource(user_id="u1")
        life.attention_capital = AttentionCapital(balance=-0.5, overdraft_count=10)
        penalty = compute_overdraft_penalty(life)
        assert penalty == 0.7


class TestFinalScore:
    """最终质量分 = 综合 × 惩罚"""

    def test_no_penalty(self):
        final = compute_final_score(composite=0.8, penalty=1.0)
        assert final == pytest.approx(0.8)

    def test_with_penalty(self):
        final = compute_final_score(composite=0.8, penalty=0.7)
        assert final == pytest.approx(0.56)


class TestAuditSoftQuality:
    """软质量审核（Agent 客观审核）"""

    def test_returns_score_and_rationale(self):
        """审核返回分数+理由"""
        life = LifeResource(user_id="u1")
        result = audit_soft_quality(
            dimensions={"readability": 0.8, "depth": 0.7,
                        "originality": 0.6, "alignment": 0.9,
                        "maintainability": 0.7},
            life=life,
            hard_quality=0.8,
        )
        assert "soft_quality" in result
        assert "rationale" in result
        assert "penalty" in result
        assert 0.0 <= result["soft_quality"] <= 1.0

    def test_overdraft_adds_penalty_note(self):
        """透支时理由中包含惩罚说明"""
        life = LifeResource(user_id="u1")
        life.attention_capital = AttentionCapital(balance=-0.3, overdraft_count=1)
        result = audit_soft_quality(
            dimensions={"readability": 0.8, "depth": 0.7,
                        "originality": 0.6, "alignment": 0.9,
                        "maintainability": 0.7},
            life=life,
            hard_quality=0.8,
        )
        assert "透支" in result["rationale"] or "惩罚" in result["rationale"]
        assert result["penalty"] < 1.0


class TestApplyQualityImpact:
    """质量影响传导——质量分影响三件事"""

    def test_surplus_multiplier(self):
        """高质量 → 更多盈余倍率"""
        # final_score=1.0 → multiplier=1.5
        impact = apply_quality_impact(
            final_score=1.0, estimated_surplus=2.0,
            consecutive_high_quality=0,
        )
        assert impact["surplus_multiplier"] == pytest.approx(1.5)
        assert impact["actual_surplus"] == pytest.approx(3.0)

    def test_low_quality_reduces_surplus(self):
        """低质量 → 减少盈余"""
        # final_score=0.0 → multiplier=0.5
        impact = apply_quality_impact(
            final_score=0.0, estimated_surplus=2.0,
            consecutive_high_quality=0,
        )
        assert impact["surplus_multiplier"] == pytest.approx(0.5)
        assert impact["actual_surplus"] == pytest.approx(1.0)

    def test_consecutive_high_quality_triggers_reweight_suggestion(self):
        """连续 3 次高质量 → 触发权重重分配建议"""
        impact = apply_quality_impact(
            final_score=0.9, estimated_surplus=2.0,
            consecutive_high_quality=3,
        )
        assert impact["reweight_suggested"] is True

    def test_no_reweight_before_3_consecutive(self):
        """不足 3 次 → 不建议重分配"""
        impact = apply_quality_impact(
            final_score=0.9, estimated_surplus=2.0,
            consecutive_high_quality=2,
        )
        assert impact["reweight_suggested"] is False


class TestAuditAppeal:
    """申诉机制"""

    def test_create_appeal(self):
        appeal = AuditAppeal(
            quality_score_id="qs1",
            user_reason="我认为可读性评分过低",
        )
        assert appeal.quality_score_id == "qs1"
        assert appeal.appeal_status == "pending"
        assert appeal.re_audit_score is None
