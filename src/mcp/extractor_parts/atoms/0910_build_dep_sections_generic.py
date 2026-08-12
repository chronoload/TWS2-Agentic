# 原子：build_dep_sections_generic（原 interface_chain_extractor.py 第 910 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def build_dep_sections_generic(endpoints: list, root: Path) -> str:
    """通用依赖链文档：按文件为端点生成调用链（text 树 + mermaid）。

    端点 file 字段只存 basename（extract_endpoints 约定），项目内可能同名文件
    （如多个 app.py）——故按「函数定义归属」分组：端点 func 出现在哪个文件的
    func_map 里，就用哪个文件展开链，消除歧义。
    TS2 语义表（PARAM_TYPE_HINTS / HELPER_RETURN_TYPES / KNOWN_TYPE_FILES）
    缺失时，跨模块/类调用以 unknown/builtin 叶子标记，不崩溃、仍可读链结构。
    """
    if not root.is_dir():
        return ""
    py_files = sorted(p for p in root.rglob("*.py")
                      if not any(x in p.parts for x in
                                 ("node_modules", "dist", "build", "venv", ".venv", "test", "tests")))
    # func → 定义文件（同名取先出现的文件；端点函数名通常在文件内唯一）
    func_file: dict[str, Path] = {}
    for p in py_files:
        fmap = extract_func_map(p)
        if not fmap:
            continue
        for name in fmap:
            func_file.setdefault(name, p)

    todo = [(ep, func_file.get(ep.func)) for ep in endpoints if ep.func in func_file]
    if not todo:
        return ""
    L = []
    L.append("\n## 7. 关键端点依赖链（端点 → 同文件 helper → 跨模块/类方法）\n")
    L.append("> 静态调用图：text 树 + mermaid 图（mermaid 块可在支持 Mermaid 的查看器中渲染）。\n")
    L.append("> 同类方法已用 `类型.方法` 标记，文件名即其定义位置。`↦ 亲属` 标注跨文件反射定位。\n")
    L.append("> 🔴 broken = 调用目标在项目内未找到定义（链路断裂，优先排查）。\n")
    global_index = build_global_symbol_index(root)
    cache: dict[Path, tuple] = {}
    broken_all: list = []
    for ep, p in sorted(todo, key=lambda t: (t[0].path, t[0].method)):
        if p not in cache:
            cache[p] = (extract_func_map(p), extract_imports(p))
        fmap, imports = cache[p]
        root_node = trace_chain(ep.func, fmap, imports, p, max_depth=2,
                                global_index=global_index)
        L.append(f"### `{ep.method} {ep.path}` — `{ep.func}` ({p.name}:{ep.line})\n")
        L.append("```text")
        L.extend(chain_text(root_node))
        L.append("```")
        L.append("```mermaid")
        L.append("graph TD")
        L.append("classDef broken fill:#f8d7da,stroke:#dc3545;")
        L.extend(chain_mermaid(root_node))
        L.append("```\n")
        for tgt, ln, detail in collect_broken_refs(root_node, []):
            broken_all.append((ep.method, ep.path, ep.func, p.name, ln, tgt, detail))
    if broken_all:
        L.append("\n### 🔴 链路断裂反射索引（跨文件核查，一步定位）\n")
        L.append("| 端点 | 调用位置 | 断裂目标 | 说明 |")
        L.append("|------|----------|----------|------|")
        for method, path, func, fname, ln, tgt, detail in broken_all:
            L.append(f"| `{method} {path}` | {fname}:{ln} | `{tgt}` | {detail} |")
    return "\n".join(L)
