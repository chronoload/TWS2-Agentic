"""数据枢纽 Hub API 测试 — RSS 管理"""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest

_ws = str(Path(__file__).resolve().parent.parent.parent)
if _ws not in sys.path:
    sys.path.insert(0, _ws)

from ws2_data_hub import init_data_hub, RSSSubscription


class _SyncAppClient:
    """starlette 0.35 TestClient 与 httpx 0.28 不兼容，用 ASGITransport 轻量替代"""

    def __init__(self, app):
        self._app = app
        self._base = "http://testserver"

    def _call(self, method: str, url: str, json=None):
        async def _run():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(transport=transport, base_url=self._base) as c:
                if method == "post":
                    return await c.post(url, json=json)
                return await c.get(url)

        return asyncio.run(_run())

    def post(self, url, json=None):
        return self._call("post", url, json)

    def get(self, url):
        return self._call("get", url)


@pytest.fixture()
def hub_env(tmp_path, monkeypatch):
    """隔离 DataHub 实例：临时目录 + 全局单例重置"""
    from ws2_data_hub import _g_data_hub
    monkeypatch.setattr(sys.modules["ws2_data_hub"], "_g_data_hub", None)
    hub = init_data_hub(tmp_path)
    # RSS 源指向本地文件（避免真实网络）
    feed_file = tmp_path / "feed.xml"
    feed_file.write_text(
        '<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>'
        "<item><title>Entry 1</title><link>http://example.com/1</link>"
        "<description>desc one</description></item></channel></rss>",
        encoding="utf-8",
    )
    hub.add_rss_subscription(RSSSubscription(url=feed_file.as_uri(), title="Test Feed"))
    return hub, tmp_path


def _make_app(hub_env):
    from mcp.server.app import create_app
    hub, tmp = hub_env
    app = create_app(workspace_dir=str(tmp), port=6999)
    # 覆盖 hub 实例指向测试隔离实例
    app.state._hub = hub
    app.state._hub_ready = True
    return _SyncAppClient(app)


def test_rss_list(hub_env):
    c = _make_app(hub_env)
    r = c.post("/api/hub/rss/list")
    assert r.status_code == 200
    d = r.json()
    assert d["code"] == 0
    assert len(d["data"]["subscriptions"]) == 1
    assert d["data"]["subscriptions"][0]["title"] == "Test Feed"


def test_rss_add_remove(hub_env):
    c = _make_app(hub_env)
    r = c.post("/api/hub/rss/add", json={
        "url": "http://example.com/feed2.xml", "title": "Feed2", "category": "物理",
    })
    assert r.json()["code"] == 0
    sub_id = r.json()["data"]["id"]
    r = c.post("/api/hub/rss/list")
    assert len(r.json()["data"]["subscriptions"]) == 2
    r = c.post("/api/hub/rss/remove", json={"sub_id": sub_id})
    assert r.json()["code"] == 0
    r = c.post("/api/hub/rss/list")
    assert len(r.json()["data"]["subscriptions"]) == 1


def test_rss_poll(hub_env):
    c = _make_app(hub_env)
    r = c.post("/api/hub/rss/poll", json={"sub_id": ""})
    assert r.json()["code"] == 0
    assert r.json()["data"]["total_new"] == 1
    # 第二次轮询应为 0（去重）
    r = c.post("/api/hub/rss/poll", json={"sub_id": ""})
    assert r.json()["data"]["total_new"] == 0


def test_hub_items_query(hub_env):
    c = _make_app(hub_env)
    # fixture 为函数级隔离，需先轮询产生条目
    c.post("/api/hub/rss/poll", json={"sub_id": ""})
    r = c.post("/api/hub/items", json={"source_type": "rss", "unread_only": True})
    assert r.json()["code"] == 0
    assert r.json()["data"]["count"] == 1
    r = c.post("/api/hub/items/update", json={"item_id": "x", "is_read": True})
    assert r.json()["code"] != 0  # 不存在的 item 报错


def test_hub_stats(hub_env):
    c = _make_app(hub_env)
    r = c.post("/api/hub/stats")
    assert r.json()["code"] == 0
    d = r.json()["data"]
    assert "total_items" in d and "rss_subscriptions" in d


def test_hub_discover(hub_env):
    c = _make_app(hub_env)
    r = c.post("/api/hub/discover", json={"url": "http://example.com/", "discover_feeds": False})
    assert r.status_code == 200
    assert r.json()["code"] == 0  # 网络失败时返回空 feeds 而非 500


def test_push_dashboard_has_rss(hub_env):
    c = _make_app(hub_env)
    # 先轮询产生未读条目
    c.post("/api/hub/rss/poll", json={"sub_id": ""})
    r = c.get("/api/push/dashboard")
    assert r.json()["code"] == 0
    d = r.json()["data"]
    assert "rss_new_entries" in d
    assert "rss_new_count" in d
    assert d["rss_new_count"] == 1
    assert d["rss_new_entries"][0]["title"] == "Entry 1"