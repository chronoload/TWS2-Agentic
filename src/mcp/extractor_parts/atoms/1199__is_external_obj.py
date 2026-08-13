# 原子：_is_external_obj（原 interface_chain_extractor.py 第 1199 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _is_external_obj(obj: str) -> bool:
    if obj in _EXTERNAL_OBJ_HINTS:
        return True
    if obj == "?":  # 复杂表达式对象（如 getattr(x[0].y, ...)）—— 动态，无法静态定位
        return True
    # 单字母变量名（t/s/c/m/r/v/f/e 等）多为临时/库对象
    return len(obj) == 1 and obj.isalpha()
