# 原子：_flag_attr_of（原 interface_chain_extractor.py 第 1476 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _flag_attr_of(call) -> str:
    """从 `self._chat_active.clear()` 提取 attr 名；非 self.attr 形式返回 ''"""
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) \
            and isinstance(f.value.value, ast.Name) and f.value.value.id in ("self", "cls"):
        return f.value.attr
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
            and f.value.id in ("self", "cls"):
        return f.attr
    return ""
