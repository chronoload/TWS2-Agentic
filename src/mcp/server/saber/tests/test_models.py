"""
SaberSystem 数据模型测试
TDD: 先写测试，看着它失败，再写最小实现通过
"""
import pytest
from datetime import datetime
from mcp.server.saber.models import (
    CognitiveLayer,
    Ideal,
    Goal,
    Plan,
    Task,
    Constraint,
    DecisionOption,
    DecisionPoint,
)


class TestCognitiveLayer:
    """认知阶梯 K-C-T-S-W"""

    def test_layer_values(self):
        assert CognitiveLayer.KNOWLEDGE.value == "K"
        assert CognitiveLayer.CONCEPT.value == "C"
        assert CognitiveLayer.THEORY.value == "T"
        assert CognitiveLayer.SKILL.value == "S"
        assert CognitiveLayer.WORKFLOW.value == "W"

    def test_layer_order(self):
        """认知层级应可比较顺序"""
        assert CognitiveLayer.KNOWLEDGE < CognitiveLayer.CONCEPT
        assert CognitiveLayer.CONCEPT < CognitiveLayer.THEORY
        assert CognitiveLayer.THEORY < CognitiveLayer.SKILL
        assert CognitiveLayer.SKILL < CognitiveLayer.WORKFLOW


class TestIdeal:
    """理想——顶层目的锚点"""

    def test_create_ideal(self):
        ideal = Ideal(title="成为独立思考的创造者",
                      description="在 AI 时代保持独立思考与创造能力")
        assert ideal.id is not None
        assert ideal.title == "成为独立思考的创造者"
        assert ideal.status == "active"
        assert ideal.created_at is not None

    def test_ideal_can_evolve(self):
        """旧理想转为 evolved 而非删除"""
        ideal = Ideal(title="旧理想", description="被取代")
        ideal.status = "evolved"
        assert ideal.status == "evolved"


class TestGoal:
    """目标——Ideal 下的可衡量方向"""

    def test_create_goal_with_weight(self):
        goal = Goal(title="掌握 LLM 工程",
                    description="",
                    ideal_id="ideal-1",
                    priority_weight=0.6,
                    target_layer=CognitiveLayer.SKILL)
        assert goal.priority_weight == 0.6
        assert goal.target_layer == CognitiveLayer.SKILL
        assert goal.status == "active"

    def test_goal_weight_must_be_between_0_and_1(self):
        with pytest.raises(ValueError):
            Goal(title="x", description="", ideal_id="i1",
                 priority_weight=1.5, target_layer=CognitiveLayer.K)


class TestPlan:
    """计划——可执行的实例化容器"""

    def test_create_plan(self):
        plan = Plan(title="LLM 项目",
                    description="",
                    goal_id="goal-1",
                    cognitive_focus=CognitiveLayer.WORKFLOW,
                    priority_weight=0.6)
        assert plan.title == "LLM 项目"
        assert plan.status == "draft"
        assert plan.parent_plan_id is None
        assert plan.children_ids == []
        assert plan.predecessors == []
        assert plan.successors == []
        assert plan.tasks == []

    def test_plan_tree_relationship(self):
        """Plan 可形成树（parent/children）"""
        root = Plan(title="根", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.6)
        child = Plan(title="子", description="", goal_id="g1",
                     parent_plan_id=root.id,
                     cognitive_focus=CognitiveLayer.W, priority_weight=0.6)
        root.children_ids.append(child.id)
        assert child.parent_plan_id == root.id
        assert child.id in root.children_ids

    def test_plan_partial_order(self):
        """Plan 可有偏序（predecessors/successors）"""
        a = Plan(title="A", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.6)
        b = Plan(title="B", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.6)
        b.predecessors.append(a.id)
        a.successors.append(b.id)
        assert a.id in b.predecessors
        assert b.id in a.successors


class TestTask:
    """任务——具体动作"""

    def test_create_task(self):
        task = Task(title="实现 self-attention",
                    description="",
                    plan_id="plan-1",
                    goal_id="goal-1",
                    cognitive_layer=CognitiveLayer.SKILL,
                    estimated_hours=2.0)
        assert task.title == "实现 self-attention"
        assert task.status == "todo"
        assert task.estimated_hours == 2.0
        assert task.is_one_time_only is False
        assert task.can_be_rescheduled is True

    def test_task_opportunity_cost_fields(self):
        """机会成本评估字段"""
        task = Task(title="开会", description="",
                    plan_id="p1", goal_id="g1",
                    cognitive_layer=CognitiveLayer.W,
                    estimated_hours=1.0,
                    is_one_time_only=True,
                    can_be_rescheduled=False,
                    time_window_remaining=0.2)
        assert task.is_one_time_only is True
        assert task.can_be_rescheduled is False
        assert task.time_window_remaining == 0.2


class TestConstraint:
    """结果约束——路径无关核验"""

    def test_create_constraint(self):
        c = Constraint(plan_id="p1",
                       type="file_exists",
                       target="output/report.md",
                       operator="exists",
                       value=True,
                       must_hold=True)
        assert c.plan_id == "p1"
        assert c.must_hold is True


class TestDecisionOption:
    """决策选项——含生活成本明示（§4.4）"""

    def test_create_option(self):
        opt = DecisionOption(
            description="继续写报告",
            rationale="距 deadline 仅剩 2 天",
            estimated_impact="完成报告主体",
            confidence=0.8,
            action_payload={"action": "continue_report"},
            attention_cost=0.4,
            energy_cost=0.15,
            missed_opportunities=["opp-1"],
            surplus_delta=-2.0,
        )
        assert opt.id is not None
        assert opt.confidence == 0.8
        assert opt.surplus_delta == -2.0

    def test_option_confidence_range(self):
        """confidence 应在 0~1"""
        with pytest.raises(ValueError):
            DecisionOption(description="x", rationale="", estimated_impact="",
                           confidence=1.5, action_payload={}, attention_cost=0,
                           energy_cost=0, missed_opportunities=[], surplus_delta=0)
        with pytest.raises(ValueError):
            DecisionOption(description="x", rationale="", estimated_impact="",
                           confidence=-0.1, action_payload={}, attention_cost=0,
                           energy_cost=0, missed_opportunities=[], surplus_delta=0)


class TestDecisionPoint:
    """决策点——限制建议强度，配合负指数衰减（§4.4）"""

    def _make_options(self, n: int = 2) -> list[DecisionOption]:
        return [DecisionOption(description=f"选项{i}", rationale="",
                                estimated_impact="", confidence=0.5,
                                action_payload={}, attention_cost=0.1,
                                energy_cost=0.05, missed_opportunities=[],
                                surplus_delta=0.0)
                for i in range(n)]

    def test_create_decision_point(self):
        dp = DecisionPoint(
            plan_id="p1",
            context_snapshot="Plan A 进度 68%，注意力 68%",
            options=self._make_options(3),
            agent_intensity=0.32,
            opportunity_cost_shown={"option_0": "low"},
        )
        assert dp.id is not None
        assert dp.plan_id == "p1"
        assert len(dp.options) == 3
        assert dp.resolved_at is None
        assert dp.selected_option_id is None

    def test_rejects_zero_options(self):
        """空选项列表报错"""
        with pytest.raises(ValueError):
            DecisionPoint(plan_id="p1", context_snapshot="x" * 200,
                          options=[], agent_intensity=0.5,
                          opportunity_cost_shown={})

    def test_allows_single_option(self):
        """允许只有 1 个选项（自由对话场景）"""
        dp = DecisionPoint(plan_id="p1", context_snapshot="x" * 200,
                           options=self._make_options(1), agent_intensity=0.5,
                           opportunity_cost_shown={})
        assert len(dp.options) == 1

    def test_allows_many_options(self):
        """允许超过 4 个选项（丰富决策场景）"""
        dp = DecisionPoint(plan_id="p1", context_snapshot="x" * 200,
                           options=self._make_options(6), agent_intensity=0.5,
                           opportunity_cost_shown={})
        assert len(dp.options) == 6

    def test_context_snapshot_length_limit(self):
        """context_snapshot ≤ 500 字"""
        with pytest.raises(ValueError):
            DecisionPoint(plan_id="p1", context_snapshot="x" * 501,
                          options=self._make_options(2), agent_intensity=0.5,
                          opportunity_cost_shown={})

    def test_resolve_decision(self):
        """用户选择后，resolved_at 和 selected_option_id 被设置"""
        dp = DecisionPoint(plan_id="p1", context_snapshot="ctx",
                           options=self._make_options(2), agent_intensity=0.5,
                           opportunity_cost_shown={})
        selected = dp.options[0].id
        dp.resolve(selected)
        assert dp.selected_option_id == selected
        assert dp.resolved_at is not None
