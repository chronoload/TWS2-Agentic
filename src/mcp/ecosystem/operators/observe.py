"""
observe 算子——TS2 自动追踪。

消费 gateway 收集的 TS2 事件（GatewayEvent），将其转化为
生态系统的 ActionRecord 和 Concept 变更。

这是"TS2 自动追踪"的第一优先级流水线：
  GatewayEvent → observe → ActionRecord + depth/freshness/entropy 更新
"""

import uuid
import time
import logging
from typing import List, Optional, Dict, Tuple, Set
from ..models import GatewayEvent, ActionRecord, Observation, Concept, EcosystemState
from .base import BaseOperator, OperatorResult

logger = logging.getLogger(__name__)

# action_type → (depth_delta, freshness_delta, entropy_delta, connectivity_delta)
_EFFECT_MATRIX: Dict[str, Tuple[float, float, float, float]] = {
    "reading":     ( 0.20,  0.30, -0.05,  0.10),
    "writing":     ( 0.10,  0.20, -0.10,  0.20),
    "coding":      ( 0.15,  0.20,  0.10,  0.15),
    "experiment":  ( 0.05,  0.25,  0.20,  0.10),
    "discussion":  ( 0.10,  0.30, -0.05,  0.15),
    "checkpoint":  ( 0.00,  0.15,  0.00,  0.05),
    "course":      ( 0.30,  0.20, -0.10,  0.10),
    "exploration": ( 0.05,  0.10,  0.00,  0.05),
    "project":     ( 0.10,  0.15, -0.10,  0.20),
    "record":      ( 0.10,  0.20, -0.05,  0.10),
}


class ObserveOperator(BaseOperator):
    """
    TS2 自动追踪算子

    消费 GatewayEvent → 更新生态系统状态：
      - READING:   命中概念 depth↑, freshness↑
      - WRITING:   产出概念的 freshness↑, connectivity↑
      - CODING:    相关概念 depth↑, entropy↑（实验性增加熵）
      - EXPERIMENT: 相关概念 entropy↑（实验引入不确定性）
      - CHECKPOINT: 所有活跃概念 freshness↑（回溯刷新）
      - COURSE:    课程概念 depth↑
      - EXPLORATION: 弱影响，connectivity 微增
      - PROJECT:   项目概念 entropy↓, freshness↑
    """

    def __init__(self, state: EcosystemState):
        super().__init__(state)
        self._last_processed_source_id: str = ""

    def process_event(self, event: GatewayEvent) -> OperatorResult:
        """
        处理一个 gateway 事件

        Step:
          1. 在事件摘要和详情中搜索已知概念
          2. 根据 action_type 更新匹配到的概念的 depth/freshness/entropy
          3. 生成 ActionRecord + Observation
        """
        matched_ids = self._match_concepts(event)
        effects = self._apply_action_effects(event, matched_ids)

        # 生成 ActionRecord
        action = ActionRecord(
            id=uuid.uuid4().hex[:12],
            action_type="observe",
            concept_ids=matched_ids,
            narrative=f"[auto] {event.action_type}: {event.summary}",
            depth_changes=effects.get("depth", {}),
            freshness_changes=effects.get("freshness", {}),
            entropy_changes=effects.get("entropy", {}),
            source=event.source,
            source_event_id=event.source_event_id,
            timestamp=event.timestamp,
        )
        self.state.actions.append(action)

        # 生成 Observation
        obs = Observation(
            id=uuid.uuid4().hex[:12],
            action_record_id=action.id,
            action_type=event.action_type,
            content=event.summary,
            mentioned_concept_ids=matched_ids,
            timestamp=event.timestamp,
            narrative=f"检测到 {event.action_type} 活动: {event.summary}",
        )
        self.state.observations.append(obs)

        self.state.player.total_actions += 1
        self.state.player.total_concepts_encountered = len(self.state.concepts)

        return OperatorResult(
            success=True,
            action_record=action,
            narrative=obs.narrative,
            depth_changes=action.depth_changes,
            freshness_changes=action.freshness_changes,
            entropy_changes=action.entropy_changes,
        )

    def process_batch(self, events: List[GatewayEvent]) -> List[OperatorResult]:
        """批量处理"""
        return [self.process_event(ev) for ev in events]

    # ── 概念匹配 ──

    def _match_concepts(self, event: GatewayEvent) -> List[str]:
        """
        在事件中搜索已知概念。

        三层匹配：
          1. label/alias 精确匹配（事件摘要/详情中的文本）
          2. 文件路径匹配（detail 中的 path 字段 vs concept 的 source_refs）
          3. 关键词子串匹配（label 作为子串出现在摘要中）
        """
        matched: Set[str] = set()
        search_text = f"{event.summary} {self._detail_to_text(event.detail)}".lower()

        file_path = (event.detail or {}).get("path", "")

        for cid, concept in self.state.concepts.items():
            if concept.is_fossilized:
                continue

            # 1. label/alias 精确匹配
            if concept.label.lower() in search_text:
                matched.add(cid)
                continue
            for alias in concept.aliases:
                if alias.lower() in search_text:
                    matched.add(cid)
                    break
            if cid in matched:
                continue

            # 2. 文件路径匹配
            if file_path:
                for ref in concept.source_refs:
                    if ref.file_path and ref.file_path in file_path:
                        matched.add(cid)
                        break
                if cid in matched:
                    continue

            # 3. 关键词子串匹配（label 长度 ≥ 2 且出现在文本中）
            if len(concept.label) >= 2 and concept.label.lower() in search_text:
                matched.add(cid)

        return list(matched)

    def _detail_to_text(self, detail: dict) -> str:
        """将 detail 字典扁平化为可搜索文本"""
        parts = []
        for v in detail.values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, list):
                parts.extend(str(x) for x in v if isinstance(x, str))
            elif isinstance(v, dict):
                for sub in v.values():
                    if isinstance(sub, str):
                        parts.append(sub)
        return " ".join(parts)

    # ── 效果应用 ──

    def _apply_action_effects(self, event: GatewayEvent,
                              matched_ids: List[str]) -> dict:
        """
        根据 action_type 调整概念属性。

        返回:
            {
                "depth": {concept_id: delta, ...},
                "freshness": {concept_id: delta, ...},
                "entropy": {concept_id: delta, ...},
                "connectivity": {concept_id: delta, ...},
            }
        """
        effects = {"depth": {}, "freshness": {}, "entropy": {}, "connectivity": {}}
        atype = event.action_type
        matrix = _EFFECT_MATRIX.get(atype, (0.05, 0.10, 0.0, 0.05))
        imp = event.importance

        d_depth, d_fresh, d_entropy, d_conn = [v * imp for v in matrix]

        for cid in matched_ids:
            concept = self.state.concepts.get(cid)
            if not concept or concept.is_fossilized:
                continue

            old_depth = concept.depth
            old_fresh = concept.freshness
            old_entropy = concept.entropy
            old_conn = concept.connectivity

            concept.depth = max(0.0, min(10.0, concept.depth + d_depth))
            concept.freshness = max(0.0, min(1.0, concept.freshness + d_fresh))
            concept.entropy = max(0.0, min(1.0, concept.entropy + d_entropy))
            concept.connectivity = max(0.0, concept.connectivity + d_conn)

            effects["depth"][cid] = concept.depth - old_depth
            effects["freshness"][cid] = concept.freshness - old_fresh
            effects["entropy"][cid] = concept.entropy - old_entropy
            effects["connectivity"][cid] = concept.connectivity - old_conn

        return effects
