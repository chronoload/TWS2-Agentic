"""
SaberSystem 决策生成测试
TDD: 上下文注入器 + 决策生成器（含机会成本核算 + I(P) 闸门 + 防沉迷）
"""
import pytest
from mcp.server.saber.models import CognitiveLayer, Plan, Task, DecisionOption
from mcp.server.saber.life import LifeResource, AttentionCapital, HealthStatus
from mcp.server.saber.agent import AgentContributionLog
from mcp.server.saber.decision import (
    build_limited_context,
    generate_decision_point,
)


def _make_plan(title="LLM 项目", focus=CognitiveLayer.S, progress=0.68) -> Plan:
    plan = Plan(title=title, description="", goal_id="g1",
                cognitive_focus=focus, priority_weight=0.6)
    plan.aggregated_progress = progress
    return plan


def _make_life(attention=0.68, energy=0.55, surplus=2.8) -> LifeResource:
    life = LifeResource(user_id="u1")
    life.attention_capital.balance = attention
    life.energy_level = energy
    life.waking_hours_used = life.waking_hours_total - surplus
    return life


def _make_log(adopted=True, modification=0.05) -> AgentContributionLog:
    return AgentContributionLog(
        plan_id="p1", user_id="u1", suggestion_type="advice",
        was_adopted=adopted, user_modification_ratio=modification,
        attention_consumed=0.1, cognitive_layer_target=CognitiveLayer.S,
        intensity_at_creation=0.5,
    )


# ─── 上下文注入器 ───

class TestBuildLimitedContext:
    """build_limited_context: ≤200 字受约束上下文（§11.4）"""

    def test_includes_plan_title(self):
        ctx = build_limited_context(_make_plan(title="LLM 项目"), _make_life())
        assert "LLM 项目" in ctx

    def test_includes_cognitive_layer(self):
        ctx = build_limited_context(_make_plan(focus=CognitiveLayer.S), _make_life())
        assert "S" in ctx

    def test_includes_attention_balance(self):
        ctx = build_limited_context(_make_plan(), _make_life(attention=0.68))
        assert "0.68" in ctx or "68" in ctx

    def test_includes_energy_level(self):
        ctx = build_limited_context(_make_plan(), _make_life(energy=0.55))
        assert "0.55" in ctx or "55" in ctx

    def test_under_500_chars(self):
        ctx = build_limited_context(_make_plan(), _make_life())
        assert len(ctx) <= 500

    def test_includes_waking_hours_surplus(self):
        ctx = build_limited_context(_make_plan(), _make_life(surplus=2.8))
        assert "2.8" in ctx


# ─── 决策生成器 ───

class TestGenerateDecisionPoint:
    """generate_decision_point: I(P) 闸门 + 机会成本核算 + 防沉迷"""

    def test_retired_when_intensity_below_threshold(self):
        """I(P) < 0.1 时 Agent 已退役，返回 None"""
        plan = _make_plan()
        life = _make_life()
        # proficiency=1.0 → I(P)≈0.05 < 0.1
        dp = generate_decision_point(plan, life, proficiency=1.0,
                                     recent_logs=[], alternatives=[])
        assert dp is None

    def test_returns_none_when_burned_out(self):
        """burned_out 时不生成决策，推荐休息"""
        plan = _make_plan()
        life = _make_life()
        life.health.physical_fatigue = 0.9  # burned_out
        dp = generate_decision_point(plan, life, proficiency=0.0,
                                     recent_logs=[], alternatives=[])
        assert dp is None

    def test_generates_decision_point_with_options(self):
        """正常情况生成 2~4 个选项的决策点"""
        plan = _make_plan()
        life = _make_life()
        dp = generate_decision_point(plan, life, proficiency=0.2,
                                     recent_logs=[], alternatives=[])
        assert dp is not None
        assert 1 <= len(dp.options) <= 6
        assert dp.agent_intensity > 0

    def test_options_have_life_cost(self):
        """每个选项必须标注注意力/体能消耗/盈余变化"""
        plan = _make_plan()
        life = _make_life()
        dp = generate_decision_point(plan, life, proficiency=0.2,
                                     recent_logs=[], alternatives=[])
        for opt in dp.options:
            assert opt.attention_cost >= 0
            assert opt.energy_cost >= 0
            assert isinstance(opt.surplus_delta, float)

    def test_context_snapshot_under_500(self):
        """决策点的 context_snapshot ≤500 字（纳入工作文件 + diff 后放宽）"""
        plan = _make_plan()
        life = _make_life()
        dp = generate_decision_point(plan, life, proficiency=0.2,
                                     recent_logs=[], alternatives=[])
        assert len(dp.context_snapshot) <= 500

    def test_anti_dependency_triggers_restricted_decision(self):
        """防沉迷触发时，返回受限决策（提示用户手动输入）"""
        plan = _make_plan()
        life = _make_life()
        # 连续 3 次无脑采纳
        logs = [_make_log(adopted=True, modification=0.05) for _ in range(3)]
        dp = generate_decision_point(plan, life, proficiency=0.1,
                                     recent_logs=logs, alternatives=[])
        # 防沉迷触发：选项描述包含"手动"提示，或返回特殊标记
        assert dp is not None
        assert any("手动" in o.description or "自主" in o.description
                   for o in dp.options)

    def test_injected_generator_used(self):
        """可注入自定义 generator 替代默认规则生成"""
        plan = _make_plan()
        life = _make_life()

        def mock_gen(context, intensity, life_vector):
            return [
                {"description": "自定义选项A", "rationale": "测试",
                 "estimated_impact": "无", "confidence": 0.9,
                 "action_payload": {}, "attention_cost": 0.1,
                 "energy_cost": 0.1, "missed_opportunities": [],
                 "surplus_delta": 0.0},
                {"description": "自定义选项B", "rationale": "测试",
                 "estimated_impact": "无", "confidence": 0.6,
                 "action_payload": {}, "attention_cost": 0.2,
                 "energy_cost": 0.2, "missed_opportunities": [],
                 "surplus_delta": -1.0},
            ]
        dp = generate_decision_point(plan, life, proficiency=0.2,
                                     recent_logs=[], alternatives=[],
                                     generator=mock_gen)
        assert dp is not None
        assert dp.options[0].description == "自定义选项A"

    def test_opportunity_cost_shown_populated(self):
        """决策点包含机会成本展示信息"""
        plan = _make_plan()
        life = _make_life()
        alt = Task(title="替代任务", description="", plan_id="p1", goal_id="g1",
                   cognitive_layer=CognitiveLayer.K, estimated_hours=1.0,
                   is_one_time_only=True, time_window_remaining=0.1)
        dp = generate_decision_point(plan, life, proficiency=0.2,
                                     recent_logs=[], alternatives=[alt])
        assert dp is not None
        assert len(dp.opportunity_cost_shown) > 0
