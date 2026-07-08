from typing import List, Callable, Any, Dict
from .dag_executor import DAGExecutor, DAGNode, DAGEdge


class SequentialPattern:
    @staticmethod
    def build(steps: List[Dict], executor_factory: Callable) -> DAGExecutor:
        dag = DAGExecutor()
        for i, step in enumerate(steps):
            deps = [steps[i - 1]["id"]] if i > 0 else []
            node = DAGNode(
                id=step["id"],
                name=step.get("name", step["id"]),
                executor=executor_factory(step),
                dependencies=deps,
            )
            dag.add_node(node)
            if i > 0:
                dag.add_edge(DAGEdge(source=steps[i - 1]["id"], target=step["id"]))
        return dag


class ParallelPattern:
    @staticmethod
    def build(tasks: List[Dict], executor_factory: Callable, merge_id: str = "merge") -> DAGExecutor:
        dag = DAGExecutor()
        merge_deps = []
        for task in tasks:
            node = DAGNode(
                id=task["id"],
                name=task.get("name", task["id"]),
                executor=executor_factory(task),
            )
            dag.add_node(node)
            merge_deps.append(task["id"])
        merge_node = DAGNode(
            id=merge_id,
            name="合并结果",
            executor=lambda context, dependencies: dependencies,
            dependencies=merge_deps,
        )
        dag.add_node(merge_node)
        for dep in merge_deps:
            dag.add_edge(DAGEdge(source=dep, target=merge_id))
        return dag


class ConditionalPattern:
    @staticmethod
    def build(condition_id: str, condition_fn: Callable,
              true_steps: List[Dict], false_steps: List[Dict],
              executor_factory: Callable) -> DAGExecutor:
        dag = DAGExecutor()
        cond_node = DAGNode(
            id=condition_id,
            name="条件判断",
            executor=lambda context, dependencies: condition_fn(context, dependencies),
        )
        dag.add_node(cond_node)
        for step in true_steps:
            node = DAGNode(
                id=step["id"],
                name=step.get("name", step["id"]),
                executor=executor_factory(step),
                dependencies=[condition_id],
            )
            dag.add_node(node)
            dag.add_edge(DAGEdge(
                source=condition_id, target=step["id"],
                condition=lambda result: result is True,
            ))
        for step in false_steps:
            node = DAGNode(
                id=step["id"],
                name=step.get("name", step["id"]),
                executor=executor_factory(step),
                dependencies=[condition_id],
            )
            dag.add_node(node)
            dag.add_edge(DAGEdge(
                source=condition_id, target=step["id"],
                condition=lambda result: result is False,
            ))
        return dag
