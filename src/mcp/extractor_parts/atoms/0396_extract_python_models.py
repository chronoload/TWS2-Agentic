# 原子：extract_python_models（原 interface_chain_extractor.py 第 396 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def extract_python_models(path: Path, models: list):
    if not path.exists():
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            _extract_model_class(node, path.name, models)
