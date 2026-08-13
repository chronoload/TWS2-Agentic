"""
SaberSystem 多目标资源分配优化器测试
优先级评分 = 权重 × 紧迫度 × 健康匹配度 × 认知层级增益
按 Softmax 比例分配有限清醒小时与注意力
"""
import pytest
from datetime import datetime, timedelta
from mcp.server.saber.models import CognitiveLayer, Plan
from mcp.server.saber.life import LifeResource, HealthStatus
from mcp.server.saber.optimizer import (
    plan_priority_score,
    allocate_life_resources,
    check_weight_imbalance,
    compute_urgency,
    compute_health_match,
)


def make_plan(title, weight=0.5, deadline_days=7, energy_cost=0.3,
              cognitive_layer=CognitiveLayer.W):
    """测试辅助：构造 Plan"""
    plan = Plan(title=title, description="", goal_id="g1",
                cognitive_focus=cognitive_layer, priority_weight=weight,
                energy_cost=energy_cost,
                maturity_deadline=datetime.now() + timedelta(days=deadline_days))
    return plan


class TestComputeUrgency:
    """紧迫度计算"""

    def test_far_deadline_low_urgency(self):
        """截止日远 → 低紧迫"""
        plan = make_plan("A", deadline_days=30)
        urgency = compute_urgency(plan)
        assert urgency < 0.3

    def test_near_deadline_high_urgency(self):
        """截止日近 → 高紧迫"""
        plan = make_plan("A", deadline_days=1)
        urgency = compute_urgency(plan)
        assert urgency > 0.7

    def test_overdue_max_urgency(self):
        """已逾期 → 最高紧迫"""
        plan = make_plan("A", deadline_days=-1)
        urgency = compute_urgency(plan)
        assert urgency == 1.0


class TestComputeHealthMatch:
    """健康匹配度——Plan 所需体能与当前体能的匹配"""

    def test_high_energy_plan_matches_healthy_user(self):
        """高能耗 Plan + 健康 user → 高匹配"""
        plan = make_plan("A", energy_cost=0.8)
        life = LifeResource(user_id="u1")
        life.energy_level = 0.9
        match = compute_health_match(plan, life)
        assert match > 0.7

    def test_high_energy_plan_mismatches_tired_user(self):
        """高能耗 Plan + 疲惫 user → 低匹配"""
        plan = make_plan("A", energy_cost=0.8)
        life = LifeResource(user_id="u1")
        life.energy_level = 0.2
        match = compute_health_match(plan, life)
        assert match < 0.4


class TestPlanPriorityScore:
    """优先级评分 = 权重 × 紧迫度 × 健康匹配度"""

    def test_high_weight_high_urgency_yields_high_score(self):
        """高权重+高紧迫 → 高分"""
        plan = make_plan("A", weight=0.8, deadline_days=1, energy_cost=0.3)
        life = LifeResource(user_id="u1")
        life.energy_level = 0.8
        score = plan_priority_score(plan, life)
        assert score > 0.5

    def test_low_weight_low_urgency_yields_low_score(self):
        """低权重+低紧迫 → 低分"""
        plan = make_plan("A", weight=0.1, deadline_days=30, energy_cost=0.3)
        life = LifeResource(user_id="u1")
        life.energy_level = 0.8
        score = plan_priority_score(plan, life)
        assert score < 0.1

    def test_score_ordering(self):
        """高分 Plan 应排在低分 Plan 之前"""
        life = LifeResource(user_id="u1")
        life.energy_level = 0.8
        high = make_plan("高优先", weight=0.8, deadline_days=1)
        low = make_plan("低优先", weight=0.1, deadline_days=30)
        assert plan_priority_score(high, life) > plan_priority_score(low, life)


class TestAllocateLifeResources:
    """多目标资源分配——Softmax 比例分配"""

    def test_returns_allocation_dict(self):
        plans = [make_plan("A", weight=0.6), make_plan("B", weight=0.4)]
        life = LifeResource(user_id="u1")
        alloc = allocate_life_resources(plans, life)
        assert isinstance(alloc, dict)
        assert len(alloc) == 2

    def test_higher_weight_gets_more_resources(self):
        """高权重 Plan 分配更多资源"""
        high = make_plan("高", weight=0.8, deadline_days=1)
        low = make_plan("低", weight=0.2, deadline_days=30)
        life = LifeResource(user_id="u1")
        life.energy_level = 0.8
        alloc = allocate_life_resources([high, low], life)
        assert alloc[high.id]["waking_hours"] > alloc[low.id]["waking_hours"]

    def test_preserves_20_percent_buffer(self):
        """保留 20% 余量供休息/意外"""
        plan = make_plan("A", weight=1.0, deadline_days=1)
        life = LifeResource(user_id="u1")
        life.energy_level = 0.8
        alloc = allocate_life_resources([plan], life)
        # 单个 Plan 也只能拿到 80% 的盈余
        allocated = alloc[plan.id]["waking_hours"]
        available = life.waking_hours_surplus * 0.8
        assert allocated == pytest.approx(available, abs=0.01)

    def test_empty_plans_returns_empty(self):
        """无活跃 Plan → 空分配"""
        life = LifeResource(user_id="u1")
        alloc = allocate_life_resources([], life)
        assert alloc == {}


class TestCheckWeightImbalance:
    """权重失衡警告——理想偏航检测"""

    def test_warns_when_high_weight_starved(self):
        """高权重 Goal 长期无资源 → 警告"""
        high_weight_plan = make_plan("重要", weight=0.6)
        # 模拟该 Plan 过去 7 天收到 0% 资源
        warning = check_weight_imbalance(
            active_plans=[high_weight_plan],
            actual_allocation={high_weight_plan.id: 0.0},
            window_days=7,
        )
        assert warning is not None
        assert "偏航" in warning.message or "未投入" in warning.message

    def test_warns_when_low_weight_dominates(self):
        """低权重 Goal 独占 70% 资源 → 警告"""
        low_weight = make_plan("次要", weight=0.1)
        warning = check_weight_imbalance(
            active_plans=[low_weight],
            actual_allocation={low_weight.id: 0.75},
            window_days=7,
        )
        assert warning is not None
        assert "独占" in warning.message or "权重" in warning.message

    def test_no_warning_when_balanced(self):
        """平衡分配 → 无警告"""
        plan = make_plan("A", weight=0.5)
        warning = check_weight_imbalance(
            active_plans=[plan],
            actual_allocation={plan.id: 0.5},
            window_days=7,
        )
        assert warning is None
