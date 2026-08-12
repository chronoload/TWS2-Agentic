# 原子：cmd_doc（原 plan_cli.py 第 1767 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_doc(args) -> int:
    """自举导出 CLI 命令文档：从 argparse 定义 + 反射生成两份文档——使用文档(PLAN_CLI.md) + 开发文档(PLAN_CLI_DEV.md)。"""
    ap = _build_parser()
    lines = ["# PLAN CLI 命令参考（自举生成）",
             "",
             "> 由 `python mcp/plan_cli.py doc` 从 argparse 定义自动生成，勿手改。",
             "",
             "所有命令以 `python mcp/plan_cli.py <命令> [子命令] [参数]` 运行。",
             ""]
    lines.append("## 命令总览")
    lines.append("")
    for sa in [a for a in ap._actions if isinstance(a, argparse._SubParsersAction)]:
        for name, subp in sa.choices.items():
            desc = _choice_help(sa, name) or subp.description or ""
            lines.append(f"- `{name}` — {desc}")
    lines.append("")
    lines.append("## 命令详情")
    _doc_walk(ap, 1, lines)
    lines.append("")

    out = Path(args.out) if args.out else MCP_ROOT / "docs" / "PLAN_CLI.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[doc] 使用文档 → {out}")

    # ── 开发文档（反射生成） ──
    dev_lines = ["# PLAN CLI 开发文档（自举生成）",
                 "",
                 "> 由 `python mcp/plan_cli.py doc --dev` 从源码反射生成，勿手改。",
                 "> 包含：数据模型/SQLite 表结构、命令→函数映射、TDD 检查规则、常量清单、扩展指南。",
                 ""]

    # 反射：SQLite 表结构
    dev_lines.append("## SQLite 数据模型（自反射 `_connect` 的 CREATE TABLE）")
    dev_lines.append("")
    dev_lines.append("> 由 `_reflect_db_schema` 从 `_connect` 函数体的 CREATE TABLE 语句自动解析。")
    dev_lines.append("")
    for table, cols in _reflect_db_schema():
        dev_lines.append(f"### `{table}`")
        dev_lines.append("")
        dev_lines.append("| 列名 | 类型 | 默认值 |")
        dev_lines.append("|------|------|--------|")
        for col_name, col_type, col_default in cols:
            dev_lines.append(f"| `{col_name}` | `{col_type}` | `{col_default or '—'}` |")
        dev_lines.append("")

    # 反射：命令→函数映射
    dev_lines.append("## 命令→处理函数映射（自反射 `_dispatch` 的 return 链）")
    dev_lines.append("")
    dev_lines.append("> 由 `_reflect_dispatch_map` 从 `_dispatch` 函数体自动解析。")
    dev_lines.append("")
    dev_lines.append("| 命令 | 子命令 | 处理函数 |")
    dev_lines.append("|------|--------|----------|")
    for cmd, sub_cmd, func in _reflect_dispatch_map():
        sub_display = f"`{sub_cmd}`" if sub_cmd else "—"
        dev_lines.append(f"| `{cmd}` | {sub_display} | `{func}()` |")
    dev_lines.append("")

    # 反射：TDD 检查规则
    dev_lines.append("## TDD 检查规则（自反射 `cmd_tdd_check`）")
    dev_lines.append("")
    dev_lines.append("> 由 `_reflect_tdd_rules` 从 `cmd_tdd_check` 函数体自动提取规则定义。")
    dev_lines.append("")
    dev_lines.append("| kind | 标签 | 严重度 |")
    dev_lines.append("|------|------|--------|")
    for kind, label, severity in _reflect_tdd_rules():
        dev_lines.append(f"| `{kind}` | {label} | `{severity}` |")
    dev_lines.append("")

    # 反射：模块级常量
    dev_lines.append("## 模块级常量（自反射 `module.__dict__`）")
    dev_lines.append("")
    dev_lines.append("> 由 `_reflect_constants` 从模块级 `UPPER_CASE` 变量自动提取。")
    dev_lines.append("")
    dev_lines.append("| 常量名 | 值 |")
    dev_lines.append("|--------|----|")
    for name, val in _reflect_constants():
        dev_lines.append(f"| `{name}` | `{val}` |")
    dev_lines.append("")

    # 扩展指南
    dev_lines.append("## 如何扩展（反射代码结构指南）")
    dev_lines.append("")
    dev_lines.append("### 新增数据库表")
    dev_lines.append("1. 在 `_connect` 函数的 `conn.execute(\"\"\"CREATE TABLE IF NOT EXISTS ...\"\"\")` 追加建表语句")
    dev_lines.append("2. 在 `_migrate` 函数追加 `ALTER TABLE` 兼容旧库")
    dev_lines.append("3. 重跑 `doc` 命令，表结构文档自动更新")
    dev_lines.append("")
    dev_lines.append("### 新增子命令")
    dev_lines.append("1. 在 `_build_parser` 的对应 `subparsers` 中添加 `add_parser('sub', help='...')`")
    dev_lines.append("2. 在 `_dispatch` 中添加 `if args.cmd == 'xxx': return cmd_xxx(args)`")
    dev_lines.append("3. 实现 `cmd_xxx(args)` 函数")
    dev_lines.append("4. 重跑 `doc` 命令，命令映射文档自动更新")
    dev_lines.append("")
    dev_lines.append("### 新增 TDD 检查规则")
    dev_lines.append("1. 在 `cmd_tdd_check` 函数的 `rules` 字典追加条目")
    dev_lines.append("2. 每条规则：`kind: {label: '...', severity: 'red/orange/yellow'}`")
    dev_lines.append("3. 重跑 `doc` 命令，规则文档自动更新")
    dev_lines.append("")
    dev_lines.append("### 全局常量/变量清单（反射函数）")
    dev_lines.append("")
    dev_lines.append("| 反射函数 | 提取对象 |")
    dev_lines.append("|----------|----------|")
    dev_lines.append("| `_reflect_db_schema()` | SQLite 表结构（CREATE TABLE 语句解析） |")
    dev_lines.append("| `_reflect_dispatch_map()` | 命令→处理函数映射（_dispatch return 链解析） |")
    dev_lines.append("| `_reflect_tdd_rules()` | TDD 检查规则（cmd_tdd_check 规则字典解析） |")
    dev_lines.append("| `_reflect_constants()` | 模块级 UPPER_CASE 常量 |")
    dev_lines.append("")

    dev_out = out.parent / "PLAN_CLI_DEV.md"
    dev_out.write_text("\n".join(dev_lines), encoding="utf-8")
    print(f"[doc] 开发文档 → {dev_out}")

    return 0
