"""
配置多源回退测试（TDD）
~/.ts2/agent_config 优先，回退 $TS2_WORKSPACE/agent_config。
"""
import json
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def env_setup(monkeypatch):
    """构造临时 ~/.ts2 与工作区目录，模拟双源。"""
    tmp = Path(tempfile.mkdtemp(prefix="ts2_cfg_test_"))
    home = tmp / "home"
    ws = tmp / "ws"
    (home / ".ts2" / "agent_config").mkdir(parents=True, exist_ok=True)
    (ws / "agent_config").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("TS2_WORKSPACE", str(ws))
    return {"home": home, "ws": ws}


def test_ts2_preferred_over_workspace(env_setup):
    """~/.ts2 有配置时优先读取。"""
    from mcp.config import ConfigManager

    home, ws = env_setup["home"], env_setup["ws"]
    (home / ".ts2" / "agent_config" / "settings.json").write_text('{"a": 1}', encoding="utf-8")
    (ws / "agent_config" / "settings.json").write_text('{"a": 2}', encoding="utf-8")

    cm = ConfigManager(config_dir=Path.home() / ".ts2" / "agent_config")
    assert cm.settings_file == (home / ".ts2" / "agent_config" / "settings.json")


def test_workspace_fallback_when_ts2_missing(env_setup):
    """~/.ts2 缺失时回退工作区。"""
    from mcp.config import ConfigManager

    ws = env_setup["ws"]
    (ws / "agent_config" / "providers.json").write_text("[]", encoding="utf-8")

    cm = ConfigManager(config_dir=Path.home() / ".ts2" / "agent_config")
    assert cm.providers_config_file == (ws / "agent_config" / "providers.json")