"""
熵引擎——生态系统的动力核心。

职责：
  1. 全局熵增：每个 tick 所有概念 freshness 衰减
  2. 化石化：freshness 跌至 0 的概念变为化石（不可操作但保留）
  3. 网络保护：connectivity 高的概念熵增速度慢
  4. 并行张力：一个线程活跃时，其他线程 clarity 下降
  5. 灵感触发：特定条件下推荐用户行动
  6. 气候系统：周期性的全局状态变化
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Set
from .models import EcosystemState, Concept, ResearchThread
from .operators.speciation import SpeciationDetector, SpeciationEvent

logger = logging.getLogger(__name__)


@dataclass
class TickResult:
    """单次心跳的结果"""
    fossilized: List[str] = field(default_factory=list)
    entropy_spikes: List[str] = field(default_factory=list)
    thread_clarity_changes: Dict[str, float] = field(default_factory=dict)
    speciation_events: List[SpeciationEvent] = field(default_factory=list)
    narrative: str = ""


@dataclass
class InspirationTrigger:
    """系统建议玩家采取的行动"""
    action_type: str           # "dive", "cross", "express", "record"
    label: str
    description: str
    target_concept_ids: List[str] = field(default_factory=list)
    priority: float = 0.5     # 0~1


class EntropyEngine:

    def __init__(self, state: EcosystemState):
        self.state = state
        self._inspiration_hooks: List[Callable] = []

        self.speciation_detector = SpeciationDetector(state, threshold=0.65)
        self._speciation_interval: int = 5
        self._auto_save_interval: int = 10

        self.freshness_decay_rate: float = 0.02
        self.fossilization_threshold: float = 0.05
        self.network_protection_factor: float = 0.3
        self.parallel_tension_factor: float = 0.02
        self.max_decay_rate: float = 0.05

    def tick(self, active_thread_id: str = "") -> TickResult:
        """
        执行一个演化心跳

        Step:
          1. 所有概念 freshness 衰减（带网络保护折扣）
          2. freshness ≤ 阈值 → 化石化
          3. 非活跃线程 clarity 下降（并行张力）
          4. 全局熵值更新
          5. 更新 tick 计数
        """
        self.state.tick += 1
        result = TickResult()

        decay_amounts = self._apply_freshness_decay()
        result.entropy_spikes = [
            cid for cid, d in decay_amounts.items() if d >= self.max_decay_rate * 0.8
        ]

        result.fossilized = self._check_fossilization()

        if active_thread_id:
            result.thread_clarity_changes = self._apply_parallel_tension(active_thread_id)

        if self.state.tick % self._speciation_interval == 0:
            events = self.speciation_detector.scan_all()
            for ev in events:
                new_thread = self.speciation_detector.apply(ev)
                if new_thread:
                    result.speciation_events.append(ev)

        self._update_global_entropy()

        if self.state.tick % self._auto_save_interval == 0:
            try:
                from .persistence import save
                save(self.state)
            except Exception as e:
                logger.warning(f"Auto-save failed: {e}")

        result.narrative = self._compose_narrative(result)
        return result

    def _apply_freshness_decay(self) -> Dict[str, float]:
        """所有概念 freshness 衰减，返回 {concept_id: decay_amount}"""
        decays: Dict[str, float] = {}

        for cid, concept in self.state.concepts.items():
            if concept.is_fossilized:
                continue

            decay = self.freshness_decay_rate * (1 - self._apply_network_protection(concept))
            decay = min(decay, self.max_decay_rate)

            concept.freshness = max(0.0, concept.freshness - decay)
            concept.updated_at = time.time()
            decays[cid] = decay

        return decays

    def _apply_network_protection(self, concept: Concept) -> float:
        """
        计算网络保护效应，返回衰减折扣 (0~1)

        公式: discount = connectivity / (connectivity + 5) * protection_factor
        高 connectivity 的概念获得更多保护。
        """
        raw = concept.connectivity / (concept.connectivity + 5.0)
        return raw * self.network_protection_factor

    def _check_fossilization(self) -> List[str]:
        """freshness ≤ 阈值的概念 → 化石化"""
        fossilized = []
        for cid, concept in self.state.concepts.items():
            if concept.is_fossilized:
                continue
            if concept.freshness <= self.fossilization_threshold:
                concept.is_fossilized = True
                concept.fossilized_at = time.time()
                fossilized.append(cid)
                logger.info(f"Concept fossilized: {concept.label} ({cid})")
        return fossilized

    def _apply_parallel_tension(self, active_thread_id: str) -> Dict[str, float]:
        """
        非活跃线程 clarity 下降。

        并行张力机制：
          主动投喂一个线程时，其他线程的清晰度自然下降。
          这是"用进废退"的体现。
        """
        changes: Dict[str, float] = {}
        for tid, thread in self.state.threads.items():
            if tid == active_thread_id or thread.is_archived:
                continue
            old = thread.clarity
            thread.clarity = max(0.0, thread.clarity - self.parallel_tension_factor)
            thread.updated_at = time.time()
            changes[tid] = thread.clarity - old
        return changes

    def _update_global_entropy(self):
        """更新全局熵值 = 所有概念熵值的加权平均"""
        alive = [c for c in self.state.concepts.values() if c.is_alive]
        if not alive:
            self.state.global_entropy = 0.0
            return
        self.state.global_entropy = sum(
            c.entropy * (1 + c.depth * 0.1) for c in alive
        ) / sum(1 + c.depth * 0.1 for c in alive)

    def _compose_narrative(self, result: TickResult) -> str:
        """组装心跳叙事"""
        parts = [f"Tick #{self.state.tick}"]
        if result.fossilized:
            labels = []
            for cid in result.fossilized[:3]:
                c = self.state.concepts.get(cid)
                if c:
                    labels.append(c.label)
            parts.append(f"化石化: {', '.join(labels)}")
        if result.entropy_spikes:
            parts.append(f"熵增: {len(result.entropy_spikes)} 个概念")
        if result.thread_clarity_changes:
            parts.append(f"并行张力: {len(result.thread_clarity_changes)} 个线程")
        if result.speciation_events:
            labels = []
            for ev in result.speciation_events[:3]:
                thread = self.state.threads.get(ev.thread_id)
                if thread:
                    labels.append(thread.label)
            parts.append(f"分岔: {', '.join(labels)}")
        parts.append(f"全局熵: {self.state.global_entropy:.3f}")
        return " | ".join(parts)

    # ── 手动操作 ──

    def fossilize(self, concept_id: str) -> bool:
        """手动化石化一个概念"""
        concept = self.state.concepts.get(concept_id)
        if not concept or concept.is_fossilized:
            return False
        concept.is_fossilized = True
        concept.fossilized_at = time.time()
        concept.freshness = 0.0
        return True

    def resurrect(self, concept_id: str, energy: float = 0.5) -> bool:
        """复活一个化石概念"""
        concept = self.state.concepts.get(concept_id)
        if not concept or not concept.is_fossilized:
            return False
        concept.is_fossilized = False
        concept.fossilized_at = None
        concept.freshness = min(1.0, energy)
        concept.depth = max(0.5, concept.depth * 0.5)  # 复活后 depth 折半
        return True

    # ── 灵感系统 ──

    def check_inspirations(self) -> List[InspirationTrigger]:
        """
        检查灵感触发条件

        触发类型：
          - stale: 某个概念 depth > 2.0 但 freshness 已低 → 建议 dive
          - ready: 同线程两个概念 depth 都 ≥ 2.0 → 建议 cross
          - clarity_high: 线程 clarity 过高 → 建议 express
          - entropy_high: 线程 entropy 过高 → 建议 express
          - long_idle: 长时间无活动 → 建议探索
        """
        triggers: List[InspirationTrigger] = []

        # 1. stale concept → dive
        for cid, c in self.state.concepts.items():
            if not c.is_alive:
                continue
            if c.depth >= 2.0 and c.freshness < 0.2:
                triggers.append(InspirationTrigger(
                    action_type="dive",
                    label=f"深潜 {c.label}",
                    description=f"{c.label} 已经很深入但快生疏了",
                    target_concept_ids=[cid],
                    priority=0.6,
                ))
                if len(triggers) >= 2:
                    break

        # 2. ready concepts → cross
        for tid, thread in self.state.threads.items():
            if thread.is_archived or len(thread.concept_ids) < 2:
                continue
            ready = [cid for cid in thread.concept_ids
                     if (c := self.state.concepts.get(cid)) and c.depth >= 2.0]
            if len(ready) >= 2:
                triggers.append(InspirationTrigger(
                    action_type="cross",
                    label=f"合成 {thread.label}",
                    description=f"线程内 {len(ready)} 个概念 depth 达标",
                    target_concept_ids=ready[:3],
                    priority=0.7,
                ))
                break

        # 3. high clarity → express
        for tid, thread in self.state.threads.items():
            if not thread.is_archived and thread.clarity >= 0.8:
                triggers.append(InspirationTrigger(
                    action_type="express",
                    label=f"表达 {thread.label}",
                    description=f"线程清晰度 {thread.clarity:.1f}，适合固化",
                    target_concept_ids=thread.concept_ids[:3],
                    priority=0.5,
                ))
                break

        # 自定义 hooks
        for hook in self._inspiration_hooks:
            try:
                extra = hook(self.state)
                if extra:
                    triggers.extend(extra if isinstance(extra, list) else [extra])
            except Exception:
                logger.exception("Inspiration hook error")

        triggers.sort(key=lambda t: t.priority, reverse=True)
        return triggers[:5]

    def register_inspiration_hook(self, hook: Callable):
        """注册自定义灵感触发器"""
        self._inspiration_hooks.append(hook)
