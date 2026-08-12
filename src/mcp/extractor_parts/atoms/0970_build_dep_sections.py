# 原子：build_dep_sections（原 interface_chain_extractor.py 第 970 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def build_dep_sections(endpoints: list) -> str:
    """关键端点依赖链（亲属追逐 → 跨模块/存储）。

    入口泛化：任务配置 CHAINS_CFG.entries（{kind: endpoint, prefix} 或 {kind: function, name}），
    全部走同一 trace_chain 引擎 + 全局符号索引（亲属反射定位），展示（text + mermaid + 断裂索引）通用；
    预置链路（CHAINS_CFG.preset，TS2 特化静态文本）作为补充块渲染，不硬编码。
    """
    cfg = CHAINS_CFG or {}
    max_depth = int(cfg.get("max_depth", 3))
    entries = cfg.get("entries") or [{"kind": "endpoint", "prefix": "/api/agent/"}]

    # func → 定义文件索引（泛化归属，消除同名文件歧义）
    func_file: dict[str, Path] = {}
    for p in sorted(p for p in MCP_ROOT.rglob("*.py")
                    if not any(x in p.parts for x in DEFAULT_EXCLUDE)):
        fmap = extract_func_map(p)
        if not fmap:
            continue
        for name in fmap:
            func_file.setdefault(name, p)

    todo: list = []  # (label, func, file)
    global_index: dict = {}
    for e in entries:
        if e.get("kind") == "function":
            name = e.get("name", "")
            if "." in name:
                # 类方法名 Class.method：全局符号索引定位定义文件，起点取方法名
                if not global_index:
                    global_index = build_global_symbol_index(MCP_ROOT)
                for rel, ln, kind in global_index.get(name, []):
                    if kind == "method":
                        todo.append((f"function `{name}`", name.split(".")[-1], MCP_ROOT / rel))
                        break
            else:
                p = func_file.get(name)
                if p:
                    todo.append((f"function `{name}`", name, p))
        else:
            prefix = e.get("prefix", "")
            for ep in endpoints:
                if ep.path.startswith(prefix):
                    p = func_file.get(ep.func)
                    if p:
                        todo.append((f"`{ep.method} {ep.path}` — `{ep.func}`", ep.func, p))

    L = []
    if todo:
        L.append("\n## 8. 关键端点依赖链（亲属追逐 → 跨模块/存储）\n")
        L.append("> 静态调用图：入口 → 同文件 helper → 跨模块类方法 → 源文件定位。\n")
        L.append("> 同类方法已用 `类型.方法` 标记（如 `Agent.chat`），文件名即其定义位置。\n")
        L.append("> `↦ 亲属` = 跨文件反射定位（目标在本文件未解析，全项目索引命中）。\n")
        L.append("> 🔴 broken = 调用目标在项目内未找到定义（链路断裂，优先排查）。\n")
        global_index = build_global_symbol_index(MCP_ROOT)
        cache: dict[Path, tuple] = {}
        broken_all: list = []
        seen: set = set()
        for label, func, p in todo:
            if label in seen:
                continue
            seen.add(label)
            if p not in cache:
                cache[p] = (extract_func_map(p), extract_imports(p))
            fmap, imports = cache[p]
            root = trace_chain(func, fmap, imports, p, max_depth=max_depth,
                               global_index=global_index)
            L.append(f"### {label}\n")
            L.append("```text")
            L.extend(chain_text(root))
            L.append("```")
            L.append("```mermaid")
            L.append("graph TD")
            L.append("classDef broken fill:#f8d7da,stroke:#dc3545;")
            L.extend(chain_mermaid(root))
            L.append("```\n")
            for tgt, ln, detail in collect_broken_refs(root, []):
                broken_all.append((label, ln, tgt, detail))
        # 链路断裂反射索引（亲属反射汇总，一步定位 bug，免去 grep-read）
        if broken_all:
            L.append("\n### 🔴 链路断裂反射索引（跨文件核查，一步定位）\n")
            L.append("| 入口 | 调用位置 | 断裂目标 | 说明 |")
            L.append("|------|----------|----------|------|")
            for label, ln, tgt, detail in broken_all:
                L.append(f"| {label} | {ln} | `{tgt}` | {detail} |")

    # 预置链路（任务配置 chains.preset，静态文本，不硬编码）
    preset = cfg.get("preset")
    if preset:
        title = preset.get("title", "预置链路") if isinstance(preset, dict) else "预置链路"
        lines = preset.get("lines", []) if isinstance(preset, dict) else preset
        if lines:
            L.append(f"### {title}\n")
            L.append("```text")
            L.extend(lines if isinstance(lines, list) else [lines])
            L.append("```")
    return "\n".join(L)
