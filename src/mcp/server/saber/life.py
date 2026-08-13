"""
SaberSystem 生命资源模型
注意力资本化（可积累消耗透支）+ 健康硬约束 + 机遇捕捉
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from mcp.server.saber.models import CognitiveLayer


@dataclass
class AttentionCapital:
    """注意力资本账户——TS2 第二大硬通货，可积累、可消耗、可透支"""
    balance: float = 0.75           # 初始 0.75，已部分消耗（苏醒 4.5h）
    cap_max: float = 1.0
    depletion_rate: float = 0.35    # 每小时工作支出比例
    recovery_rate: float = 0.20     # 每小时休息存入比例
    overdraft_count: int = 0
    last_recover_at: datetime | None = None

    def is_depleted(self) -> bool:
        """余额低于 0.15 时视为耗尽，应冻结新任务启动"""
        return self.balance < 0.15

    def is_overdrawn(self) -> bool:
        """余额为负即透支"""
        return self.balance < 0

    def spend(self, hours: float, intensity: float = 1.0) -> float:
        """工作时支出注意力资本。intensity 为任务复杂度系数"""
        amount = hours * self.depletion_rate * intensity
        self.balance -= amount
        if self.balance < 0:
            self.overdraft_count += 1
        return amount

    def recover(self, hours: float, quality: float = 1.0) -> float:
        """休息时存入注意力资本。quality 为休息质量（散步>刷手机）"""
        amount = hours * self.recovery_rate * quality
        self.balance = min(self.cap_max, self.balance + amount)
        self.last_recover_at = datetime.now()
        return amount


def current_attention(capital: AttentionCapital, elapsed_hours: float) -> float:
    """
    瞬时可用注意力 = 资本余额 × 双指数衰减 + 最低保底
    A(t) = balance × e^(-k·t) + 0.2 × (1 - e^(-t))
    连续工作 3 小时后衰减极其明显。
    """
    balance_factor = max(0, capital.balance)  # 透支时归零
    decay_rate = 0.35
    base_attention = 0.2
    current = (balance_factor * math.exp(-decay_rate * elapsed_hours)
               + base_attention * (1 - math.exp(-elapsed_hours)))
    return min(1.0, current)


def update_trust_score(current: float, final_score: float,
                       self_destructive_increment: int = 0) -> float:
    """
    更新信任分：
    - 高质量（final_score > 0.5）→ 上升
    - 低质量（final_score < 0.5）→ 下降
    - 自毁行为额外扣分（已在 record_self_destructive 中处理）
    范围钳制 [0.1, 1.0]
    """
    delta = (final_score - 0.5) * 0.2  # final_score=1 → +0.1, final_score=0 → -0.1
    new_score = current + delta - self_destructive_increment * 0.05
    return max(0.1, min(1.0, new_score))


def settle_surplus_on_archive(
    life: LifeResource,
    estimated_surplus: float,
    final_score: float,
    plan_id: str | None = None,
) -> dict:
    """
    归档结算函数——Plan 完成归档时触发：
    1. 质量分决定盈余倍率（0.5x~1.5x）
    2. 累加 free_time_surplus_total
    3. 写入 surplus_reward Transaction
    4. 更新 trust_score
    """
    from mcp.server.saber.quality import apply_quality_impact
    impact = apply_quality_impact(final_score, estimated_surplus, consecutive_high_quality=0)
    actual_surplus = impact["actual_surplus"]
    life.record_surplus_reward(actual_surplus, plan_id=plan_id,
                               desc=f"归档结算：{estimated_surplus}h × {impact['surplus_multiplier']:.2f} 倍率")
    life.trust_score = update_trust_score(life.trust_score, final_score)
    return impact


@dataclass
class HealthStatus:
    """健康——决定一切产出的物理基础"""
    physical_fatigue: float = 0.3   # 0~1，积累的体能消耗（初始 0.3 = 已苏醒活动数小时）
    mental_fatigue: float = 0.4     # 0~1，积累的精神消耗（初始 0.4 = 已进行过认知活动）
    recovery_rate: float = 0.2      # 每小时休息恢复速度

    def is_burned_out(self) -> bool:
        """透支阈值——任一疲劳度超过 0.85"""
        return self.mental_fatigue > 0.85 or self.physical_fatigue > 0.85

    def is_optimal(self) -> bool:
        """最佳状态"""
        return self.mental_fatigue < 0.4 and self.physical_fatigue < 0.3


@dataclass
class Opportunity:
    """机遇——稍纵即逝的时间窗口"""
    description: str
    window_start: datetime
    window_end: datetime
    energy_requirement: float
    reward: float
    penalty_if_missed: float
    cognitive_layer: CognitiveLayer | None
    id: str = field(default_factory=lambda: str(uuid4()))

    def is_active(self) -> bool:
        """当前是否在窗口期内"""
        now = datetime.now()
        return self.window_start <= now <= self.window_end


@dataclass
class Transaction:
    """生命资源交易日志"""
    type: Literal[
        "time_investment", "surplus_reward", "fatigue_penalty",
        "opportunity_gain", "opportunity_miss", "rag_attention_cost",
        "recovery", "self_destructive", "attention_spend", "attention_recover"
    ]
    amount: float
    description: str
    id: str = field(default_factory=lambda: str(uuid4()))
    plan_id: str | None = None
    opportunity_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class LifeResource:
    """生活者（用户）的核心资源账户"""
    user_id: str
    # 时间资产（绝对硬通货，不可再生）
    waking_hours_total: float = 16.0
    waking_hours_used: float = 4.5    # 已苏醒 4.5h（≈ 早 7:00 → 午 11:30）
    # 注意力资本（第二大硬通货，可积累消耗透支）
    attention_capital: AttentionCapital = field(default_factory=AttentionCapital)
    # 身体与精神资产
    energy_level: float = 0.7         # 已消耗部分体能
    mood_index: float = 0.65          # 略低于满值
    health: HealthStatus = field(default_factory=HealthStatus)
    # 机会窗口
    active_opportunities: list[Opportunity] = field(default_factory=list)
    missed_opportunities: int = 0
    serendipity_buff: float = 0.3     # 初始小量机遇缓冲
    # 累计生命质量
    free_time_surplus_total: float = 0.5   # 已有微量盈余积累
    self_destructive_choices: int = 0
    trust_score: float = 0.9          # 新用户 0.9，可通过良性决策提升
    # 交易日志
    transactions: list[Transaction] = field(default_factory=list)

    @property
    def waking_hours_surplus(self) -> float:
        """盈余 = 总 - 已用，最小为 0"""
        return max(0.0, self.waking_hours_total - self.waking_hours_used)

    def spend_time(self, hours: float, plan_id: str | None = None) -> None:
        """投入工作消耗清醒小时"""
        actual = min(hours, self.waking_hours_surplus)
        self.waking_hours_used += actual
        self._log_txn("time_investment", -actual, f"投入工作 {actual}h", plan_id=plan_id)

    def _log_txn(self, txn_type: str, amount: float, desc: str,
                 plan_id: str | None = None, opp_id: str | None = None) -> Transaction:
        """统一写入交易日志（写入内存 + EventLogger 审计）"""
        txn = Transaction(type=txn_type, amount=amount, description=desc,
                          plan_id=plan_id, opportunity_id=opp_id)
        self.transactions.append(txn)
        try:
            from mcp.event_logger import EventLogger
            el = EventLogger.get_instance()
            if el:
                el.log_tool_call(
                    tool_name="saber_transaction",
                    tool_args={"type": txn_type, "amount": amount, "plan_id": plan_id},
                    tool_result=desc,
                    context_info=f"saber:life:{self.user_id}",
                )
        except Exception:
            pass
        return txn

    def record_recovery(self, hours: float, desc: str = "") -> None:
        """休息恢复"""
        self._log_txn("recovery", hours, desc or f"休息恢复 {hours}h")

    def record_attention_spend(self, amount: float, plan_id: str | None = None) -> None:
        """注意力资本支出"""
        self._log_txn("attention_spend", -amount, f"消耗注意力 {amount:.2f}", plan_id=plan_id)

    def record_attention_recover(self, amount: float) -> None:
        """注意力资本恢复"""
        self._log_txn("attention_recover", amount, f"恢复注意力 {amount:.2f}")

    def record_rag_cost(self, amount: float, plan_id: str | None = None) -> None:
        """万有 RAG 检索消耗注意力"""
        self._log_txn("rag_attention_cost", -amount,
                      f"RAG 检索消耗注意力 {amount:.2f}", plan_id=plan_id)

    def record_opportunity_gain(self, amount: float, opp_id: str) -> None:
        """成功捕捉机遇"""
        self._log_txn("opportunity_gain", amount, "捕捉机遇", opp_id=opp_id)

    def record_opportunity_miss(self, amount: float, opp_id: str) -> None:
        """错过机遇"""
        self._log_txn("opportunity_miss", -amount, "错过机遇", opp_id=opp_id)

    def record_fatigue_penalty(self, amount: float) -> None:
        """透支疲劳惩罚"""
        self._log_txn("fatigue_penalty", -amount, "疲劳透支惩罚")

    def record_self_destructive(self) -> None:
        """强行忽略健康/透支警告"""
        self.self_destructive_choices += 1
        self._log_txn("self_destructive", -0.5, "强行忽略健康/透支警告")
        # 自毁行为同时降低信任分
        self.trust_score = max(0.1, self.trust_score - 0.05)

    def record_surplus_reward(self, amount: float, plan_id: str | None = None,
                              desc: str = "") -> None:
        """归档结算发放自由时间盈余"""
        self.free_time_surplus_total += amount
        self._log_txn("surplus_reward", amount,
                      desc or f"归档盈余 +{amount:.2f}h", plan_id=plan_id)
