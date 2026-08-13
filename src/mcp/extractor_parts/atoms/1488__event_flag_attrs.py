# 原子：_event_flag_attrs（原 interface_chain_extractor.py 第 1488 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _event_flag_attrs(tree) -> set:
    """收集文件中初始化为 threading.Event() 的属性名（只对这些做 clear/set 配对）。

    关键：`self._queue.clear()` / `self._trackers.clear()` 是 list/dict 的 clear，
    不是 Event 标志——必须用「初始化赋值 = Event()」来区分，否则大量误报。
    """
    attrs: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Assign):
                continue
            # self._xxx = threading.Event() / Event()
            if (sub.value and isinstance(sub.value, ast.Call)
                    and isinstance(sub.value.func, ast.Attribute)
                    and sub.value.func.attr == "Event"):
                for t in sub.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                            and t.value.id in ("self", "cls"):
                        attrs.add(t.attr)
            # 兼容 import 别名：_chat_active = Event()（Name 形式）
            elif (sub.value and isinstance(sub.value, ast.Call)
                  and isinstance(sub.value.func, ast.Name)
                  and sub.value.func.id == "Event"):
                for t in sub.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                            and t.value.id in ("self", "cls"):
                        attrs.add(t.attr)
    return attrs
