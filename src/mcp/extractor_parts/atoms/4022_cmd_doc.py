# 原子：cmd_doc（原 interface_chain_extractor.py 第 4022 行）
# 逻辑组：cli · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def cmd_doc(args) -> int:
    """自举导出两份文档：使用文档(EXTRACTOR_DOC.md) + 开发文档(EXTRACTOR_DEV_DOC.md)，均从源码反射生成。"""
    # ── 使用文档 ──
    usage_lines = ["# Interface Chain Extractor 使用文档（自举生成）",
             "",
             "> 由 `python mcp/interface_chain_extractor.py --doc` 从 argparse 定义 + 产物清单常量"
             "自动生成，勿手改。改参数/产物文件名 → 只改代码，重跑 `--doc` 即可。",
             "",
             "运行方式：`python mcp/interface_chain_extractor.py [参数]`（TS2 默认 8 维全量流程），"
             "或 `--root <项目根>` / `--preset <name>` 通用项目模式。",
             "",
             "## 命令参数",
             ""]
    ap = argparse.ArgumentParser(description="TS2 接口链路提取器（仅内置模块）")
    ap.add_argument("--json", action="store_true", help="额外输出 JSON 索引")
    ap.add_argument("--md", action="store_true", help="额外输出 Markdown 文档")
    ap.add_argument("--out", type=str, default=str(MCP_ROOT / "docs"), help="输出目录（默认 mcp/docs）")
    ap.add_argument("--no-defuse", action="store_true", help="跳过 def-use 属性一致性检查")
    ap.add_argument("--defuse-files", action="append", default=None, metavar="FILE",
                    help="def-use 检查的额外 Python 文件（可多次指定，用于其他项目/语言适配）")
    ap.add_argument("--root", type=str, default="",
                    help="通用项目分析模式：指定任意 Python 项目根目录，输出模块地图+跨模块调用链")
    ap.add_argument("--exclude", action="append", default=None, metavar="DIR",
                    help="--root 模式下排除的子目录名（可多次指定）")
    ap.add_argument("--preset", type=str, default="", help="预设项目一键分析（ts2 / kimi，--presets-file 追加自定义）")
    ap.add_argument("--presets-file", type=str, default="", help="自定义预设 JSON 文件")
    ap.add_argument("--list-presets", action="store_true", help="列出可用预设")
    ap.add_argument("--frontend", type=str, default="",
                    help="前端入口文件（--root/--preset 模式）：生成 FRONTEND_TRACE.md")
    ap.add_argument("--frontend-class", type=str, default="", help="前端 client 类名（默认 TS2Client）")
    ap.add_argument("--client", type=str, default="client", help="前端调用点变量名（默认 client）")
    ap.add_argument("--no-db", action="store_true", help="--root/--preset 模式跳过 SQLite 输出")
    ap.add_argument("--no-chain", action="store_true", help="--root/--preset 模式跳过端点依赖链章节")
    ap.add_argument("--plugin", action="append", default=None, metavar="LANG:PATH", help="外部扫描插件")
    ap.add_argument("--plugins-dir", type=str, default="", help="批量插件目录")
    ap.add_argument("--doc", action="store_true", help="自文档反射：生成 EXTRACTOR_DOC.md + EXTRACTOR_DEV_DOC.md")
    ap.add_argument("--doc-out", type=str, default="", help="--doc 输出目录（默认 mcp/docs）")
    for a in ap._actions:
        if a.dest == "help":
            continue
        usage_lines.append(f"- {_extractor_arg_help(a)}")

    usage_lines.append("")
    usage_lines.append("## 产物清单（自文档反射：与写文件共用 EXTRACTOR_ARTIFACTS 常量）")
    usage_lines.append("")
    usage_lines.append("| 文件名 | 内容 |")
    usage_lines.append("|--------|------|")
    for name, desc in EXTRACTOR_ARTIFACTS:
        usage_lines.append(f"| `{name}` | {desc} |")
    usage_lines.append("")
    usage_lines.append("> 补充：TS2 默认流程 `interface_chain_index.json` 与 `interface_chain.db` "
                 "与 CSV 均覆盖更新；`--root/--preset` 模式额外产出上述通用模式文件，"
                 "并默认生成 `interface_chain.db`（--no-db 关闭）。")
    usage_lines.append("")

    # 使用文档：预设清单
    usage_lines.append("## 内置预设（--preset，--list-presets 查看）")
    usage_lines.append("")
    presets = _load_presets(args.presets_file if getattr(args, "presets_file", "") else "")
    if presets:
        for name, p in presets.items():
            usage_lines.append(f"- `{name}`：root=`{p['root']}` out=`{p.get('out', name)}` "
                         f"exclude={p.get('exclude', [])}")
    else:
        usage_lines.append("-（无，或见 --list-presets）")
    usage_lines.append("")

    # ── 开发文档（反射生成） ──
    dev_lines = ["# Interface Chain Extractor 开发文档（自举生成）",
                 "",
                 "> 由 `python mcp/interface_chain_extractor.py --doc` 从源码反射生成，勿手改。",
                 "> 包含：数据结构、扫描函数、正则模式、扫描机制、扩展指南。",
                 ""]

    # 反射：4 类扫描 dataclass schema
    dev_lines.append("## 扫描数据结构（自反射 dataclass 字段）")
    dev_lines.append("")
    dev_lines.append("> 由 `_reflect_dataclass_fields` 从 `@dataclass` 定义自动提取，"
                 "新增字段 → 文档自动更新。")
    dev_lines.append("")
    for cls_name, cls, desc in _reflect_dataclass_schemas():
        dev_lines.append(f"### `{cls_name}` — {desc}")
        dev_lines.append("")
        dev_lines.append("| 字段 | 类型 | 默认值 |")
        dev_lines.append("|------|------|--------|")
        for fname, ftype, fdefault in _reflect_dataclass_fields(cls):
            dev_lines.append(f"| `{fname}` | `{ftype}` | `{fdefault}` |")
        dev_lines.append("")

    # 反射：模块函数总表（全量暴露）
    dev_lines.append("## 模块函数总表（自反射，全量暴露）")
    dev_lines.append("")
    dev_lines.append("> 由 `_reflect_scan_functions` 反射**模块所有顶层函数**（签名/行数/说明），"
                 "新增/改签名 → 重跑 `--doc` 自动更新，不维护白名单。")
    dev_lines.append("")
    dev_lines.append("| 函数 | 签名 | 行数 |")
    dev_lines.append("|------|------|------|")
    for info in _reflect_scan_functions():
        dev_lines.append(f"| `{info['name']}` | `{info['signature']}` | {info['lines']} |")
    dev_lines.append("")

    # 反射：默认排除目录
    dev_lines.append("## 默认排除目录（自反射 `_SCAN_DEFAULT_EXCLUDE`）")
    dev_lines.append("")
    dev_lines.append(f"`{'`, `'.join(_reflect_exclude_dirs())}`")
    dev_lines.append("")

    # 反射：正则模式
    dev_lines.append("## 识别正则模式（自反射 re.Pattern.pattern）")
    dev_lines.append("")
    dev_lines.append("> 由 `_reflect_regex_patterns` 从全局 `re.compile(...)` 变量自动提取。")
    dev_lines.append("")
    dev_lines.append("| 变量名 | pattern |")
    dev_lines.append("|--------|---------|")
    for vname, pat in _reflect_regex_patterns():
        dev_lines.append(f"| `{vname}` | `{pat[:120]}` |")
    dev_lines.append("")

    # 反射：数据池 kind 映射
    dev_lines.append("## 数据池 kind 映射（自反射 `_DATA_POOL_KINDS`）")
    dev_lines.append("")
    dev_lines.append("> 由 `_reflect_data_pool_kinds` 从 `_DATA_POOL_KINDS` dict 自动提取。")
    dev_lines.append("")
    dev_lines.append("| kind | 匹配正则 |")
    dev_lines.append("|------|---------|")
    for kind, pat in _reflect_data_pool_kinds():
        dev_lines.append(f"| `{kind}` | `{pat[:120]}` |")
    dev_lines.append("")

    # 反射：扫描实现机制说明
    dev_lines.append("## 扫描实现机制（自反射源码结构）")
    dev_lines.append("")
    dev_lines.append("> 以下说明从 `_reflect_scan_functions` + AST 结构反射生成，描述每类扫描的工作方式。")
    dev_lines.append("")
    dev_lines.append("### 硬编码常量扫描 (`scan_hardcoded`)")
    dev_lines.append("")
    dev_lines.append("| 源 | 识别方式 | 提取 kind |")
    dev_lines.append("|----|----------|-----------|")
    dev_lines.append("| Python | AST `ast.walk`：模块级 `Assign`（字符串/数值常量）、`AnnAssign`、函数默认参数 | url, port, path, key, secret |")
    dev_lines.append("| JS/TS | 正则 `_HARDCODE_URL_RE` / `_HARDCODE_PORT_RE` / `_HARDCODE_PATH_RE` / `_HARDCODE_KEYWORDS` | url, port, path, key, secret |")
    dev_lines.append("")
    dev_lines.append("**局限**：JS/TS 正则粗扫可能误报 CSS/SVG 中的 URL；Python 侧仅提取模块级和类级常量，不追踪局部变量。")
    dev_lines.append("")
    dev_lines.append("### 环境变量扫描 (`scan_env_vars`)")
    dev_lines.append("")
    dev_lines.append("| 源 | 识别方式 | 提取信息 |")
    dev_lines.append("|----|----------|----------|")
    dev_lines.append("| Python | AST：`os.environ.get(name, default)` / `os.environ[name]` / `os.getenv(name, default)` | name, default |")
    dev_lines.append("| JS/TS | 正则 `_ENV_VAR_JS_RE`：`process.env['XXX']` / `process.env.XXX` | name |")
    dev_lines.append("")
    dev_lines.append("**局限**：不识别 `dotenv` / `configparser` / `pydantic_settings` 等间接配置读取；不追踪 `os.environ` 变量的传递链。")
    dev_lines.append("")
    dev_lines.append("### 数据池/状态扫描 (`scan_data_pools`)")
    dev_lines.append("")
    dev_lines.append("| 源 | 识别方式 | 提取 kind |")
    dev_lines.append("|----|----------|-----------|")
    dev_lines.append("| Python | AST：模块级 `Assign`（dict/list/Singleton/cache/pool/store 命名）、类属性 `self.*_cache` 等 | cache, pool, store, agent_pool, model_cache, vector_store, singleton, dict, list |")
    dev_lines.append("| JS/TS | 正则：`(const\\|let\\|var)\\s+(\\w*[Cc]ache\\w*)\\s*=` 等 | cache, pool, store, agent_pool, model_cache, vector_store, singleton |")
    dev_lines.append("")
    dev_lines.append("**局限**：基于命名模式匹配，可能漏报非标准命名的数据池（如 `_buf` / `_tbl`），也可能误报普通变量。")
    dev_lines.append("")
    dev_lines.append("### 静态资源扫描 (`scan_static_resources`)")
    dev_lines.append("")
    dev_lines.append("| 源 | 识别方式 | 提取 kind |")
    dev_lines.append("|----|----------|-----------|")
    dev_lines.append("| Python | AST：`StaticFiles(...)` / `statics(...)` / `express.static(...)` 挂载、`open(...)` / `Path(...)` 文件 IO、路径字面量（html/css/js/image/font/pdf 等扩展名） | static_files, express_static, template, image, font, css, js, io_path |")
    dev_lines.append("| JS/TS | 正则 `_STATIC_FILE_RE` / `_IO_PATH_RE` / `_PATH_LITERAL_RE` | express_static, io_path, template, image, font, css, js |")
    dev_lines.append("")
    dev_lines.append("**局限**：路径字面量仅识别带扩展名的字符串，不追踪变量传递（如 `BASE + 'index.html'`）。")
    dev_lines.append("")

    # 反射：扩展指南
    dev_lines.append("## 如何扩展（自反射代码结构指南）")
    dev_lines.append("")
    dev_lines.append("> 以下说明基于反射代码结构生成，告诉你加什么、改什么。")
    dev_lines.append("")
    dev_lines.append("### 新增一类扫描维度")
    dev_lines.append("1. **新增 dataclass**：在现有 dataclass 区域（文件开头）添加 `@dataclass class XxxItem`")
    dev_lines.append("   - 字段需包含 `file: str` / `line: int` / 业务字段 / `context: str = ''`")
    dev_lines.append("2. **新增扫描函数**：`def scan_xxx(root, files, exclude)` → 返回 `list[XxxItem]`")
    dev_lines.append("   - Python 侧用 `ast.walk` 遍历，JS/TS 侧用正则匹配")
    dev_lines.append("3. **新增 CSV 产物**：在 `EXTRACTOR_ARTIFACTS` 追加 `('xxx.csv', '说明')`")
    dev_lines.append("4. **集成到 cmd_project**：在 `cmd_project` 中调用 `scan_xxx`，写 CSV，追加 Markdown 章节")
    dev_lines.append("5. **集成到 main**：在 TS2 默认流程中调用 `scan_xxx`，写 CSV + SQLite，追加统计")
    dev_lines.append("6. **扩展 SQLite**：在 `_write_sqlite` 新增 CREATE TABLE + INSERT")
    dev_lines.append("7. **重跑 `--doc`**：文档自动更新")
    dev_lines.append("")
    dev_lines.append("### 修改排除目录")
    dev_lines.append("```python")
    dev_lines.append("_SCAN_DEFAULT_EXCLUDE = ('test', 'tests', ...)  # 直接修改元组")
    dev_lines.append("```")
    dev_lines.append("")
    dev_lines.append("### 修改正则匹配规则")
    dev_lines.append("```python")
    dev_lines.append("_HARDCODE_KEYWORDS = re.compile(r'(api[_-]?key|secret|...)', re.I)  # 直接修改")
    dev_lines.append("_HARDCODE_URL_RE = re.compile(r'https?://[^\\s\\'\"<>]+')  # 直接修改")
    dev_lines.append("```")
    dev_lines.append("")
    dev_lines.append("### 修改数据池 kind 映射")
    dev_lines.append("```python")
    dev_lines.append("_DATA_POOL_KINDS = {")
    dev_lines.append("    'cache': re.compile(r'(?:cache|_cache|Cache)'),")
    dev_lines.append("    ...")
    dev_lines.append("}  # 新增 kind 只需追加条目")
    dev_lines.append("```")
    dev_lines.append("")

    # 反射函数清单
    dev_lines.append("### 全局常量/变量清单（自反射 `_reflect_*` 函数）")
    dev_lines.append("")
    dev_lines.append("| 反射函数 | 提取对象 |")
    dev_lines.append("|----------|----------|")
    dev_lines.append("| `_reflect_dataclass_fields(cls)` | dataclass 字段名/类型/默认值 |")
    dev_lines.append("| `_reflect_scan_functions()` | 扫描函数签名/文档/行数 |")
    dev_lines.append("| `_reflect_regex_patterns()` | 全局正则 `re.compile` 变量 |")
    dev_lines.append("| `_reflect_data_pool_kinds()` | `_DATA_POOL_KINDS` dict 映射 |")
    dev_lines.append("| `_reflect_exclude_dirs()` | `_SCAN_DEFAULT_EXCLUDE` 元组 |")
    dev_lines.append("| `_reflect_dataclass_schemas()` | 4 个 dataclass 元信息 |")
    dev_lines.append("")

    # 行为契约规则表
    dev_lines.append("## 行为契约规则表（BEHAVIOR_RULES，声明式）")
    dev_lines.append("")
    dev_lines.append("| 入口函数 | must-call 目标（任一命中即满足，全缺才报缺陷） |")
    dev_lines.append("|----------|----------------------------------------------|")
    for entry, targets in BEHAVIOR_RULES.items():
        dev_lines.append(f"| `{entry}` | {', '.join(f'`{t}`' for t in targets)} |")
    dev_lines.append("")
    dev_lines.append("> 入口规则全局匹配：同名入口在多文件出现时各自独立检查；"
                 "所有文件都找不到入口才报「规则失效」（规则过期或改名）。")
    dev_lines.append("")

    # 标识符命名空间来源契约规则表
    dev_lines.append("## 标识符命名空间来源契约规则表（ID_SOURCE_RULES，声明式）")
    dev_lines.append("")
    dev_lines.append("| 命名空间 | 前缀 | 消费者 | conflict_hints | 需守卫 |")
    dev_lines.append("|----------|------|--------|----------------|--------|")
    for r in ID_SOURCE_RULES:
        hints = ", ".join(r.get("conflict_hints", ()))
        dev_lines.append(f"| `{r.get('ns')}` | `{r.get('prefix')}` | "
                     f"{', '.join(f'`{c}`' for c in r.get('consumers', ()))} | "
                     f"{hints or '—'} | {r.get('guard')} |")
    dev_lines.append("")

    # ── 写入两份文档 ──
    out_dir = Path(args.out) if getattr(args, "out", "") else MCP_ROOT / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    usage_out = out_dir / "EXTRACTOR_DOC.md"
    usage_out.write_text("\n".join(usage_lines), encoding="utf-8")
    print(f"[doc] 使用文档 → {usage_out}")

    dev_out = out_dir / "EXTRACTOR_DEV_DOC.md"
    dev_out.write_text("\n".join(dev_lines), encoding="utf-8")
    print(f"[doc] 开发文档 → {dev_out}")

    return 0
