import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


@dataclass
class DAGNode:
    id: str
    name: str
    executor: Callable[..., Any]
    dependencies: List[str] = field(default_factory=list)
    timeout: float = 300.0
    retry_count: int = 0


@dataclass
class DAGEdge:
    source: str
    target: str
    condition: Optional[Callable[[Any], bool]] = None


@dataclass
class DAGResult:
    node_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None


class DAGExecutor:
    def __init__(self, max_workers: int = 4):
        self._nodes: Dict[str, DAGNode] = {}
        self._edges: List[DAGEdge] = []
        self._max_workers = max_workers

    def add_node(self, node: DAGNode):
        self._nodes[node.id] = node

    def add_edge(self, edge: DAGEdge):
        self._edges.append(edge)

    def execute(self, context: Dict[str, Any]) -> Dict[str, DAGResult]:
        results: Dict[str, DAGResult] = {}
        completed = set()
        remaining = set(self._nodes.keys())
        max_iterations = len(self._nodes) * 2
        iteration = 0

        while remaining and iteration < max_iterations:
            iteration += 1
            ready = self._find_ready_nodes(remaining, completed, results)
            if not ready:
                if remaining:
                    for node_id in remaining:
                        results[node_id] = DAGResult(
                            node_id=node_id, success=False,
                            error="无法满足依赖条件，节点被跳过",
                        )
                break
            with ThreadPoolExecutor(max_workers=min(len(ready), self._max_workers)) as pool:
                future_map = {}
                for node_id in ready:
                    node = self._nodes[node_id]
                    deps = {dep: results[dep].output for dep in node.dependencies if dep in results}
                    future = pool.submit(self._execute_node, node, context, deps)
                    future_map[future] = node_id
                try:
                    max_timeout = max(self._nodes[nid].timeout for nid in ready)
                    for future in as_completed(future_map, timeout=max_timeout):
                        node_id = future_map[future]
                        try:
                            results[node_id] = future.result(timeout=self._nodes[node_id].timeout)
                        except Exception as e:
                            results[node_id] = DAGResult(node_id=node_id, success=False, error=str(e))
                        completed.add(node_id)
                        remaining.discard(node_id)
                except Exception as e:
                    for node_id in list(remaining):
                        if node_id not in results:
                            results[node_id] = DAGResult(node_id=node_id, success=False, error=str(e))
                    break

        return results

    def _find_ready_nodes(self, remaining, completed, results) -> List[str]:
        ready = []
        for node_id in remaining:
            node = self._nodes[node_id]
            deps_met = all(dep in completed for dep in node.dependencies)
            if not deps_met:
                continue
            edge_conditions_met = True
            for edge in self._edges:
                if edge.target == node_id and edge.source in completed:
                    if edge.condition and results.get(edge.source):
                        if not edge.condition(results[edge.source].output):
                            edge_conditions_met = False
                            break
            if edge_conditions_met:
                ready.append(node_id)
        return ready

    def _execute_node(self, node: DAGNode, context: Dict, deps: Dict) -> DAGResult:
        try:
            output = node.executor(context=context, dependencies=deps)
            return DAGResult(node_id=node.id, success=True, output=output)
        except Exception as e:
            logger.error(f"DAG节点 {node.name} 执行失败: {e}")
            return DAGResult(node_id=node.id, success=False, error=str(e))
