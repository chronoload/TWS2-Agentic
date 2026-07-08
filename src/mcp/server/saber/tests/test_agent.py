"""
SaberSystem Agent 负指数衰减律测试
I(P) = I₀ · e^(-k·P)
建议职能衰减，审核职能永不衰减
"""
import math
import pytest
from mcp.server.saber.agent import (
    AgentContributionLog,
    compute_intensity,
    update_proficiency,
    should_block_for_anti_dependency,
    AGENT_INTENSITY_I0,
    AGENT_INTENSITY_K,
)


class TestComputeIntensity:
    """I(P) = I₀ · e^(-k·P)"""

    def test_zero_proficiency_yields_max_intensity(self):
        """P=0 时 I=I₀（最大干预）"""
        intensity = compute_intensity(proficiency=0.0)
        assert intensity == pytest.approx(AGENT_INTENSITY_I0)

    def test_full_proficiency_yields_near_zero(self):
        """P=1 时 I≈0（几乎退役）"""
        intensity = compute_intensity(proficiency=1.0)
        assert intensity < 0.1  # 接近零

    def test_intensity_decreases_with_proficiency(self):
        """熟练度越高，介入度越低"""
        i_low = compute_intensity(0.1)
        i_mid = compute_intensity(0.5)
        i_high = compute_intensity(0.9)
        assert i_low > i_mid > i_high

    def test_formula_matches_math(self):
        """公式与数学定义一致"""
        P = 0.5
        expected = AGENT_INTENSITY_I0 * math.exp(-AGENT_INTENSITY_K * P)
        assert compute_intensity(P) == pytest.approx(expected)


class TestUpdateProficiency:
    """熟练度更新公式
    P_new = P_old + α·(AdoptionRate - 0.3) - β·(UserModificationRatio)
    """

    def test_high_adoption_low_modification_decreases_p(self):
        """高频采纳+低修改 → P 下降（依赖 Agent，未真正掌握）"""
        p_new = update_proficiency(
            p_old=0.3, adoption_rate=0.8, modification_ratio=0.1)
        assert p_new < 0.3  # 依赖 Agent → P 下降

    def test_low_adoption_high_modification_increases_p(self):
        """低采纳+高修改 → P 上升（用户已独立）"""
        p_new = update_proficiency(
            p_old=0.3, adoption_rate=0.1, modification_ratio=0.8)
        assert p_new > 0.3  # 已独立 → P 上升

    def test_p_clamped_to_0_1(self):
        """P 限制在 [0, 1]"""
        p_new = update_proficiency(
            p_old=0.95, adoption_rate=1.0, modification_ratio=0.0)
        assert p_new <= 1.0
        p_new2 = update_proficiency(
            p_old=0.05, adoption_rate=0.0, modification_ratio=0.0)
        assert p_new2 >= 0.0


class TestAntiDependency:
    """防沉迷机制——连续 3 次无脑采纳，第 4 次拒绝生成"""

    def _make_log(self, was_adopted=True, modification_ratio=0.05):
        """测试辅助：构造完整 AgentContributionLog"""
        return AgentContributionLog(
            plan_id="p1", user_id="u1",
            suggestion_type="structure",
            was_adopted=was_adopted,
            user_modification_ratio=modification_ratio,
            attention_consumed=0.1,
            cognitive_layer_target=None,
            intensity_at_creation=0.8,
        )

    def test_blocks_after_3_blind_adoptions(self):
        """连续 3 次无脑采纳 → 第 4 次拒绝"""
        logs = [self._make_log(True, 0.05) for _ in range(3)]
        assert should_block_for_anti_dependency(logs) is True

    def test_no_block_when_user_modifies(self):
        """用户有修改 → 不触发"""
        logs = [
            self._make_log(True, 0.5),
            self._make_log(True, 0.05),
            self._make_log(True, 0.05),
        ]
        assert should_block_for_anti_dependency(logs) is False

    def test_no_block_with_fewer_than_3(self):
        """不足 3 次 → 不触发"""
        logs = [self._make_log(True, 0.05) for _ in range(2)]
        assert should_block_for_anti_dependency(logs) is False

    def test_no_block_when_not_all_adopted(self):
        """并非全部采纳 → 不触发"""
        logs = [
            self._make_log(False, 0.0),
            self._make_log(True, 0.05),
            self._make_log(True, 0.05),
        ]
        assert should_block_for_anti_dependency(logs) is False


class TestAgentContributionLog:
    """Agent 贡献日志"""

    def test_create_log(self):
        log = AgentContributionLog(
            plan_id="p1", user_id="u1",
            suggestion_type="structure",
            was_adopted=True,
            user_modification_ratio=0.2,
            attention_consumed=0.1,
            cognitive_layer_target=None,
            intensity_at_creation=0.8,
        )
        assert log.was_adopted is True
        assert log.suggestion_type == "structure"
