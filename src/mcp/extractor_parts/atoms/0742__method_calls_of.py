# 原子：_method_calls_of（原 interface_chain_extractor.py 第 742 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _method_calls_of(module_path: Path, cls_name: str, method_name: str) -> list:
    """提取类方法内部的调用目标（1 层）"""
    if not module_path.exists():
        return []
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == method_name:
                    for t in collect_call_targets(sub):
                        out.append(t)
                    return out
    return out
