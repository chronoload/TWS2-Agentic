"""
cross 算子——交叉（合成）。

将两个概念进行交叉合成，可能产生全新的概念。
类似遗传算法的交叉（crossover），远距合成回报更高但风险也大。

影响：
  - 生成混合概念（两个父概念的深度加权和）
  - 父概念 connectivity↑
  - 远距合成额外增益（bell-curve 距离加权）
  - 失败也可能产生有价值的"失败经验"
"""

import uuid
import time
import random
import math
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from ..models import EcosystemState, Concept, ActionRecord, Observation
from .base import BaseOperator, OperatorResult

logger = logging.getLogger(__name__)


# 学科关键词（用于计算语义类别距离）
_DISCIPLINE_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("physics", ["量子", "力学", "物理", "场", "波", "粒子", "相对论", "电磁"]),
    ("math", ["代数", "几何", "拓扑", "分析", "函数", "方程", "概率", "统计"]),
    ("cs", ["算法", "计算", "程序", "数据", "网络", "编程", "神经", "学习"]),
    ("biology", ["生物", "基因", "进化", "细胞", "生态", "蛋白"]),
    ("chemistry", ["化学", "分子", "原子", "反应", "化合"]),
    ("engineering", ["工程", "系统", "控制", "优化", "设计", "信号"]),
]


@dataclass
class CrossResult(OperatorResult):
    child_concept: Optional[Concept] = None
    child_id: Optional[str] = None
    parent_ids: List[str] = field(default_factory=list)
    hybrid_strength: float = 0.0
    failure_narrative: str = ""


class CrossOperator(BaseOperator):

    MIN_DEPTH = 2.0

    def validate(self, concept_id_a: str, concept_id_b: str, **kwargs) -> Optional[str]:
        a = self.state.concepts.get(concept_id_a)
        b = self.state.concepts.get(concept_id_b)
        if not a:
            return f"概念 A 不存在: {concept_id_a}"
        if not b:
            return f"概念 B 不存在: {concept_id_b}"
        if concept_id_a == concept_id_b:
            return "不能与自己交叉"
        if a.is_fossilized:
            return f"概念 A 已化石化: {a.label}"
        if b.is_fossilized:
            return f"概念 B 已化石化: {b.label}"
        if a.depth < self.MIN_DEPTH:
            return f"概念 A depth ({a.depth:.1f}) 不足 (需 ≥ {self.MIN_DEPTH})"
        if b.depth < self.MIN_DEPTH:
            return f"概念 B depth ({b.depth:.1f}) 不足 (需 ≥ {self.MIN_DEPTH})"
        return None

    async def execute(self, concept_id_a: str, concept_id_b: str,
                      **kwargs) -> CrossResult:
        a = self.state.concepts.get(concept_id_a)
        b = self.state.concepts.get(concept_id_b)
        if not a or not b:
            return CrossResult(success=False, error="概念不存在")

        distance = self._compute_semantic_distance(a, b)
        success_prob = self._compute_success_probability(distance, a.depth, b.depth)
        roll = random.random()
        success = roll < success_prob

        child = None
        failure_narrative = ""
        parent_ids = [concept_id_a, concept_id_b]

        if success:
            child = self._crossover(a, b, distance)
            if child:
                self.state.concepts[child.id] = child
                a.child_ids.append(child.id)
                b.child_ids.append(child.id)

            # 父概念 connectivity 增加
            old_conn_a = a.connectivity
            old_conn_b = b.connectivity
            a.connectivity += 0.2
            b.connectivity += 0.2

            hybrid_strength = distance * 0.3 + (a.depth + b.depth) * 0.1
        else:
            hybrid_strength = 0.0
            failure_narrative = self._generate_failure_narrative(a, b, distance, roll)
            logger.info(f"Cross failed: {a.label} × {b.label} (roll={roll:.2f} < {success_prob:.2f})")

        # ActionRecord
        action = ActionRecord(
            id=uuid.uuid4().hex[:12],
            action_type="cross",
            concept_ids=parent_ids + ([child.id] if child else []),
            narrative=f"交叉合成 {a.label} × {b.label}" + (" ✓" if success else " ✗"),
            depth_changes={},
            freshness_changes={},
            new_concept_ids=[child.id] if child else [],
            timestamp=time.time(),
        )
        self.state.actions.append(action)

        obs = Observation(
            id=uuid.uuid4().hex[:12],
            action_record_id=action.id,
            action_type="cross",
            content=f"尝试交叉 {a.label} + {b.label}",
            mentioned_concept_ids=[concept_id_a, concept_id_b],
            new_concept_labels=[child.label] if child else [],
            timestamp=time.time(),
            narrative=f"交叉: {a.label} × {b.label}" +
                      (f" → {child.label}" if child else f" 失败 ({failure_narrative[:40]})"),
        )
        self.state.observations.append(obs)
        self.state.player.total_actions += 1

        return CrossResult(
            success=success,
            action_record=action,
            narrative=obs.narrative,
            depth_changes={},
            new_concepts=[child.id] if child else [],
            child_concept=child,
            child_id=child.id if child else None,
            parent_ids=parent_ids,
            hybrid_strength=hybrid_strength,
            failure_narrative=failure_narrative,
        )

    def _compute_semantic_distance(self, a: Concept, b: Concept) -> float:
        """
        计算两个概念之间的语义距离 (0~1)。

        当前使用基于学科关键词的简化距离。
        未来可替换为 embedding 向量余弦距离。
        """
        def score(concept: Concept) -> List[float]:
            s = [0.0] * len(_DISCIPLINE_KEYWORDS)
            text = f"{concept.label} {' '.join(concept.aliases)}"
            for i, (_, keywords) in enumerate(_DISCIPLINE_KEYWORDS):
                for kw in keywords:
                    if kw in text:
                        s[i] += 1.0
            total = sum(s)
            return [v / max(total, 1) for v in s]

        va = score(a)
        vb = score(b)
        dot = sum(va[i] * vb[i] for i in range(len(va)))
        return 1.0 - dot  # 距离 = 1 - 余弦相似度

    def _compute_success_probability(self, distance: float,
                                      depth_a: float, depth_b: float) -> float:
        """
        计算合成成功概率。

        bell-curve on distance: 太近或太远都难成功。
        太近（同领域）→ 缺少新意
        太远（跨领域）→ 难以融合
        最佳距离: 0.3~0.7
        """
        depth_factor = min(1.0, (depth_a + depth_b) / 8.0)

        # Bell curve: peak at distance=0.5, sigma=0.25
        bell = math.exp(-((distance - 0.5) ** 2) / (2 * 0.25 ** 2))
        base = 0.2 + 0.6 * bell

        return min(0.95, base * depth_factor)

    def _crossover(self, a: Concept, b: Concept, distance: float) -> Optional[Concept]:
        """执行交叉算法，返回子概念"""
        a_weight = a.depth / (a.depth + b.depth)
        b_weight = 1.0 - a_weight

        child_depth = (a.depth * a_weight + b.depth * b_weight) * 0.3
        child_depth = max(0.5, min(5.0, child_depth))

        # 混合标签
        child_label = self._mix_labels(a.label, b.label)

        child = Concept(
            id=uuid.uuid4().hex[:12],
            label=child_label,
            depth=child_depth,
            freshness=1.0,
            parent_ids=[a.id, b.id],
            entropy=(a.entropy + b.entropy) / 2,
            connectivity=0.3,
            source_refs=list(a.source_refs) + list(b.source_refs),
        )
        logger.info(f"Cross success: {a.label} × {b.label} = {child.label} (depth={child_depth:.2f})")
        return child

    def _mix_labels(self, label_a: str, label_b: str) -> str:
        """混合两个概念的标签（简单启发式）"""
        connectors = ["·", "×", "融合", "与"]
        conn = random.choice(connectors)

        # 取前半 + 后半
        cuts = [
            lambda a, b: f"{a[:max(1, len(a)//2)]}{conn}{b[max(0, len(b)//2):]}",
            lambda a, b: f"{a}{conn}{b}",
            lambda a, b: f"{b}{conn}{a}",
            lambda a, b: f"{a[:max(1, len(a)//2)]}{b[max(0, len(b)//2):]}",
        ]
        return random.choice(cuts)(label_a, label_b)

    def _generate_failure_narrative(self, a: Concept, b: Concept,
                                     distance: float, roll: float) -> str:
        """生成失败说明"""
        if distance < 0.2:
            return f"{a.label} 和 {b.label} 太相似，没有产生新洞见"
        if distance > 0.8:
            return f"{a.label} 与 {b.label} 差距过大，无法建立有效连接"
        if roll < 0.1:
            return f"虽然思考了很久，但 {a.label} 和 {b.label} 之间似乎找不到交叉点"
        return f"尝试连接 {a.label} 和 {b.label} 失败，但获得了一些启发"
