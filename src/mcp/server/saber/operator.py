"""
SaberSystem Plan 算子
P: (History, State, Constraints, LifeResource) → Compressed_Context
双重职能：Orchestrate（编排）+ Compress（压缩）
含 LifeGuard 双层前置检查（健康+注意力资本）
树聚合 + 偏序拓扑 + 违规裁决
"""
from __future__ import annotations
import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Literal

from mcp.server.saber.models import Plan, Task
from mcp.server.saber.life import (
    LifeResource, AttentionCapital, HealthStatus, current_attention,
)


@dataclass
class CompressedContext:
    """Plan 算子的输出——压缩上下文"""
    summary: str
    fingerprint: str
    progress_vector: tuple[float, float] | None = None
    life_vector: tuple[float, float, float, float] | None = None
    risk_factors: int = 0
    opportunity_cost: float = 0.0
    execution_order: list[str] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    recommended_recovery_minutes: int | None = None


class LifeGuard:
    """生命守护者——双层前置检查（健康+注意力资本）"""

    def __init__(self, life: LifeResource):
        self.life = life
        self.block_reason: str | None = None

    def is_blocked(self) -> bool:
        """检查是否应冻结新任务启动"""
        if self.life.health.is_burned_out():
            self.block_reason = "burned_out"
            return True
        if self.life.attention_capital.is_depleted():
            self.block_reason = "attention_depleted"
            return True
        self.block_reason = None
        return False


# ─── 树聚合 ───

def flatten_tree(root_plan_id: str, get_plan: Callable[[str], Plan | None]) -> list[Plan]:
    """BFS 遍历 Plan 树，返回所有后代 Plan（含自身）"""
    result = []
    queue = deque([root_plan_id])
    while queue:
        pid = queue.popleft()
        p = get_plan(pid)
        if p is None:
            continue
        result.append(p)
        for cid in p.children_ids:
            queue.append(cid)
    return result


def _aggregate_tree_state(
    plan: Plan,
    get_plan: Callable[[str], Plan | None],
) -> tuple[float, str]:
    """递归聚合 Plan 树状态

    返回 (aggregated_progress, aggregated_status)
    - 无子 Plan → tasks_progress
    - 有子 Plan → weighted_avg(children)
    - 任一子 blocked → 父 blocked
    - 全部 completed → 父 completed
    """
    if not plan.children_ids:
        if not plan.tasks:
            plan.aggregated_progress = 0.0
            plan.aggregated_status = "blocked"
            return 0.0, "blocked"
        completed = sum(1 for t in plan.tasks if t.status == "done")
        progress = completed / len(plan.tasks)
        plan.aggregated_progress = progress
        plan.aggregated_status = "completed" if progress >= 1.0 else "active"
        return progress, plan.aggregated_status

    children_progress = []
    all_completed = True
    any_blocked = False
    for cid in plan.children_ids:
        child = get_plan(cid)
        if child is None:
            continue
        cp, cs = _aggregate_tree_state(child, get_plan)
        children_progress.append(cp)
        if cs == "blocked":
            any_blocked = True
        if cs != "completed":
            all_completed = False

    if children_progress:
        progress = sum(cp for cp in children_progress) / len(children_progress)
    else:
        progress = 0.0

    plan.aggregated_progress = progress
    if any_blocked:
        plan.aggregated_status = "blocked"
    elif all_completed:
        plan.aggregated_status = "completed"
    else:
        plan.aggregated_status = "active"
    return progress, plan.aggregated_status


# ─── 偏序（DAG）───

def detect_cycle(
    plan_ids: list[str],
    get_plan: Callable[[str], Plan | None],
) -> list[str] | None:
    """检测 DAG 中的环，返回环路径或 None

    用三色 DFS（white/gray/black）。
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {pid: WHITE for pid in plan_ids}
    parent = {}

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        p = get_plan(node)
        if p is not None:
            for succ in p.successors:
                if succ not in color:
                    continue
                if color[succ] == GRAY:
                    cycle = [succ, node]
                    cur = node
                    while cur != succ:
                        cur = parent.get(cur)
                        if cur is None:
                            break
                        cycle.append(cur)
                    cycle.reverse()
                    return cycle
                elif color[succ] == WHITE:
                    parent[succ] = node
                    result = dfs(succ)
                    if result is not None:
                        return result
        color[node] = BLACK
        return None

    for pid in plan_ids:
        if color[pid] == WHITE:
            result = dfs(pid)
            if result is not None:
                return result
    return None


def topological_sort(
    plan_ids: list[str],
    get_plan: Callable[[str], Plan | None],
) -> list[str]:
    """拓扑排序（Kahn 算法），返回 plan_id 列表

    按 successors 构建邻接表，入度递减。
    """
    in_degree = {pid: 0 for pid in plan_ids}
    adj = {pid: [] for pid in plan_ids}

    for pid in plan_ids:
        p = get_plan(pid)
        if p is None:
            continue
        for succ in p.successors:
            if succ in adj:
                adj[pid].append(succ)
                in_degree[succ] = in_degree.get(succ, 0) + 1

    queue = deque([pid for pid in plan_ids if in_degree.get(pid, 0) == 0])
    result = []
    while queue:
        pid = queue.popleft()
        result.append(pid)
        for succ in adj.get(pid, []):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    if len(result) != len(plan_ids):
        raise ValueError(f"拓扑排序失败：存在环，已排序 {len(result)}/{len(plan_ids)}")
    return result


def find_critical_path(
    plan_ids: list[str],
    get_plan: Callable[[str], Plan | None],
) -> list[str]:
    """在偏序 DAG 中找关键路径（最长路径）

    先拓扑排序，再 DP 求最长路径。
    """
    try:
        order = topological_sort(plan_ids, get_plan)
    except ValueError:
        return []

    dist = {pid: 0 for pid in plan_ids}
    prev = {pid: None for pid in plan_ids}

    for pid in order:
        p = get_plan(pid)
        if p is None:
            continue
        for succ in p.successors:
            if succ in dist:
                if dist[succ] < dist[pid] + 1:
                    dist[succ] = dist[pid] + 1
                    prev[succ] = pid

    if not dist:
        return []
    end = max(dist, key=lambda k: dist[k])
    path = []
    cur = end
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path


# ─── 违规裁决 ───

@dataclass
class ViolationResult:
    """违规裁决结果"""
    has_violation: bool
    violation_type: str | None  # predecessor | transitive_closure | cycle | aggregation | life
    message: str
    plan_id: str | None = None


def check_predecessor_violation(
    plan: Plan,
    get_plan: Callable[[str], Plan | None],
) -> ViolationResult:
    """检查显式前置违规：B 依赖 A，A 未完成即启动 B"""
    for pred_id in plan.predecessors:
        pred = get_plan(pred_id)
        if pred is None:
            continue
        if pred.status not in ("completed", "archived"):
            return ViolationResult(
                has_violation=True,
                violation_type="predecessor",
                message=f"前置 Plan「{pred.title}」尚未完成（状态: {pred.status}），当前 Plan 不可启动。",
                plan_id=pred_id,
            )
    return ViolationResult(has_violation=False, violation_type=None, message="")


def check_transitive_closure_violation(
    plan: Plan,
    get_plan: Callable[[str], Plan | None],
) -> ViolationResult:
    """检查传递闭包违规：A→B→C，跳过 B 完成 C

    BFS 从所有前驱遍历，如果某个前驱的所有前驱都不完整但当前 Plan 已完成，则违规。
    实际上是检查：如果 current status=completed，但存在 predecessor 未完成。
    """
    if plan.status != "completed":
        return ViolationResult(has_violation=False, violation_type=None, message="")

    visited = set()
    queue = deque(plan.predecessors)
    while queue:
        pid = queue.popleft()
        if pid in visited:
            continue
        visited.add(pid)
        pred = get_plan(pid)
        if pred is None:
            continue
        if pred.status not in ("completed", "archived"):
            return ViolationResult(
                has_violation=True,
                violation_type="transitive_closure",
                message=f"传递闭包违规：Plan「{pred.title}」（{pred.status}）未完成，但其后继已完成。",
                plan_id=pid,
            )
        for pp in pred.predecessors:
            if pp not in visited:
                queue.append(pp)

    return ViolationResult(has_violation=False, violation_type=None, message="")


def check_aggregation_violation(
    plan: Plan,
    get_plan: Callable[[str], Plan | None],
) -> ViolationResult:
    """检查聚合违规：父未完成子却强行归档"""
    if plan.status != "archived":
        return ViolationResult(has_violation=False, violation_type=None, message="")

    if plan.parent_plan_id:
        parent = get_plan(plan.parent_plan_id)
        if parent is not None and parent.status not in ("completed", "archived"):
            return ViolationResult(
                has_violation=True,
                violation_type="aggregation",
                message=f"父 Plan「{parent.title}」尚未完成，子 Plan 不可独立归档。",
                plan_id=parent.id,
            )

    for cid in plan.children_ids:
        child = get_plan(cid)
        if child is not None and child.status not in ("completed", "archived"):
            return ViolationResult(
                has_violation=True,
                violation_type="aggregation",
                message=f"子 Plan「{child.title}」尚未完成，父 Plan 不可归档。",
                plan_id=cid,
            )

    return ViolationResult(has_violation=False, violation_type=None, message="")


def check_violations(
    plan: Plan,
    get_plan: Callable[[str], Plan | None],
) -> list[ViolationResult]:
    """统一违规检查，返回所有违规"""
    results = []

    if plan.status == "active" or plan.status == "draft":
        r = check_predecessor_violation(plan, get_plan)
        if r.has_violation:
            results.append(r)

    r = check_transitive_closure_violation(plan, get_plan)
    if r.has_violation:
        results.append(r)

    r = check_aggregation_violation(plan, get_plan)
    if r.has_violation:
        results.append(r)

    return results


# ─── 算力（原局部聚合函数）───

def _aggregate_state(plan: Plan) -> tuple[float, float]:
    """（向后兼容）单 Plan 任务级聚合"""
    if not plan.tasks:
        return 0.0, 0.0
    completed = sum(1 for t in plan.tasks if t.status == "done")
    completed_ratio = completed / len(plan.tasks)

    total_estimated = sum(t.estimated_hours for t in plan.tasks)
    total_actual = sum(t.actual_hours for t in plan.tasks)
    if total_estimated > 0:
        elapsed_ratio = min(1.0, total_actual / total_estimated)
    else:
        elapsed_ratio = 0.0

    return completed_ratio, elapsed_ratio


def _compute_risk_factors(plan: Plan) -> int:
    """计算风险因子数"""
    blocked = sum(1 for t in plan.tasks if t.status == "blocked")
    return blocked


# ─── 组合 apply() ───

def plan_operator_apply(
    plan: Plan,
    life: LifeResource,
    elapsed_hours: float = 0.0,
    get_plan: Callable[[str], Plan | None] | None = None,
) -> CompressedContext:
    """
    Plan 算子 apply()——双重职能
    0. LifeGuard 双层前置检查
    1. 树感知拓扑（扁平树 + 偏序拓扑排序 + 关键路径）
    2. 聚合状态（递归树聚合）
    3. 违规裁决（前置/传递闭包/聚合）
    4. 注意力资本消耗核算
    5. 压缩上下文 + 指纹
    """
    # 0. 生命前置检查（LifeGuard）
    guard = LifeGuard(life)
    if guard.is_blocked():
        if guard.block_reason == "burned_out":
            plan.compliance_status = "burned_out"
            return CompressedContext(
                summary="用户已透支，新任务被冻结。请先休息。",
                fingerprint=hashlib.sha256(
                    f"{plan.id}:burned_out".encode()).hexdigest()[:16],
                blocked_reason="burned_out",
                recommended_recovery_minutes=60,
            )
        elif guard.block_reason == "attention_depleted":
            plan.compliance_status = "attention_depleted"
            return CompressedContext(
                summary="注意力资本已耗尽，强行工作将透支并招致质量惩罚。建议休息 30 分钟存入资本。",
                fingerprint=hashlib.sha256(
                    f"{plan.id}:attention_depleted".encode()).hexdigest()[:16],
                blocked_reason="attention_depleted",
                recommended_recovery_minutes=30,
            )

    # 1. 树感知拓扑
    execution_order = [t.id for t in plan.tasks]
    critical_path_ids: list[str] = []

    if get_plan is not None:
        # 获取树中所有 Plan
        tree_plans = flatten_tree(plan.id, get_plan)
        tree_ids = [p.id for p in tree_plans]

        # 检测循环
        cycle = detect_cycle(tree_ids, get_plan)
        if cycle:
            plan.compliance_status = "deviated"
            return CompressedContext(
                summary=f"检测到循环依赖: {' → '.join(cycle[:6])}。强制进入修订模式。",
                fingerprint=hashlib.sha256(
                    f"{plan.id}:cycle:{'-'.join(cycle)}".encode()).hexdigest()[:16],
                blocked_reason="cycle_detected",
            )

        # 树聚合
        _aggregate_tree_state(plan, get_plan)

        # 违规检查
        violations = check_violations(plan, get_plan)
        if violations:
            msg = violations[0].message
            vtype = violations[0].violation_type
            plan.compliance_status = "deviated"
            return CompressedContext(
                summary=msg,
                fingerprint=hashlib.sha256(
                    f"{plan.id}:violation:{vtype}".encode()).hexdigest()[:16],
                blocked_reason=vtype,
            )

        # 拓扑排序
        try:
            topo_order = topological_sort(tree_ids, get_plan)
            cp = find_critical_path(tree_ids, get_plan)
            critical_path_ids = cp or []
            # 执行顺序 = 拓扑序 + task 执行
            execution_order = topo_order + [t.id for t in plan.tasks]
        except ValueError:
            execution_order = [t.id for t in plan.tasks]
    else:
        # 无 store 时仅聚合单 Plan 任务级进度
        _aggregate_state(plan)

    # 2. 聚合状态（向后兼容）
    completed_ratio, elapsed_ratio = _aggregate_state(plan)
    risk_factors = _compute_risk_factors(plan)

    # 3. 注意力资本消耗核算（支出资本）
    if elapsed_hours > 0:
        life.attention_capital.spend(elapsed_hours, intensity=1.0)

    # 4. 计算生命向量
    att = current_attention(life.attention_capital, elapsed_hours)
    life_vector = (
        att,                                    # 瞬时可用注意力
        life.attention_capital.balance,         # 资本余额
        life.energy_level,                      # 体能（LifeResource 上）
        life.mood_index,                        # 情绪
    )

    # 5. 进度向量
    progress_vector = (completed_ratio, elapsed_ratio)

    # 6. 合规状态
    if plan.compliance_status not in ("burned_out", "deviated"):
        if risk_factors > 0:
            plan.compliance_status = "at_risk"
        elif plan.aggregated_status == "blocked":
            plan.compliance_status = "blocked"
        else:
            plan.compliance_status = "on_track"

    # 7. 生成摘要
    summary = (f"Plan「{plan.title}」进度 {completed_ratio*100:.0f}%，"
               f"聚合状态 {plan.aggregated_status}，合规 {plan.compliance_status}，"
               f"已完成 {sum(1 for t in plan.tasks if t.status == 'done')}/{len(plan.tasks)} 任务，"
               f"风险因子 {risk_factors}，注意力 {att*100:.0f}%。")

    # 8. 指纹
    fingerprint_input = (f"{plan.id}:{summary}:{progress_vector}:{life_vector}:{plan.aggregated_status}:{plan.compliance_status}")
    fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]

    return CompressedContext(
        summary=summary,
        fingerprint=fingerprint,
        progress_vector=progress_vector,
        life_vector=life_vector,
        risk_factors=risk_factors,
        execution_order=execution_order,
        critical_path=critical_path_ids,
    )
