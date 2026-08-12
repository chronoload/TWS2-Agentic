# 原子：gen_markdown（原 interface_chain_extractor.py 第 3485 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def gen_markdown(endpoints, models, subagent_types, param_types, agent_methods,
                 client_methods, drifts, index_models, defuse=None,
                 behavior=None, flag=None, merge=None, id_source=None,
                 hardcoded=None, env_vars=None, data_pools=None, static_resources=None) -> str:
    L: list[str] = []
    L.append("# TS2 接口链路文档（自动生成）\n")
    L.append("> 由 `mcp/interface_chain_extractor.py` 自动生成。代码变更后运行：")
    L.append(">\n> ```\n> python mcp/interface_chain_extractor.py\n> ```\n")
    L.append(f"- 后端端点总数: **{len(endpoints)}**")
    L.append(f"- Pydantic 请求模型: **{len(models)}**")
    L.append(f"- 子代理/参数链类型: **{len(subagent_types) + len(param_types)}**")
    L.append(f"- 前端对齐: 见 `AGENT_FRONTEND_TRACE.md`（由 Node 脚本生成）\n")

    # 1. 语义偏移（后端内部：重复模型名等）
    L.append("---\n\n## 1. 语义偏移检测（后端内部）\n")
    dup_models = {}
    for m in models:
        dup_models.setdefault(m.name, []).append(f"{m.file}:{m.line}")
    dups = {k: v for k, v in dup_models.items() if len(v) > 1}
    if dups:
        L.append("⚠️ **重复定义的模型名**（后定义会覆盖先定义，极易引发语义偏移）：\n")
        L.append("| 模型名 | 定义位置 |")
        L.append("|--------|----------|")
        for k, v in dups.items():
            L.append(f"| `{k}` | {'; '.join(v)} |")
    else:
        L.append("后端模型无重名。\n")

    # 2. 后端端点
    L.append("\n## 2. 后端端点一览\n")
    L.append("| 方法 | 路径 | 函数 | 请求模型 | 返回字段 | 说明 |")
    L.append("|------|------|------|----------|----------|------|")
    for ep in sorted(endpoints, key=lambda e: e.path):
        rm = f"`{ep.request_model}`" if ep.request_model else "—"
        resp = ", ".join(f"`{k}`" for k in ep.response_keys[:8]) if ep.response_keys else "—"
        L.append(f"| {ep.method} | `{ep.path}` | `{ep.func}` | {rm} | {resp} | {ep.doc or ''} |")

    # 3. 请求模型详情
    L.append("\n## 3. Pydantic 请求模型（参数块）\n")
    for m in sorted(models, key=lambda x: x.name):
        L.append(f"### `{m.name}` — {m.file}:{m.line}\n")
        if m.doc:
            L.append(f"_{m.doc}_\n")
        L.append("| 字段 | 类型 | 必填 | 默认值 |")
        L.append("|------|------|------|--------|")
        for f in m.fields:
            L.append(f"| `{f.name}` | `{_type_short(f.type)}` | {'✅' if f.required else '—'} | `{f.default}` |")
        L.append("")

    # 4. 子代理类型
    L.append("\n## 4. 子代理模块类型（mcp/subagent/*）\n")
    for t in subagent_types:
        L.append(f"### `{t.name}` — {t.file}:{t.line} ({t.kind})\n")
        if t.kind == "enum":
            vals = [f"{f.name} = {f.default}" for f in t.fields]
            L.append(f"`{', '.join(vals)}`\n")
        else:
            L.append("| 字段 | 类型 | 必填 | 默认值 |")
            L.append("|------|------|------|--------|")
            for f in t.fields:
                L.append(f"| `{f.name}` | `{_type_short(f.type)}` | {'✅' if f.required else '—'} | `{f.default}` |")
            L.append("")

    # 5. 参数链类型
    L.append("\n## 5. 参数链路模块类型（mcp/param_chain.py）\n")
    for t in param_types:
        L.append(f"### `{t.name}` — {t.file}:{t.line} ({t.kind})\n")
        L.append("| 字段 | 类型 | 必填 | 默认值 |")
        L.append("|------|------|------|--------|")
        for f in t.fields:
            L.append(f"| `{f.name}` | `{_type_short(f.type)}` | {'✅' if f.required else '—'} | `{f.default}` |")
        L.append("")
    L.append("**内置 transform 注册表**：")
    L.append("`" + ", ".join(sorted(_BUILTIN_TRANSFORM_NAMES)) + "`\n" if _BUILTIN_TRANSFORM_NAMES else "")

    # 6. Agent 关键方法
    L.append("\n## 6. Agent 类关键方法（mcp/agent.py）\n")
    L.append("| 方法 | 行号 | 签名 | 说明 |")
    L.append("|------|------|------|------|")
    for m in agent_methods:
        sig = ", ".join(m["params"])
        L.append(f"| `{m['name']}` | {m['line']} | `({sig})` | {m['doc']} |")

    # 7. 前端客户端方法
    L.append("\n## 7. 前端 TS2Client 方法 → 端点映射\n")
    L.append("> 由 Node 脚本 `mcp/server/static/trace_agent_frontend.mjs` 生成 → `docs/AGENT_FRONTEND_TRACE.md`\n")
    L.append("> 运行：`node mcp/server/static/trace_agent_frontend.mjs`\n")

    # 8. def-use 属性一致性检查
    L.append("\n## 8. def-use 属性一致性检查（跨文件）\n")
    L.append("> 扫描 `getattr(obj, 'attr', default)` 读取点，交叉验证全库是否存在 `obj.attr` 赋值点。\n")
    L.append("> 目的：捕获「接口形状合法但值恒为默认」的运行时语义 bug（如 `_is_streaming` 从未赋值 → 恒 False）。\n")
    if defuse:
        _reads, _writes, issues, closed = defuse
        hard = [i for i in issues if i.kind == "no_assignment"]
        loose = [i for i in issues if i.kind == "loose_match"]
        external = [i for i in issues if i.kind == "external_contract"]
        L.append(f"\n**读取点 {len(_reads)}（含 hasattr 确认 {sum(1 for r in _reads if r.default == 'hasattr')}）· "
                 f"赋值点 {len(_writes)} · 恒值风险 {len(issues)}"
                 f"（无赋值 {len(hard)} / 对象不匹配 {len(loose)} / 外部契约 {len(external)}）**\n")
        if hard:
            L.append("\n### 🔴 恒值风险：读取点无任何赋值\n")
            L.append("| 属性 | 读取位置 | 对象 | 默认值 | 风险说明 |")
            L.append("|------|----------|------|--------|----------|")
            for i in hard:
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | `{i.obj}` | `{i.default}` | {i.detail} |")
        if loose:
            L.append("\n### 🟡 对象名不匹配（跨对象同名属性，需人工确认）\n")
            L.append("| 属性 | 读取位置 | 对象 | 默认值 | 可能的赋值位置 |")
            L.append("|------|----------|------|--------|----------------|")
            for i in loose:
                wl = "; ".join(f"{f}:{ln}" for f, ln, *_ in i.writes[:4]) or "—"
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | `{i.obj}` | `{i.default}` | {wl} |")
        if not hard and not loose:
            L.append("\n✅ 核心业务代码中所有假值默认的 `getattr` 读取均有赋值点闭合。\n")
        if external:
            L.append("\n### 🟠 外部/库对象属性读取（项目内无赋值，需人工核查是否存在该参数）\n")
            L.append("> 若确属库 SDK 标准属性则正常；若库中不存在该属性，即为「调用了库的不存在参数」（库 API 变更/误用）。\n")
            L.append("| 属性 | 读取位置 | 对象 | 默认值 | 核查结论 |")
            L.append("|------|----------|------|--------|----------|")
            for i in external[:40]:
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | `{i.obj}` | `{i.default}` | {i.detail} |")
        if closed:
            L.append("\n### 已闭合读取（赋值链）\n")
            L.append("| 属性 | 读取位置 | 对象 | 赋值位置 |")
            L.append("|------|----------|------|----------|")
            for r, wl in closed[:40]:
                ws = "; ".join(f"{f}:{ln}" for f, ln, *_ in wl) or "—"
                L.append(f"| `{r.attr}` | {r.file}:{r.line} | `{r.obj}` | {ws} |")
    else:
        L.append("\n（未启用）\n")

    # 8.5 行为契约检查（规范 F：must-call 路径覆盖）
    L.append("\n## 8.5 行为契约检查（must-call 路径覆盖）\n")
    L.append("> 依赖链只验证「被调用的函数存在」，无法验证「入口的正常完成路径必须触发某副作用」。\n")
    L.append("> 本维度用声明式规则「入口函数 → 必须调用的目标」做静态路径覆盖，捕获副作用缺失（如对话完成后未写回会话记录）。\n")
    if behavior:
        hard = [b for b in behavior if b.missing and "未找到" not in b.detail]
        missing_entry = [b for b in behavior if "未找到" in b.detail]
        L.append(f"\n**规则 {sum(len(v) for v in BEHAVIOR_RULES.values())} 项 · 入口 {len(BEHAVIOR_RULES)} · "
                 f"命中问题 {len(hard)} · 规则失效 {len(missing_entry)}**\n")
        if hard:
            L.append("\n### 🔴 缺少必须的副作用调用\n")
            L.append("| 入口 | 缺失目标 | 说明 |")
            L.append("|------|----------|------|")
            for b in hard:
                L.append(f"| `{b.entry}` | {', '.join(f'`{m}`' for m in b.missing)} | {b.detail} |")
        if missing_entry:
            L.append("\n### 🟠 规则失效（入口函数未找到，规则需更新）\n")
            for b in missing_entry:
                L.append(f"- `{b.entry}`：{b.detail}")
        if not hard and not missing_entry:
            L.append("\n✅ 所有入口的正常完成路径均触发了声明的副作用。\n")
    else:
        L.append("\n（未启用）\n")

    # 8.6 状态标志生命周期检查（规范 G）
    L.append("\n## 8.6 状态标志生命周期检查（clear/set 配对 · 跨会话缓存重置）\n")
    L.append("> 捕获 Event/锁标志 clear 后无 set 恢复（wait 永久卡死），以及会话级缓存字段")
    L.append("> （`_instance_id`/`_last_hash`/`_snapshot_seq`）在 session 切换处未重置（跨会话污染）。\n")
    if flag:
        cw = [i for i in flag if i.kind == "clear_without_set"]
        sc = [i for i in flag if i.kind == "stale_cache"]
        L.append(f"\n**clear_without_set {len(cw)} · stale_cache {len(sc)}**\n")
        if cw:
            L.append("\n### 🔴 clear 后无 set 恢复\n")
            L.append("| 标志 | 位置 | 说明 |")
            L.append("|------|------|------|")
            for i in cw:
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | {i.detail} |")
        if sc:
            L.append("\n### 🟠 跨会话缓存未重置\n")
            L.append("| 字段 | 位置 | 说明 |")
            L.append("|------|------|------|")
            for i in sc:
                L.append(f"| `{i.attr}` | {i.file}:{i.line} | {i.detail} |")
        if not cw and not sc:
            L.append("\n✅ 状态标志生命周期正常。\n")
    else:
        L.append("\n（未启用）\n")

    # 8.7 状态机合并方向仲裁（规范 H）
    L.append("\n## 8.7 状态机合并方向仲裁（数量仲裁 vs 版本仲裁）\n")
    L.append("> 捕获同步/合并函数用「消息数量比较」决定覆盖方向、却无版本/时间戳字段参与：")
    L.append("> 数量相等而内容不同时新旧无法识别，旧存储可能反向覆盖新数据（加载旧会话的根因）。\n")
    if merge:
        cma = [i for i in merge if i.kind == "count_only_arbitration"]
        L.append(f"\n**count_only_arbitration {len(cma)}**\n")
        if cma:
            L.append("\n### 🔴 数量仲裁无版本字段\n")
            L.append("| 函数 | 位置 | 说明 |")
            L.append("|------|------|------|")
            for i in cma:
                L.append(f"| `{i.fn}` | {i.file}:{i.line} | {i.detail} |")
        else:
            L.append("\n✅ 合并方向均携带版本仲裁或无需合并。\n")
    else:
        L.append("\n（未启用）\n")

    # 8.8 标识符命名空间来源契约（规范 J）
    L.append("\n## 8.8 标识符命名空间来源契约（跨命名空间 key 误用 · 无守卫消费者）\n")
    L.append("> 存储系统把「标识符」当 key 用，而标识符有命名空间（cp-* / sess_* / sqlite id）。")
    L.append("> 捕获把另一命名空间的 ID 传给本系统消费点（查询必 miss / 误删），")
    L.append("> 以及消费者函数直接把 key 用于存储查找而无前缀守卫（防御缺失）。\n")
    if id_source:
        ck = [i for i in id_source if i.kind == "cross_namespace_key"]
        ug = [i for i in id_source if i.kind == "unguarded_key_consumer"]
        L.append(f"\n**cross_namespace_key {len(ck)} · unguarded_key_consumer {len(ug)}**\n")
        if ck:
            L.append("\n### 🔴 跨命名空间 key 误用\n")
            L.append("| 消费点 | key 实参 | 位置 | 说明 |")
            L.append("|--------|----------|------|------|")
            for i in ck:
                L.append(f"| `{i.consumer}()` | `{i.key_arg}` | {i.file}:{i.line} | {i.detail} |")
        if ug:
            L.append("\n### 🟠 消费者无命名空间守卫\n")
            L.append("| 消费者 | key 形参 | 位置 | 说明 |")
            L.append("|--------|----------|------|------|")
            for i in ug:
                L.append(f"| `{i.consumer}()` | `{i.key_arg}` | {i.file}:{i.line} | {i.detail} |")
        if not ck and not ug:
            L.append("\n✅ 所有存储消费点的 key 均来自同命名空间创建点，且有前缀守卫。\n")
    else:
        L.append("\n（未启用）\n")

    # 9. 硬编码常量
    L.append(f"\n## 9. 硬编码常量（{len(hardcoded) if hardcoded else 0}）\n")
    if hardcoded:
        L.append("| 文件 | 行 | 类型 | 值 | 上下文 |")
        L.append("|------|----|------|----|--------|")
        for i in hardcoded[:30]:
            L.append(f"| {i.file} | {i.line} | `{i.kind}` | `{i.value[:60]}` | {i.context[:30]} |")
        if len(hardcoded) > 30:
            L.append(f"| ... | ... | ... | 共 {len(hardcoded)} 条，详见 hardcoded.csv |")
    else:
        L.append("未检测到硬编码常量。\n")

    # 10. 环境变量读取
    L.append(f"\n## 10. 环境变量读取（{len(env_vars) if env_vars else 0}）\n")
    if env_vars:
        L.append("| 文件 | 行 | 变量名 | 默认值 | 上下文 |")
        L.append("|------|----|--------|--------|--------|")
        for i in env_vars[:30]:
            L.append(f"| {i.file} | {i.line} | `{i.name}` | `{i.default or '—'}` | {i.context[:30]} |")
        if len(env_vars) > 30:
            L.append(f"| ... | ... | ... | 共 {len(env_vars)} 条，详见 env_vars.csv |")
    else:
        L.append("未检测到环境变量读取。\n")

    # 11. 数据池/状态
    L.append(f"\n## 11. 数据池/状态（{len(data_pools) if data_pools else 0}）\n")
    if data_pools:
        L.append("| 文件 | 行 | 名称 | 类型 | 规模 | 上下文 |")
        L.append("|------|----|------|------|------|--------|")
        for i in data_pools[:30]:
            L.append(f"| {i.file} | {i.line} | `{i.name}` | `{i.kind}` | {i.size_hint[:30]} | {i.context[:20]} |")
        if len(data_pools) > 30:
            L.append(f"| ... | ... | ... | 共 {len(data_pools)} 条，详见 data_pools.csv |")
    else:
        L.append("未检测到数据池/状态。\n")

    # 12. 静态资源路径
    L.append(f"\n## 12. 静态资源路径（{len(static_resources) if static_resources else 0}）\n")
    if static_resources:
        L.append("| 文件 | 行 | 路径 | 类型 | 上下文 |")
        L.append("|------|----|------|------|--------|")
        for i in static_resources[:30]:
            L.append(f"| {i.file} | {i.line} | `{i.path[:60]}` | `{i.kind}` | {i.context[:30]} |")
        if len(static_resources) > 30:
            L.append(f"| ... | ... | ... | 共 {len(static_resources)} 条，详见 static_resources.csv |")
    else:
        L.append("未检测到静态资源路径。\n")

    # 13. 依赖链（亲属追逐）
    L.append(build_dep_sections(endpoints))

    # 14. 链路参考（index.json 指针）
    if index_models:
        L.append("\n## 14. 接口索引（index.json）\n")
        L.append("```json")
        L.append(json.dumps(index_models, ensure_ascii=False, indent=1)[:6000])
        L.append("```")

    return "\n".join(L)
