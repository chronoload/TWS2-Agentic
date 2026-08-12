# -*- coding: utf-8 -*-
"""TS2 skill/context 链路收敛重构（plan 1）的 TDD 测试。

T1 统一 skill 注册表 / T2 统一上下文压缩 / T3 清理死代码。
"""
import importlib
import importlib.util
import json
from pathlib import Path

import pytest


def test_single_skill_registry():
    """T1：extensions.skills 与 ExtensionSkillTool 必须共享同一注册表单例。"""
    from mcp.extensions.skills import get_skill_registry
    from mcp.tools import ExtensionSkillTool

    tool_registry = ExtensionSkillTool()._get_registry()
    assert get_skill_registry() is tool_registry, \
        "extensions.skills 与 ExtensionSkillTool 用了不同注册表单例"


def test_legacy_skills_module_removed():
    """T1：旧版 mcp/skills.py 注册表模块已删除。

    注意：mcp/skills/ 目录（A 类文本技能内容，如 arxiv-reader）必须保留，
    因此不通过 import 判断（目录会被当作 namespace package），改为断言文件不存在。
    """
    import mcp
    mcp_dir = Path(mcp.__file__).parent
    assert not (mcp_dir / "skills.py").exists(), "旧版 mcp/skills.py 注册表仍存在"


def test_config_ui_uses_single_registry():
    """T1：config_ui 内无旧版 .skills import 残留（读源码，避免 tkinter 依赖）。"""
    import mcp
    src = (Path(mcp.__file__).parent / "config_ui.py").read_text(encoding="utf-8")
    assert "from .skills import" not in src, "config_ui 仍引用旧版 mcp/skills"
    assert "from .extensions.skills import" in src


def test_single_compactor_impl():
    """T2：context_compactor 已删除，压缩唯一实现 = context_window.auto_compact。

    用 find_spec 判断模块删除（import 判断会误捕获内部依赖缺失的异常）。
    """
    assert importlib.util.find_spec("mcp.context_compactor") is None, \
        "旧 context_compactor 模块仍存在"
    from mcp.prompt import context_window

    assert hasattr(context_window, "auto_compact")


def test_agent_assistant_uses_unified_compactor():
    """T2：agent_assistant 不再依赖 context_compactor.AutoCompact（读源码，避免 tkinter）。"""
    import mcp
    src = (Path(mcp.__file__).parent / "agent_assistant.py").read_text(encoding="utf-8")
    assert "context_compactor" not in src, "agent_assistant 仍引用旧压缩实现"
    assert "auto_compact" in src


def test_no_dead_code():
    """T3：无调用方死代码已清。"""
    from mcp.prompt import context_window as cw

    assert not hasattr(cw, "compact_messages")
    assert not hasattr(cw, "create_auto_compact")
    assert not hasattr(cw, "create_context_window")


def test_event_stream_ndjson(tmp_path):
    """T4：事件化 — emit 追加 NDJSON 行到指定文件。"""
    from mcp.event_stream import emit

    target = tmp_path / "events.ndjson"
    emit("skill.registry.changed", {"action": "register", "name": "demo"}, path=target)
    emit("context.compacted", {"before": 20, "after": 8}, path=target)

    lines = [ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "skill.registry.changed"
    assert first["data"]["name"] == "demo"
    second = json.loads(lines[1])
    assert second["event"] == "context.compacted"
    assert second["data"]["after"] == 8
