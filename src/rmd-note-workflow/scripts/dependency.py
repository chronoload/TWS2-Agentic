"""依赖图分析：拓扑排序 + 并发分组"""

from collections import defaultdict, deque
from pathlib import Path
import re


class DependencyGraph:
    """有向无环图（DAG），用于分析文档依赖"""

    def __init__(self):
        self._edges: dict[str, set[str]] = defaultdict(set)  # node → {依赖它的节点}
        self._reverse: dict[str, set[str]] = defaultdict(set)  # node → {它依赖的节点}
        self._nodes: set[str] = set()

    def add_node(self, node: str) -> None:
        self._nodes.add(node)

    def add_edge(self, from_id: str, to_id: str) -> None:
        """添加依赖边：to_id 依赖 from_id（from_id 先写）"""
        self._nodes.add(from_id)
        self._nodes.add(to_id)
        self._edges[from_id].add(to_id)
        self._reverse[to_id].add(from_id)

    def topological_sort(self) -> list[list[str]]:
        """
        Kahn's 算法拓扑排序
        返回：[[同层可并发的节点], [下一层], ...]
        """
        in_degree = {n: len(self._reverse[n]) for n in self._nodes}
        levels = []
        queue = deque([n for n in self._nodes if in_degree[n] == 0])

        while queue:
            level = list(queue)
            levels.append(sorted(level))
            next_queue = deque()
            for node in level:
                for dependent in self._edges[node]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)
            queue = next_queue

        # 检测循环
        processed = sum(len(l) for l in levels)
        if processed != len(self._nodes):
            remaining = self._nodes - {n for l in levels for n in l}
            raise ValueError(f"循环依赖检测到，未处理节点: {remaining}")

        return levels

    def get_parallel_groups(self) -> list[list[str]]:
        """返回并行分组（与 topological_sort 相同，语义更明确）"""
        return self.topological_sort()

    @property
    def nodes(self) -> set[str]:
        return self._nodes.copy()

    def __repr__(self) -> str:
        return f"DependencyGraph(nodes={len(self._nodes)}, edges={sum(len(v) for v in self._edges.values())})"


def extract_from_frameworks(frameworks_dir: str | Path) -> DependencyGraph:
    """
    从 framework 目录中提取依赖关系
    查找格式：'依赖 L{N}' 或 'prerequisites: L{N}' 或 '→ L{N}'
    """
    graph = DependencyGraph()
    fw_dir = Path(frameworks_dir)

    if not fw_dir.exists():
        return graph

    for fw_file in fw_dir.glob("*-framework.md"):
        with open(fw_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取本 framework 覆盖的 lesson IDs
        lesson_ids = re.findall(r"(?:###\s+)(L\d+)", content)
        for lid in lesson_ids:
            graph.add_node(lid)

        # 提取依赖关系
        # 格式: "依赖: L22" 或 "Prerequisites: L22, L30"
        dep_matches = re.findall(r"(?:依赖|prerequisites?|depends?\s*on)[:\s]+((?:L\d+[\s,]*)+)", content, re.IGNORECASE)
        for match in dep_matches:
            deps = re.findall(r"L\d+", match)
            for lid in lesson_ids:
                for dep in deps:
                    if dep != lid:
                        graph.add_edge(dep, lid)

    return graph


def extract_from_config_edges(edges: list[list[str]]) -> DependencyGraph:
    """从 config.json 的 edges 字段构建依赖图"""
    graph = DependencyGraph()
    for src, dst in edges:
        graph.add_edge(src, dst)
    return graph
