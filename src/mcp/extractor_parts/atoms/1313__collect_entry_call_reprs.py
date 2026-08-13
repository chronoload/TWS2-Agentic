# 原子：_collect_entry_call_reprs（原 interface_chain_extractor.py 第 1313 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _collect_entry_call_reprs(func) -> list:
    """收集入口函数体（含嵌套闭包/回调）内所有调用目标的可读串，供 must-call 匹配。

    注意：必须包含嵌套函数体（如 _run_agent_stream / _on_tool_result 等闭包），
    因为副作用往往在回调/工作线程里触发，只在顶层 body 扫描会漏报。
    """
    out = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            r = _call_repr(node)
            if r:
                out.append(r)
    return out
