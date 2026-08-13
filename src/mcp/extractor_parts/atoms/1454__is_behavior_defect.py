# 原子：_is_behavior_defect（原 interface_chain_extractor.py 第 1454 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _is_behavior_defect(b) -> bool:
    """真实行为缺陷判定（日志 / db / json / csv 统一口径）：
    must-call 全部缺失才算缺陷；'入口未找到'属规则过期警告，不算缺陷。
    """
    return bool(getattr(b, "missing", None)) and "未找到" not in (b.detail or "")
