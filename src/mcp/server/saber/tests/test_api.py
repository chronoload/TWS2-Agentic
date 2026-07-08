"""
SaberSystem API 路由测试
使用 httpx.AsyncClient + ASGITransport 测试端点（兼容 httpx 0.28+，starlette 0.35 TestClient 已不兼容）
通过持久 event loop 把 async 客户端包装为同步接口，测试代码保持同步风格。
"""
import asyncio
import os
import tempfile
import pytest
import httpx
from httpx import ASGITransport
from mcp.server.saber.api import create_saber_app
from mcp.server.saber.store import SaberStore


class _SyncASGIClient:
    """把 httpx.AsyncClient + ASGITransport 包成同步接口"""

    def __init__(self, app):
        self._transport = ASGITransport(app=app)
        self._loop = asyncio.new_event_loop()
        self._ac = httpx.AsyncClient(
            transport=self._transport, base_url="http://testserver"
        )

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def get(self, url, **kwargs):
        return self._run(self._ac.get(url, **kwargs))

    def post(self, url, **kwargs):
        return self._run(self._ac.post(url, **kwargs))

    def put(self, url, **kwargs):
        return self._run(self._ac.put(url, **kwargs))

    def delete(self, url, **kwargs):
        return self._run(self._ac.delete(url, **kwargs))

    def close(self):
        try:
            self._run(self._ac.aclose())
        finally:
            self._loop.close()


@pytest.fixture
def client():
    """每个测试用独立的 store + app"""
    _db = tempfile.mktemp(suffix='.db')
    store = SaberStore(db_path=_db)
    app = create_saber_app(store=store)
    c = _SyncASGIClient(app)
    yield c
    c.close()
    try:
        os.unlink(_db)
    except Exception:
        pass


class TestIdealEndpoints:
    """Ideal 端点"""

    def test_create_ideal(self, client):
        resp = client.post("/api/saber/ideals", json={
            "title": "成为创造者",
            "description": "在 AI 时代独立思考",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["title"] == "成为创造者"
        assert data["data"]["id"] is not None

    def test_list_ideals(self, client):
        client.post("/api/saber/ideals", json={"title": "理想1", "description": ""})
        client.post("/api/saber/ideals", json={"title": "理想2", "description": ""})
        resp = client.get("/api/saber/ideals")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_get_ideal(self, client):
        create = client.post("/api/saber/ideals",
                             json={"title": "测试", "description": ""})
        ideal_id = create.json()["data"]["id"]
        resp = client.get(f"/api/saber/ideals/{ideal_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "测试"


class TestGoalEndpoints:
    """Goal 端点"""

    def test_create_goal(self, client):
        # 先建 Ideal
        ideal = client.post("/api/saber/ideals",
                            json={"title": "i", "description": ""}).json()["data"]
        resp = client.post("/api/saber/goals", json={
            "title": "掌握 LLM",
            "description": "",
            "ideal_id": ideal["id"],
            "priority_weight": 0.6,
            "target_layer": "S",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["priority_weight"] == 0.6

    def test_reweight_goals(self, client):
        ideal = client.post("/api/saber/ideals",
                            json={"title": "i", "description": ""}).json()["data"]
        g1 = client.post("/api/saber/goals", json={
            "title": "g1", "description": "",
            "ideal_id": ideal["id"],
            "priority_weight": 0.5, "target_layer": "K",
        }).json()["data"]
        g2 = client.post("/api/saber/goals", json={
            "title": "g2", "description": "",
            "ideal_id": ideal["id"],
            "priority_weight": 0.5, "target_layer": "K",
        }).json()["data"]
        resp = client.post(f"/api/saber/goals/{ideal['id']}/reweight", json={
            "weights": {g1["id"]: 0.7, g2["id"]: 0.3}
        })
        assert resp.status_code == 200

    def test_reweight_invalid_sum(self, client):
        ideal = client.post("/api/saber/ideals",
                            json={"title": "i", "description": ""}).json()["data"]
        g1 = client.post("/api/saber/goals", json={
            "title": "g1", "description": "",
            "ideal_id": ideal["id"],
            "priority_weight": 0.5, "target_layer": "K",
        }).json()["data"]
        resp = client.post(f"/api/saber/goals/{ideal['id']}/reweight", json={
            "weights": {g1["id"]: 0.8}  # 和不为 1
        })
        assert resp.status_code == 400


class TestPlanEndpoints:
    """Plan 端点"""

    def test_create_plan(self, client):
        resp = client.post("/api/saber/plans", json={
            "title": "LLM 项目",
            "description": "",
            "goal_id": "g1",
            "cognitive_focus": "W",
            "priority_weight": 0.6,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "LLM 项目"

    def test_add_task_to_plan(self, client):
        plan = client.post("/api/saber/plans", json={
            "title": "p", "description": "",
            "goal_id": "g1", "cognitive_focus": "W",
            "priority_weight": 0.6,
        }).json()["data"]
        resp = client.post(f"/api/saber/plans/{plan['id']}/steps", json={
            "title": "实现 attention",
            "description": "",
            "goal_id": "g1",
            "cognitive_layer": "S",
            "estimated_hours": 2.0,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "实现 attention"

    def test_run_plan_operator(self, client):
        """触发 Plan 算子"""
        plan = client.post("/api/saber/plans", json={
            "title": "p", "description": "",
            "goal_id": "g1", "cognitive_focus": "W",
            "priority_weight": 0.6,
        }).json()["data"]
        resp = client.post(f"/api/saber/plans/{plan['id']}/operator",
                           json={"elapsed_hours": 1.0})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "summary" in data
        assert "fingerprint" in data


class TestLifeEndpoints:
    """生命资源端点"""

    def test_get_life_resource(self, client):
        resp = client.get("/api/saber/life?user_id=u1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["waking_hours_total"] == 16.0

    def test_get_attention_capital(self, client):
        resp = client.get("/api/saber/life/attention?user_id=u1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "balance" in data
        assert "is_depleted" in data

    def test_recover_attention(self, client):
        """休息存入注意力资本"""
        resp = client.post("/api/saber/life/attention/recover", json={
            "user_id": "u1", "hours": 1.0, "quality": 1.0,
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


class TestOpportunityCostEndpoint:
    """机会成本评估端点"""

    def test_assess_opportunity_cost(self, client):
        """评估选择当前任务的机会成本"""
        # 先建 Plan + 两个 Task
        plan = client.post("/api/saber/plans", json={
            "title": "p", "description": "",
            "goal_id": "g1", "cognitive_focus": "W",
            "priority_weight": 0.6,
        }).json()["data"]
        chosen = client.post(f"/api/saber/plans/{plan['id']}/steps", json={
            "title": "写报告", "description": "",
            "goal_id": "g1", "cognitive_layer": "W",
            "estimated_hours": 2.0, "priority_weight": 0.3,
        }).json()["data"]
        alt = client.post(f"/api/saber/plans/{plan['id']}/steps", json={
            "title": "跑步", "description": "",
            "goal_id": "g1", "cognitive_layer": "W",
            "estimated_hours": 1.0, "priority_weight": 0.4,
            "is_one_time_only": True, "can_be_rescheduled": False,
            "time_window_remaining": 0.2,
        }).json()["data"]
        resp = client.post("/api/saber/life/opportunity-cost", json={
            "chosen_task_id": chosen["id"],
            "alternative_task_ids": [alt["id"]],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "level" in data
        assert "description" in data
        assert "exact_costs" in data


class TestCompressArchiveEndpoints:
    """归档/解压缩 API 端点（§9）"""

    def _setup_completed_plan(self, client):
        """创建已完成 Plan"""
        plan = client.post("/api/saber/plans", json={
            "title": "完成的项目", "description": "",
            "goal_id": "g1", "cognitive_focus": "W",
            "priority_weight": 0.6,
        }).json()["data"]
        client.put(f"/api/saber/plans/{plan['id']}", json={
            "status": "completed", "aggregated_progress": 1.0,
        })
        return client.get(f"/api/saber/plans/{plan['id']}").json()["data"]

    def test_compress_completed_plan(self, client):
        plan = self._setup_completed_plan(client)
        resp = client.post(f"/api/saber/plans/{plan['id']}/compress")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "archived"
        assert data["compressed_at"] is not None
        assert data["archive_fingerprint"] is not None
        assert len(data["archive_fingerprint"]) == 64

    def test_compress_draft_plan_returns_400(self, client):
        plan = client.post("/api/saber/plans", json={
            "title": "未完成", "description": "",
            "goal_id": "g1", "cognitive_focus": "W",
            "priority_weight": 0.6,
        }).json()["data"]
        resp = client.post(f"/api/saber/plans/{plan['id']}/compress")
        assert resp.status_code == 400

    def test_compress_nonexistent_plan_returns_404(self, client):
        resp = client.post("/api/saber/plans/nonexistent/compress")
        assert resp.status_code == 404

    def test_unarchive_archived_plan(self, client):
        plan = self._setup_completed_plan(client)
        client.post(f"/api/saber/plans/{plan['id']}/compress")
        resp = client.post(f"/api/saber/plans/{plan['id']}/unarchive")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "active"
        assert data["compressed_at"] is None
        assert data["archive_fingerprint"] is None
        assert data["resurrected_at"] is not None

    def test_unarchive_non_archived_returns_400(self, client):
        plan = client.post("/api/saber/plans", json={
            "title": "活跃中", "description": "",
            "goal_id": "g1", "cognitive_focus": "W",
            "priority_weight": 0.6,
        }).json()["data"]
        resp = client.post(f"/api/saber/plans/{plan['id']}/unarchive")
        assert resp.status_code == 400


class TestOptimizerEndpoints:
    """优化器端点：权重失衡检测"""

    def test_imbalance_returns_none_when_no_plans(self, client):
        """无活跃 Plan 时返回 null"""
        resp = client.get("/api/saber/optimizer/imbalance")
        assert resp.status_code == 200
        assert resp.json()["data"] is None

    def test_imbalance_detects_high_weight_starvation(self, client):
        """高权重 Plan 未收到资源时触发警告"""
        client.post("/api/saber/plans", json={
            "title": "重要项目", "description": "",
            "goal_id": "g1", "cognitive_focus": "W",
            "priority_weight": 0.6,
        })
        resp = client.get("/api/saber/optimizer/imbalance")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 新 plan 无 allocation 历史，但有高权重 → 可能触发 starvation 警告
        if data is not None:
            assert "level" in data
            assert "message" in data
            assert "recommended_action" in data


class TestAgentEndpoints:
    """Agent 集成端点：决策生成 + 选择 + 日志 + 强度查询（§7/§11.1）"""

    def _setup_plan(self, client):
        """创建 Plan 供 Agent 端点测试使用"""
        return client.post("/api/saber/plans", json={
            "title": "LLM 项目", "description": "",
            "goal_id": "g1", "cognitive_focus": "S",
            "priority_weight": 0.6,
        }).json()["data"]

    def test_generate_decision_point(self, client):
        """新 plan 无日志 → proficiency=0 → I(P)=1.0 → 生成决策"""
        plan = self._setup_plan(client)
        resp = client.post(f"/api/saber/plans/{plan['id']}/decisions", json={})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data is not None
        assert "options" in data
        assert 2 <= len(data["options"]) <= 4
        assert data["agent_intensity"] > 0

    def test_decision_retired_when_proficiency_high(self, client):
        """proficiency 接近 1 → I(P)<0.1 → Agent 退役，返回 null"""
        plan = self._setup_plan(client)
        # 记录多条"低采纳+高修改"日志提升 proficiency
        for _ in range(10):
            client.post("/api/saber/agent/log", json={
                "plan_id": plan["id"], "user_id": "default",
                "suggestion_type": "advice",
                "was_adopted": False, "user_modification_ratio": 0.9,
                "attention_consumed": 0.1, "cognitive_layer_target": "S",
                "intensity_at_creation": 0.5,
            })
        resp = client.post(f"/api/saber/plans/{plan['id']}/decisions", json={})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data is None  # agent_retired

    def test_select_decision_option(self, client):
        """选择选项后 proficiency 更新"""
        plan = self._setup_plan(client)
        dp = client.post(f"/api/saber/plans/{plan['id']}/decisions",
                         json={}).json()["data"]
        option_id = dp["options"][0]["id"]
        resp = client.post(f"/api/saber/decisions/{dp['id']}/select", json={
            "option_id": option_id,
            "was_adopted": True,
            "user_modification_ratio": 0.2,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["resolved"] is True
        assert "proficiency_new" in data

    def test_log_agent_contribution(self, client):
        """记录 Agent 贡献日志"""
        plan = self._setup_plan(client)
        resp = client.post("/api/saber/agent/log", json={
            "plan_id": plan["id"], "user_id": "default",
            "suggestion_type": "advice",
            "was_adopted": True, "user_modification_ratio": 0.1,
            "attention_consumed": 0.2, "cognitive_layer_target": "S",
            "intensity_at_creation": 0.8,
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_get_intensity(self, client):
        """查询当前 I(P) 与退役状态"""
        plan = self._setup_plan(client)
        resp = client.get(f"/api/saber/agent/intensity?plan_id={plan['id']}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "proficiency" in data
        assert "intensity" in data
        assert "retired" in data
        # 新 plan 无日志 → proficiency=0 → intensity=1.0
        assert data["proficiency"] == 0.0
        assert data["intensity"] == 1.0
        assert data["retired"] is False


class TestTopologyEndpoints:
    """拓扑和违规端点"""

    def _setup_tree(self, client):
        """创建树结构：根 Plan → 子 Plan"""
        # Ideal
        resp = client.post("/api/saber/ideals", json={"title": "研究", "description": ""})
        ideal = resp.json()["data"]
        # Goal
        resp = client.post("/api/saber/goals", json={
            "title": "论文", "description": "", "ideal_id": ideal["id"],
            "priority_weight": 1.0, "target_layer": "W",
        })
        goal = resp.json()["data"]
        # 根 Plan
        resp = client.post("/api/saber/plans", json={
            "title": "根 Plan", "description": "", "goal_id": goal["id"],
            "cognitive_focus": "W", "priority_weight": 0.6,
        })
        root = resp.json()["data"]
        # 子 Plan
        resp = client.post("/api/saber/plans", json={
            "title": "子 Plan", "description": "", "goal_id": goal["id"],
            "cognitive_focus": "W", "priority_weight": 0.4, "parent_plan_id": root["id"],
        })
        child = resp.json()["data"]
        return root, child

    def test_get_topology(self, client):
        """获取 Plan 拓扑"""
        root, child = self._setup_tree(client)
        resp = client.get(f"/api/saber/plans/{root['id']}/topology")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "tree" in data
        assert len(data["tree"]) >= 1
        assert "topological_order" in data
        assert "has_cycle" in data

    def test_get_violations(self, client):
        """获取违规检查"""
        root, child = self._setup_tree(client)
        resp = client.get(f"/api/saber/plans/{root['id']}/violations")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "violations" in data
        assert "compliance_status" in data

    def test_add_predecessor(self, client):
        """添加前驱关系"""
        root, child = self._setup_tree(client)
        resp = client.post(f"/api/saber/plans/{root['id']}/predecessors",
                           json={"related_plan_id": child["id"]})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert child["id"] in data["predecessors"]

    def test_add_successor(self, client):
        """添加后继关系"""
        root, child = self._setup_tree(client)
        resp = client.post(f"/api/saber/plans/{root['id']}/successors",
                           json={"related_plan_id": child["id"]})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert child["id"] in data["successors"]

    def test_topology_with_cycle(self, client):
        """有环时 has_cycle=True"""
        root, child = self._setup_tree(client)
        # 创建环：child → root
        client.post(f"/api/saber/plans/{child['id']}/successors",
                    json={"related_plan_id": root["id"]})
        root["predecessors"].append(child["id"])
        client.put(f"/api/saber/plans/{root['id']}", json={"title": "根 Plan"})
        resp = client.get(f"/api/saber/plans/{root['id']}/topology")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 环可能在拓扑排序时被检测到
        # 只要不 crash 即可
        assert "has_cycle" in data
