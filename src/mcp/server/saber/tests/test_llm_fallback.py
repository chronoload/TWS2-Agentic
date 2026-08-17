"""
LLM provider 配置回退测试（TDD）
~/.ts2/agent_config/providers.json 优先，回退 $TS2_WORKSPACE/agent_config/providers.json。
缓存仅在成功时生效，失败不缓存。
"""
import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def env_setup(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="ts2_llm_test_"))
    home = tmp / "home"
    ws = tmp / "ws"
    (home / ".ts2" / "agent_config").mkdir(parents=True, exist_ok=True)
    (ws / "agent_config").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("TS2_WORKSPACE", str(ws))
    return {"home": home, "ws": ws}


def _provider(name="openai", priority=1, enabled=True):
    return {"name": name, "provider": name, "model": "gpt-4o-mini",
            "api_key": "sk-test", "priority": priority, "enabled": enabled}


def test_load_providers_ts2_preferred(env_setup):
    """~/.ts2 有 providers.json 时优先读取。"""
    from mcp.server.saber.llm_manager import _load_providers

    home, ws = env_setup["home"], env_setup["ws"]
    (home / ".ts2" / "agent_config" / "providers.json").write_text(
        json.dumps([_provider("ts2-p", priority=1)]), encoding="utf-8")
    (ws / "agent_config" / "providers.json").write_text(
        json.dumps([_provider("ws-p", priority=1)]), encoding="utf-8")

    providers = _load_providers()
    assert providers[0]["name"] == "ts2-p"


def test_load_providers_workspace_fallback(env_setup):
    """~/.ts2 缺失时回退工作区。"""
    from mcp.server.saber.llm_manager import _load_providers

    ws = env_setup["ws"]
    (ws / "agent_config" / "providers.json").write_text(
        json.dumps([_provider("ws-p", priority=1)]), encoding="utf-8")

    providers = _load_providers()
    assert providers[0]["name"] == "ws-p"


def test_cache_not_persist_on_failure(env_setup, monkeypatch):
    """读取失败时不缓存；数据补上后再次读取能拿到。"""
    from mcp.server.saber import llm_manager

    llm_manager.clear_cache()
    ws = env_setup["ws"]
    ws_cfg = ws / "agent_config" / "providers.json"

    assert llm_manager.get_llm_config()["model"] == "gpt-4o-mini"  # 无配置，走 env 默认

    # 补上配置后应能读到（此前若有失败缓存会阻碍）
    ws_cfg.write_text(json.dumps([_provider("ws-p", priority=1)]), encoding="utf-8")
    cfg = llm_manager.get_llm_config()
    assert cfg["api_key"] == "sk-test"  # 证明读到了工作区 provider，而非 env 默认

    llm_manager.clear_cache()