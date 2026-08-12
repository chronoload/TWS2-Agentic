# 原子：cmd_project（原 interface_chain_extractor.py 第 3307 行）
# 逻辑组：cli · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def cmd_project(root: str, out: Path, exclude: tuple = (),
                frontend: str = "", frontend_class: str = "", client_var: str = "client",
                no_db: bool = False, no_chain: bool = False,
                plugins: list | None = None, plugins_dir: str = "") -> int:
    root_p = Path(root)
    if not root_p.is_dir():
        print(f"[project] 目录不存在: {root}")
        return 1
    modules, funcs, edges = analyze_project(root_p, exclude)

    # API 端点 + Pydantic 请求模型（复用 TS2 特化的提取逻辑，loose 模式任意 router/app 对象）
    endpoints: list[Endpoint] = []
    models: list[RequestModel] = []
    http_methods = ("get", "post", "put", "delete", "patch", "websocket", "api_route", "route")
    for m in modules:
        p = Path(m.file)
        if p.suffix != ".py":
            _extract_ts_api(p, endpoints)   # JS/TS 用正则提端点（Fastify/Express/Hono 风格）
            continue
        extract_endpoints(p, http_methods, endpoints, loose=True)
        extract_python_models(p, models)

    report = {
        "root": str(root_p),
        "modules": [asdict(m) for m in modules],
        "funcs": [asdict(f) for f in funcs],
        "call_edges": [asdict(e) for e in edges],
        "endpoints": [{"method": e.method, "path": e.path, "func": e.func,
                       "file": e.file, "line": e.line, "request_model": e.request_model,
                       "response_keys": e.response_keys} for e in endpoints],
        "models": [asdict(m) for m in models],
        "stats": {"modules": len(modules), "funcs": len(funcs),
                  "edges": len(edges),
                  "cross_module": sum(1 for e in edges if e.dst_kind == "cross_module"),
                  "endpoints": len(endpoints), "models": len(models)},
    }
    out.mkdir(parents=True, exist_ok=True)

    # subprocess 插件编排（多语言全栈扫描：node/mjs/rust/任意可执行）
    plugin_results: list[dict] = []
    if plugins or plugins_dir:
        specs = list(plugins or [])
        if plugins_dir:
            pd = Path(plugins_dir)
            if pd.is_dir():
                for f in sorted(pd.iterdir()):
                    if f.suffix in (".mjs", ".js") and f.name != "package.json":
                        specs.append(f"node:{f}")
                    elif f.suffix == ".py":
                        specs.append(f"python:{f}")
                    elif f.suffix == ".exe" or os.access(f, os.X_OK):
                        specs.append(str(f))
        if specs:
            plugin_results = run_plugins(root_p, out, specs, {
                "root": str(root_p), "out": str(out),
                "backend": str(MCP_ROOT / "docs" / "interface_chain_index.json"),
                "frontend_class": frontend_class, "client": client_var,
            })
    if plugin_results:
        report["plugins"] = [{
            "name": r.get("name"), "lang": r.get("lang"),
            "stats": r.get("stats") or {}, "sections": r.get("sections") or {},
        } for r in plugin_results]

    _art(out, "project_map.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    _write_csv(_art(out, "call_chain.csv"),
               ["src_file", "src_func", "dst", "dst_kind", "dst_module", "line"],
               [[e.src_file, e.src_func, e.dst, e.dst_kind, e.dst_module, e.line] for e in edges])
    _write_csv(_art(out, "module_map.csv"),
               ["module", "file", "classes", "funcs", "lines", "out_degree", "in_degree"],
               [[m.module, m.file, m.classes, m.funcs, m.lines, m.out_degree, m.in_degree]
                for m in modules])
    _write_csv(_art(out, "endpoints.csv"),
               ["method", "path", "func", "file", "line", "request_model", "response_keys"],
               [[e.method, e.path, e.func, e.file, e.line, e.request_model,
                 "|".join(e.response_keys)] for e in endpoints])
    _write_csv(_art(out, "models.csv"),
               ["name", "file", "line", "field", "type", "required", "default"],
               [[m.name, m.file, m.line, f.name, _type_short(f.type), f.required, f.default]
                for m in models for f in m.fields])

    # 新增 4 维度扫描
    all_files = [Path(m.file) for m in modules]
    hardcoded_items = scan_hardcoded(root_p, all_files, exclude)
    env_var_items = scan_env_vars(root_p, all_files, exclude)
    data_pool_items = scan_data_pools(root_p, all_files, exclude)
    static_resource_items = scan_static_resources(root_p, all_files, exclude)

    _write_csv(_art(out, "hardcoded.csv"),
               ["file", "line", "kind", "value", "context"],
               [[i.file, i.line, i.kind, i.value, i.context] for i in hardcoded_items])
    _write_csv(_art(out, "env_vars.csv"),
               ["file", "line", "name", "default", "context"],
               [[i.file, i.line, i.name, i.default, i.context] for i in env_var_items])
    _write_csv(_art(out, "data_pools.csv"),
               ["file", "line", "name", "kind", "size_hint", "context"],
               [[i.file, i.line, i.name, i.kind, i.size_hint, i.context] for i in data_pool_items])
    _write_csv(_art(out, "static_resources.csv"),
               ["file", "line", "path", "kind", "context"],
               [[i.file, i.line, i.path, i.kind, i.context] for i in static_resource_items])

    report["hardcoded"] = [asdict(i) for i in hardcoded_items]
    report["env_vars"] = [asdict(i) for i in env_var_items]
    report["data_pools"] = [asdict(i) for i in data_pool_items]
    report["static_resources"] = [asdict(i) for i in static_resource_items]
    report["stats"].update({
        "hardcoded": len(hardcoded_items), "env_vars": len(env_var_items),
        "data_pools": len(data_pool_items), "static_resources": len(static_resource_items),
    })

    md_path = _art(out, "PROJECT_CHAIN.md")
    md_text = _project_md(modules, funcs, edges, root_p, endpoints, models,
                           hardcoded=hardcoded_items, env_vars=env_var_items,
                           data_pools=data_pool_items, static_resources=static_resource_items)
    if not no_chain:
        # 通用依赖链章节（text + mermaid）：每端点的调用链图，链调用架构主视图
        md_text += build_dep_sections_generic(endpoints, root_p)
    # 插件 report_md 并入（各插件章节追加到报告尾部）
    md_text = _merge_plugin_results(report, plugin_results, md_text)
    md_path.write_text(md_text, encoding="utf-8")
    print(f"[project] 模块={len(modules)} 函数={len(funcs)} 调用边={len(edges)} "
          f"(跨模块={sum(1 for e in edges if e.dst_kind == 'cross_module')}) "
          f"API端点={len(endpoints)} 请求模型={len(models)}")
    print(f"[project] map      → {_art(out, 'project_map.json')}")
    print(f"[project] edges    → {_art(out, 'call_chain.csv')}")
    print(f"[project] modules  → {_art(out, 'module_map.csv')}")
    print(f"[project] api      → {_art(out, 'endpoints.csv')} / {_art(out, 'models.csv')}")
    print(f"[project] new4     → hardcoded={len(hardcoded_items)} env_vars={len(env_var_items)} "
          f"data_pools={len(data_pool_items)} static_resources={len(static_resource_items)}")
    print(f"[project] report   → {md_path}")
    if not no_chain:
        print(f"[project] chains   → {md_path}（含 {sum(1 for e in endpoints if Path(e.file).suffix == '.py')} 个端点依赖链图）")

    if not no_db:
        # 通用维度落库：endpoints/models + def-use（纯 AST 属性一致性，任意项目适用）；
        # behavior/flag/merge/id_source 依赖 TS2 状态机语义（规则表/Event/仲裁），通用项目跳过。
        defuse_files = [Path(m.file) for m in modules if m.file.endswith(".py")]
        defuse_result = analyze_defuse(defuse_files) if defuse_files else None
        _write_sqlite(_art(out, "interface_chain.db"), defuse_result, endpoints, models,
                      [], [], [], [], [], [],
                      hardcoded=hardcoded_items, env_vars=env_var_items,
                      data_pools=data_pool_items, static_resources=static_resource_items)
        print(f"[project] db       → {_art(out, 'interface_chain.db')}（endpoints/models/defuse/新4维度，"
              f"TS2 专属其余维度跳过）")

        # 生成数据资源追踪报告
        trace_report = _gen_data_resources_trace(out)
        if trace_report:
            trace_path = _art(out, "DATA_RESOURCES_TRACE.md")
            trace_path.write_text(trace_report, encoding="utf-8")
            print(f"[project] trace     → {trace_path}")

    # 前端对齐追踪（可选：--frontend 指定前端入口，用 Node 词法范本）
    if frontend:
        backend = str(MCP_ROOT / "docs" / "interface_chain_index.json")
        _run_frontend_trace(_frontend_script(), frontend,
                            frontend_class or "TS2Client", client_var, out, backend)
    return 0
