"""
SaberSystem 生命资源模型测试
注意力资本化 + 健康硬约束 + 机遇捕捉
"""
import math
import pytest
from datetime import datetime, timedelta
from mcp.server.saber.life import (
    AttentionCapital,
    HealthStatus,
    Opportunity,
    LifeResource,
    Transaction,
    current_attention,
)


class TestAttentionCapital:
    """注意力资本账户——可积累、可消耗、可透支"""

    def test_create_capital(self):
        cap = AttentionCapital()
        assert cap.balance == 0.75  # 初始基线
        assert cap.is_depleted() is False
        assert cap.is_overdrawn() is False

    def test_spend_attention(self):
        """工作消耗注意力资本"""
        cap = AttentionCapital()
        cap.spend(hours=2.0, intensity=1.0)
        # 初始 0.75 - 2h × 0.35 depletion_rate = 0.05
        assert cap.balance == pytest.approx(0.05, abs=0.01)

    def test_recover_attention(self):
        """休息存入注意力资本"""
        cap = AttentionCapital(balance=0.3)
        cap.recover(hours=1.0, quality=1.0)
        # 1h × 0.20 recovery_rate = 0.2 存入
        assert cap.balance == pytest.approx(0.5, abs=0.01)

    def test_recover_capped_at_max(self):
        """恢复不超过上限"""
        cap = AttentionCapital(balance=0.9)
        cap.recover(hours=2.0, quality=1.0)
        assert cap.balance == 1.0  # cap_max

    def test_overdraft(self):
        """透支注意力资本"""
        cap = AttentionCapital(balance=0.1)
        cap.spend(hours=2.0, intensity=1.0)
        # 0.1 - 0.7 = -0.6
        assert cap.is_overdrawn() is True
        assert cap.overdraft_count == 1

    def test_is_depleted_threshold(self):
        """余额低于 0.15 时视为耗尽"""
        cap = AttentionCapital(balance=0.14)
        assert cap.is_depleted() is True
        cap2 = AttentionCapital(balance=0.15)
        assert cap2.is_depleted() is False


class TestCurrentAttention:
    """瞬时可用注意力 = 资本余额 × 双指数衰减"""

    def test_initial_attention(self):
        cap = AttentionCapital(balance=1.0)
        att = current_attention(cap, elapsed_hours=0.0)
        assert att == pytest.approx(1.0, abs=0.01)

    def test_decay_after_3_hours(self):
        """连续工作 3 小时后衰减明显"""
        cap = AttentionCapital(balance=1.0)
        att = current_attention(cap, elapsed_hours=3.0)
        # A(3) = 1.0 * e^(-0.35*3) + 0.2*(1-e^(-3))
        expected = 1.0 * math.exp(-0.35 * 3) + 0.2 * (1 - math.exp(-3))
        assert att == pytest.approx(expected, abs=0.01)
        assert att < 0.6  # 从 1.0 衰减到 0.54，衰减明显

    def test_overdrawn_capital_yields_base_only(self):
        """透支时余额归零，只剩基础保底"""
        cap = AttentionCapital(balance=-0.5)
        att = current_attention(cap, elapsed_hours=0.0)
        # 透支时 balance_factor=0，只剩 0.2*(1-1)=0
        assert att == pytest.approx(0.0, abs=0.01)


class TestHealthStatus:
    """健康——决定一切产出的物理基础"""

    def test_optimal(self):
        h = HealthStatus(physical_fatigue=0.2, mental_fatigue=0.3)
        assert h.is_optimal() is True
        assert h.is_burned_out() is False

    def test_burned_out_physical(self):
        h = HealthStatus(physical_fatigue=0.9)
        assert h.is_burned_out() is True

    def test_burned_out_mental(self):
        h = HealthStatus(mental_fatigue=0.9)
        assert h.is_burned_out() is True

    def test_not_burned_out(self):
        h = HealthStatus(physical_fatigue=0.5, mental_fatigue=0.5)
        assert h.is_burned_out() is False


class TestOpportunity:
    """机遇——稍纵即逝的时间窗口"""

    def test_create_opportunity(self):
        opp = Opportunity(
            description="今天下午思维最活跃",
            window_start=datetime.now(),
            window_end=datetime.now() + timedelta(hours=1),
            energy_requirement=0.6,
            reward=1.5,
            penalty_if_missed=0.3,
            cognitive_layer=None,  # 测试中暂用 None
        )
        assert opp.description == "今天下午思维最活跃"
        assert opp.reward == 1.5

    def test_is_active(self):
        """窗口期内为活跃"""
        opp = Opportunity(
            description="test",
            window_start=datetime.now() - timedelta(minutes=10),
            window_end=datetime.now() + timedelta(minutes=50),
            energy_requirement=0.5,
            reward=1.0,
            penalty_if_missed=0.2,
            cognitive_layer=None,
        )
        assert opp.is_active() is True

    def test_is_expired(self):
        """窗口期外为过期"""
        opp = Opportunity(
            description="test",
            window_start=datetime.now() - timedelta(hours=2),
            window_end=datetime.now() - timedelta(hours=1),
            energy_requirement=0.5,
            reward=1.0,
            penalty_if_missed=0.2,
            cognitive_layer=None,
        )
        assert opp.is_active() is False


class TestLifeResource:
    """生活者核心资源账户"""

    def test_create_life_resource(self):
        life = LifeResource(user_id="user-1")
        assert life.user_id == "user-1"
        assert life.waking_hours_total == 16.0
        assert life.waking_hours_used == 4.5  # 初始基线
        assert life.waking_hours_surplus == 11.5
        assert life.attention_capital is not None
        assert isinstance(life.health, HealthStatus)

    def test_spend_time(self):
        """投入工作消耗清醒小时"""
        life = LifeResource(user_id="u1", waking_hours_used=0.0)
        life.spend_time(2.0)
        assert life.waking_hours_used == 2.0
        assert life.waking_hours_surplus == 14.0

    def test_surplus_cannot_go_negative_via_normal_work(self):
        """正常工作不应让盈余为负（硬约束应阻止）"""
        life = LifeResource(user_id="u1", waking_hours_used=0.0)
        # 假设有外部检查，这里只测会计逻辑
        life.spend_time(16.0)
        assert life.waking_hours_surplus == 0.0
