"""
分岔检测器——检测概念种群的分岔。

当一组相关概念的分歧度超过阈值时，触发：
  1. 分裂为新线程
  2. 或标记为"悖论"（有奖励）

使用 DBSCAN 对线程内概念进行聚类，
检测概念群是否分裂为两个差异显著的子群。
"""

import uuid
import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..models import EcosystemState, ResearchThread, Concept

logger = logging.getLogger(__name__)


@dataclass
class SpeciationEvent:
    """分岔事件"""
    thread_id: str
    parent_cluster: List[str]
    child_cluster: List[str]
    divergence_score: float
    suggested_new_label: str = ""


class SpeciationDetector:
    """
    分岔检测器

    定期扫描线程内的概念，检测是否出现显著分岔。
    使用 DBSCAN 聚类 + 分歧度阈值来判断。

    距离定义：
      - 0.0: 同一概念
      - 0.0~0.3: 直接连接（related_ids 接近 1.0）
      - 0.3~0.6: 间接连接（共享父概念或子概念）
      - 0.6~1.0: 弱连接或无连接
    """

    def __init__(self, state: EcosystemState, threshold: float = 0.65,
                 min_cluster_size: int = 2):
        self.state = state
        self.threshold = threshold
        self.min_cluster_size = min_cluster_size

    def scan_thread(self, thread_id: str) -> Optional[SpeciationEvent]:
        """扫描一个线程，返回分岔事件（如果有）"""
        thread = self.state.threads.get(thread_id)
        if not thread or thread.is_archived:
            return None
        if len(thread.concept_ids) < self.min_cluster_size * 2:
            return None

        cids = [c for c in thread.concept_ids
                if c in self.state.concepts and not self.state.concepts[c].is_fossilized]
        if len(cids) < self.min_cluster_size * 2:
            return None

        clusters = self._cluster(cids)
        if len(clusters) < 2:
            return None

        clusters = [c for c in clusters if len(c) >= self.min_cluster_size]
        if len(clusters) < 2:
            return None

        clusters.sort(key=len, reverse=True)
        parent_cluster = clusters[0]
        child_cluster = clusters[1]

        divergence = self._inter_cluster_distance(parent_cluster, child_cluster)
        if divergence < self.threshold:
            return None

        labels_a = [self.state.concepts[cid].label for cid in parent_cluster[:3]]
        labels_b = [self.state.concepts[cid].label for cid in child_cluster[:3]]
        suggested = f"{labels_a[0]}/{labels_b[0]}"

        event = SpeciationEvent(
            thread_id=thread_id,
            parent_cluster=parent_cluster,
            child_cluster=child_cluster,
            divergence_score=divergence,
            suggested_new_label=suggested,
        )
        logger.info(
            f"Speciation in {thread.label}: divergence={divergence:.2f}, "
            f"parent={len(parent_cluster)} concepts, child={len(child_cluster)} concepts"
        )
        return event

    def scan_all(self) -> List[SpeciationEvent]:
        """扫描所有活跃线程"""
        events = []
        for tid, thread in self.state.threads.items():
            if thread.is_archived:
                continue
            ev = self.scan_thread(tid)
            if ev:
                events.append(ev)
        return events

    def apply(self, event: SpeciationEvent) -> Optional[ResearchThread]:
        """
        执行分岔：创建新线程并转移子群概念。

        返回新创建的线程，None 表示分岔失败。
        """
        thread = self.state.threads.get(event.thread_id)
        if not thread:
            return None

        labels = [self.state.concepts[cid].label for cid in event.child_cluster[:5]]
        new_label = event.suggested_new_label or " / ".join(labels)

        new_thread = ResearchThread(
            id=uuid.uuid4().hex[:12],
            label=new_label,
            description=f"从 {thread.label} 分岔而来（分歧度 {event.divergence_score:.2f}）",
            concept_ids=list(event.child_cluster),
            clarity=thread.clarity * 0.6,
            entropy=sum(self.state.concepts[c].entropy for c in event.child_cluster
                       if c in self.state.concepts) / max(len(event.child_cluster), 1),
            momentum=thread.momentum * 0.5,
        )
        self.state.threads[new_thread.id] = new_thread

        thread.concept_ids = [c for c in thread.concept_ids
                              if c not in event.child_cluster]
        thread.updated_at = __import__('time').time()

        logger.info(
            f"Applied speciation: new thread '{new_label}' ({new_thread.id[:8]}) "
            f"with {len(event.child_cluster)} concepts"
        )
        return new_thread

    def _cluster(self, cids: List[str]) -> List[List[str]]:
        """
        DBSCAN 聚类。

        使用 sklearn DBSCAN，eps=0.5（距离 < 0.5 视为同一邻域），
        min_samples=1（离群点自成簇，后续由 min_cluster_size 过滤）。
        """
        try:
            from sklearn.cluster import DBSCAN
            import numpy as np
        except ImportError:
            return self._fallback_cluster(cids)

        n = len(cids)
        if n < 3:
            return [cids]

        dist_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = self._distance(cids[i], cids[j])
                dist_matrix[i, j] = d
                dist_matrix[j, i] = d

        clustering = DBSCAN(eps=0.5, min_samples=1, metric='precomputed')
        labels = clustering.fit_predict(dist_matrix)

        clusters: Dict[int, List[str]] = {}
        for idx, label in enumerate(labels):
            clusters.setdefault(int(label), []).append(cids[idx])

        return list(clusters.values())

    def _fallback_cluster(self, cids: List[str]) -> List[List[str]]:
        """
        无 sklearn 时的简单聚类替代。

        使用凝聚层次聚类：从每个点作为独立簇开始，
        合并距离 < 0.5 的簇对，直到没有可合并的对。
        """
        clusters = [[c] for c in cids]

        changed = True
        while changed:
            changed = False
            for i in range(len(clusters)):
                if i >= len(clusters):
                    break
                for j in range(i + 1, len(clusters)):
                    if j >= len(clusters):
                        break
                    dist = self._cluster_distance(clusters[i], clusters[j])
                    if dist < 0.5:
                        clusters[i].extend(clusters[j])
                        clusters.pop(j)
                        changed = True
                        break
                if changed:
                    break

        return clusters

    def _distance(self, cid_a: str, cid_b: str) -> float:
        """
        两个概念间的结构化距离。

        因子：
          1. 直接连接强度（related_ids）：1 - strength
          2. 共享父概念/子概念折扣
          3. 共享活动（actions）折扣
        """
        if cid_a == cid_b:
            return 0.0

        ca = self.state.concepts.get(cid_a)
        cb = self.state.concepts.get(cid_b)
        if not ca or not cb:
            return 1.0

        d = 1.0

        if cid_b in ca.related_ids:
            d = min(d, 1.0 - ca.related_ids[cid_b])
        if cid_a in cb.related_ids:
            d = min(d, 1.0 - cb.related_ids[cid_a])

        shared_parents = set(ca.parent_ids) & set(cb.parent_ids)
        shared_children = set(ca.child_ids) & set(cb.child_ids)
        if shared_parents or shared_children:
            d *= 0.6

        shared_coactions = self._count_shared_actions(cid_a, cid_b)
        if shared_coactions > 0:
            discount = max(0.0, 1.0 - shared_coactions * 0.15)
            d *= discount

        d = max(0.0, min(1.0, d))
        return d

    def _inter_cluster_distance(self, cluster_a: List[str],
                                 cluster_b: List[str]) -> float:
        """两个簇之间的平均最小距离"""
        if not cluster_a or not cluster_b:
            return 1.0
        distances = []
        for a in cluster_a:
            for b in cluster_b:
                distances.append(self._distance(a, b))
        return sum(distances) / len(distances)

    def _cluster_distance(self, cluster_a: List[str],
                          cluster_b: List[str]) -> float:
        """两簇间的最小距离（用于凝聚聚类）"""
        min_dist = 1.0
        for a in cluster_a:
            for b in cluster_b:
                d = self._distance(a, b)
                if d < min_dist:
                    min_dist = d
        return min_dist

    def _count_shared_actions(self, cid_a: str, cid_b: str) -> int:
        """两个概念共同出现的动作记录数"""
        count = 0
        for action in self.state.actions:
            if cid_a in action.concept_ids and cid_b in action.concept_ids:
                count += 1
        return count
