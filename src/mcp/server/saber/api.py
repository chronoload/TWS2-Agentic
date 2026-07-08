"""
SaberSystem API 路由模块
独立 FastAPI 应用，可挂载到主 app.py
端点见文档 §11.1
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, APIRouter
from pydantic import BaseModel

from mcp.server.saber.models import (
    CognitiveLayer, Ideal, Goal, Plan, Task, Constraint, DecisionPoint,
)
from mcp.server.saber.life import LifeResource, AttentionCapital
from mcp.server.saber.store import SaberStore
from mcp.server.saber.operator import (
    plan_operator_apply,
    flatten_tree, detect_cycle, topological_sort, find_critical_path,
    _aggregate_tree_state, check_violations,
)
from mcp.server.saber.opportunity_cost import assess_opportunity_cost
from mcp.server.saber.optimizer import (
    allocate_life_resources, check_weight_imbalance,
)
from mcp.server.saber.decision import (
    generate_decision_point, generate_plans_for_goal,
    INTENSITY_RETIREMENT_THRESHOLD, _llm_generator,
)
from mcp.server.saber.agent import AgentContributionLog, compute_intensity


# ─── 请求模型 ───

class IdealCreateRequest(BaseModel):
    title: str
    description: str = ""


class GoalCreateRequest(BaseModel):
    title: str
    description: str = ""
    ideal_id: str
    priority_weight: float
    target_layer: str  # K/C/T/S/W


class IdealUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None


class GoalUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    priority_weight: float | None = None
    target_layer: str | None = None


class ReweightRequest(BaseModel):
    weights: dict[str, float]


class PlanCreateRequest(BaseModel):
    title: str
    description: str = ""
    goal_id: str
    cognitive_focus: str  # K/C/T/S/W
    priority_weight: float
    parent_plan_id: str | None = None


class PlanUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    cognitive_focus: str | None = None
    priority_weight: float | None = None
    status: str | None = None
    aggregated_progress: float | None = None
    parent_plan_id: str | None = None


class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    goal_id: str
    cognitive_layer: str
    estimated_hours: float
    priority_weight: float = 1.0
    is_one_time_only: bool = False
    can_be_rescheduled: bool = True
    time_window_remaining: float = 1.0


class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    goal_id: str = ""
    cognitive_layer: str = "procedural"
    estimated_hours: float = 1.0
    status: str = "todo"
    deadline: str | None = None
    priority_weight: float = 1.0
    is_one_time_only: bool = False
    can_be_rescheduled: bool = True
    time_window_remaining: float = 1.0


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    cognitive_layer: str | None = None
    estimated_hours: float | None = None
    priority_weight: float | None = None


class OperatorRequest(BaseModel):
    elapsed_hours: float = 0.0


class LinkRequest(BaseModel):
    related_plan_id: str


class RecoverRequest(BaseModel):
    user_id: str
    hours: float
    quality: float = 1.0


class OpportunityCostRequest(BaseModel):
    chosen_task_id: str
    alternative_task_ids: list[str]


class DecisionGenerateRequest(BaseModel):
    alternatives: list[str] = []  # 替代 task id 列表，可选


class DecisionSelectRequest(BaseModel):
    option_id: str
    was_adopted: bool
    user_modification_ratio: float = 0.0


class AgentLogRequest(BaseModel):
    plan_id: str
    user_id: str = "default"
    suggestion_type: str  # structure/advice/translation/remediation/rag_injection
    was_adopted: bool
    user_modification_ratio: float
    attention_consumed: float
    cognitive_layer_target: str
    intensity_at_creation: float


class ChatRequest(BaseModel):
    plan_id: str
    message: str
    user_id: str = "default"


# ─── 响应辅助 ───

def _ok(data: Any) -> dict:
    return {"code": 0, "msg": "", "data": data}


def _err(msg: str, code: int = 1) -> dict:
    return {"code": code, "msg": msg, "data": None}


def _to_dict(obj) -> dict:
    """dataclass 转 dict，处理 enum/datetime"""
    d = asdict(obj) if hasattr(obj, '__dataclass_fields__') else dict(obj)
    for k, v in d.items():
        if hasattr(v, 'value'):  # Enum
            d[k] = v.value
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
        elif hasattr(v, '__dataclass_fields__'):
            d[k] = _to_dict(v)
        elif isinstance(v, list):
            d[k] = [_to_dict(i) if hasattr(i, '__dataclass_fields__') else i for i in v]
    # 附加 @property 字段
    if hasattr(obj, 'waking_hours_surplus'):
        d['waking_hours_surplus'] = obj.waking_hours_surplus
    return d


def _layer(s: str) -> CognitiveLayer:
    """字符串转 CognitiveLayer，支持全称与简写"""
    s = s.upper()
    for layer in CognitiveLayer:
        if layer.value == s or layer.name == s:
            return layer
    raise HTTPException(400, f"无效的认知层级: {s}")


# ─── 路由工厂 ───

def create_saber_router(store: SaberStore | None = None) -> APIRouter:
    """创建 SaberSystem 路由（可挂载到任意 FastAPI app）

    用法：
      # 独立子应用（测试用）
      app = FastAPI()
      app.include_router(create_saber_router(store))

      # 挂载到主 app.py
      from mcp.server.saber.api import create_saber_router
      app.include_router(create_saber_router())
    """
    if store is None:
        from mcp.server.saber.store import get_store
        store = get_store()

    router = APIRouter(prefix="/api/saber")

    # ─── Ideal 端点 ───

    @router.get("/ideals")
    def list_ideals():
        return _ok([_to_dict(i) for i in store.list_ideals()])

    @router.post("/ideals")
    def create_ideal(req: IdealCreateRequest):
        ideal = Ideal(title=req.title, description=req.description)
        store.add_ideal(ideal)
        return _ok(_to_dict(ideal))

    @router.get("/ideals/{ideal_id}")
    def get_ideal(ideal_id: str):
        ideal = store.get_ideal(ideal_id)
        if ideal is None:
            raise HTTPException(404, "Ideal 不存在")
        return _ok(_to_dict(ideal))

    @router.delete("/ideals/{ideal_id}")
    def delete_ideal(ideal_id: str):
        store.delete_ideal(ideal_id)
        return _ok(True)

    @router.patch("/ideals/{ideal_id}")
    def update_ideal(ideal_id: str, req: IdealUpdateRequest):
        ideal = store.get_ideal(ideal_id)
        if ideal is None:
            raise HTTPException(404, "Ideal 不存在")
        if req.title is not None:
            ideal.title = req.title
        if req.description is not None:
            ideal.description = req.description
        store.update_ideal(ideal)
        return _ok(_to_dict(ideal))

    # ─── Goal 端点 ───

    @router.get("/goals")
    def list_goals(ideal_id: str | None = None):
        return _ok([_to_dict(g) for g in store.list_goals(ideal_id)])

    @router.post("/goals")
    def create_goal(req: GoalCreateRequest):
        goal = Goal(
            title=req.title, description=req.description,
            ideal_id=req.ideal_id,
            priority_weight=req.priority_weight,
            target_layer=_layer(req.target_layer),
        )
        store.add_goal(goal)
        return _ok(_to_dict(goal))

    @router.get("/goals/{goal_id}")
    def get_goal(goal_id: str):
        goal = store.get_goal(goal_id)
        if goal is None:
            raise HTTPException(404, "Goal 不存在")
        return _ok(_to_dict(goal))

    @router.patch("/goals/{goal_id}")
    def update_goal(goal_id: str, req: GoalUpdateRequest):
        goal = store.get_goal(goal_id)
        if goal is None:
            raise HTTPException(404, "Goal 不存在")
        if req.title is not None:
            goal.title = req.title
        if req.description is not None:
            goal.description = req.description
        if req.priority_weight is not None:
            goal.priority_weight = req.priority_weight
        if req.target_layer is not None:
            goal.target_layer = _layer(req.target_layer)
        store.update_goal(goal)
        return _ok(_to_dict(goal))

    @router.delete("/goals/{goal_id}")
    def delete_goal(goal_id: str):
        store.delete_goal(goal_id)
        return _ok(True)

    @router.post("/goals/{ideal_id}/reweight")
    def reweight_goals(ideal_id: str, req: ReweightRequest):
        try:
            store.reweight_goals(ideal_id, req.weights)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return _ok({"reweighted": True})

    @router.post("/goals/{goal_id}/generate-plans")
    def generate_plans(goal_id: str):
        """LLM 为 Goal 生成 Plan 方案建议"""
        goal = store.get_goal(goal_id)
        if goal is None:
            raise HTTPException(404, "Goal 不存在")
        existing = [p.title for p in store.list_plans(goal_id)]
        try:
            suggestions = generate_plans_for_goal(
                goal.title, goal.description,
                goal.target_layer.value,
                existing_plan_titles=existing,
            )
            return _ok({"suggestions": suggestions, "goal_id": goal_id})
        except Exception as e:
            raise HTTPException(503, f"Plan 生成失败: {e}")

    # ─── Plan 端点 ───

    @router.get("/plans")
    def list_plans(goal_id: str | None = None):
        return _ok([_to_dict(p) for p in store.list_plans(goal_id)])

    @router.post("/plans")
    def create_plan(req: PlanCreateRequest):
        plan = Plan(
            title=req.title, description=req.description,
            goal_id=req.goal_id,
            cognitive_focus=_layer(req.cognitive_focus),
            priority_weight=req.priority_weight,
            parent_plan_id=req.parent_plan_id,
        )
        store.add_plan(plan)
        return _ok(_to_dict(plan))

    @router.get("/plans/{plan_id}")
    def get_plan(plan_id: str):
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        return _ok(_to_dict(plan))

    @router.put("/plans/{plan_id}")
    def update_plan(plan_id: str, req: PlanUpdateRequest):
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        if req.title is not None:
            plan.title = req.title
        if req.description is not None:
            plan.description = req.description
        if req.cognitive_focus is not None:
            plan.cognitive_focus = _layer(req.cognitive_focus)
        if req.priority_weight is not None:
            plan.priority_weight = req.priority_weight
        if req.status is not None:
            plan.status = req.status
        if req.aggregated_progress is not None:
            plan.aggregated_progress = req.aggregated_progress
        if req.parent_plan_id is not None:
            plan.parent_plan_id = req.parent_plan_id
        store.update_plan(plan)
        return _ok(_to_dict(plan))

    @router.post("/plans/{plan_id}/tasks")
    def create_task(plan_id: str, req: TaskCreateRequest):
        task = Task(
            title=req.title, description=req.description,
            plan_id=plan_id, goal_id=req.goal_id,
            cognitive_layer=CognitiveLayer(req.cognitive_layer),
            estimated_hours=req.estimated_hours, status=req.status,
            priority_weight=req.priority_weight,
            is_one_time_only=req.is_one_time_only,
            can_be_rescheduled=req.can_be_rescheduled,
            time_window_remaining=req.time_window_remaining,
        )
        if req.deadline:
            from datetime import datetime
            task.deadline = datetime.fromisoformat(req.deadline)
        store.add_task(task)
        return _ok(_to_dict(task))

    @router.get("/plans/{plan_id}/tasks")
    def list_tasks(plan_id: str):
        return _ok([_to_dict(t) for t in store.list_tasks(plan_id)])

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str):
        tasks = []
        for p in store.list_plans():
            tasks.extend(store.list_tasks(p.id))
        for t in tasks:
            if t.id == task_id:
                return _ok(_to_dict(t))
        raise HTTPException(404, "Task 不存在")

    @router.delete("/tasks/{task_id}")
    def delete_task(task_id: str):
        store.delete_task(task_id)
        return _ok(True)

    @router.delete("/plans/{plan_id}")
    def delete_plan(plan_id: str):
        store.delete_plan(plan_id)
        return _ok(True)

    @router.post("/plans/{plan_id}/compress")
    def compress_plan(plan_id: str, final_score: float = Query(0.5)):
        try:
            life = store.get_life_resource("default")
            plan = store.compress_plan(plan_id, life=life, final_score=final_score)
            return _ok(_to_dict(plan))
        except KeyError:
            raise HTTPException(404, "Plan 不存在")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @router.post("/plans/{plan_id}/unarchive")
    def unarchive_plan(plan_id: str):
        try:
            plan = store.unarchive_plan(plan_id)
            return _ok(_to_dict(plan))
        except KeyError:
            raise HTTPException(404, "Plan 不存在")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @router.post("/plans/{plan_id}/steps")
    def add_task(plan_id: str, req: TaskCreateRequest):
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        task = Task(
            title=req.title, description=req.description,
            plan_id=plan_id, goal_id=req.goal_id,
            cognitive_layer=_layer(req.cognitive_layer),
            estimated_hours=req.estimated_hours,
            priority_weight=req.priority_weight,
            is_one_time_only=req.is_one_time_only,
            can_be_rescheduled=req.can_be_rescheduled,
            time_window_remaining=req.time_window_remaining,
        )
        store.add_task(task)
        plan.tasks.append(task)
        return _ok(_to_dict(task))

    @router.patch("/tasks/{task_id}")
    def update_task(task_id: str, req: TaskUpdateRequest):
        task = store.get_task(task_id)
        if task is None:
            raise HTTPException(404, "Task 不存在")
        if req.title is not None:
            task.title = req.title
        if req.status is not None:
            if req.status == "done":
                raise HTTPException(400, "不能直接设置为完成状态，请使用 POST /tasks/{id}/deliver 交付")
            task.status = req.status
        if req.cognitive_layer is not None:
            task.cognitive_layer = _layer(req.cognitive_layer)
        if req.estimated_hours is not None:
            task.estimated_hours = req.estimated_hours
        if req.priority_weight is not None:
            task.priority_weight = req.priority_weight
        store.update_task(task)
        return _ok(_to_dict(task))

    @router.post("/tasks/{task_id}/deliver")
    def deliver_task(task_id: str, artifacts: list[str] | None = Query(None),
                     notes: str = Query("")):
        try:
            if artifacts:
                artifacts_list = artifacts
            else:
                artifacts_list = None
            result = store.deliver_task(task_id, artifacts_list, notes)
            return _ok(result)
        except KeyError:
            raise HTTPException(404, "Task 不存在")

    @router.post("/tasks/{task_id}/verify")
    def verify_task(task_id: str):
        try:
            result = store.verify_task_delivery(task_id)
            return _ok(result)
        except KeyError:
            raise HTTPException(404, "Task 不存在")

    @router.post("/tasks/{task_id}/git-start")
    def start_git_tracking(task_id: str):
        sha = store.start_task_git_tracking(task_id)
        if sha is None:
            raise HTTPException(404, "Task 不存在")
        return _ok({"commit_sha": sha})

    @router.post("/tasks/{task_id}/git-capture")
    def capture_git_diff(task_id: str):
        diff = store.capture_task_git_diff(task_id)
        if diff is None:
            raise HTTPException(404, "Task 不存在")
        return _ok({"diff_length": len(diff), "diff_preview": diff[:500]})

    @router.post("/plans/{plan_id}/operator")
    def run_operator(plan_id: str, req: OperatorRequest):
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        life = store.get_life_resource("default")
        ctx = plan_operator_apply(plan, life, elapsed_hours=req.elapsed_hours, get_plan=store.get_plan)
        return _ok({
            "summary": ctx.summary,
            "fingerprint": ctx.fingerprint,
            "blocked_reason": ctx.blocked_reason,
            "progress_vector": ctx.progress_vector,
            "life_vector": ctx.life_vector,
            "risk_factors": ctx.risk_factors,
            "critical_path": ctx.critical_path,
            "execution_order": ctx.execution_order,
        })

    # ─── 拓扑 & 违规端点 ───

    @router.get("/plans/{plan_id}/topology")
    def get_topology(plan_id: str):
        """Plan 树拓扑 + 偏序 DAG 数据"""
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        tree_plans = flatten_tree(plan_id, store.get_plan)
        tree_ids = [p.id for p in tree_plans]
        cycle = detect_cycle(tree_ids, store.get_plan)
        try:
            topo_order = topological_sort(tree_ids, store.get_plan)
        except ValueError:
            topo_order = []
        critical_path = find_critical_path(tree_ids, store.get_plan)
        _aggregate_tree_state(plan, store.get_plan)

        return _ok({
            "tree": [
                {
                    "id": p.id,
                    "title": p.title,
                    "parent_plan_id": p.parent_plan_id,
                    "children_ids": p.children_ids,
                    "predecessors": p.predecessors,
                    "successors": p.successors,
                    "status": p.status,
                    "aggregated_progress": p.aggregated_progress,
                    "aggregated_status": p.aggregated_status,
                    "compliance_status": p.compliance_status,
                }
                for p in tree_plans
            ],
            "topological_order": topo_order,
            "critical_path": critical_path,
            "has_cycle": cycle is not None,
            "cycle_path": cycle or [],
        })

    @router.get("/plans/{plan_id}/violations")
    def get_violations(plan_id: str):
        """检查 Plan 违规状态"""
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        violations = check_violations(plan, store.get_plan)
        return _ok({
            "violations": [
                {"type": v.violation_type, "message": v.message, "plan_id": v.plan_id}
                for v in violations
            ],
            "compliance_status": plan.compliance_status,
        })

    @router.post("/plans/{plan_id}/predecessors")
    def add_predecessor(plan_id: str, req: LinkRequest):
        """添加偏序前驱 Plan"""
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        pred = store.get_plan(req.related_plan_id)
        if pred is None:
            raise HTTPException(404, "前驱 Plan 不存在")
        if req.related_plan_id not in plan.predecessors:
            plan.predecessors.append(req.related_plan_id)
        if plan_id not in pred.successors:
            pred.successors.append(plan_id)
        store.update_plan(plan)
        store.update_plan(pred)
        return _ok({"predecessors": plan.predecessors, "successors": pred.successors})

    @router.post("/plans/{plan_id}/successors")
    def add_successor(plan_id: str, req: LinkRequest):
        """添加偏序后继 Plan"""
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        succ = store.get_plan(req.related_plan_id)
        if succ is None:
            raise HTTPException(404, "后继 Plan 不存在")
        if req.related_plan_id not in plan.successors:
            plan.successors.append(req.related_plan_id)
        if plan_id not in succ.predecessors:
            succ.predecessors.append(plan_id)
        store.update_plan(plan)
        store.update_plan(succ)
        return _ok({"successors": plan.successors, "predecessors": succ.predecessors})

    # ─── Life 端点 ───

    @router.get("/life")
    def get_life(user_id: str = Query("default")):
        life = store.get_life_resource(user_id)
        return _ok(_to_dict(life))

    @router.get("/life/attention")
    def get_attention(user_id: str = Query("default")):
        life = store.get_life_resource(user_id)
        cap = life.attention_capital
        return _ok({
            "balance": cap.balance,
            "is_depleted": cap.is_depleted(),
            "is_overdrawn": cap.is_overdrawn(),
            "overdraft_count": cap.overdraft_count,
        })

    @router.post("/life/attention/recover")
    def recover_attention(req: RecoverRequest):
        life = store.get_life_resource(req.user_id)
        life.attention_capital.recover(req.hours, req.quality)
        return _ok({
            "balance": life.attention_capital.balance,
            "is_depleted": life.attention_capital.is_depleted(),
        })

    # ─── 机会成本端点 ───

    @router.post("/life/opportunity-cost")
    def assess_cost(req: OpportunityCostRequest):
        chosen = store.get_task(req.chosen_task_id)
        if chosen is None:
            raise HTTPException(404, "chosen_task 不存在")
        alternatives = []
        for tid in req.alternative_task_ids:
            t = store.get_task(tid)
            if t is not None:
                alternatives.append(t)
        assessment = assess_opportunity_cost(chosen, alternatives)
        return _ok({
            "level": assessment.level,
            "description": assessment.description,
            "exact_costs": assessment.exact_costs,
            "components": [
                {
                    "task_title": c["task"].title,
                    "level": c["level"],
                    "is_one_time": c["is_one_time"],
                    "weight_value": c["weight_value"],
                }
                for c in assessment.components
            ],
        })

    # ─── 优化器端点 ───

    @router.get("/optimizer/imbalance")
    def check_imbalance():
        """权重失衡检测（§2.4.4 理想偏航警告）"""
        active = [p for p in store.list_plans() if p.status == "active"]
        life = store.get_life_resource("default")
        alloc = allocate_life_resources(active, life)
        # 将 allocation 转成 {plan_id: ratio} 格式
        actual = {}
        for pid, info in alloc.items():
            total = info["waking_hours"] + info["attention_budget"]
            total_score = sum(v["priority_score"] for v in alloc.values()) or 1
            actual[pid] = (info["priority_score"]) / total_score if total_score else 0
        warning = check_weight_imbalance(active, actual)
        if warning:
            return _ok({
                "level": warning.level,
                "message": warning.message,
                "recommended_action": warning.recommended_action,
            })
        return _ok(None)

    # ─── Agent 集成端点（§7/§11.1）───

    @router.post("/plans/{plan_id}/decisions")
    def generate_decisions(plan_id: str, req: DecisionGenerateRequest):
        """生成 DecisionPoint（I(P) 闸门 + 机会成本 + 防沉迷）

        返回 null 表示 agent_retired 或 burned_out。
        """
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        life = store.get_life_resource("default")
        proficiency = store.get_proficiency(plan_id)
        recent_logs = store.list_agent_logs(plan_id)
        alternatives = [store.get_task(tid) for tid in req.alternatives
                        if store.get_task(tid) is not None]
        dp = generate_decision_point(plan, life, proficiency, recent_logs,
                                      alternatives, generator=_llm_generator)
        if dp is None:
            return _ok(None)  # agent_retired / burned_out
        store.add_decision_point(dp)
        return _ok(_to_dict(dp))

    @router.post("/decisions/{dp_id}/select")
    def select_decision(dp_id: str, req: DecisionSelectRequest):
        """用户选择选项 → 执行 action + 更新 proficiency"""
        dp = store.get_decision_point(dp_id)
        if dp is None:
            raise HTTPException(404, "DecisionPoint 不存在")
        opt = next((o for o in dp.options if o.id == req.option_id), None)
        action_result = {}
        if opt and opt.action_payload:
            payload = opt.action_payload if isinstance(opt.action_payload, dict) else {}
            action = payload.get("action", "")
            plan = store.get_plan(dp.plan_id)
            life = store.get_life_resource("default")
            if action == "create_tasks" and plan:
                titles = payload.get("titles", [])
                created = []
                for t in titles:
                    task = Task(
                        title=t, description="",
                        plan_id=plan.id, goal_id=plan.goal_id,
                        cognitive_layer=plan.cognitive_focus,
                        estimated_hours=payload.get("hours_per_task", 1.0),
                    )
                    store.add_task(task)
                    plan.tasks.append(task)
                    created.append(_to_dict(task))
                action_result["created_tasks"] = len(created)
            elif action == "rest" and life:
                hours = payload.get("minutes", 15) / 60.0
                consumed = life.attention_capital.recover(hours, 1.0)
                life.energy_level = min(1.0, life.energy_level + hours * 0.1)
                action_result["rest_hours"] = hours
            elif action == "switch_task" and plan:
                task_id = opt.action_payload.get("task_id", "")
                task = store.get_task(task_id)
                if task:
                    task.status = "doing"
                    store.update_task(task)
                    action_result["switched_to_task"] = task.title
            elif action == "continue_plan" and plan:
                plan.aggregated_progress = min(1.0, (plan.aggregated_progress or 0) + 0.05)
                store.update_plan(plan)
                action_result["progress_boost"] = 0.05
        dp.resolve(req.option_id)
        log = AgentContributionLog(
            plan_id=dp.plan_id, user_id="default",
            suggestion_type="advice",
            was_adopted=req.was_adopted,
            user_modification_ratio=req.user_modification_ratio,
            attention_consumed=0.1,
            cognitive_layer_target=None,
            intensity_at_creation=dp.agent_intensity,
        )
        store.add_agent_log(log)
        proficiency_new = store.get_proficiency(dp.plan_id)
        return _ok({"resolved": True, "proficiency_new": proficiency_new, "action": action_result})

    @router.post("/agent/log")
    def log_agent_contribution(req: AgentLogRequest):
        """记录 Agent 贡献日志（衰减依据，仅建议职能）"""
        layer = _layer(req.cognitive_layer_target) if req.cognitive_layer_target else None
        log = AgentContributionLog(
            plan_id=req.plan_id, user_id=req.user_id,
            suggestion_type=req.suggestion_type,
            was_adopted=req.was_adopted,
            user_modification_ratio=req.user_modification_ratio,
            attention_consumed=req.attention_consumed,
            cognitive_layer_target=layer,
            intensity_at_creation=req.intensity_at_creation,
        )
        store.add_agent_log(log)
        try:
            from mcp.event_logger import EventLogger
            el = EventLogger.get_instance()
            if el:
                el.log_tool_call(
                    tool_name="saber_agent_contribution",
                    tool_args={"plan_id": req.plan_id, "suggestion_type": req.suggestion_type},
                    tool_result=f"was_adopted={req.was_adopted}, modification_ratio={req.user_modification_ratio}",
                    context_info=f"saber:agent:{req.plan_id}",
                )
        except Exception:
            pass
        return _ok({"logged": True})

    @router.get("/agent/intensity")
    def get_intensity(plan_id: str = Query(...)):
        """查询当前 I(P) 与退役状态"""
        proficiency = store.get_proficiency(plan_id)
        intensity = compute_intensity(proficiency)
        retired = intensity < INTENSITY_RETIREMENT_THRESHOLD
        return _ok({
            "proficiency": proficiency,
            "intensity": intensity,
            "retired": retired,
        })

    @router.post("/agent/chat")
    def agent_chat(req: ChatRequest):
        """Agent 自由对话——不受决策框限制，可深入讨论任何内容"""
        plan = store.get_plan(req.plan_id)
        if plan is None:
            raise HTTPException(404, "Plan 不存在")
        life = store.get_life_resource(req.user_id)
        proficiency = store.get_proficiency(req.plan_id)
        intensity = compute_intensity(proficiency)

        # 收集上下文
        tasks = store.list_tasks(req.plan_id)
        done = sum(1 for t in tasks if t.status == "done")
        total = len(tasks)
        task_context = f"任务完成 {done}/{total}" if total else "尚无任务"
        tracked = [t for t in tasks if t.git_diff_summary]
        diff_context = f"已完成交付 {len(tracked)} 个任务" if tracked else ""

        system_prompt = f"""你是 SaberSystem 的 Agent（天使/导师），当前介入度 {intensity:.1%}。
Plan: {plan.title}
认知层级: {plan.cognitive_focus.value}
进度: {plan.aggregated_progress:.0%}
{task_context}
{diff_context}

你可以自由回答用户关于此 Plan 的任何问题——任务拆解、思路探讨、技术方案、时间安排。
你用中文回答，简洁但深入。"""

        try:
            from mcp.llm import get_model_provider
            provider = get_model_provider()
            if provider:
                resp = provider.chat(messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": req.message},
                ])
                reply = resp.content.strip()
            else:
                reply = f"LLM 未配置，无法自由对话。当前 Plan 进度 {plan.aggregated_progress:.0%}，建议继续推进。"
        except Exception as e:
            reply = f"对话服务暂不可用: {e}"

        return _ok({"reply": reply, "intensity": intensity})

    return router


def create_saber_app(store: SaberStore | None = None) -> FastAPI:
    """创建 SaberSystem FastAPI 子应用（用于独立测试）"""
    app = FastAPI(title="SaberSystem")
    app.include_router(create_saber_router(store))
    return app
