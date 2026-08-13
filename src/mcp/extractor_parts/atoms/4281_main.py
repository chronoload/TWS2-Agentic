# 原子：main（原 interface_chain_extractor.py 第 4281 行）
# 逻辑组：cli · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def main():
    ap = argparse.ArgumentParser(description="TS2 接口链路提取器（仅内置模块）")
    ap.add_argument("--json", action="store_true", help="额外输出 JSON 索引")
    ap.add_argument("--md", action="store_true", help="额外输出 Markdown 文档")
    ap.add_argument("--out", type=str, default=str(MCP_ROOT / "docs"),
                    help="输出目录（默认 mcp/docs）")
    ap.add_argument("--no-defuse", action="store_true",
                    help="跳过 def-use 属性一致性检查")
    ap.add_argument("--defuse-files", action="append", default=None, metavar="FILE",
                    help="def-use 检查的额外 Python 文件（可多次指定，用于其他项目/语言适配）")
    ap.add_argument("--root", type=str, default="",
                    help="通用项目分析模式：指定任意 Python 项目根目录，输出模块地图+跨模块调用链"
                         "（替代 TS2 专用流程；用于解析参考仓库/重构目标）")
    ap.add_argument("--exclude", action="append", default=None, metavar="DIR",
                    help="--root 模式下排除的子目录名（可多次指定）")
    ap.add_argument("--preset", type=str, default="",
                    help="预设项目一键分析（免写 --root/--out/--exclude）：ts2 / kimi；"
                         "自定义预设用 --presets-file 追加")
    ap.add_argument("--presets-file", type=str, default="",
                    help="自定义预设 JSON 文件（{name: {root, out, exclude[]}}，与内置合并）")
    ap.add_argument("--list-presets", action="store_true", help="列出可用预设")
    ap.add_argument("--frontend", type=str, default="",
                    help="前端入口文件（--root/--preset 模式）：调用 Node 词法范本 trace_agent_frontend.mjs "
                         "生成 FRONTEND_TRACE.md（方法→端点→后端对齐）")
    ap.add_argument("--frontend-class", type=str, default="",
                    help="前端 client 类名（默认 TS2Client；如 kimi-web 的 client 类）")
    ap.add_argument("--client", type=str, default="client",
                    help="前端调用点变量名（默认 client）")
    ap.add_argument("--no-db", action="store_true",
                    help="--root/--preset 模式跳过 SQLite 输出（默认生成 interface_chain.db：endpoints/models/def-use）")
    ap.add_argument("--no-chain", action="store_true",
                    help="--root/--preset 模式跳过端点依赖链章节（默认 PROJECT_CHAIN.md 含 text + mermaid 图）")
    ap.add_argument("--plugin", action="append", default=None, metavar="LANG:PATH",
                    help="外部扫描插件（可选扩展，可多次，多语言全栈）：node:path.mjs / python:path.py / 裸可执行文件（rust 二进制）。"
                         "默认主流程仍为内置 CLI 直链扫描，不传此参数则完全不受影响。"
                         "extractor 以 stdin 传 JSON 上下文 {root,out,backend,...}，插件 stdout 回 JSON"
                         " {name,stats,report_md,artifacts,sections}，产物合并进 project_map.json / PROJECT_CHAIN.md / out/")
    ap.add_argument("--plugins-dir", type=str, default="",
                    help="批量插件目录（可选）：目录下 *.mjs/*.js（node）、*.py（python）、*.exe/可执行文件均视为插件自动编排。"
                         "仅显式指定时启用，默认不扫描任何插件目录")
    ap.add_argument("--doc", action="store_true",
                    help="自文档反射：从 argparse 定义 + 产物清单常量生成 EXTRACTOR_DOC.md（不执行提取）")
    ap.add_argument("--doc-out", type=str, default="",
                    help="--doc 输出路径（默认 mcp/docs/EXTRACTOR_DOC.md）")
    ap.add_argument("--task", type=str, default="",
                    help="任务配置文件（默认 mcp/tasks/ts2.task.json）：外置全部 TS2 特化参数"
                         "（文件/装饰器/依赖链入口/规则表/扫描目录），引擎保持通用。")
    args = ap.parse_args()

    if args.list_presets:
        for name, p in _load_presets(args.presets_file).items():
            print(f"  {name}: root={p['root']} out={p.get('out', name)} "
                  f"exclude={p.get('exclude', [])}")
        return 0

    if args.doc:
        # 规则表等来自默认任务文件，保证自举文档与运行时一致
        try:
            _apply_task(load_task(args.task or DEFAULT_TASK))
        except Exception as e:
            print(f"[warn] 任务配置加载失败，用内置默认: {e}")
        return cmd_doc(argparse.Namespace(out=args.doc_out))

    if args.preset:
        presets = _load_presets(args.presets_file)
        p = presets.get(args.preset)
        if not p:
            print(f"[project] 未知预设 '{args.preset}'，可用: {', '.join(presets) or '(无)'}")
            return 1
        out_dir = MCP_ROOT / "docs" / str(p.get("out", args.preset))
        excl = DEFAULT_EXCLUDE + tuple(p.get("exclude", []))
        return cmd_project(str(p["root"]), out_dir, excl,
                           frontend=args.frontend, frontend_class=args.frontend_class,
                           client_var=args.client, no_db=args.no_db, no_chain=args.no_chain,
                           plugins=args.plugin, plugins_dir=args.plugins_dir)

    if args.root:
        excl = DEFAULT_EXCLUDE + (tuple(args.exclude) if args.exclude else ())
        return cmd_project(args.root, Path(args.out), excl,
                           frontend=args.frontend, frontend_class=args.frontend_class,
                           client_var=args.client, no_db=args.no_db, no_chain=args.no_chain,
                           plugins=args.plugin, plugins_dir=args.plugins_dir)

    # TS2 默认流程：加载外置任务配置（特化参数单一事实源）
    try:
        _apply_task(load_task(args.task or DEFAULT_TASK))
    except Exception as e:
        print(f"[task] 任务配置加载失败，用内置默认: {e}")

    endpoints: list[Endpoint] = []
    models: list[RequestModel] = []
    subagent_types: list[DataclassDef] = []
    param_types: list[DataclassDef] = []

    # 端点 + 模型（任务配置 endpoints：文件/module/方法/前缀，可任意扩展）
    _FILE_MAP = {"app": APP_PY, "saber": SABER_PY, "agent": AGENT_PY,
                 "param_chain": PARAM_CHAIN_PY}
    for ep_cfg in TASK_ENDPOINTS:
        ep_path = _FILE_MAP.get(ep_cfg.get("file"), APP_PY)
        module = ep_cfg.get("module", "app")
        decs = tuple(f"{module}.{m}" for m in ep_cfg.get("methods", []))
        extract_endpoints(ep_path, decs, endpoints, prefix=ep_cfg.get("prefix", ""))
        extract_python_models(ep_path, models)

    # 类型
    for f in sorted(SUBAGENT_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        extract_dataclasses(f, subagent_types)
    extract_dataclasses(PARAM_CHAIN_PY, param_types)

    agent_methods = extract_agent_methods(AGENT_PY, TASK_AGENT_METHODS)

    # 前端 TS2Client 解析已交给 Node（mcp/server/static/trace_agent_frontend.mjs），
    # 因为正则解析 JS 会产生大量噪声（if/catch/setTimeout 误判为方法）。
    drifts: list[Drift] = []
    client_methods: list[ClientMethod] = []

    # def-use 属性一致性检查：getattr 读取 ↔ 赋值点 跨文件闭环
    # 扫描文件集来自任务配置（files.defuse_extra + scan_dirs），避免把第三方/工具脚本误报进来；
    # 其他模块可用 --defuse-files 追加。
    defuse_result = None
    if not args.no_defuse:
        defuse_files = [APP_PY, SABER_PY, AGENT_PY, PARAM_CHAIN_PY]
        defuse_files += [MCP_ROOT / d for d in TASK_FILES.get("defuse_extra", [])]
        defuse_files += _task_dir_files(
            TASK_SCAN_DIRS, {"subagent", "middleware", "harness", "cache", "mcp_client", "memory"})
        if args.defuse_files:
            defuse_files += [Path(p) for p in args.defuse_files]
        defuse_result = analyze_defuse(defuse_files)

    # 行为契约检查（规范 F：must-call 路径覆盖）
    # 在声明入口所在的源码文件上执行规则；入口可能在 app.py 或 saber/api.py。
    behavior_issues = analyze_behavior(
        [APP_PY, SABER_PY], BEHAVIOR_RULES)

    # 状态标志生命周期检查（规范 G：clear/set 配对 + 跨会话缓存重置）
    flag_files = [APP_PY, AGENT_PY, SABER_PY, PARAM_CHAIN_PY]
    flag_files += _task_dir_files(TASK_SCAN_DIRS, {"middleware", "harness"})
    if TASK_FILES.get("llm") and (MCP_ROOT / TASK_FILES["llm"]).exists():
        flag_files.append(MCP_ROOT / TASK_FILES["llm"])
    flag_issues = analyze_flag_lifecycle(flag_files)

    # 状态机合并方向仲裁检查（规范 H：数量仲裁 vs 版本仲裁）
    merge_issues = analyze_merge_direction(flag_files)

    # 标识符命名空间来源契约检查（规范 J：跨命名空间 key 误用 + 无守卫消费者）
    # 扫描范围更广：不只 agent/中间件，还包括会话/检查点存储的消费方（server、agent_assistant）
    id_files = [APP_PY, AGENT_PY, SABER_PY, PARAM_CHAIN_PY]
    id_files += _task_dir_files(TASK_SCAN_DIRS, {"server", "middleware", "harness", "cache"})
    if TASK_FILES.get("agent_assistant") and (MCP_ROOT / TASK_FILES["agent_assistant"]).exists():
        id_files.append(MCP_ROOT / TASK_FILES["agent_assistant"])
    id_source_issues = analyze_id_source_contract(id_files)

    # 新增 4 维度扫描
    core_files = [APP_PY, SABER_PY, AGENT_PY, PARAM_CHAIN_PY]
    if TASK_FILES.get("llm") and (MCP_ROOT / TASK_FILES["llm"]).exists():
        core_files.append(MCP_ROOT / TASK_FILES["llm"])
    core_files += _task_dir_files(
        TASK_SCAN_DIRS, {"subagent", "middleware", "cache", "mcp_client", "memory", "server"})
    hardcoded_items = scan_hardcoded(MCP_ROOT, core_files)
    env_var_items = scan_env_vars(MCP_ROOT, core_files)
    data_pool_items = scan_data_pools(MCP_ROOT, core_files)
    static_resource_items = scan_static_resources(MCP_ROOT, core_files)

    global _BUILTIN_TRANSFORM_NAMES
    _BUILTIN_TRANSFORM_NAMES = ACTIVE_STRATEGY.collect_builtin_transforms()

    index_models = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "endpoints": len(endpoints),
            "models": len(models),
            "subagent_types": len(subagent_types),
            "param_types": len(param_types),
            "agent_methods": len(agent_methods),
            "hardcoded": len(hardcoded_items),
            "env_vars": len(env_var_items),
            "data_pools": len(data_pool_items),
            "static_resources": len(static_resource_items),
        },
        "defuse": None if defuse_result is None else {
            "reads": len(defuse_result[0]),
            "writes": len(defuse_result[1]),
            "issues": [asdict(i) for i in defuse_result[2]],
        },
        "behavior": [asdict(b) for b in behavior_issues if _is_behavior_defect(b)],
        "flag_lifecycle": [asdict(i) for i in flag_issues],
        "merge_direction": [asdict(i) for i in merge_issues],
        "id_source": [asdict(i) for i in id_source_issues],
        "hardcoded": [asdict(i) for i in hardcoded_items],
        "env_vars": [asdict(i) for i in env_var_items],
        "data_pools": [asdict(i) for i in data_pool_items],
        "static_resources": [asdict(i) for i in static_resource_items],
        "drifts": [asdict(d) for d in drifts],
        "endpoints": [{ "method": e.method, "path": e.path, "func": e.func,
                        "request_model": e.request_model, "response_keys": e.response_keys,
                        "file": e.file, "line": e.line, "doc": e.doc } for e in endpoints],
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV（机器索引/Excel 分析）
    _write_csv(_art(out_dir, "endpoints.csv"),
               ["method", "path", "func", "request_model", "response_keys", "file", "line", "doc"],
               [[e.method, e.path, e.func, e.request_model, "|".join(e.response_keys), e.file, e.line, e.doc]
                for e in endpoints])
    _write_csv(_art(out_dir, "models.csv"),
               ["name", "file", "line", "field", "type", "required", "default"],
               [[m.name, m.file, m.line, f.name, _type_short(f.type), f.required, f.default]
                for m in models for f in m.fields])
    _write_csv(_art(out_dir, "drifts.csv"),
               ["kind", "client", "endpoint", "detail"],
               [[d.kind, d.client, d.endpoint, d.detail] for d in drifts])
    if defuse_result:
        _write_csv(_art(out_dir, "defuse_issues.csv"),
                   ["kind", "attr", "file", "line", "obj", "default", "detail"],
                   [[i.kind, i.attr, i.file, i.line, i.obj, i.default, i.detail]
                    for i in defuse_result[2]])
        _write_csv(_art(out_dir, "defuse_reads.csv"),
                   ["file", "line", "obj", "attr", "default"],
                   [[r.file, r.line, r.obj, r.attr, r.default] for r in defuse_result[0]])
    _write_csv(_art(out_dir, "behavior_issues.csv"),
               ["entry", "missing", "file", "detail"],
               [[b.entry, "|".join(b.missing), b.file, b.detail]
                for b in behavior_issues if _is_behavior_defect(b)])
    _write_csv(_art(out_dir, "flag_lifecycle.csv"),
               ["kind", "attr", "file", "line", "detail"],
               [[i.kind, i.attr, i.file, i.line, i.detail] for i in flag_issues])
    _write_csv(_art(out_dir, "merge_direction.csv"),
               ["kind", "fn", "file", "line", "detail"],
               [[i.kind, i.fn, i.file, i.line, i.detail] for i in merge_issues])
    _write_csv(_art(out_dir, "id_source.csv"),
               ["kind", "consumer", "key_arg", "file", "line", "detail"],
               [[i.kind, i.consumer, i.key_arg, i.file, i.line, i.detail] for i in id_source_issues])

    # 新增 4 维度 CSV
    _write_csv(_art(out_dir, "hardcoded.csv"),
               ["file", "line", "kind", "value", "context"],
               [[i.file, i.line, i.kind, i.value, i.context] for i in hardcoded_items])
    _write_csv(_art(out_dir, "env_vars.csv"),
               ["file", "line", "name", "default", "context"],
               [[i.file, i.line, i.name, i.default, i.context] for i in env_var_items])
    _write_csv(_art(out_dir, "data_pools.csv"),
               ["file", "line", "name", "kind", "size_hint", "context"],
               [[i.file, i.line, i.name, i.kind, i.size_hint, i.context] for i in data_pool_items])
    _write_csv(_art(out_dir, "static_resources.csv"),
               ["file", "line", "path", "kind", "context"],
               [[i.file, i.line, i.path, i.kind, i.context] for i in static_resource_items])

    # SQLite（复杂查询/与需求对齐联动）
    _write_sqlite(_art(out_dir, "interface_chain.db"), defuse_result,
                  endpoints, models, drifts, client_methods, behavior_issues,
                  flag_issues, merge_issues, id_source_issues,
                  hardcoded=hardcoded_items, env_vars=env_var_items,
                  data_pools=data_pool_items, static_resources=static_resource_items)

    # 生成数据资源追踪报告
    trace_report = _gen_data_resources_trace(out_dir)
    if trace_report:
        trace_path = _art(out_dir, "DATA_RESOURCES_TRACE.md")
        trace_path.write_text(trace_report, encoding="utf-8")
        print(f"[OK] Trace    → {trace_path}")

    md_path = _art(out_dir, "INTERFACE_CHAIN.md")
    md_path.write_text(
        gen_markdown(endpoints, models, subagent_types, param_types, agent_methods,
                     client_methods, drifts, index_models, defuse_result,
                     behavior_issues, flag_issues, merge_issues, id_source_issues,
                     hardcoded_items, env_var_items, data_pool_items, static_resource_items),
        encoding="utf-8")

    json_path = _art(out_dir, "interface_chain_index.json")
    json_path.write_text(json.dumps(index_models, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[OK] Markdown → {md_path}")
    print(f"[OK] JSON     → {json_path}")
    print(f"统计: 端点={len(endpoints)} 模型={len(models)} "
          f"子代理类型={len(subagent_types)} 参数链类型={len(param_types)} "
          f"Agent方法={len(agent_methods)}")
    print(f"新增4维度: hardcoded={len(hardcoded_items)} env_vars={len(env_var_items)} "
          f"data_pools={len(data_pool_items)} static_resources={len(static_resource_items)}")
    if defuse_result:
        _dr, _dw, issues, _dc = defuse_result
        hard = sum(1 for i in issues if i.kind == "no_assignment")
        print(f"def-use: 读取={len(_dr)} 赋值={len(_dw)} 恒值风险={len(issues)}（无赋值={hard}）")
        for i in issues:
            print(f"  ⚠ [{i.kind}] {i.file}:{i.line} getattr({i.obj}, '{i.attr}', {i.default}) — {i.detail}")
    bh = [b for b in behavior_issues if _is_behavior_defect(b)]
    print(f"行为契约: 规则={sum(len(v) for v in BEHAVIOR_RULES.values())} 问题={len(bh)}")
    for b in bh:
        print(f"  ⚠ [missing_behavior] {b.file} {b.entry} — 缺失: {', '.join(b.missing)}")
    fc = flag_issues
    print(f"状态标志: clear_without_set={sum(1 for i in fc if i.kind=='clear_without_set')} "
          f"stale_cache={sum(1 for i in fc if i.kind=='stale_cache')}")
    for i in fc:
        print(f"  ⚠ [{i.kind}] {i.file}:{i.line} {i.attr} — {i.detail}")
    mj = merge_issues
    print(f"合并仲裁: count_only_arbitration={sum(1 for i in mj if i.kind=='count_only_arbitration')}")
    for i in mj:
        print(f"  ⚠ [{i.kind}] {i.file}:{i.line} {i.fn} — {i.detail}")
    isc = id_source_issues
    print(f"ID来源契约: cross_namespace_key={sum(1 for i in isc if i.kind=='cross_namespace_key')} "
          f"unguarded_key_consumer={sum(1 for i in isc if i.kind=='unguarded_key_consumer')}")
    for i in isc:
        print(f"  ⚠ [{i.kind}] {i.file}:{i.line} {i.consumer}({i.key_arg}) — {i.detail}")
    for d in drifts:
        print(f"  ⚠ [{d.kind}] {d.client} → {d.endpoint}: {d.detail}")
    print("提示: 前端对齐报告请运行 node mcp/server/static/trace_agent_frontend.mjs")
    print("产物利用（宏观优先，勿陷于缺陷清单）:")
    print(f"  ① 整体链路图 → {md_path}（§关键端点依赖链 text 树 + mermaid 图，先看整体再入细节）")
    print(f"  ② 可查询链路库 → {json_path.parent / 'interface_chain.db'}（SQL 或 python mcp/plan_cli.py chain endpoints/issues/models 替代 grep-read）")
    print("  ③ 主产品 = 链路数据库 + 文档；缺陷清单只是附加值，别用缺陷数量衡量本次价值")
    _auto_refresh_extractor_doc()
