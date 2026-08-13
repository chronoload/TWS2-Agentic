# 原子：_py_collect_env_vars（原 interface_chain_extractor.py 第 2036 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _py_collect_env_vars(file: Path, tree, rel: str) -> list:
    items = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute):
            if f.value.attr == "environ" and isinstance(f.value.value, ast.Name) and f.value.value.id == "os":
                if f.attr == "get" and node.args:
                    name = ""
                    default = ""
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        name = node.args[0].value
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        default = str(node.args[1].value)
                    items.append(EnvVarItem(file=rel, line=node.lineno,
                                             name=name, default=default,
                                             context="os.environ.get"))
                elif f.attr == "__getitem__" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        items.append(EnvVarItem(file=rel, line=node.lineno,
                                                 name=node.args[0].value, default="",
                                                 context="os.environ[...]"))
            elif isinstance(f.value, ast.Name) and f.value.id == "os" and f.attr == "getenv":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    default = ""
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        default = str(node.args[1].value)
                    items.append(EnvVarItem(file=rel, line=node.lineno,
                                             name=node.args[0].value, default=default,
                                             context="os.getenv"))
        elif isinstance(f, ast.Attribute) and f.attr == "get":
            if isinstance(f.value, ast.Attribute) and f.value.attr == "environ":
                if f.value.value and isinstance(f.value.value, ast.Name) and f.value.value.id == "os":
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        default = ""
                        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                            default = str(node.args[1].value)
                        items.append(EnvVarItem(file=rel, line=node.lineno,
                                                 name=node.args[0].value, default=default,
                                                 context="os.environ.get"))
    return items
