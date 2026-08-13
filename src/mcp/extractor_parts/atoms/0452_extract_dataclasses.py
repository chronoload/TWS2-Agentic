# 原子：extract_dataclasses（原 interface_chain_extractor.py 第 452 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def extract_dataclasses(path: Path, out: list):
    if not path.exists():
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            base_names = [_unparse(b) for b in node.bases]
            deco_names = [_unparse(d) for d in node.decorator_list]
            is_dataclass = any("dataclass" in d for d in deco_names)
            is_enum = any("Enum" in b for b in base_names)
            if is_dataclass or is_enum:
                d = DataclassDef(name=node.name, file=path.name, line=node.lineno,
                                 kind="enum" if is_enum else "dataclass")
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        required = stmt.value is None
                        d.fields.append(ModelField(
                            name=stmt.target.id,
                            type=_unparse(stmt.annotation),
                            default=_unparse(stmt.value) if stmt.value else "",
                            required=required,
                        ))
                    elif isinstance(stmt, ast.Assign) and is_enum:
                        # enum 成员如 CODER = "coder"
                        for t in stmt.targets:
                            if isinstance(t, ast.Name):
                                d.fields.append(ModelField(
                                    name=t.id, type="", default=_unparse(stmt.value), required=False,
                                ))
                out.append(d)
