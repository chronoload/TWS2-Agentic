# 原子：_frontend_script（原 interface_chain_extractor.py 第 3201 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _frontend_script() -> Path:
    """定位泛化的前端追踪脚本（docs 范本优先）"""
    cands = [
        Path(__file__).resolve().parent.parent / "docs" / "interface-chain-audit" / "scripts" / "trace_agent_frontend.mjs",
        Path(__file__).resolve().parent.parent / ".trae" / "skills" / "interface-chain-audit" / "scripts" / "trace_agent_frontend.mjs",
    ]
    for c in cands:
        if c.exists():
            return c
    return cands[0]
