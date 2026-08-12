"""
学术熵增生态系统核心数据模型

模型关系：
  Concept ←── ActionRecord ──→ Observation
     ↑            ↑
     └── ResearchThread ──→ Artifact
     
  GatewayEvent ──→ observe 算子 ──→ ActionRecord + Concept 变更
"""

import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple


# ── 图节点基础 ──

@dataclass
class SourceRef:
    """
    指向 TS2 中某个来源的引用
    
    用法：
      - concept.bind_source(file_path="Notes/L03_QM.Rmd")
      - concept.bind_source(checkpoint_id="abc123")
      - concept.bind_source(note_id="note_xyz")
    """
    source_type: str          # "note", "pdf", "course", "checkpoint", "project", "code"
    source_id: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    label: str = ""           # 人类可读的标签（如"L03 量子力学笔记"）
    created_at: float = field(default_factory=time.time)


@dataclass
class Concept:
    """
    知识概念——生态系统中的基本单元，对应知识图谱中的一个节点。
    
    属性含义：
      depth        — 理解深度（0.0~10.0），通过 dive/read 增长，熵减
      freshness    — 新鲜度（0.0~1.0），不使用则衰减，使用则刷新
      connectivity — 连接度（其他概念引用的数量），网络保护效应
      entropy      — 熵值（0.0~1.0），积累到阈值会触发演化压力
    """
    id: str
    label: str
    aliases: List[str] = field(default_factory=list)
    
    # 知识属性
    depth: float = 0.5
    freshness: float = 1.0
    connectivity: float = 0.0
    entropy: float = 0.0
    
    # 图结构
    parent_ids: List[str] = field(default_factory=list)
    child_ids: List[str] = field(default_factory=list)
    related_ids: Dict[str, float] = field(default_factory=dict)  # concept_id → strength
    
    # 外部链接
    source_refs: List[SourceRef] = field(default_factory=list)
    
    # 元数据
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_fossilized: bool = False  # 熵值耗尽已变成化石
    fossilized_at: Optional[float] = None

    @property
    def age_days(self) -> float:
        return (time.time() - self.created_at) / 86400

    @property
    def is_alive(self) -> bool:
        return not self.is_fossilized and self.freshness > 0.05

    def bind_source(self, file_path: str = "", source_type: str = "note",
                    source_id: str = "", label: str = "") -> SourceRef:
        ref = SourceRef(
            source_type=source_type,
            source_id=source_id or uuid.uuid4().hex[:12],
            file_path=file_path,
            label=label or file_path.split("/")[-1] if file_path else "",
        )
        self.source_refs.append(ref)
        self.updated_at = time.time()
        return ref


# ── 线程 ──

@dataclass
class ResearchThread:
    """
    研究线程——一组相关概念的集合，代表一条独立的研究方向。
    
    属性含义：
      clarity   — 清晰度（0.0~1.0），express 可以提高，过高会降低再合成欲望
      entropy   — 线程熵值，是所有概念熵值的加权和
      momentum  — 动量（0.0~1.0），最近活跃程度
    """
    id: str
    label: str
    description: str = ""
    concept_ids: List[str] = field(default_factory=list)
    
    clarity: float = 0.3
    entropy: float = 0.0
    momentum: float = 0.5
    
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_archived: bool = False


# ── 产物 ──

@dataclass
class Artifact:
    """
    学术产出——express 算子生成的笔记/论文/代码。
    这是"写入文件系统"的产物，具有外部持久性。
    """
    id: str
    artifact_type: str          # "note", "paper", "code", "diagram"
    title: str = ""
    file_path: Optional[str] = None
    concept_ids: List[str] = field(default_factory=list)
    thread_id: Optional[str] = None
    
    created_at: float = field(default_factory=time.time)
    word_count: int = 0
    is_published: bool = False


# ── 动作与观察 ──

@dataclass
class ActionRecord:
    """
    用户动作记录——用户在生态系统中执行的每次操作。
    所有算子（dive/cross/express/observe/record）都会生成一条。
    """
    id: str
    action_type: str            # "dive", "cross", "express", "observe", "record"
    concept_ids: List[str] = field(default_factory=list)
    narrative: str = ""
    
    # 效果
    depth_changes: Dict[str, float] = field(default_factory=dict)    # concept_id → delta
    freshness_changes: Dict[str, float] = field(default_factory=dict)
    entropy_changes: Dict[str, float] = field(default_factory=dict)
    new_concept_ids: List[str] = field(default_factory=list)
    
    # 元数据
    source: str = "direct"      # "eventbus", "eventlogger", "direct"
    source_event_id: str = ""
    scene: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class Observation:
    """
    观察日志——由每个动作自动生成，是生态系统的「感知」记录。
    不同于 ActionRecord（谁做了什么），Observation 是「世界发生了什么」。
    """
    id: str
    action_record_id: str = ""
    action_type: str = ""
    content: str = ""
    
    mentioned_concept_ids: List[str] = field(default_factory=list)
    new_concept_labels: List[str] = field(default_factory=list)
    
    timestamp: float = field(default_factory=time.time)
    narrative: str = ""


# ── 网关事件（从 gateway 到 observe 算子的中间格式） ──

@dataclass
class GatewayEvent:
    """
    网关事件——gateway 从 TS2 收集的原始事件。
    observe 算子消费 GatewayEvent → 生成 ActionRecord + Concept 变更。
    """
    action_type: str            # EcosystemActionType 的值（接受 enum，自动转 str）
    source: str                 # "eventbus", "eventlogger", "direct"
    source_event_id: str
    timestamp: float
    summary: str
    detail: Dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5

    def __post_init__(self):
        if hasattr(self.action_type, 'value'):
            self.action_type = self.action_type.value


# ── 世界状态 ──

@dataclass
class PlayerState:
    """
    玩家状态——玩家在知识世界中的位置与能力。
    """
    # 位置
    current_concept_id: Optional[str] = None
    current_thread_id: Optional[str] = None
    
    # 统计数据
    total_actions: int = 0
    total_concepts_encountered: int = 0
    total_artifacts_created: int = 0
    total_threads_started: int = 0
    
    # 能力（随时间增长）
    dive_power: float = 1.0       # 每次 dive 可增加的 depth
    cross_range: float = 1.0      # cross 可探测的最大距离
    express_efficiency: float = 1.0  # express 的 freshness 增益倍率
    
    # 活跃线程列表
    active_thread_ids: List[str] = field(default_factory=list)


@dataclass
class EcosystemState:
    """
    生态系统全局状态——快照，可用于保存/加载/检查点。
    """
    concepts: Dict[str, Concept] = field(default_factory=dict)
    threads: Dict[str, ResearchThread] = field(default_factory=dict)
    artifacts: Dict[str, Artifact] = field(default_factory=dict)
    actions: List[ActionRecord] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    
    player: PlayerState = field(default_factory=PlayerState)
    
    # 全局指标
    global_entropy: float = 0.0
    era: str = "寒武纪"  # 寒武纪 / 经典 / 量子 / 复杂 / 统计
    tick: int = 0  # 演化步数
    
    version: int = 1
    saved_at: float = field(default_factory=time.time)
    
    # 已解析的笔记文件路径（避免 jieba 重复解析）
    parsed_notes: Set[str] = field(default_factory=set)
