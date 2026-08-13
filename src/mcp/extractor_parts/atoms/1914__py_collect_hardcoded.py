# 原子：_py_collect_hardcoded（原 interface_chain_extractor.py 第 1914 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _py_collect_hardcoded(file: Path, tree, rel: str) -> list:
    items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            val_node = node.value
            kind = ""
            val_text = ""
            if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
                val_text = val_node.value
                if _HARDCODE_URL_RE.search(val_text):
                    kind = "url"
                elif _HARDCODE_PORT_RE.search(val_text) and ":" in val_text:
                    kind = "port"
                elif val_text.startswith("/") or ("/" in val_text and not val_text.startswith("http")):
                    kind = "path"
                elif _HARDCODE_KEYWORDS.search(name):
                    kind = "key"
                elif _HARDCODE_KEYWORDS.search(val_text):
                    kind = "secret"
                if kind:
                    items.append(HardcodedItem(
                        file=rel, line=node.lineno, kind=kind,
                        value=val_text[:120], context=name))
            elif isinstance(val_node, ast.Constant) and isinstance(val_node.value, (int, float)):
                if name.endswith(("PORT", "_port")) or "port" in name.lower():
                    items.append(HardcodedItem(
                        file=rel, line=node.lineno, kind="port",
                        value=str(val_node.value), context=name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if node.value:
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    val_text = node.value.value
                    if _HARDCODE_KEYWORDS.search(name):
                        items.append(HardcodedItem(
                            file=rel, line=node.lineno,
                            kind="key" if "key" in name.lower() else "secret",
                            value=val_text[:120], context=name))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args + node.args.kwonlyargs:
                if arg.arg in ("self", "cls"):
                    continue
                default = None
                if arg in node.args.defaults:
                    idx = node.args.defaults.index(arg)
                    default = node.args.defaults[idx]
                elif arg in node.args.kw_defaults:
                    default = node.args.kw_defaults[node.args.kwonlyargs.index(arg)]
                if default and isinstance(default, ast.Constant) and isinstance(default.value, str):
                    val_text = default.value
                    if _HARDCODE_URL_RE.search(val_text) or _HARDCODE_KEYWORDS.search(arg.arg):
                        kind = "url" if _HARDCODE_URL_RE.search(val_text) else "key"
                        items.append(HardcodedItem(
                            file=rel, line=default.lineno or node.lineno,
                            kind=kind, value=val_text[:120], context=f"{node.name}({arg.arg}={val_text[:40]})"))
    return items
