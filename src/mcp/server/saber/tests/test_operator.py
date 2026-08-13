"""
SaberSystem Plan 算子测试
P: (History, State, Constraints, LifeResource) → Compressed_Context
含 LifeGuard 双层前置检查（健康+注意力资本）
树聚合 + 偏序拓扑 + 违规裁决
"""
import pytest
from datetime import datetime
from mcp.server.saber.models import CognitiveLayer, Plan, Task, Constraint
from mcp.server.saber.life import LifeResource, AttentionCapital, HealthStatus
from mcp.server.saber.operator import (
    plan_operator_apply,
    CompressedContext,
    LifeGuard,
    flatten_tree,
    detect_cycle,
    topological_sort,
    find_critical_path,
    _aggregate_tree_state,
    check_predecessor_violation,
    check_transitive_closure_violation,
    check_aggregation_violation,
    check_violations,
)


def make_plan_with_task():
    """测试辅助：构造一个含单个任务的 Plan"""
    plan = Plan(title="测试 Plan", description="",
                goal_id="g1",
                cognitive_focus=CognitiveLayer.W,
                priority_weight=0.6)
    task = Task(title="任务 1", description="",
                plan_id=plan.id, goal_id="g1",
                cognitive_layer=CognitiveLayer.W,
                estimated_hours=2.0)
    plan.tasks.append(task)
    plan.status = "active"
    return plan


class TestLifeGuard:
    """LifeGuard 双层前置检查"""

    def test_blocks_when_burned_out(self):
        """健康透支时冻结任务启动"""
        life = LifeResource(user_id="u1")
        life.health = HealthStatus(physical_fatigue=0.9)
        guard = LifeGuard(life)
        assert guard.is_blocked() is True
        assert guard.block_reason == "burned_out"

    def test_blocks_when_attention_depleted(self):
        """注意力资本耗尽时冻结任务启动"""
        life = LifeResource(user_id="u1")
        life.attention_capital = AttentionCapital(balance=0.1)
        guard = LifeGuard(life)
        assert guard.is_blocked() is True
        assert guard.block_reason == "attention_depleted"

    def test_allows_when_healthy(self):
        """健康且注意力充足时放行"""
        life = LifeResource(user_id="u1")
        life.health = HealthStatus(physical_fatigue=0.2, mental_fatigue=0.3)
        life.attention_capital = AttentionCapital(balance=0.8)
        guard = LifeGuard(life)
        assert guard.is_blocked() is False
        assert guard.block_reason is None


class TestPlanOperatorApply:
    """Plan 算子 apply()"""

    def test_returns_compressed_context(self):
        """正常情况返回 CompressedContext"""
        plan = make_plan_with_task()
        life = LifeResource(user_id="u1")
        ctx = plan_operator_apply(plan, life, elapsed_hours=1.0)
        assert isinstance(ctx, CompressedContext)
        assert ctx.fingerprint is not None

    def test_blocked_when_burned_out(self):
        """健康透支时返回 blocked context"""
        plan = make_plan_with_task()
        life = LifeResource(user_id="u1")
        life.health = HealthStatus(physical_fatigue=0.9)
        ctx = plan_operator_apply(plan, life, elapsed_hours=0.0)
        assert ctx.blocked_reason == "burned_out"
        assert "休息" in ctx.summary or "透支" in ctx.summary

    def test_blocked_when_attention_depleted(self):
        """注意力资本耗尽时返回 blocked context"""
        plan = make_plan_with_task()
        life = LifeResource(user_id="u1")
        life.attention_capital = AttentionCapital(balance=0.1)
        ctx = plan_operator_apply(plan, life, elapsed_hours=0.0)
        assert ctx.blocked_reason == "attention_depleted"
        assert "注意力" in ctx.summary

    def test_spends_attention_capital(self):
        """算子运行时支出注意力资本"""
        plan = make_plan_with_task()
        life = LifeResource(user_id="u1")
        initial_balance = life.attention_capital.balance
        plan_operator_apply(plan, life, elapsed_hours=2.0)
        assert life.attention_capital.balance < initial_balance

    def test_computes_life_vector(self):
        """压缩上下文包含生命资源向量"""
        plan = make_plan_with_task()
        life = LifeResource(user_id="u1")
        ctx = plan_operator_apply(plan, life, elapsed_hours=1.0)
        assert ctx.life_vector is not None
        assert len(ctx.life_vector) == 4  # attention, attention_balance, energy, mood

    def test_computes_progress_vector(self):
        """压缩上下文包含进度向量"""
        plan = make_plan_with_task()
        life = LifeResource(user_id="u1")
        ctx = plan_operator_apply(plan, life, elapsed_hours=1.0)
        assert ctx.progress_vector is not None
        assert len(ctx.progress_vector) == 2  # completed_ratio, elapsed_ratio

    def test_fingerprint_changes_with_state(self):
        """状态变化时指纹变化"""
        plan = make_plan_with_task()
        life = LifeResource(user_id="u1")
        ctx1 = plan_operator_apply(plan, life, elapsed_hours=1.0)
        # 改变状态
        plan.tasks[0].status = "done"
        ctx2 = plan_operator_apply(plan, life, elapsed_hours=1.0)
        assert ctx1.fingerprint != ctx2.fingerprint


class TestTreeAggregation:
    """Plan 树递归聚合"""

    def make_store(self):
        """创建内存 store 模拟"""
        class FakeStore:
            def __init__(self):
                self.plans = {}
            def add(self, p):
                self.plans[p.id] = p
            def get(self, pid):
                return self.plans.get(pid)

        return FakeStore()

    def test_leaf_plan_aggregates_tasks(self):
        """叶子 Plan：聚合来自任务进度"""
        plan = Plan(title="叶子", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        t1 = Task(title="t1", description="", plan_id=plan.id, goal_id="g1",
                  cognitive_layer=CognitiveLayer.W, estimated_hours=1.0, status="done")
        t2 = Task(title="t2", description="", plan_id=plan.id, goal_id="g1",
                  cognitive_layer=CognitiveLayer.W, estimated_hours=1.0, status="todo")
        plan.tasks = [t1, t2]
        store = self.make_store()
        store.add(plan)
        progress, status = _aggregate_tree_state(plan, store.get)
        assert progress == 0.5
        assert status == "active"

    def test_parent_aggregates_children(self):
        """父 Plan：聚合来自子 Plan 的加权平均"""
        store = self.make_store()
        parent = Plan(title="父", description="", goal_id="g1",
                      cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        child1 = Plan(title="子1", description="", goal_id="g1",
                      cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                      parent_plan_id=parent.id)
        child2 = Plan(title="子2", description="", goal_id="g1",
                      cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                      parent_plan_id=parent.id)
        t1 = Task(title="t1", description="", plan_id=child1.id, goal_id="g1",
                  cognitive_layer=CognitiveLayer.W, estimated_hours=1.0, status="done")
        t2 = Task(title="t2", description="", plan_id=child2.id, goal_id="g1",
                  cognitive_layer=CognitiveLayer.W, estimated_hours=1.0, status="todo")
        child1.tasks = [t1]
        child2.tasks = [t2]
        parent.children_ids = [child1.id, child2.id]
        store.add(parent)
        store.add(child1)
        store.add(child2)
        progress, status = _aggregate_tree_state(parent, store.get)
        assert progress == 0.5  # (1.0 + 0.0) / 2
        assert status == "active"

    def test_any_child_blocked_propagates(self):
        """任一子 blocked → 父 blocked"""
        store = self.make_store()
        parent = Plan(title="父", description="", goal_id="g1",
                      cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        child_bad = Plan(title="子_bad", description="", goal_id="g1",
                         cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                         parent_plan_id=parent.id)
        child_bad.tasks = []
        child_bad.children_ids = []
        parent.children_ids = [child_bad.id]
        store.add(parent)
        store.add(child_bad)
        _, status = _aggregate_tree_state(parent, store.get)
        assert status == "blocked"

    def test_all_completed_propagates(self):
        """全部 completed → 父 completed"""
        store = self.make_store()
        parent = Plan(title="父", description="", goal_id="g1",
                      cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        child = Plan(title="子", description="", goal_id="g1",
                     cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                     parent_plan_id=parent.id)
        t = Task(title="t", description="", plan_id=child.id, goal_id="g1",
                 cognitive_layer=CognitiveLayer.W, estimated_hours=1.0, status="done")
        child.tasks = [t]
        parent.children_ids = [child.id]
        store.add(parent)
        store.add(child)
        _, status = _aggregate_tree_state(parent, store.get)
        assert status == "completed"


class TestFlattenTree:
    """Plan 树 flatten"""

    def make_store(self):
        class FakeStore:
            def __init__(self):
                self.plans = {}
            def add(self, p):
                self.plans[p.id] = p
            def get(self, pid):
                return self.plans.get(pid)
        return FakeStore()

    def test_flatten_tree(self):
        """BFS 遍历树返回所有后代"""
        store = self.make_store()
        root = Plan(title="root", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        c1 = Plan(title="c1", description="", goal_id="g1",
                  cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        c2 = Plan(title="c2", description="", goal_id="g1",
                  cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        gc = Plan(title="gc", description="", goal_id="g1",
                  cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        root.children_ids = [c1.id, c2.id]
        c1.children_ids = [gc.id]
        store.add(root)
        store.add(c1)
        store.add(c2)
        store.add(gc)
        plans = flatten_tree(root.id, store.get)
        assert len(plans) == 4
        assert root in plans
        assert gc in plans


class TestCycleDetection:
    """偏序 DAG 循环检测"""

    def make_store(self):
        class FakeStore:
            def __init__(self):
                self.plans = {}
            def add(self, p):
                self.plans[p.id] = p
            def get(self, pid):
                return self.plans.get(pid)
        return FakeStore()

    def test_no_cycle(self):
        """无环 DAG"""
        store = self.make_store()
        a = Plan(title="A", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        b = Plan(title="B", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        a.successors = [b.id]
        b.predecessors = [a.id]
        store.add(a)
        store.add(b)
        assert detect_cycle([a.id, b.id], store.get) is None

    def test_cycle_detected(self):
        """A→B→A 检测到环"""
        store = self.make_store()
        a = Plan(title="A", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        b = Plan(title="B", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        a.successors = [b.id]
        b.successors = [a.id]
        a.predecessors = [b.id]
        b.predecessors = [a.id]
        store.add(a)
        store.add(b)
        cycle = detect_cycle([a.id, b.id], store.get)
        assert cycle is not None
        assert len(cycle) >= 2


class TestTopologicalSort:
    """偏序拓扑排序"""

    def make_store(self):
        class FakeStore:
            def __init__(self):
                self.plans = {}
            def add(self, p):
                self.plans[p.id] = p
            def get(self, pid):
                return self.plans.get(pid)
        return FakeStore()

    def test_simple_order(self):
        """A → B → C 拓扑序正确"""
        store = self.make_store()
        a = Plan(title="A", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        b = Plan(title="B", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        c = Plan(title="C", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        a.successors = [b.id]
        b.predecessors = [a.id]
        b.successors = [c.id]
        c.predecessors = [b.id]
        store.add(a)
        store.add(b)
        store.add(c)
        order = topological_sort([a.id, b.id, c.id], store.get)
        assert order.index(a.id) < order.index(b.id)
        assert order.index(b.id) < order.index(c.id)

    def test_cycle_raises(self):
        """有环时抛出 ValueError"""
        store = self.make_store()
        a = Plan(title="A", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        b = Plan(title="B", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        a.successors = [b.id]
        b.successors = [a.id]
        store.add(a)
        store.add(b)
        with pytest.raises(ValueError):
            topological_sort([a.id, b.id], store.get)


class TestCriticalPath:
    """偏序 DAG 关键路径"""

    def make_store(self):
        class FakeStore:
            def __init__(self):
                self.plans = {}
            def add(self, p):
                self.plans[p.id] = p
            def get(self, pid):
                return self.plans.get(pid)
        return FakeStore()

    def test_critical_path(self):
        """A→B→C, A→D: 关键路径为 A→B→C"""
        store = self.make_store()
        a = Plan(title="A", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        b = Plan(title="B", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        c = Plan(title="C", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        d = Plan(title="D", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5)
        a.successors = [b.id, d.id]
        b.predecessors = [a.id]
        b.successors = [c.id]
        c.predecessors = [b.id]
        d.predecessors = [a.id]
        store.add(a)
        store.add(b)
        store.add(c)
        store.add(d)
        path = find_critical_path([a.id, b.id, c.id, d.id], store.get)
        assert path[0] == a.id
        # The longest path is a→b→c (3 nodes)
        assert len(path) == 3


class TestViolations:
    """违规裁决"""

    def make_store(self):
        class FakeStore:
            def __init__(self):
                self.plans = {}
            def add(self, p):
                self.plans[p.id] = p
            def get(self, pid):
                return self.plans.get(pid)
        return FakeStore()

    def test_predecessor_violation(self):
        """前驱未完成时触发违规"""
        store = self.make_store()
        pred = Plan(title="前置", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                    status="draft")
        plan = Plan(title="当前", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                    status="draft")
        plan.predecessors = [pred.id]
        store.add(pred)
        store.add(plan)
        result = check_predecessor_violation(plan, store.get)
        assert result.has_violation is True
        assert result.violation_type == "predecessor"

    def test_no_predecessor_violation(self):
        """前驱已完成时通过"""
        store = self.make_store()
        pred = Plan(title="前置", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                    status="completed")
        plan = Plan(title="当前", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                    status="active")
        plan.predecessors = [pred.id]
        store.add(pred)
        store.add(plan)
        result = check_predecessor_violation(plan, store.get)
        assert result.has_violation is False

    def test_transitive_closure_violation(self):
        """A→B→C，B 未完成 C 已完成 → 违规"""
        store = self.make_store()
        a = Plan(title="A", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                 status="completed")
        b = Plan(title="B", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                 status="draft")
        c = Plan(title="C", description="", goal_id="g1",
                 cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                 status="completed")
        a.successors = [b.id]
        b.predecessors = [a.id]
        b.successors = [c.id]
        c.predecessors = [b.id]
        store.add(a)
        store.add(b)
        store.add(c)
        result = check_transitive_closure_violation(c, store.get)
        assert result.has_violation is True
        assert result.violation_type == "transitive_closure"

    def test_aggregation_violation(self):
        """父未完成，子强制归档 → 违规"""
        store = self.make_store()
        parent = Plan(title="父", description="", goal_id="g1",
                      cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                      status="active")
        child = Plan(title="子", description="", goal_id="g1",
                     cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                     parent_plan_id=parent.id, status="archived")
        parent.children_ids = [child.id]
        store.add(parent)
        store.add(child)
        result = check_aggregation_violation(child, store.get)
        assert result.has_violation is True
        assert result.violation_type == "aggregation"

    def test_operator_with_tree_and_violations(self):
        """带 get_plan 的 apply() 执行树聚合+违规检查"""
        store = self.make_store()
        pred = Plan(title="前置", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                    status="draft")
        plan = Plan(title="当前", description="", goal_id="g1",
                    cognitive_focus=CognitiveLayer.W, priority_weight=0.5,
                    status="draft")
        plan.predecessors = [pred.id]
        t1 = Task(title="t1", description="", plan_id=plan.id, goal_id="g1",
                  cognitive_layer=CognitiveLayer.W, estimated_hours=1.0)
        plan.tasks = [t1]
        store.add(pred)
        store.add(plan)
        life = LifeResource(user_id="u1")
        ctx = plan_operator_apply(plan, life, elapsed_hours=0.0, get_plan=store.get)
        assert ctx.blocked_reason == "predecessor"
