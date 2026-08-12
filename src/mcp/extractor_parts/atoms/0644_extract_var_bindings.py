# 原子：extract_var_bindings（原 interface_chain_extractor.py 第 644 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def extract_var_bindings(func) -> dict:
    """提取函数体内变量 → 类型名/来源（Assign/AnnAssign 直接赋值）"""
    binds: dict = {}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var = node.targets[0].id
            if isinstance(node.value, ast.Call):
                f = node.value.func
                if isinstance(f, ast.Name):
                    binds[var] = f.id  # x = helper(...) → 类型=helper（用 HELPER_RETURN_TYPES 解析）
                elif isinstance(f, ast.Attribute):
                    binds[var] = f.attr  # x = obj.method(...)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            var = node.target.id
            if isinstance(node.value, ast.Call):
                f = node.value.func
                if isinstance(f, ast.Name):
                    binds[var] = f.id
    return binds
