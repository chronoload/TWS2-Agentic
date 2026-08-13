# 原子：_py_collect_data_pools（原 interface_chain_extractor.py 第 2140 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _py_collect_data_pools(file: Path, tree, rel: str) -> list:
    items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            val = node.value
            kind = ""
            size_hint = ""
            for k, pat in _DATA_POOL_KINDS.items():
                if pat.search(name):
                    kind = k
                    break
            if not kind:
                if isinstance(val, ast.Call):
                    f = val.func
                    fname = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                    if fname in ("dict", "list", "set", "OrderedDict", "defaultdict", "Singleton",
                                "AgentPool", "ModelCache", "SessionStore", "VectorStore",
                                "QdrantClient", "ChromaClient", "FaissIndex", "Redis",
                                "ConnectionPool", "asyncio.Queue", "Queue"):
                        kind = "dict" if fname in ("dict", "OrderedDict", "defaultdict") else (
                            "list" if fname in ("list", "set") else "pool")
            if kind:
                size_hint = _unparse(val)[:60]
                items.append(DataPoolItem(file=rel, line=node.lineno, name=name,
                                          kind=kind, size_hint=size_hint,
                                          context="module_level_init"))
        elif isinstance(node, ast.Assign) and len(node.targets) > 1:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name = t.id
                    for k, pat in _DATA_POOL_KINDS.items():
                        if pat.search(name):
                            items.append(DataPoolItem(file=rel, line=node.lineno, name=name,
                                                      kind=k, size_hint="",
                                                      context="module_level_multi_assign"))
                            break
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                                and t.value.id in ("self", "cls"):
                            attr = t.attr
                            for k, pat in _DATA_POOL_KINDS.items():
                                if pat.search(attr):
                                    sh = _unparse(stmt.value)[:60] if stmt.value else ""
                                    items.append(DataPoolItem(file=rel, line=stmt.lineno,
                                                              name=f"{node.name}.{attr}",
                                                              kind=k, size_hint=sh,
                                                              context="class_attr_init"))
                                    break
    return items
