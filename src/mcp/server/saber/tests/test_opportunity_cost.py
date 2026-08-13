"""
SaberSystem 机会成本评估框架测试
三层评估模型：精确层 + 区间层 + 场景层 + 最小后悔原则
关键：不返回单一数值，而是区间+场景描述
"""
import pytest
from datetime import datetime, timedelta
from mcp.server.saber.models import CognitiveLayer, Task
from mcp.server.saber.opportunity_cost import (
    OpportunityCostType,
    OpportunityCostAssessment,
    assess_opportunity_cost,
    assess_single_alternative,
    synthesize_level,
    check_regret_risk,
    generate_scenario_description,
)


def make_task(title, priority_weight=0.5, hours=2.0,
              is_one_time=False, can_reschedule=True,
              window_remaining=1.0):
    """测试辅助：快速构造 Task"""
    return Task(
        title=title, description="", plan_id="p1", goal_id="g1",
        cognitive_layer=CognitiveLayer.W, estimated_hours=hours,
        priority_weight=priority_weight,
        is_one_time_only=is_one_time,
        can_be_rescheduled=can_reschedule,
        time_window_remaining=window_remaining,
    )


class TestOpportunityCostType:
    """机会成本分类枚举"""

    def test_types_exist(self):
        assert OpportunityCostType.TIME_LOSS
        assert OpportunityCostType.OPPORTUNITY_MISS
        assert OpportunityCostType.REGRET_RISK
        assert OpportunityCostType.HEALTH_RISK


class TestAssessSingleAlternative:
    """评估放弃单个替代方案的成本"""

    def test_low_cost_when_recoverable(self):
        """可重新安排的替代方案 → 低成本"""
        chosen = make_task("A", priority_weight=0.5)
        alt = make_task("B", priority_weight=0.3, is_one_time=False,
                        can_reschedule=True, window_remaining=0.8)
        result = assess_single_alternative(chosen, alt)
        assert result["level"] in ("low", "medium")
        assert result["recoverability"] == 0.8  # 可补做

    def test_high_cost_when_one_time_and_urgent(self):
        """一次性机会且窗口即将关闭 → 高成本"""
        chosen = make_task("A", priority_weight=0.3)
        alt = make_task("重要会议", priority_weight=0.7,
                        is_one_time=True, can_reschedule=False,
                        window_remaining=0.1)
        result = assess_single_alternative(chosen, alt)
        assert result["level"] in ("high", "very_high")
        assert result["is_one_time"] is True

    def test_low_cost_when_low_weight(self):
        """低权重的替代方案 → 低成本"""
        chosen = make_task("A", priority_weight=0.6)
        alt = make_task("B", priority_weight=0.1,
                        is_one_time=False, window_remaining=0.9)
        result = assess_single_alternative(chosen, alt)
        assert result["level"] == "low"


class TestSynthesizeLevel:
    """综合多个替代方案的成本等级"""

    def test_very_high_dominates(self):
        components = [
            {"level": "low", "task": None},
            {"level": "very_high", "task": None},
        ]
        assert synthesize_level(components) == "very_high"

    def test_high_overrides_medium(self):
        components = [
            {"level": "medium", "task": None},
            {"level": "high", "task": None},
        ]
        assert synthesize_level(components) == "high"

    def test_all_low_yields_low(self):
        components = [
            {"level": "low", "task": None},
            {"level": "low", "task": None},
        ]
        assert synthesize_level(components) == "low"


class TestAssessOpportunityCost:
    """完整机会成本评估——返回区间+场景，非单一数值"""

    def test_no_alternatives(self):
        """无替代方案时成本为低"""
        chosen = make_task("A")
        result = assess_opportunity_cost(chosen, [])
        assert result.level == "low"
        assert "无其他选择" in result.description or "无明显" in result.description

    def test_returns_assessment_not_number(self):
        """返回 OpportunityCostAssessment 对象，非 float"""
        chosen = make_task("A")
        alt = make_task("B")
        result = assess_opportunity_cost(chosen, [alt])
        assert isinstance(result, OpportunityCostAssessment)
        assert hasattr(result, "level")
        assert hasattr(result, "description")
        assert hasattr(result, "exact_costs")
        assert "time_hours" in result.exact_costs

    def test_exact_costs_included(self):
        """精确层：时间/注意力消耗必须精确"""
        chosen = make_task("A", hours=2.0)
        result = assess_opportunity_cost(chosen, [])
        assert result.exact_costs["time_hours"] == 2.0

    def test_scenario_description_generated(self):
        """场景层：生成自然语言描述"""
        chosen = make_task("写报告", hours=2.0)
        alt = make_task("跑步", priority_weight=0.4,
                        is_one_time=False, window_remaining=0.3)
        result = assess_opportunity_cost(chosen, [alt])
        assert "写报告" in result.description
        assert "2h" in result.description or "2.0" in result.description


class TestCheckRegretRisk:
    """最小后悔原则——检测高后悔风险"""

    def test_no_risk_when_alternative_recoverable(self):
        """可补做的替代方案 → 无高后悔风险"""
        chosen = make_task("A", priority_weight=0.3)
        alt = make_task("B", priority_weight=0.5,
                        is_one_time=False, can_reschedule=True,
                        window_remaining=0.8)
        risk = check_regret_risk(chosen, [alt])
        assert risk is None

    def test_high_risk_when_one_time_high_weight_urgent(self):
        """高权重一次性机会即将关闭 → 高后悔风险"""
        chosen = make_task("写报告", priority_weight=0.3)
        important = make_task("重要会议", priority_weight=0.7,
                              is_one_time=True, can_reschedule=False,
                              window_remaining=0.2)
        risk = check_regret_risk(chosen, [important])
        assert risk is not None
        assert risk.level == "high"
        assert "重要会议" in risk.message
        assert "后悔" in risk.message or "风险" in risk.message

    def test_no_risk_when_chosen_weight_higher(self):
        """当前任务权重高于替代方案 → 无高后悔风险"""
        chosen = make_task("A", priority_weight=0.8)
        alt = make_task("B", priority_weight=0.3,
                        is_one_time=True, window_remaining=0.1)
        risk = check_regret_risk(chosen, [alt])
        assert risk is None


class TestGenerateScenarioDescription:
    """场景化自然语言描述"""

    def test_description_includes_chosen_task(self):
        chosen = make_task("写报告", hours=3.0)
        desc = generate_scenario_description(chosen, [])
        assert "写报告" in desc
        assert "3h" in desc or "3.0" in desc

    def test_description_includes_alternatives(self):
        chosen = make_task("写报告")
        components = [
            {
                "task": make_task("跑步"),
                "level": "high",
                "urgency": 0.8,
                "weight_value": 0.4,
                "recoverability": 0.5,
                "is_one_time": False,
            },
        ]
        desc = generate_scenario_description(chosen, components)
        assert "跑步" in desc
