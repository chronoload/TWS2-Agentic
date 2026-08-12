# 原子：_scan_ts_file（原 interface_chain_extractor.py 第 2555 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _scan_ts_file(path: Path, root: Path, lang: str) -> tuple:
    """JS/TS 文件扫描 → (ModuleSummary, [FuncInfo], [CallEdge], aliases)"""
    text = path.read_text(encoding="utf-8", errors="replace")
    clean = _strip_comments(text)
    mod = _rel_module(path, root)
    lines = text.count("\n") + 1

    # import 别名（含相对路径解析）
    aliases: dict[str, str] = {}
    for m in _TS_IMPORT_RE.finditer(text):
        mod_str = m.group(1)
        seg = text[m.start():m.start(1)]
        dm = re.search(r"import\s+([A-Za-z_$][\w$]*)", seg)
        if dm:
            aliases[dm.group(1)] = mod_str
        nm = re.search(r"import\s+\*\s+as\s+([A-Za-z_$][\w$]*)", seg)
        if nm:
            aliases[nm.group(1)] = mod_str
        for x in re.finditer(r"\{([^}]*)\}", seg):
            for part in x.group(1).split(","):
                part = part.strip()
                if not part:
                    continue
                if " as " in part:
                    key = part.split(" as ")[-1].strip()
                else:
                    key = part
                if re.match(r"^[A-Za-z_$][\w$]*$", key):
                    aliases[key] = mod_str
    for m in _TS_REQUIRE_RE.finditer(text):
        aliases[m.group(1)] = m.group(2)

    funcs: list[FuncInfo] = []
    classes = set()
    for m in _TS_CLASS_RE.finditer(clean):
        classes.add(m.group(1))
    # 类方法 + 独立函数 + 箭头函数
    seen: set[tuple] = set()
    for m in _TS_METHOD_RE.finditer(clean):
        name = m.group(1)
        if name in _TS_KEYWORDS or name in classes:
            continue
        key = (name, m.start())
        if key in seen:
            continue
        seen.add(key)
        funcs.append(FuncInfo(name=name, file=str(path), line=lines, end_line=lines,
                              size=0, is_method=True, class_name="", params=[],
                              is_entry=False))
    for m in list(_TS_FN_RE.finditer(clean)) + list(_TS_ARROW_RE.finditer(clean)):
        name = m.group(1)
        if name in _TS_KEYWORDS:
            continue
        funcs.append(FuncInfo(name=name, file=str(path), line=lines, end_line=lines,
                              size=0, is_method=False, class_name="", params=[],
                              is_entry=False))

    entry_points: list[str] = []
    if _TS_ENTRY_RE.search(clean):
        entry_points.append("L? main/argv-guard")

    # 调用边（按行去重）
    edges: list[CallEdge] = []
    out_count = 0
    cur_func = ""
    for lineno, line in enumerate(text.split("\n"), 1):
        for m in (_TS_FN_RE, _TS_ARROW_RE, _TS_METHOD_RE):
            mm = m.search(line)
            if mm and mm.group(1) not in _TS_KEYWORDS:
                cur_func = mm.group(1)
                break
        for cm in _TS_CALL_RE.finditer(line):
            obj, method = cm.group(1), cm.group(2)
            if obj in ("this", "console"):
                continue
            if obj in aliases:
                dst_module = _resolve_ts_module(aliases[obj], path, root)
                edges.append(CallEdge(str(path), cur_func, method, "cross_module",
                                      dst_module, lineno))
                out_count += 1
            else:
                edges.append(CallEdge(str(path), cur_func, method, "attr", "", lineno))

    ms = ModuleSummary(file=str(path), module=mod, classes=len(classes), funcs=len(funcs),
                       lines=lines, entry_points=entry_points,
                       out_degree=out_count, in_degree=0)
    return ms, funcs, edges, aliases
