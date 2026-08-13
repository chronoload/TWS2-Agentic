# 原子：_collect_response_keys（原 interface_chain_extractor.py 第 367 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _collect_response_keys(func: ast.FunctionDef) -> list[str]:
    """静态提取 ok(data={...}) / ok(data=dict(...)) 的顶层键"""
    keys: list[str] = []

    def _walk_dict(d: ast.Dict):
        for k in d.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.append(k.value)

    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ok":
            for kw in node.keywords:
                if kw.arg == "data":
                    if isinstance(kw.value, ast.Dict):
                        _walk_dict(kw.value)
                    elif isinstance(kw.value, ast.Call) and isinstance(kw.value.func, ast.Name) and kw.value.func.id == "dict":
                        for a in kw.value.args:
                            if isinstance(a, ast.Dict):
                                _walk_dict(a)
    # 去重保序
    seen = set()
    out = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out
