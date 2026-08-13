"""
SaberSystem Agent 负指数衰减律
I(P) = I₀ · e^(-k·P)
建议职能按负指数律衰减直至退场，审核职能永不衰减（见 quality.py）
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from mcp.server.saber.models import CognitiveLayer

# 衰减系数
AGENT_INTENSITY_I0 = 1.0   # 初始干预强度
AGENT_INTENSITY_K = 3.0    # 衰减系数（P=1 时 I≈0.05）

# 熟练度更新系数
ALPHA = 0.15   # 采纳率影响
BETA = 0.20    # 修改率影响

# 防沉迷阈值
ANTI_DEPENDENCY_THRESHOLD = 3
ANTI_DEPENDENCY_MODIFICATION_LIMIT = 0.1  # 修改率低于此值视为"无脑采纳"


@dataclass
class AgentContributionLog:
    """Agent 贡献日志——衰减依据"""
    plan_id: str
    user_id: str
    suggestion_type: Literal[
        "structure", "advice", "translation", "remediation", "rag_injection"
    ]
    was_adopted: bool
    user_modification_ratio: float
    attention_consumed: float
    cognitive_layer_target: CognitiveLayer | None
    intensity_at_creation: float
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)


def compute_intensity(proficiency: float) -> float:
    """
    计算建议职能介入度
    I(P) = I₀ · e^(-k·P)
    P=0 → I=I₀（最大干预）
    P=1 → I≈0（几乎退役）
    """
    P = max(0.0, min(1.0, proficiency))
    return AGENT_INTENSITY_I0 * math.exp(-AGENT_INTENSITY_K * P)


def update_proficiency(
    p_old: float,
    adoption_rate: float,
    modification_ratio: float,
) -> float:
    """
    熟练度更新公式
    P_new = P_old + α·(AdoptionRate - 0.3) - β·(UserModificationRatio)

    关键论断（生活语境修正）：
    - 用户高频采纳且很少修改 → P 下降（依赖 Agent，未真正掌握）
    - 用户低频采纳但高自主完成 → P 急剧上升（已独立）

    但此处 adoption_rate 高 + modification 低 = P 下降；
    adoption_rate 低 + modification 高 = P 上升。
    公式实现：α·(adoption - 0.3) 为正向（高采纳→+），-β·modification 为负向（高修改→-）
    综合：高采纳+低修改 → +（但这是"依赖"应该 -）
    因此实际公式应为：
    P_new = P_old - α·(AdoptionRate - 0.3) + β·(UserModificationRatio)
    （高采纳 → P 下降；高修改 → P 上升）
    """
    p_new = p_old - ALPHA * (adoption_rate - 0.3) + BETA * modification_ratio
    return max(0.0, min(1.0, p_new))


def should_block_for_anti_dependency(recent_logs: list[AgentContributionLog]) -> bool:
    """
    防沉迷机制——连续 3 次无脑采纳，第 4 次拒绝生成完整草案
    "无脑采纳" = was_adopted=True 且 user_modification_ratio < 0.1
    """
    if len(recent_logs) < ANTI_DEPENDENCY_THRESHOLD:
        return False
    # 检查最近 3 次
    recent = recent_logs[-ANTI_DEPENDENCY_THRESHOLD:]
    for log in recent:
        if not log.was_adopted:
            return False
        if log.user_modification_ratio >= ANTI_DEPENDENCY_MODIFICATION_LIMIT:
            return False
    return True
