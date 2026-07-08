"""
SaberSystem 存储测试
"""
import os
import pytest
import tempfile
from mcp.server.saber.store import SaberStore
from mcp.server.saber.models import (
    CognitiveLayer, Ideal, Goal, Plan, Task, Constraint,
    DecisionPoint, DecisionOption,
)
from mcp.server.saber.life import LifeResource
from mcp.server.saber.agent import AgentContributionLog


class TestSaberStore:
    """内存存储——Ideal/Goal/Plan/Task CRUD"""

    def setup_method(self):
        self._db = tempfile.mktemp(suffix='.db')
        self.store = SaberStore(db_path=self._db)
        self.ideal = Ideal(title="测试理想", description="")
        self.goal = Goal(title="测试目标", description="",
                         ideal_id=self.ideal.id,
                         priority_weight=0.6,
                         target_layer=CognitiveLayer.SKILL)
        self.plan = Plan(title="测试计划", description="",
                         goal_id=self.goal.id,
                         cognitive_focus=CognitiveLayer.W,
                         priority_weight=0.6)
        self.task = Task(title="测试任务", description="",
                         plan_id=self.plan.id,
                         goal_id=self.goal.id,
                         cognitive_layer=CognitiveLayer.W,
                         estimated_hours=2.0)

    def teardown_method(self):
        try:
            os.unlink(self._db)
        except Exception:
            pass

    # ─── Ideal ───

    def test_ideal_crud(self):
        self.store.add_ideal(self.ideal)
        assert self.store.get_ideal(self.ideal.id) == self.ideal
        assert len(self.store.list_ideals()) == 1
        self.ideal.status = "evolved"
        self.store.update_ideal(self.ideal)
        assert self.store.get_ideal(self.ideal.id).status == "evolved"

    # ─── Goal ───

    def test_goal_crud(self):
        self.store.add_ideal(self.ideal)
        self.store.add_goal(self.goal)
        assert self.store.get_goal(self.goal.id) == self.goal
        assert len(self.store.list_goals(ideal_id=self.ideal.id)) == 1

    def test_goal_weight_reweight(self):
        """同 Ideal 下 Goal 权重和为 1"""
        self.store.add_ideal(self.ideal)
        g1 = Goal(title="g1", description="", ideal_id=self.ideal.id,
                  priority_weight=0.6, target_layer=CognitiveLayer.K)
        g2 = Goal(title="g2", description="", ideal_id=self.ideal.id,
                  priority_weight=0.4, target_layer=CognitiveLayer.K)
        self.store.add_goal(g1)
        self.store.add_goal(g2)
        # 重分配权重
        self.store.reweight_goals(ideal_id=self.ideal.id,
                                   weights={g1.id: 0.7, g2.id: 0.3})
        assert self.store.get_goal(g1.id).priority_weight == 0.7
        assert self.store.get_goal(g2.id).priority_weight == 0.3

    def test_reweight_must_sum_to_1(self):
        """权重和必须为 1，否则报错"""
        self.store.add_ideal(self.ideal)
        g1 = Goal(title="g1", description="", ideal_id=self.ideal.id,
                  priority_weight=0.5, target_layer=CognitiveLayer.K)
        self.store.add_goal(g1)
        with pytest.raises(ValueError):
            self.store.reweight_goals(ideal_id=self.ideal.id,
                                       weights={g1.id: 0.8})

    # ─── Plan ───

    def test_plan_crud(self):
        self.store.add_plan(self.plan)
        assert self.store.get_plan(self.plan.id) == self.plan
        assert len(self.store.list_plans(goal_id=self.plan.goal_id)) == 1

    def test_plan_tree(self):
        """Plan 树关系——子 Plan 可通过 parent 查询"""
        self.store.add_plan(self.plan)
        child = Plan(title="子", description="",
                     goal_id=self.goal.id,
                     parent_plan_id=self.plan.id,
                     cognitive_focus=CognitiveLayer.W,
                     priority_weight=0.6)
        self.store.add_plan(child)
        children = self.store.list_child_plans(self.plan.id)
        assert child in children

    # ─── Task ───

    def test_task_crud(self):
        self.store.add_task(self.task)
        assert self.store.get_task(self.task.id) == self.task
        assert len(self.store.list_tasks(plan_id=self.plan.id)) == 1
        self.task.status = "done"
        self.store.update_task(self.task)
        assert self.store.get_task(self.task.id).status == "done"

    # ─── LifeResource ───

    def test_life_resource(self):
        life = LifeResource(user_id="u1")
        self.store.set_life_resource(life)
        assert self.store.get_life_resource("u1") == life

    def test_life_resource_default(self):
        """无记录时返回默认 LifeResource"""
        life = self.store.get_life_resource("new-user")
        assert life.user_id == "new-user"
        assert life.waking_hours_total == 16.0


class TestAgentLogStore:
    """Agent 贡献日志存储 + 熟练度重算（§7.3/§7.4）"""

    def setup_method(self):
        self._db = tempfile.mktemp(suffix='.db')
        self.store = SaberStore(db_path=self._db)
        self.plan = Plan(title="p", description="", goal_id="g1",
                         cognitive_focus=CognitiveLayer.S, priority_weight=0.6)

    def teardown_method(self):
        try:
            os.unlink(self._db)
        except Exception:
            pass

    def _make_log(self, adopted=True, modification=0.05):
        return AgentContributionLog(
            plan_id=self.plan.id, user_id="u1", suggestion_type="advice",
            was_adopted=adopted, user_modification_ratio=modification,
            attention_consumed=0.1, cognitive_layer_target=CognitiveLayer.S,
            intensity_at_creation=0.5,
        )

    def test_add_and_list_agent_log(self):
        log = self._make_log()
        self.store.add_agent_log(log)
        logs = self.store.list_agent_logs(self.plan.id)
        assert len(logs) == 1
        assert logs[0] == log

    def test_list_agent_logs_filtered_by_plan(self):
        """按 plan_id 过滤日志"""
        self.store.add_agent_log(self._make_log())
        other = AgentContributionLog(
            plan_id="other-plan", user_id="u1", suggestion_type="advice",
            was_adopted=True, user_modification_ratio=0.05,
            attention_consumed=0.1, cognitive_layer_target=CognitiveLayer.S,
            intensity_at_creation=0.5,
        )
        self.store.add_agent_log(other)
        logs = self.store.list_agent_logs(self.plan.id)
        assert len(logs) == 1
        assert all(l.plan_id == self.plan.id for l in logs)

    def test_get_proficiency_initial_zero(self):
        """无日志时熟练度 P=0"""
        assert self.store.get_proficiency(self.plan.id) == 0.0

    def test_get_proficiency_updates_with_logs(self):
        """有日志时 P 基于 update_proficiency 重算

        高采纳+低修改 → P 下降（依赖 Agent）
        低采纳+高修改 → P 上升（独立完成）
        """
        # 高采纳+低修改 → P 应下降（低于初始 0）
        log = self._make_log(adopted=True, modification=0.05)
        self.store.add_agent_log(log)
        p = self.store.get_proficiency(self.plan.id)
        # adoption=1.0, modification=0.05 → P = 0 - 0.15*(1.0-0.3) + 0.20*0.05 = -0.095 → clamp 0
        assert p == 0.0  # clamp 到 0

        # 低采纳+高修改 → P 应上升
        log2 = self._make_log(adopted=False, modification=0.8)
        self.store.add_agent_log(log2)
        p2 = self.store.get_proficiency(self.plan.id)
        # 从 0 开始: P = 0 - 0.15*(0-0.3) + 0.20*0.8 = 0.045 + 0.16 = 0.205
        assert p2 > 0.0
        assert 0.15 < p2 < 0.30


class TestCompressArchive:
    """Plan 归档/解压缩（§9 四步归档法）"""

    def setup_method(self):
        self._db = tempfile.mktemp(suffix='.db')
        self.store = SaberStore(db_path=self._db)
        self.plan = Plan(title="测试计划", description="",
                         goal_id="g1",
                         cognitive_focus=CognitiveLayer.W,
                         priority_weight=0.6,
                         status="completed",
                         aggregated_progress=1.0)
        self.store.add_plan(self.plan)

    def teardown_method(self):
        try:
            os.unlink(self._db)
        except Exception:
            pass

    # ─── compress_plan ───

    def test_compress_completed_plan(self):
        """归档一个已完成 Plan：status→archived, compressed_at 置为 now, fingerprint 生成"""
        result = self.store.compress_plan(self.plan.id)
        assert result is not None
        stored = self.store.get_plan(self.plan.id)
        assert stored.status == "archived"
        assert stored.compressed_at is not None
        assert stored.archive_fingerprint is not None
        assert len(stored.archive_fingerprint) == 64  # SHA-256 hex

    def test_compress_non_completed_plan_raises(self):
        """归档未完成的 Plan 应报错"""
        draft = Plan(title="draft", description="",
                     goal_id="g1",
                     cognitive_focus=CognitiveLayer.W,
                     priority_weight=0.6, status="draft")
        self.store.add_plan(draft)
        with pytest.raises(ValueError, match="只允许归档已完成的 Plan"):
            self.store.compress_plan(draft.id)

    def test_compress_already_archived_raises(self):
        """重复归档应报错"""
        self.store.add_plan(self.plan)
        self.store.compress_plan(self.plan.id)
        with pytest.raises(ValueError, match="已归档"):
            self.store.compress_plan(self.plan.id)

    def test_compress_nonexistent_plan_raises(self):
        """归档不存在的 Plan 应报错"""
        with pytest.raises(KeyError):
            self.store.compress_plan("nonexistent")

    def test_compress_generates_unique_fingerprint(self):
        """不同 Plan 生成的 fingerprint 不同"""
        p1 = Plan(title="p1", description="", goal_id="g1",
                  cognitive_focus=CognitiveLayer.W, priority_weight=0.6,
                  status="completed")
        self.store.add_plan(p1)
        self.store.compress_plan(p1.id)
        fp1 = self.store.get_plan(p1.id).archive_fingerprint
        # 改动 Plan 内容后应得到不同指纹
        p2 = Plan(title="p2", description="不同的描述", goal_id="g1",
                  cognitive_focus=CognitiveLayer.W, priority_weight=0.6,
                  status="completed")
        self.store.add_plan(p2)
        self.store.compress_plan(p2.id)
        fp2 = self.store.get_plan(p2.id).archive_fingerprint
        assert fp1 != fp2

    # ─── unarchive_plan ───

    def test_unarchive_archived_plan(self):
        """解压缩后 status→active, compressed_at/archive_fingerprint 清空, resurrected_at 记录"""
        self.store.add_plan(self.plan)
        self.store.compress_plan(self.plan.id)
        result = self.store.unarchive_plan(self.plan.id)
        assert result is not None
        stored = self.store.get_plan(self.plan.id)
        assert stored.status == "active"
        assert stored.compressed_at is None
        assert stored.archive_fingerprint is None
        assert stored.resurrected_at is not None

    def test_unarchive_non_archived_raises(self):
        """解压缩未归档的 Plan 应报错"""
        self.store.add_plan(self.plan)
        with pytest.raises(ValueError, match="只允许解压缩已归档的 Plan"):
            self.store.unarchive_plan(self.plan.id)

    def test_unarchive_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.store.unarchive_plan("nonexistent")


class TestDecisionPointStore:
    """决策点存储（§4.4）"""

    def setup_method(self):
        self._db = tempfile.mktemp(suffix='.db')
        self.store = SaberStore(db_path=self._db)

    def teardown_method(self):
        try:
            os.unlink(self._db)
        except Exception:
            pass

    def _make_dp(self, plan_id="p1"):
        opts = [DecisionOption(description=f"选项{i}", rationale="",
                                estimated_impact="", confidence=0.5,
                                action_payload={}, attention_cost=0.1,
                                energy_cost=0.05, missed_opportunities=[],
                                surplus_delta=0.0) for i in range(2)]
        return DecisionPoint(plan_id=plan_id, context_snapshot="ctx",
                             options=opts, agent_intensity=0.5,
                             opportunity_cost_shown={})

    def test_add_and_get_decision_point(self):
        dp = self._make_dp()
        self.store.add_decision_point(dp)
        assert self.store.get_decision_point(dp.id) == dp

    def test_get_nonexistent_decision_point(self):
        assert self.store.get_decision_point("nonexistent") is None
