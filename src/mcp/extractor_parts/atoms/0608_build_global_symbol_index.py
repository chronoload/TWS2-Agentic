# 原子：build_global_symbol_index（原 interface_chain_extractor.py 第 608 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def build_global_symbol_index(root: Path) -> dict:
    """全局符号索引（亲属反射表）：{符号名: [(相对文件, 行号, 种类)]}
    种类: func | class | var | method（类方法）
    用于跨文件反射核查：trace_chain 遇到本文件未解析的目标时，反射全项目
    是否有定义——有则定位（亲属已找到），无则判为链路断裂（broken）。
    排除副本/第三方目录（web/android/archs 等是 android 副本，避免重复误定位）。
    """
    index: dict[str, list] = {}
    if not root.is_dir():
        return index
    extra_exclude = ("web", "android", "archs", "static_capacitor", "static_electron",
                     "staticselfcontaine", "static-branch", "static_arch", "draft")
    py_files = sorted(p for p in root.rglob("*.py")
                      if not any(x in p.parts for x in DEFAULT_EXCLUDE + extra_exclude))
    for p in py_files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                index.setdefault(node.name, []).append((rel, node.lineno, "func"))
            elif isinstance(node, ast.ClassDef):
                index.setdefault(node.name, []).append((rel, node.lineno, "class"))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        index.setdefault(f"{node.name}.{sub.name}", []).append(
                            (rel, sub.lineno, "method"))
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        index.setdefault(t.id, []).append((rel, node.lineno, "var"))
    return index
