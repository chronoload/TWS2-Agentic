# 原子：extract_imports（原 interface_chain_extractor.py 第 573 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def extract_imports(path: Path) -> dict:
    """提取模块内所有 import（含函数内），返回 {名称: 模块路径}"""
    if not path.exists():
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return {}
    imports: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                imports[a.asname or a.name] = mod
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports[a.asname or a.name] = a.name
    return imports
