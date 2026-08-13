# 原子：_project_md（原 interface_chain_extractor.py 第 2798 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _project_md(modules, funcs, edges, root, endpoints=None, models=None,
                hardcoded=None, env_vars=None, data_pools=None, static_resources=None) -> str:
    L: list[str] = []
    L.append(f"# 项目调用链分析（--root 模式，自动生成）\n")
    L.append(f"> 根目录: `{root}` · 模块 {len(modules)} · 函数/方法 {len(funcs)} · 调用边 {len(edges)}\n")
    entries = [(f, m) for m in modules for f in m.entry_points]
    L.append("\n## 1. 入口点\n")
    if entries:
        for f, m in entries:
            L.append(f"- `{m.file}`: `{f}`")
    else:
        L.append("未检测到标准入口（main-guard / asyncio.run / uvicorn.run）。\n")
    L.append("\n## 2. 模块地图（按规模排序）\n")
    L.append("| 模块 | 文件 | 类 | 函数 | 行数 | 出度→ | 入度← | 入口 |")
    L.append("|------|------|----|------|------|-------|-------|------|")
    for m in sorted(modules, key=lambda x: x.lines, reverse=True):
        L.append(f"| `{m.module}` | {Path(m.file).name} | {m.classes} | {m.funcs} | {m.lines} "
                 f"| {m.out_degree} | {m.in_degree} | {'; '.join(m.entry_points) if m.entry_points else '—'} |")
    L.append("\n## 3. 枢纽模块（被跨模块调用 Top 15）\n")
    L.append("> 入度最高的模块是架构核心——对比时优先看这里。\n")
    hubs = sorted([m for m in modules if m.in_degree], key=lambda x: x.in_degree, reverse=True)[:15]
    if hubs:
        L.append("| 模块 | 入度 | 出度 | 行数 |")
        L.append("|------|------|------|------|")
        for m in hubs:
            L.append(f"| `{m.module}` | {m.in_degree} | {m.out_degree} | {m.lines} |")
    else:
        L.append("无跨模块调用（单文件项目？）。\n")
    xmod = [e for e in edges if e.dst_kind == "cross_module"]
    L.append(f"\n## 4. 跨模块调用边（共 {len(xmod)}，展示 Top 40）\n")
    if xmod:
        L.append("| 来源 | 目标 | 行 |")
        L.append("|------|------|----|")
        for e in xmod[:40]:
            L.append(f"| `{_rel_module(Path(e.src_file), root)}.{e.src_func}` | `{e.dst_module}.{e.dst}` | {e.line} |")
    else:
        L.append("无。\n")

    # 5. API 端点（复用 TS2 特化的 FastAPI/APIRouter 提取，loose 模式）
    L.append(f"\n## 5. API 端点（{len(endpoints) if endpoints else 0}）\n")
    if endpoints:
        L.append("| 方法 | 路径 | 函数 | 文件 | 行 | 请求模型 | 返回键 |")
        L.append("|------|------|------|------|----|----------|--------|")
        for ep in sorted(endpoints, key=lambda e: (e.path, e.method)):
            resp = ", ".join(f"`{k}`" for k in ep.response_keys[:6]) if ep.response_keys else "—"
            L.append(f"| {ep.method} | `{ep.path}` | `{ep.func}` | {Path(ep.file).name} | {ep.line} "
                     f"| {ep.request_model or '—'} | {resp} |")
    else:
        L.append("未检测到 `X.get/post/put/delete/patch('path')` 装饰器（非 web 项目或框架不同）。\n")

    # 6. 请求模型（Pydantic BaseModel）
    L.append(f"\n## 6. 请求模型（Pydantic BaseModel，{len(models) if models else 0}）\n")
    if models:
        L.append("| 模型 | 文件 | 行 | 字段数 |")
        L.append("|------|------|----|--------|")
        for m in sorted(models, key=lambda x: x.name):
            L.append(f"| `{m.name}` | {Path(m.file).name} | {m.line} | {len(m.fields)} |")
    else:
        L.append("未检测到 Pydantic BaseModel。\n")

    # 7. 硬编码常量
    L.append(f"\n## 7. 硬编码常量（{len(hardcoded) if hardcoded else 0}）\n")
    if hardcoded:
        L.append("| 文件 | 行 | 类型 | 值 | 上下文 |")
        L.append("|------|----|------|----|--------|")
        for i in hardcoded[:50]:
            L.append(f"| {i.file} | {i.line} | `{i.kind}` | `{i.value[:80]}` | {i.context[:40]} |")
        if len(hardcoded) > 50:
            L.append(f"| ... | ... | ... | 共 {len(hardcoded)} 条，详见 hardcoded.csv |")
    else:
        L.append("未检测到硬编码常量。\n")

    # 8. 环境变量读取
    L.append(f"\n## 8. 环境变量读取（{len(env_vars) if env_vars else 0}）\n")
    if env_vars:
        L.append("| 文件 | 行 | 变量名 | 默认值 | 上下文 |")
        L.append("|------|----|--------|--------|--------|")
        for i in env_vars[:50]:
            L.append(f"| {i.file} | {i.line} | `{i.name}` | `{i.default or '—'}` | {i.context[:40]} |")
        if len(env_vars) > 50:
            L.append(f"| ... | ... | ... | 共 {len(env_vars)} 条，详见 env_vars.csv |")
    else:
        L.append("未检测到环境变量读取。\n")

    # 9. 数据池/状态
    L.append(f"\n## 9. 数据池/状态（{len(data_pools) if data_pools else 0}）\n")
    if data_pools:
        L.append("| 文件 | 行 | 名称 | 类型 | 规模 | 上下文 |")
        L.append("|------|----|------|------|------|--------|")
        for i in data_pools[:50]:
            L.append(f"| {i.file} | {i.line} | `{i.name}` | `{i.kind}` | {i.size_hint[:40]} | {i.context[:30]} |")
        if len(data_pools) > 50:
            L.append(f"| ... | ... | ... | 共 {len(data_pools)} 条，详见 data_pools.csv |")
    else:
        L.append("未检测到数据池/状态。\n")

    # 10. 静态资源路径
    L.append(f"\n## 10. 静态资源路径（{len(static_resources) if static_resources else 0}）\n")
    if static_resources:
        L.append("| 文件 | 行 | 路径 | 类型 | 上下文 |")
        L.append("|------|----|------|------|--------|")
        for i in static_resources[:50]:
            L.append(f"| {i.file} | {i.line} | `{i.path[:80]}` | `{i.kind}` | {i.context[:40]} |")
        if len(static_resources) > 50:
            L.append(f"| ... | ... | ... | 共 {len(static_resources)} 条，详见 static_resources.csv |")
    else:
        L.append("未检测到静态资源路径。\n")

    return "\n".join(L)
