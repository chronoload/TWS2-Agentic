"""组织态势 API：three-arena 前端数据源 + HITL 决策入口（spec v16 P4）

沙盘世界单例（OrganizationWorld）：中央 → 支部 → 成员 组织态势。
端点：
- GET  /api/organization/status  → 组织态势快照（groups/members/meetings/patrol）
- POST /api/organization/meeting → 召集会议（HITL 用户处理上达决策点）
"""
from __future__ import annotations
from typing import Dict, Optional

from fastapi import APIRouter

from mcp.developmental.events import SessionStore
from mcp.developmental.agent_registry import AgentFactory
from mcp.developmental.organization import PartyGroup, PartyMember
from mcp.developmental.governance import PatrolTeam

router = APIRouter(prefix="/api/organization", tags=["organization"])

_world: Optional[dict] = None


def get_world() -> dict:
    """沙盘世界单例（首次构建组织态势，全局一致）"""
    global _world
    if _world is None:
        _world = _build_world()
    return _world


def _build_world() -> dict:
    """构建沙盘世界：中央 → 第一支部（3 成员）+ 巡回检查组"""
    store = SessionStore()
    central = PartyGroup("central", "中央")
    branch = PartyGroup("b1", "第一支部", parent=central)
    factory = AgentFactory(store=store, decision_fn=lambda p: "act:reply")
    for i in range(3):
        m = PartyMember(f"m{i}", factory.create(f"m{i}"), role="普通党员")
        branch.add_member(m)
    patrol = PatrolTeam(origin="central", targets=["b1"])
    return {"store": store, "central": central, "branch": branch,
            "factory": factory, "patrol": patrol}


@router.get("/status")
def status() -> dict:
    """组织态势快照（three-arena 视图数据源）"""
    w = get_world()
    central, branch = w["central"], w["branch"]
    return {
        "groups": [
            {"id": central.group_id, "name": central.name,
             "children": [c.group_id for c in central.children()]},
            {"id": branch.group_id, "name": branch.name, "children": []},
        ],
        "members": [{"id": m.member_id, "role": m.role,
                     "group": branch.group_id} for m in branch.members],
        "meetings": [],
        "patrol": {"origin": w["patrol"].origin, "targets": w["patrol"].targets},
    }


@router.post("/meeting")
def convene(agenda: str = "讨论任务") -> dict:
    """召集会议（HITL：用户处理上达决策点）"""
    w = get_world()
    mtg = w["branch"].convene_meeting(agenda)
    return {"meeting_id": str(id(mtg)), "agenda": agenda,
            "group": w["branch"].group_id}
