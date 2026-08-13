# 原子：extract_agent_methods（原 interface_chain_extractor.py 第 484 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def extract_agent_methods(path: Path, method_names: tuple) -> list:
    """提取 Agent 类关键方法签名（含所属类名）"""
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            cls_name = node.name
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name in method_names:
                    params = []
                    for a in sub.args.args:
                        if a.arg in ("self", "cls"):
                            continue
                        ann = _unparse(a.annotation) if a.annotation else ""
                        params.append(f"{a.arg}: {ann}" if ann else a.arg)
                    result.append({
                        "name": f"{cls_name}.{sub.name}",
                        "line": sub.lineno,
                        "params": params,
                        "doc": _get_doc(sub.body),
                    })
    return result
