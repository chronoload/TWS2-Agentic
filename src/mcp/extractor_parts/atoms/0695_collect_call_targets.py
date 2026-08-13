# 原子：collect_call_targets（原 interface_chain_extractor.py 第 695 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def collect_call_targets(func) -> list:
    """收集函数体（不含嵌套定义）内的直接调用目标，过滤装饰器与噪声"""
    targets = []
    seen = set()
    deco_lines = set()
    for node in _walk_own(func):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                deco_lines.add(d.lineno)
    for node in _walk_own(func):
        if not isinstance(node, ast.Call):
            continue
        if node.lineno in deco_lines:
            continue
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in NOISE_CALLS:
                continue
            key = (f.id, node.lineno)
            if key not in seen:
                seen.add(key)
                targets.append((f.id, "name", node.lineno))
        elif isinstance(f, ast.Attribute):
            obj = f.value
            obj_name = obj.id if isinstance(obj, ast.Name) else "*"
            method = f.attr
            if obj_name in ("app", "router") and method in HTTP_ATTRS:
                continue  # 路由装饰器
            if obj_name in NOISE_CALLS:
                continue  # logger.info / time.sleep 等
            if (obj_name == "*" or obj_name.startswith("_")) and method in NOISE_ATTRS:
                continue  # dict/list 方法（_agent_pool.get 等全局容器）
            key = (f"{obj_name}.{method}", node.lineno)
            if key not in seen:
                seen.add(key)
                targets.append((f"{obj_name}.{method}", "attr", node.lineno))
            # 线程池回调：run_in_executor(None, _func) / executor.submit(_func) 中的函数引用
            if method in ("run_in_executor", "submit", "create_task") or f.attr in ("call_soon_threadsafe",):
                for a in node.args:
                    if isinstance(a, ast.Name) and a.id not in NOISE_CALLS:
                        tkey = (a.id, node.lineno)
                        if tkey not in seen:
                            seen.add(tkey)
                            targets.append((a.id, "name", node.lineno))
    return targets
