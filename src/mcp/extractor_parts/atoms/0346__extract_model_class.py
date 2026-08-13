# 原子：_extract_model_class（原 interface_chain_extractor.py 第 346 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _extract_model_class(cls: ast.ClassDef, file: str, models: list):
    base_names = []
    for b in cls.bases:
        bn = _unparse(b)
        base_names.append(bn)
    if not any("BaseModel" in b for b in base_names):
        return  # 只提取 Pydantic 模型
    m = RequestModel(name=cls.name, file=file, line=cls.lineno, doc=_get_doc(cls.body))
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            typ = _unparse(stmt.annotation)
            default = None
            required = True
            if stmt.value is not None:
                default = _unparse(stmt.value)
                required = False
            m.fields.append(ModelField(name=name, type=typ, default=default or "", required=required))
    models.append(m)
