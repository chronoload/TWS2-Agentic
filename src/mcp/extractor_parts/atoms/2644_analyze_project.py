# 原子：analyze_project（原 interface_chain_extractor.py 第 2644 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def analyze_project(root: Path, exclude: tuple = DEFAULT_EXCLUDE):
    """扫描任意项目（Python AST + JS/TS 正则）：模块地图 + 调用边 + 入口点。
    返回 (modules, funcs, edges)。"""
    modules: list[ModuleSummary] = []
    funcs: list[FuncInfo] = []
    edges: list[CallEdge] = []
    suffixes = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".mts")

    files = sorted(p for p in root.rglob("*")
                   if p.is_file() and p.suffix in suffixes
                   and not any(part in exclude for part in p.parts))
    py_files = [f for f in files if f.suffix == ".py"]
    ts_files = [f for f in files if f.suffix != ".py"]

    # JS/TS：正则扫描（先处理，模块/函数/边直接产出；入度由跨模块边统计）
    ts_edges: list[CallEdge] = []
    for f in ts_files:
        try:
            ms, fns, ed, _aliases = _scan_ts_file(f, root, "ts")
        except (OSError, UnicodeDecodeError):
            continue
        modules.append(ms)
        funcs.extend(fns)
        edges.extend(ed)
        ts_edges.extend(ed)

    # 各文件：别名表 + 本模块函数名集合（用于 same_module 判定）
    per_file: list[tuple[Path, dict, set, dict]] = []
    for f in py_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        aliases = _import_aliases(tree)
        local_names: set[str] = set()
        classes: dict[str, int] = {}   # class name -> line
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes[node.name] = node.lineno
                local_names.add(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local_names.add(node.name)
        per_file.append((f, aliases, local_names, classes))

    # 模块地图 + 函数 + 调用边
    module_by_file: dict[str, ModuleSummary] = {}
    for f, aliases, local_names, classes in per_file:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        mod = _rel_module(f, root)
        entry_points: list[str] = []
        n_lines = sum(1 for _ in open(f, encoding="utf-8", errors="replace"))
        # 入口点：main 调用 / click.typer 装饰 / asyncio.run 等
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                tests = test.values if isinstance(test, ast.BoolOp) else ([test] if isinstance(test, ast.Compare) else [])
                if any(isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                       and t.left.id == "__name__" for t in tests):
                    entry_points.append(f"L{node.lineno} main-guard")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ("asyncio.run", "uvicorn.run", "app.run", "cli"):
                entry_points.append(f"L{node.lineno} {node.func.id}(...)")

        cls = 0
        fn = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cls += 1
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        fn += 1
                        params = [a.arg for a in sub.args.args]
                        funcs.append(FuncInfo(
                            name=sub.name, file=str(f), line=sub.lineno,
                            end_line=sub.end_lineno or sub.lineno,
                            size=(sub.end_lineno or sub.lineno) - sub.lineno,
                            is_method=True, class_name=node.name, params=params,
                            is_entry=False))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and not any(isinstance(p, ast.FunctionDef) for p in ast.walk(node)):
                fn += 1
                funcs.append(FuncInfo(
                    name=node.name, file=str(f), line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    size=(node.end_lineno or node.lineno) - node.lineno,
                    is_method=False, class_name="", params=[a.arg for a in node.args.args],
                    is_entry=False))
        ms = ModuleSummary(file=str(f), module=mod, classes=cls, funcs=fn,
                           lines=n_lines, entry_points=entry_points,
                           out_degree=0, in_degree=0)
        module_by_file[str(f)] = ms
        modules.append(ms)

    # 调用边（跨文件出度/入度由调用边统计）
    out_count: dict[str, int] = {}
    in_count: dict[str, int] = {}
    for f, aliases, local_names, classes in per_file:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        cur_func = ""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cur_func = node.name
            if not isinstance(node, ast.Call):
                continue
            dst, kind, base = _call_target(node)
            if not dst:
                continue
            if kind == "self_method":
                edges.append(CallEdge(str(f), cur_func, dst, "self_method", "", node.lineno))
                continue
            if kind == "attr":
                if base in aliases:
                    tgt_mod = aliases[base]
                    if "." in tgt_mod:
                        tgt_mod = tgt_mod.rsplit(".", 1)[0]  # 方法属于模块
                    dst_kind, dst_module = "cross_module", tgt_mod
                    out_count[str(f)] = out_count.get(str(f), 0) + 1
                    in_count[tgt_mod] = in_count.get(tgt_mod, 0) + 1
                else:
                    dst_kind, dst_module = "attr", ""
                edges.append(CallEdge(str(f), cur_func, dst, dst_kind, dst_module, node.lineno))
                continue
            # name 形式：builtin / same_module / cross_module(直接导入的函数)
            if dst in aliases and "." in aliases[dst]:
                tgt_mod = aliases[dst].rsplit(".", 1)[0]
                dst_kind, dst_module = "cross_module", tgt_mod
                out_count[str(f)] = out_count.get(str(f), 0) + 1
                in_count[tgt_mod] = in_count.get(tgt_mod, 0) + 1
            elif dst in local_names:
                dst_kind, dst_module = "same_module", ""
            elif dst in _BUILTIN_NAMES:
                dst_kind, dst_module = "builtin", ""
            else:
                dst_kind, dst_module = "unknown", ""
            edges.append(CallEdge(str(f), cur_func, dst, dst_kind, dst_module, node.lineno))

    # TS 跨模块边计入入度（按解析出的模块路径）
    for e in ts_edges:
        if e.dst_kind == "cross_module" and e.dst_module:
            in_count[e.dst_module] = in_count.get(e.dst_module, 0) + 1

    # 回填模块出/入度（TS 模块保留 _scan_ts_file 设置的出度）
    for ms in modules:
        ms.out_degree = out_count.get(ms.file, ms.out_degree)
        ms.in_degree = in_count.get(ms.module, 0)
    return modules, funcs, edges
