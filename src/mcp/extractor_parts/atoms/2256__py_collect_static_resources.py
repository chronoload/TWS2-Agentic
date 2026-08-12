# 原子：_py_collect_static_resources（原 interface_chain_extractor.py 第 2256 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _py_collect_static_resources(file: Path, tree, rel: str) -> list:
    items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            sig = _unparse(f)[:60] if f else ""
            if "StaticFiles" in sig or "statics" in sig or "express.static" in sig:
                path_val = ""
                if node.args:
                    a0 = node.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        path_val = a0.value
                kind = "static_files" if "StaticFiles" in sig else "express_static"
                items.append(StaticResourceItem(file=rel, line=node.lineno,
                                                path=path_val or sig, kind=kind,
                                                context="static_mount"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            fname = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if fname in ("open", "read_text", "read_bytes", "write_text", "write_bytes"):
                if node.args:
                    a0 = node.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        items.append(StaticResourceItem(
                            file=rel, line=node.lineno, path=a0.value[:120],
                            kind="io_path", context=fname))
            elif fname == "Path" and node.args:
                a0 = node.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    items.append(StaticResourceItem(
                        file=rel, line=node.lineno, path=a0.value[:120],
                        kind="io_path", context="Path()"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if _PATH_LITERAL_RE.match(v):
                ext = Path(v).suffix.lower().lstrip(".")
                kind_map = {"html": "template", "htm": "template", "jinja2": "template", "jinja": "template",
                            "css": "css", "js": "js", "png": "image", "jpg": "image",
                            "jpeg": "image", "gif": "image", "svg": "image", "ico": "image",
                            "woff": "font", "woff2": "font", "ttf": "font", "eot": "font"}
                kind = kind_map.get(ext, "other")
                items.append(StaticResourceItem(
                    file=rel, line=getattr(node, 'lineno', 0) or 0,
                    path=v[:120], kind=kind, context="path_literal"))
    return items
