"""
SaberSystem SQLite 持久化存储
"""
from __future__ import annotations
import json
import os
import sqlite3
import hashlib
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from mcp.server.saber.models import Ideal, Goal, Plan, Task, Constraint, DecisionPoint, DecisionOption, CognitiveLayer
from mcp.server.saber.life import (
    LifeResource, AttentionCapital, HealthStatus, Opportunity, Transaction,
    settle_surplus_on_archive,
)
from mcp.server.saber.agent import AgentContributionLog, update_proficiency


def _serialize(obj) -> str:
    """dataclass → JSON string"""
    def _conv(v):
        if hasattr(v, '__dataclass_fields__'):
            return {f: _conv(getattr(v, f)) for f in v.__dataclass_fields__}
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, Enum):
            return v.value
        if isinstance(v, list):
            return [_conv(i) for i in v]
        if isinstance(v, dict):
            return {k: _conv(i) for k, i in v.items()}
        return v
    from enum import Enum
    return json.dumps(_conv(obj), ensure_ascii=False, default=str)


def _deserialize_life(data: dict | str) -> LifeResource:
    """恢复 LifeResource（含嵌套 dataclass）"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = {}
    cap = AttentionCapital(**data.get('attention_capital', {}))
    health = HealthStatus(**data.get('health', {}))
    opps = [Opportunity(**o) for o in data.get('active_opportunities', [])]
    txns = [Transaction(**t) for t in data.get('transactions', [])]
    return LifeResource(
        user_id=data['user_id'],
        waking_hours_total=data.get('waking_hours_total', 16.0),
        waking_hours_used=data.get('waking_hours_used', 4.5),
        attention_capital=cap,
        energy_level=data.get('energy_level', 0.7),
        mood_index=data.get('mood_index', 0.65),
        health=health,
        active_opportunities=opps,
        missed_opportunities=data.get('missed_opportunities', 0),
        serendipity_buff=data.get('serendipity_buff', 0.3),
        free_time_surplus_total=data.get('free_time_surplus_total', 0.5),
        self_destructive_choices=data.get('self_destructive_choices', 0),
        trust_score=data.get('trust_score', 0.9),
        transactions=txns,
    )


def _deserialize_plan(data: dict) -> Plan:
    tasks = [Task(**t) for t in data.get('tasks', [])]
    cl = data.get('cognitive_focus', 'W')
    if isinstance(cl, str):
        cl = CognitiveLayer(cl)
    return Plan(
        title=data['title'], description=data.get('description', ''),
        goal_id=data['goal_id'], cognitive_focus=cl,
        priority_weight=data.get('priority_weight', 0.5),
        id=data.get('id', ''),
        parent_plan_id=data.get('parent_plan_id'),
        children_ids=data.get('children_ids', []),
        predecessors=data.get('predecessors', []),
        successors=data.get('successors', []),
        status=data.get('status', 'active'),
        aggregated_progress=data.get('aggregated_progress', 0.0),
        aggregated_status=data.get('aggregated_status', 'active'),
        compliance_status=data.get('compliance_status', 'on_track'),
        estimated_surplus_yield=data.get('estimated_surplus_yield'),
        tasks=tasks,
        start_date=_parse_dt(data.get('start_date')),
        end_date=_parse_dt(data.get('end_date')),
        compressed_at=_parse_dt(data.get('compressed_at')),
        archive_fingerprint=data.get('archive_fingerprint'),
        resurrected_at=_parse_dt(data.get('resurrected_at')),
    )


def _deserialize_dp(data: dict) -> DecisionPoint:
    opts = [DecisionOption(**o) for o in data.get('options', [])]
    return DecisionPoint(
        plan_id=data['plan_id'],
        context_snapshot=data.get('context_snapshot', ''),
        options=opts,
        agent_intensity=data.get('agent_intensity', 0.0),
        opportunity_cost_shown=data.get('opportunity_cost_shown', {}),
        id=data.get('id', ''),
        created_at=_parse_dt(data.get('created_at')),
        selected_option_id=data.get('selected_option_id') or data.get('resolved_option_id'),
        resolved_at=_parse_dt(data.get('resolved_at')),
    )


def _deserialize_log(data: dict) -> AgentContributionLog:
    from mcp.server.saber.models import CognitiveLayer
    cl = data.get('cognitive_layer_target')
    if cl and isinstance(cl, str):
        cl = CognitiveLayer(cl)
    return AgentContributionLog(
        plan_id=data['plan_id'], user_id=data.get('user_id', 'default'),
        suggestion_type=data.get('suggestion_type', 'advice'),
        was_adopted=data.get('was_adopted', False),
        user_modification_ratio=data.get('user_modification_ratio', 0.0),
        attention_consumed=data.get('attention_consumed', 0.0),
        cognitive_layer_target=cl,
        intensity_at_creation=data.get('intensity_at_creation', 0.0),
        id=data.get('id', ''),
        timestamp=_parse_dt(data.get('timestamp') or data.get('created_at')),
    )


def _parse_dt(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


# ─── SQLite ───

_DB_PATH = None

def _get_db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        home = Path.home() / '.ts2'
        home.mkdir(parents=True, exist_ok=True)
        _DB_PATH = str(home / 'saber.db')
    return _DB_PATH


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


_INIT_SQL = """
CREATE TABLE IF NOT EXISTS ideals (id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS goals (id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS life_resources (user_id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS agent_logs (id TEXT PRIMARY KEY, plan_id TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS decision_points (id TEXT PRIMARY KEY, data TEXT);
"""


class SaberStore:
    """SQLite 持久化存储"""

    def __init__(self, db_path: str | None = None):
        global _DB_PATH
        if db_path:
            _DB_PATH = db_path
        self._ideals: dict[str, Ideal] = {}
        self._goals: dict[str, Goal] = {}
        self._plans: dict[str, Plan] = {}
        self._tasks: dict[str, Task] = {}
        self._life_resources: dict[str, LifeResource] = {}
        self._agent_logs: dict[str, list[AgentContributionLog]] = {}
        self._decision_points: dict[str, DecisionPoint] = {}
        self._init_db()
        self._load_all()

    def _init_db(self):
        conn = _get_conn()
        conn.executescript(_INIT_SQL)
        conn.commit()
        conn.close()

    def _save(self, table: str, id_col: str, obj_id: str, data: dict):
        conn = _get_conn()
        conn.execute(f"INSERT OR REPLACE INTO {table} ({id_col}, data) VALUES (?, ?)",
                     (obj_id, _serialize(data)))
        conn.commit()
        conn.close()

    def _delete_row(self, table: str, id_col: str, obj_id: str):
        conn = _get_conn()
        conn.execute(f"DELETE FROM {table} WHERE {id_col}=?", (obj_id,))
        conn.commit()
        conn.close()

    def _load_table(self, table: str, id_col: str) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(f"SELECT {id_col}, data FROM {table}").fetchall()
        conn.close()
        result = []
        for r in rows:
            try:
                result.append(json.loads(r['data']))
            except (json.JSONDecodeError, KeyError):
                continue
        return result

    def _load_all(self):
        # LifeResource
        for d in self._load_table('life_resources', 'user_id'):
            lr = _deserialize_life(d)
            self._life_resources[lr.user_id] = lr
        # Ideals
        for d in self._load_table('ideals', 'id'):
            self._ideals[d['id']] = Ideal(**d)
        # Goals
        for d in self._load_table('goals', 'id'):
            if isinstance(d.get('target_layer'), str):
                d['target_layer'] = CognitiveLayer(d['target_layer'])
            self._goals[d['id']] = Goal(**d)
        # Plans
        for d in self._load_table('plans', 'id'):
            p = _deserialize_plan(d)
            self._plans[p.id] = p
        # Tasks
        for d in self._load_table('tasks', 'id'):
            self._tasks[d['id']] = Task(**d)
        # Agent logs
        self._agent_logs.clear()
        for d in self._load_table('agent_logs', 'id'):
            log = _deserialize_log(d)
            self._agent_logs.setdefault(log.plan_id, []).append(log)
        # Decision points
        for d in self._load_table('decision_points', 'id'):
            dp = _deserialize_dp(d)
            self._decision_points[dp.id] = dp

    # ─── Ideal ───

    def add_ideal(self, ideal: Ideal) -> None:
        self._ideals[ideal.id] = ideal
        self._save('ideals', 'id', ideal.id, asdict(ideal))

    def get_ideal(self, ideal_id: str) -> Ideal | None:
        return self._ideals.get(ideal_id)

    def list_ideals(self) -> list[Ideal]:
        return list(self._ideals.values())

    def update_ideal(self, ideal: Ideal) -> None:
        self._ideals[ideal.id] = ideal
        self._save('ideals', 'id', ideal.id, asdict(ideal))

    def delete_ideal(self, ideal_id: str) -> None:
        self._ideals.pop(ideal_id, None)
        self._delete_row('ideals', 'id', ideal_id)

    # ─── Goal ───

    def add_goal(self, goal: Goal) -> None:
        self._goals[goal.id] = goal
        self._save('goals', 'id', goal.id, asdict(goal))

    def update_goal(self, goal: Goal) -> None:
        self._goals[goal.id] = goal
        self._save('goals', 'id', goal.id, asdict(goal))

    def get_goal(self, goal_id: str) -> Goal | None:
        return self._goals.get(goal_id)

    def delete_goal(self, goal_id: str) -> None:
        self._goals.pop(goal_id, None)
        self._delete_row('goals', 'id', goal_id)

    def list_goals(self, ideal_id: str | None = None) -> list[Goal]:
        if ideal_id is None:
            return list(self._goals.values())
        return [g for g in self._goals.values() if g.ideal_id == ideal_id]

    def reweight_goals(self, ideal_id: str, weights: dict[str, float]) -> None:
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"权重和必须为 1，当前: {total}")
        for goal_id, weight in weights.items():
            goal = self._goals.get(goal_id)
            if goal is None:
                raise KeyError(f"Goal {goal_id} 不存在")
            goal.priority_weight = weight
            self._save('goals', 'id', goal_id, asdict(goal))

    # ─── Plan ───

    def add_plan(self, plan: Plan) -> None:
        self._plans[plan.id] = plan
        self._save('plans', 'id', plan.id, asdict(plan))

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def delete_plan(self, plan_id: str) -> None:
        self._plans.pop(plan_id, None)
        self._delete_row('plans', 'id', plan_id)

    def list_plans(self, goal_id: str | None = None) -> list[Plan]:
        if goal_id is None:
            return list(self._plans.values())
        return [p for p in self._plans.values() if p.goal_id == goal_id]

    def list_child_plans(self, parent_id: str) -> list[Plan]:
        return [p for p in self._plans.values() if p.parent_plan_id == parent_id]

    def update_plan(self, plan: Plan) -> None:
        self._plans[plan.id] = plan
        self._save('plans', 'id', plan.id, asdict(plan))

    def compress_plan(self, plan_id: str, life: LifeResource | None = None,
                      final_score: float | None = None) -> Plan:
        plan = self.get_plan(plan_id)
        if plan is None:
            raise KeyError(f"Plan {plan_id} 不存在")
        if plan.status == "archived":
            raise ValueError(f"Plan {plan_id} 已归档")
        if plan.status != "completed":
            raise ValueError(f"只允许归档已完成的 Plan，当前状态: {plan.status}")
        now = datetime.now()
        plan.status = "archived"
        plan.compressed_at = now
        raw = f"{plan.id}:{plan.end_date}:{now.isoformat()}"
        plan.archive_fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        self._plans[plan.id] = plan
        self._save('plans', 'id', plan.id, asdict(plan))

        # 归档结算：连接质量分与自由时间盈余
        if life is not None and final_score is not None:
            settle_surplus_on_archive(
                life=life,
                estimated_surplus=plan.estimated_surplus_yield or 1.0,
                final_score=final_score,
                plan_id=plan_id,
            )
            self.set_life_resource(life)

        return plan

    def unarchive_plan(self, plan_id: str) -> Plan:
        plan = self.get_plan(plan_id)
        if plan is None:
            raise KeyError(f"Plan {plan_id} 不存在")
        if plan.status != "archived":
            raise ValueError(f"只允许解压缩已归档的 Plan，当前状态: {plan.status}")
        plan.status = "active"
        plan.compressed_at = None
        plan.archive_fingerprint = None
        plan.resurrected_at = datetime.now()
        self._plans[plan.id] = plan
        self._save('plans', 'id', plan.id, asdict(plan))
        return plan

    # ─── Task ───

    def add_task(self, task: Task) -> None:
        self._tasks[task.id] = task
        self._save('tasks', 'id', task.id, asdict(task))

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self, plan_id: str | None = None) -> list[Task]:
        if plan_id is None:
            return list(self._tasks.values())
        return [t for t in self._tasks.values() if t.plan_id == plan_id]

    def update_task(self, task: Task) -> None:
        self._tasks[task.id] = task
        self._save('tasks', 'id', task.id, asdict(task))

    def delete_task(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._delete_row('tasks', 'id', task_id)

    # ─── 任务交付 ───

    def deliver_task(self, task_id: str, artifacts: list[str] | None = None,
                     notes: str = "") -> dict:
        """交付任务：检查 artifact + 标记完成 + 捕获 git 区间"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} 不存在")
        now = datetime.now()
        task.status = "done"
        task.delivered_at = now
        if artifacts is not None:
            task.delivery_artifacts = artifacts
        if notes:
            task.delivery_notes = notes
        if task.git_range_start and not task.git_range_end:
            task.git_range_end = now.isoformat()
        self.update_task(task)
        # 触发自动归档
        plan = None
        archived = False
        if task.plan_id:
            plan = self.get_plan(task.plan_id)
            if plan and plan.auto_archive:
                archived = self._try_auto_archive(plan)
        return {"task_id": task_id, "delivered_at": now.isoformat(),
                "plan_auto_archived": archived}

    def verify_task_delivery(self, task_id: str) -> dict:
        """核验交付质量"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} 不存在")
        checks = {"has_artifacts": len(task.delivery_artifacts) > 0,
                  "has_criteria": bool(task.completion_criteria),
                  "has_diff": bool(task.git_diff_summary),
                  "status_done": task.status == "done"}
        passed = all(checks.values())
        if passed:
            task.verified_at = datetime.now()
            self.update_task(task)
        return {"task_id": task_id, "passed": passed, "checks": checks}

    # ─── 自动归档 ───

    def _try_auto_archive(self, plan: Plan) -> bool:
        """检查是否所有任务已完成，是则自动归档"""
        tasks = self.list_tasks(plan.id)
        if not tasks:
            return False
        if not all(t.status == "done" for t in tasks):
            return False
        if plan.status == "archived" or plan.status == "completed":
            return False
        plan.status = "completed"
        plan.end_date = datetime.now()
        self._plans[plan.id] = plan
        self._save('plans', 'id', plan.id, asdict(plan))
        # compress
        try:
            self.compress_plan(plan.id)
        except (KeyError, ValueError):
            pass
        return True

    # ─── Git / 文件追踪 ───

    def start_task_git_tracking(self, task_id: str) -> str | None:
        """标记 git 追踪起点"""
        task = self.get_task(task_id)
        if task is None:
            return None
        try:
            import subprocess
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
                cwd=r"C:\Users\qu\Desktop",
            )
            if r.returncode == 0:
                sha = r.stdout.strip()
                task.git_range_start = sha
                self.update_task(task)
                return sha
        except Exception:
            pass
        task.git_range_start = datetime.now().isoformat()
        self.update_task(task)
        return task.git_range_start

    def capture_task_git_diff(self, task_id: str) -> str:
        """捕获 git diff 区间内容"""
        task = self.get_task(task_id)
        if task is None:
            return ""
        if not task.git_range_start:
            return ""
        try:
            import subprocess
            r = subprocess.run(
                ["git", "diff", task.git_range_start, "HEAD", "--"],
                capture_output=True, text=True, timeout=30,
                cwd=r"C:\Users\qu\Desktop",
            )
            if r.returncode == 0 and r.stdout:
                diff = r.stdout[:3000]
                task.git_diff_summary = diff
                self.update_task(task)
                return diff
        except Exception:
            pass
        return ""

    # ─── LifeResource ───

    def set_life_resource(self, life: LifeResource) -> None:
        self._life_resources[life.user_id] = life
        self._save('life_resources', 'user_id', life.user_id, asdict(life))

    def get_life_resource(self, user_id: str) -> LifeResource:
        if user_id not in self._life_resources:
            self._life_resources[user_id] = LifeResource(user_id=user_id)
            self._save('life_resources', 'user_id', user_id, asdict(self._life_resources[user_id]))
        return self._life_resources[user_id]

    # ─── Agent 贡献日志 + 熟练度 ───

    def add_agent_log(self, log: AgentContributionLog) -> None:
        self._agent_logs.setdefault(log.plan_id, []).append(log)
        self._save('agent_logs', 'id', log.id, asdict(log))

    def list_agent_logs(self, plan_id: str) -> list[AgentContributionLog]:
        return list(self._agent_logs.get(plan_id, []))

    def get_proficiency(self, plan_id: str) -> float:
        p = 0.0
        for log in self.list_agent_logs(plan_id):
            adoption = 1.0 if log.was_adopted else 0.0
            p = update_proficiency(p, adoption, log.user_modification_ratio)
        return p

    # ─── DecisionPoint ───

    def add_decision_point(self, dp: DecisionPoint) -> None:
        self._decision_points[dp.id] = dp
        self._save('decision_points', 'id', dp.id, asdict(dp))

    def get_decision_point(self, dp_id: str) -> DecisionPoint | None:
        return self._decision_points.get(dp_id)


# 全局单例
_store: SaberStore | None = None


def get_store() -> SaberStore:
    global _store
    if _store is None:
        _store = SaberStore()
    return _store
