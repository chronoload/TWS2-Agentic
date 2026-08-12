"""
知识图谱世界——概念 CRUD、搜索、线程管理。

world 是 ecosystem 的"数据库层"，
封装所有对 EcosystemState 的读写操作。
"""

from typing import Dict, List, Optional, Tuple
from .models import (
    Concept, SourceRef, ResearchThread, Artifact,
    ActionRecord, Observation, PlayerState, EcosystemState,
)


class World:
    """
    知识图谱世界
    
    提供对 EcosystemState 的便捷 CRUD 接口，
    以及搜索和导航功能。
    """

    def __init__(self, state: EcosystemState):
        self.state = state

    # ── 概念 CRUD ──

    def get_concept(self, concept_id: str) -> Optional[Concept]:
        return self.state.concepts.get(concept_id)

    def find_concept_by_label(self, label: str) -> Optional[Concept]:
        """通过 label 精确查找"""
        ...

    def search_concepts(self, query: str, limit: int = 10) -> List[Concept]:
        """模糊搜索概念（label + alias 匹配）"""
        ...

    def create_concept(self, label: str, **kwargs) -> Concept:
        """创建新概念"""
        ...

    def update_concept(self, concept_id: str, **kwargs) -> bool:
        ...

    def delete_concept(self, concept_id: str) -> bool:
        ...

    # ── 图遍历 ──

    def get_children(self, concept_id: str) -> List[Concept]:
        ...

    def get_parents(self, concept_id: str) -> List[Concept]:
        ...

    def get_related(self, concept_id: str,
                    min_strength: float = 0.0) -> List[Tuple[Concept, float]]:
        """返回（关联概念，关联强度）列表"""
        ...

    def get_neighbors(self, concept_id: str, depth: int = 1,
                       max_nodes: int = 100) -> List[Tuple[Concept, int]]:
        """BFS 获取 n 层邻居，返回 (概念, 距离) 列表，最多 max_nodes 个"""
        if concept_id not in self.state.concepts:
            return []
        visited = {concept_id}
        result: List[Tuple[Concept, int]] = []
        queue = [(concept_id, 0)]
        while queue and len(result) < max_nodes:
            cid, d = queue.pop(0)
            if d > 0:
                result.append((self.state.concepts[cid], d))
            if d < depth and len(result) + len(queue) < max_nodes:
                concept = self.state.concepts.get(cid)
                if concept:
                    # 按关联强度降序排列
                    nbrs = sorted(concept.related_ids.items(),
                                  key=lambda x: x[1], reverse=True)
                    for nid, _ in nbrs:
                        if nid not in visited:
                            visited.add(nid)
                            queue.append((nid, d + 1))
        return result

    def get_concept_count(self) -> int:
        return len(self.state.concepts)

    def get_alive_count(self) -> int:
        return sum(1 for c in self.state.concepts.values() if c.is_alive)

    def get_fossil_count(self) -> int:
        return sum(1 for c in self.state.concepts.values() if c.is_fossilized)

    # ── 线程管理 ──

    def create_thread(self, label: str, concept_ids: List[str],
                      description: str = "") -> ResearchThread:
        ...

    def get_thread(self, thread_id: str) -> Optional[ResearchThread]:
        ...

    def add_to_thread(self, thread_id: str, concept_id: str) -> bool:
        ...

    def remove_from_thread(self, thread_id: str, concept_id: str) -> bool:
        ...

    def archive_thread(self, thread_id: str) -> bool:
        ...

    # ── 产物管理 ──

    def create_artifact(self, artifact_type: str, title: str,
                        file_path: str, concept_ids: List[str],
                        thread_id: str = "") -> Artifact:
        ...

    # ── 玩家状态 ──

    def get_player(self) -> PlayerState:
        return self.state.player

    def move_to_concept(self, concept_id: str) -> bool:
        """移动玩家到指定概念"""
        ...

    def move_to_thread(self, thread_id: str) -> bool:
        """切换活跃线程"""
        ...

    def record_action(self, action: ActionRecord):
        """追加动作记录"""
        ...

    def record_observation(self, obs: Observation):
        """追加观察日志"""
        ...

    # ── 快照 ──

    def snapshot(self) -> EcosystemState:
        """返回当前状态的快照"""
        return self.state

    def to_dict(self) -> dict:
        """序列化为 JSON 兼容格式（用于 API 输出）"""
        ...
