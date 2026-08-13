"""
SaberSystem 核心数据模型
Ideal → Goal → Plan → Task 四层层级，含 CognitiveLayer 认知阶梯
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class CognitiveLayer(Enum):
    """认知阶梯 K-C-T-S-W，可比较顺序。支持全称与单字母简写两种访问方式"""
    KNOWLEDGE = "K"
    CONCEPT = "C"
    THEORY = "T"
    SKILL = "S"
    WORKFLOW = "W"

    # 单字母别名，便于快速访问
    K = KNOWLEDGE
    C = CONCEPT
    T = THEORY
    S = SKILL
    W = WORKFLOW

    def __lt__(self, other: "CognitiveLayer") -> bool:
        order = {
            CognitiveLayer.KNOWLEDGE: 0,
            CognitiveLayer.CONCEPT: 1,
            CognitiveLayer.THEORY: 2,
            CognitiveLayer.SKILL: 3,
            CognitiveLayer.WORKFLOW: 4,
        }
        return order[self] < order[other]


@dataclass
class Ideal:
    """理想——不可量化的人生愿景，系统的终极目的锚点"""
    title: str
    description: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "active"  # active | fulfilled | evolved


@dataclass
class Goal:
    """目标——Ideal 下的可衡量方向"""
    title: str
    description: str
    ideal_id: str
    priority_weight: float
    target_layer: CognitiveLayer
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "active"  # active | completed | archived
    start_date: datetime | None = None
    end_date: datetime | None = None

    def __post_init__(self):
        if not 0.0 <= self.priority_weight <= 1.0:
            raise ValueError(
                f"priority_weight 必须在 0~1 之间，当前: {self.priority_weight}")


@dataclass
class Constraint:
    """结果约束——路径无关核验"""
    plan_id: str
    type: str  # file_exists | test_passes | schema_matches | time_limit | output_contains | metric_threshold
    target: str
    operator: str  # exists | matches | contains | >= | <= | ==
    value: Any
    id: str = field(default_factory=lambda: str(uuid4()))
    error_message: str = ""
    must_hold: bool = True


@dataclass
class Task:
    """任务——具体动作"""
    title: str
    description: str
    plan_id: str
    goal_id: str
    cognitive_layer: CognitiveLayer
    estimated_hours: float
    id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "todo"  # todo | doing | done | blocked
    deadline: datetime | None = None
    artifacts: list[str] = field(default_factory=list)
    completion_criteria: str = ""
    dependencies: list[str] = field(default_factory=list)
    priority_weight: float = 1.0
    actual_hours: float = 0.0
    # 机会成本评估字段
    attention_cost: float = 0.0
    energy_requirement: float = 0.0
    is_one_time_only: bool = False
    can_be_rescheduled: bool = True
    time_window_remaining: float = 1.0
    user_importance_calibration: float | None = None
    # 交付相关字段
    delivery_required: bool = True
    delivery_artifacts: list[str] = field(default_factory=list)
    delivered_at: datetime | None = None
    verified_at: datetime | None = None
    delivery_notes: str = ""
    git_range_start: str | None = None
    git_range_end: str | None = None
    git_diff_summary: str = ""


@dataclass
class Plan:
    """计划——可执行的实例化容器，可形成树+偏序 DAG"""
    title: str
    description: str
    goal_id: str
    cognitive_focus: CognitiveLayer
    priority_weight: float
    id: str = field(default_factory=lambda: str(uuid4()))
    # 树关系
    parent_plan_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    # 偏序关系
    predecessors: list[str] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)
    # 认知属性
    required_prerequisites: list[CognitiveLayer] = field(default_factory=list)
    # 结果约束
    constraints: list[Constraint] = field(default_factory=list)
    # 生命预算
    waking_hours_budget: float = 0.0
    attention_cost: float = 0.0
    energy_cost: float = 0.0
    maturity_deadline: datetime | None = None
    estimated_surplus_yield: float = 0.0
    # 生命周期
    status: str = "draft"  # draft | active | completed | archived
    start_date: datetime | None = None
    end_date: datetime | None = None
    dag: dict[str, list[str]] = field(default_factory=dict)
    # 算子运行时
    orchestration_version: int = 0
    aggregated_progress: float = 0.0
    aggregated_status: str = "blocked"  # blocked | active | completed
    compliance_status: str = "on_track"  # on_track | at_risk | deviated | blocked | burned_out
    # 压缩归档
    compressed_at: datetime | None = None
    archive_fingerprint: str | None = None
    resurrected_at: datetime | None = None
    # 自动归档
    auto_archive: bool = True
    # 文件追踪
    git_tracking_enabled: bool = False
    tracked_paths: list[str] = field(default_factory=list)
    last_git_snapshot: str = ""
    # 任务列表（运行时填充，不持久化为 DAG）
    tasks: list[Task] = field(default_factory=list)

    def __post_init__(self):
        if not 0.0 <= self.priority_weight <= 1.0:
            raise ValueError(
                f"priority_weight 必须在 0~1 之间，当前: {self.priority_weight}")


@dataclass
class DecisionOption:
    """决策选项——含生活成本明示（§4.4）

    每个选项必须显式标注注意力/体能消耗、错过的机遇、盈余变化量，
    让用户在选择时感知机会成本而非盲目采纳。
    """
    description: str
    rationale: str
    estimated_impact: str
    confidence: float
    action_payload: dict
    attention_cost: float
    energy_cost: float
    missed_opportunities: list[str]
    surplus_delta: float
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence 必须在 0~1 之间，当前: {self.confidence}")


@dataclass
class DecisionPoint:
    """决策点——限制建议强度，配合负指数衰减（§4.4）

    Pilot 必须点一次"采纳"才会执行，即使置信度 0.95 也永不自动执行。
    options 至少 1 个；context_snapshot ≤500 字受约束上下文。
    """
    plan_id: str
    context_snapshot: str
    options: list[DecisionOption]
    agent_intensity: float
    opportunity_cost_shown: dict
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: datetime | None = None
    selected_option_id: str | None = None

    def __post_init__(self):
        if len(self.options) < 1:
            raise ValueError("至少需要 1 个决策选项")
        if len(self.context_snapshot) > 500:
            raise ValueError("context_snapshot 不得超过 200 字")

    def resolve(self, option_id: str) -> None:
        """用户选择某个选项，记录解决时间"""
        self.selected_option_id = option_id
        self.resolved_at = datetime.now()
