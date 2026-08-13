# 原子：_apply_task（原 interface_chain_extractor.py 第 56 行）
# 逻辑组：cli · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _apply_task(cfg: dict) -> None:
    """任务配置 → 覆盖模块级特化常量（进程内生效，不写回源码）。"""
    g = globals()
    files = cfg.get("files") or {}

    def rp(rel):
        return (MCP_ROOT / rel) if rel else None

    g["APP_PY"] = rp(files.get("app")) or MCP_ROOT / "server" / "app.py"
    g["SABER_PY"] = rp(files.get("saber")) or MCP_ROOT / "server" / "saber" / "api.py"
    g["AGENT_PY"] = rp(files.get("agent")) or MCP_ROOT / "agent.py"
    g["PARAM_CHAIN_PY"] = rp(files.get("param_chain")) or MCP_ROOT / "param_chain.py"
    g["SUBAGENT_DIR"] = rp(files.get("subagent_dir")) or MCP_ROOT / "subagent"
    g["BEHAVIOR_RULES"] = cfg.get("behavior_rules") or {}
    g["ID_SOURCE_RULES"] = cfg.get("id_source_rules") or []
    g["TASK_FILES"] = files
    g["TASK_ENDPOINTS"] = cfg.get("endpoints") or []
    g["TASK_AGENT_METHODS"] = tuple(cfg.get("agent_methods") or [])
    g["CHAINS_CFG"] = cfg.get("chains") or {}
    g["TASK_SCAN_DIRS"] = [MCP_ROOT / d for d in (files.get("scan_dirs") or [])]
    g["ACTIVE_STRATEGY"] = load_strategy(cfg.get("strategy", "base"))
