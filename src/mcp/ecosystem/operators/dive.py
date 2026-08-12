"""
dive 算子——深潜（变异）。

对一个概念投入注意力资源，增加 depth，低概率产生变异子概念。

影响：
  - 目标概念 depth↑（边际递减）
  - 目标概念 freshness↑
  - 非活跃线程的 clarity 轻微下降（并行张力由 engine 处理）
  - 低概率产生子概念（mutation）
"""

import uuid
import time
import random
import logging
from dataclasses import dataclass, field
from typing import Optional, List
from ..models import EcosystemState, Concept, ActionRecord, Observation
from .base import BaseOperator, OperatorResult

logger = logging.getLogger(__name__)


@dataclass
class DiveResult(OperatorResult):
    mutation_concept_id: Optional[str] = None
    depth_gained: float = 0.0


class DiveOperator(BaseOperator):

    def validate(self, concept_id: str, **kwargs) -> Optional[str]:
        concept = self.state.concepts.get(concept_id)
        if not concept:
            return f"概念不存在: {concept_id}"
        if concept.is_fossilized:
            return f"概念已化石化: {concept.label}"
        return None

    async def execute(self, concept_id: str, energy: float = 1.0,
                      **kwargs) -> DiveResult:
        concept = self.state.concepts.get(concept_id)
        if not concept or concept.is_fossilized:
            return DiveResult(success=False, error=f"无效概念: {concept_id}")

        old_depth = concept.depth
        old_freshness = concept.freshness

        # 基础增益（边际递减）
        raw_gain = energy * (0.15 + random.uniform(-0.03, 0.03))
        diminishing = 1.0 / (1.0 + concept.depth * 0.05)
        actual_gain = max(0.01, raw_gain * diminishing)

        concept.depth = min(10.0, concept.depth + actual_gain)
        concept.freshness = min(1.0, concept.freshness + 0.3 * energy)
        concept.updated_at = time.time()

        # 变异检骰：概率 = energy * depth * 0.02
        mutation_chance = energy * concept.depth * 0.02
        mutation_concept_id = None
        new_ids: List[str] = []

        if random.random() < mutation_chance:
            suffix = random.choice(["·变体", "·深化", "·分支", "·展开", "·特例"])
            child = Concept(
                id=uuid.uuid4().hex[:12],
                label=f"{concept.label}{suffix}",
                depth=concept.depth * 0.15,
                freshness=1.0,
                parent_ids=[concept_id],
                entropy=concept.entropy * 0.3,
                source_refs=list(concept.source_refs),  # 继承父概念来源
            )
            self.state.concepts[child.id] = child
            concept.child_ids.append(child.id)
            mutation_concept_id = child.id
            new_ids = [child.id]
            logger.info(f"Dive mutation: {concept.label} → {child.label}")

        # ActionRecord
        action = ActionRecord(
            id=uuid.uuid4().hex[:12],
            action_type="dive",
            concept_ids=[concept_id] + ([mutation_concept_id] if mutation_concept_id else []),
            narrative=f"深潜 {concept.label} (能量={energy:.1f})",
            depth_changes={concept_id: actual_gain},
            freshness_changes={concept_id: concept.freshness - old_freshness},
            new_concept_ids=new_ids,
            timestamp=time.time(),
        )
        self.state.actions.append(action)

        # Observation
        obs = Observation(
            id=uuid.uuid4().hex[:12],
            action_record_id=action.id,
            action_type="dive",
            content=f"在 {concept.label} 深入探索",
            mentioned_concept_ids=[concept_id],
            new_concept_labels=[f"{concept.label}{suffix}"] if mutation_concept_id else [],
            timestamp=time.time(),
            narrative=f"depth +{actual_gain:.2f}" + (
                f"，发现新概念: {concept.label}{suffix}" if mutation_concept_id else ""
            ),
        )
        self.state.observations.append(obs)

        self.state.player.total_actions += 1

        return DiveResult(
            success=True,
            action_record=action,
            narrative=obs.narrative,
            depth_changes={concept_id: actual_gain},
            freshness_changes={concept_id: concept.freshness - old_freshness},
            new_concepts=new_ids,
            mutation_concept_id=mutation_concept_id,
            depth_gained=actual_gain,
        )
