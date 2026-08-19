"""python -m macdev audit|plan|doc 入口。

audit  静态接口审计（亲属追逐依赖链 + 8 维分析 + 4 维扫描 + 双轨产物）
       子命令：audit chain stats|issues|endpoints|models|drifts|tables（定向查询 db）
plan   开发流程机器化（plan/task/step CRUD + export + verify/review/ledger/tdd + openspec）
doc    自举文档（从 argparse + Registry 反射生成使用/开发文档）
"""
from __future__ import annotations
import argparse, json, os, shutil, sys
from pathlib import Path
from .core.registry import Registry
from .core.bus import EventBus
from .core.engine import Engine
from .audit.task import AuditTask
from .skill import cmd_skill_inject, cmd_skill_list, cmd_skill_route, cmd_skill_scan

ARTIFACTS = [
    ("INTERFACE_CHAIN.md", "审计报告：端点/模型 + §8 亲属追逐依赖链(text+mermaid) + 6 维分析 + 4 维扫描"),
    ("interface_chain.db", "SQLite 全维度可查询索引（endpoints/models/drifts/defuse/behavior/flag/merge/id_source/扫描/stats）"),
    ("endpoints.csv / models.csv / drifts.csv", "端点/模型/漂移明细"),
    ("defuse_issues.csv / defuse_reads.csv", "def-use 缺陷与读取点"),
    ("behavior_issues.csv / flag_lifecycle.csv", "行为契约 / 状态标志缺陷"),
    ("merge_direction.csv / id_source.csv", "合并仲裁 / 命名空间缺陷"),
    ("hardcoded.csv / env_vars.csv / data_pools.csv / static_resources.csv", "4 维扫描明细"),
    ("events.ndjson", "全量事件流（机器可读，可重放）"),
]


def build_engine() -> Engine:
    reg = Registry()
    from . import audit, plan, patch, skill
    audit.register(reg)
    plan.register(reg)
    patch.register(reg)
    skill.register(reg)
    # 插件平级哲学：扫描捕捉所有已导入模块中的 Plugin 子类并装配
    from .audit import strategy_ts2  # noqa: F401（import 即登记 ts2 策略）
    from .audit import strategy_dsh  # noqa: F401（import 即登记 dsh 策略：TS monorepo 语义表）
    reg.discover()
    return Engine(reg, EventBus())


def _print_lines(code: int, lines: list) -> int:
    # Windows GBK 控制台无法编码 emoji（如 ⏳）：逐个尝试，失败降级为 ASCII 转义
    import sys as _sys
    for ln in lines:
        try:
            print(ln)
        except UnicodeEncodeError:
            try:
                # 终端是 GBK 但文本含 emoji → 用 backslashreplace 保留信息
                _sys.stdout.buffer.write((str(ln) + "\n").encode(
                    "utf-8", errors="backslashreplace"))
                _sys.stdout.buffer.flush()
            except Exception:
                print(str(ln).encode("ascii", errors="replace").decode("ascii", errors="replace"))
    return code


def _project_name(args) -> str:
    """产物目录名：显式 --project 优先，其次环境变量 MACDEV_PROJECT。"""
    return getattr(args, "project", "") or os.environ.get("MACDEV_PROJECT", "")


def _project_root(name: str) -> Path:
    """<name>-project 产物目录绝对路径（用户强制自演化 2026-08-16）：

    统一收敛到项目根的 docs/ 子目录：`<项目根>/docs/<name>-project/`。
    定位策略（健壮性）：从 cwd 逐级向上找 `docs/<name>-project`（优先），
    兼容旧版 `cwd/<name>-project`；均不存在则默认返回 `cwd/docs/<name>-project`
    （由调用方 mkdir 创建，如 project init / log add / audit）。
    """
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        cand_doc = d / "docs" / f"{name}-project"
        if cand_doc.exists():
            return cand_doc
        cand_legacy = d / f"{name}-project"
        if cand_legacy.exists():
            return cand_legacy
    return cwd / "docs" / f"{name}-project"


# ─── audit ───

def cmd_audit(args) -> int:
    engine = build_engine()
    task = AuditTask.from_json(Path(args.task), Path(args.root))
    if getattr(args, "timeout", 0) and args.timeout > 0:
        task.scan_timeout = args.timeout
    if getattr(args, "no_progress", False):
        task.progress = False
    # 产物目录：显式 --out 优先；--project/env 则收敛到 <name>-project/audit（重跑覆写）
    out = Path(args.out)
    pname = _project_name(args)
    if pname and (str(out) == "macdev_out" or not str(args.out)):
        out = _project_root(pname) / "audit"
    result = engine.run_audit(task, out)
    print(f"[macdev audit] ok={result.ok} " +
          " ".join(f"{k}={v}" for k, v in result.data.items()))
    if result.data.get("truncated"):
        print(f"[macdev audit] ⚠ 超时截断：仅汇报已扫描子集 "
              f"{result.data['scanned']}/{result.data['total']} 文件（结果不完整）")
    for a in result.artifacts:
        print(f"  artifact → {a}")
    return 0 if result.ok else 1


def cmd_audit_chain(args) -> int:
    """定向查询 interface_chain.db（替代 grep-read）。"""
    from .audit import chain_query
    fn = {"stats": chain_query.chain_stats,
          "issues": chain_query.chain_issues,
          "endpoints": chain_query.chain_endpoints,
          "models": chain_query.chain_models,
          "drifts": chain_query.chain_drifts,
          "tables": chain_query.chain_tables,
          "callers": chain_query.chain_callers,
          "kw": chain_query.chain_kw}[args.sub2]
    if args.sub2 == "stats":
        lines = fn(args.db)
    elif args.sub2 == "issues":
        lines = fn(args.db, count=getattr(args, "count", False),
                   kind=getattr(args, "kind", ""), file=getattr(args, "file", ""),
                   attr=getattr(args, "attr", ""))
    elif args.sub2 == "endpoints":
        lines = fn(args.db, by_file=getattr(args, "by_file", False),
                   path=getattr(args, "path", ""), func=getattr(args, "func", ""),
                   no_model=getattr(args, "no_model", False))
    elif args.sub2 == "models":
        lines = fn(args.db, dup=getattr(args, "dup", False), name=getattr(args, "name", ""))
    elif args.sub2 == "callers":
        lines = fn(args.db, func=getattr(args, "func", ""))
    elif args.sub2 == "kw":
        lines = fn(args.db, keyword=getattr(args, "keyword", ""))
    else:
        lines = fn(args.db)
    return _print_lines(0 if not lines or "库不存在" not in lines[0] else 1, lines)


# ─── plan ───

def _store(args) -> "PlanStore":
    from .plan.db import PlanStore
    # 产物目录：显式 --db 优先；--project/env 收敛到 <name>-project/plans.db
    db = Path(args.db) if args.db else None
    pname = _project_name(args)
    if db is None and pname:
        db = _project_root(pname) / "plans.db"
    return PlanStore(db=db or Path("plans.db"),
                     index_json=getattr(args, "index", ""),
                     req_db=getattr(args, "reqdb", ""))


def cmd_plan_create(args) -> int:
    from .plan import commands
    return _print_lines(*commands.cmd_create(_store(args), args.title, args.goal,
                                             args.arch, args.stack, args.constraints,
                                             name=args.name))


def cmd_plan_list(args) -> int:
    from .plan import commands
    return _print_lines(*commands.cmd_list(_store(args)))


def cmd_plan_update(args) -> int:
    from .plan import commands
    return _print_lines(*commands.cmd_update(_store(args), args.id,
                                             title=args.title, goal=args.goal,
                                             arch=args.arch, stack=args.stack,
                                             constraints=args.constraints, status=args.status))


def cmd_plan_delete(args) -> int:
    from .plan import commands
    return _print_lines(*commands.cmd_delete(_store(args), args.id))


def cmd_plan_task(args) -> int:
    from .plan import commands
    store = _store(args)
    if args.sub2 == "add":
        return _print_lines(*commands.cmd_task_add(store, args.plan, args.title, args.detail,
                                                   args.files, args.req, args.defect, args.interfaces))
    if args.sub2 == "list":
        return _print_lines(*commands.cmd_task_list(store, args.plan))
    if args.sub2 == "update":
        return _print_lines(*commands.cmd_task_update(store, args.id, title=args.title,
                                                      detail=args.detail, files=args.files,
                                                      req=args.req, defect=args.defect,
                                                      interfaces=args.interfaces,
                                                      status=args.status,
                                                      review_status=args.review_status,
                                                      review_findings=args.findings))
    if args.sub2 == "delete":
        return _print_lines(*commands.cmd_task_delete(store, args.id))
    return 1


def cmd_plan_step(args) -> int:
    from .plan import commands
    store = _store(args)
    if args.sub2 == "add":
        return _print_lines(*commands.cmd_step_add(store, args.task, args.text, args.action,
                                                   args.code, args.lang, args.run, args.expected))
    if args.sub2 == "list":
        return _print_lines(*commands.cmd_step_list(store, args.task))
    if args.sub2 == "update":
        return _print_lines(*commands.cmd_step_update(store, args.id, text=args.text,
                                                      action=args.action, status=args.status))
    if args.sub2 == "delete":
        return _print_lines(*commands.cmd_step_delete(store, args.id))
    return 1


def cmd_plan_export(args) -> int:
    from .plan.export import export_plan
    return _print_lines(*export_plan(_store(args), args.id, args.out, args.format)[:2])


def cmd_plan_verify(args) -> int:
    from .plan.workflow import cmd_verify
    return _print_lines(*cmd_verify(_store(args), args.plan, args.root))


def cmd_plan_review(args) -> int:
    from .plan.workflow import cmd_review
    return _print_lines(*cmd_review(_store(args), args.task, args.action, args.findings))


def cmd_plan_ledger(args) -> int:
    from .plan.workflow import cmd_ledger
    return _print_lines(*cmd_ledger(_store(args), args.plan, args.out)[:2])


def cmd_plan_tdd(args) -> int:
    from .plan.workflow import cmd_tdd_check
    return _print_lines(*cmd_tdd_check(_store(args)))


def cmd_plan_openspec(args) -> int:
    from .plan import openspec
    fn = {"list": lambda: openspec.cmd_list(args.cwd),
          "status": lambda: openspec.cmd_status(args.change, args.cwd),
          "import": lambda: openspec.cmd_import(args.change, args.cwd),
          "export": lambda: openspec.cmd_export(args.change, args.cwd),
          "sync-specs": lambda: openspec.cmd_sync_specs(args.change, args.cwd, args.req_cli),
          }[args.sub2]
    return _print_lines(*fn())


# ─── log（经验沉淀：与 plan 平级，SKILL.md 经验移入此处）───

def _pkg_root() -> Path:
    """随包经验库根：macdev 包同级 macdev-skill/（发布版随 skill 分发）。
    pyinstaller 打包后数据落在 sys._MEIPASS，需切换基准目录。"""
    base = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    return Path(base) / "macdev-skill"


def _log_store(args) -> "LogStore":
    from .log.db import LogStore
    # 库定位：显式 --db 始终优先；否则 scope=pkg → 随包库 macdev-skill/logs.db（包内保持干净）；
    # scope=project（随项目，最主要）必须指定 --project/env MACDEV_PROJECT → <name>-project/logs.db，
    # 全部项目产物跟随项目文件夹，不落到 cwd/包内
    db = Path(args.db) if getattr(args, "db", "") else None
    if db is None:
        scope = getattr(args, "scope", "") or "project"
        if scope == "pkg":
            db = _pkg_root() / "logs.db"
        else:
            pname = _project_name(args)
            if not pname:
                raise SystemExit(
                    "[log] 随项目经验必须指定 --project <name>（或 env MACDEV_PROJECT）；"
                    "随包经验用 --scope pkg，显式库用 --db")
            db = _project_root(pname) / "logs.db"
    return LogStore(db=db)


def cmd_log_add(args) -> int:
    from .log import commands
    return _print_lines(*commands.cmd_add(_log_store(args), args.title, args.category,
                                          body=args.body, tags=args.tags, refs=args.refs,
                                          file=args.file, scope=args.scope))


def cmd_log_list(args) -> int:
    from .log import commands
    return _print_lines(*commands.cmd_list(_log_store(args), category=args.category,
                                           tag=args.tag, scope=args.scope))


def cmd_log_get(args) -> int:
    from .log import commands
    return _print_lines(*commands.cmd_get(_log_store(args), args.id))


def cmd_log_query(args) -> int:
    from .log import commands
    return _print_lines(*commands.cmd_query(_log_store(args), args.keyword,
                                            category=args.category, scope=args.scope))


def cmd_log_export(args) -> int:
    from .log import commands
    return _print_lines(*commands.cmd_export(_log_store(args), args.out, scope=args.scope))


def cmd_log_delete(args) -> int:
    from .log import commands
    return _print_lines(*commands.cmd_delete(_log_store(args), args.id))


def cmd_log_update(args) -> int:
    from .log import commands
    return _print_lines(*commands.cmd_update(_log_store(args), args.id,
                                             category=args.category, title=args.title,
                                             body=args.body, tags=args.tags, refs=args.refs,
                                             scope=args.scope))


# ─── requirement（需求管理：CRUD + 规范接口对齐，双轨产物）───

def _req_store(args) -> "RequirementStore":
    from .requirement.db import RequirementStore
    # 产物收敛：显式 --db/--out/--index 优先；--project/env 则落到 <name>-project/
    db = Path(args.db) if getattr(args, "db", "") else None
    out = Path(args.out) if getattr(args, "out", "") else None
    idx = getattr(args, "index", "") or ""
    pname = _project_name(args)
    if pname:
        root = _project_root(pname)
        if db is None:
            db = root / "requirements.db"
        if out is None:
            out = root
        if not idx:
            idx = root / "interface_chain_index.json"
    return RequirementStore(db=db or Path("requirements.db"),
                            out_dir=out or Path(""), index_json=idx)


def cmd_requirement_add(args) -> int:
    from .requirement import commands
    return _print_lines(*commands.cmd_add(_req_store(args), args.kind, args.name,
                                          detail=args.detail, source=args.source))


def cmd_requirement_list(args) -> int:
    from .requirement import commands
    return _print_lines(*commands.cmd_list(_req_store(args), kind=args.kind, status=args.status))


def cmd_requirement_update(args) -> int:
    from .requirement import commands
    return _print_lines(*commands.cmd_update(_req_store(args), args.id,
                                             kind=args.kind, name=args.name,
                                             detail=args.detail, source=args.source,
                                             status=args.status))


def cmd_requirement_delete(args) -> int:
    from .requirement import commands
    return _print_lines(*commands.cmd_delete(_req_store(args), args.id))


def cmd_requirement_export(args) -> int:
    from .requirement import commands
    return _print_lines(*commands.cmd_export(_req_store(args), fmt=args.format))


def cmd_requirement_align(args) -> int:
    from .requirement import commands
    return _print_lines(*commands.cmd_align(_req_store(args), index=args.index,
                                            root=args.root, exclude=args.exclude))


def cmd_requirement_scan(args) -> int:
    from .requirement import commands
    return _print_lines(*commands.cmd_scan(_req_store(args), req_dirs=args.req_dirs,
                                           root=args.root, code=args.code,
                                           index=args.index, exclude=args.exclude))


# ─── dev（学习/模仿目标项目：目录编排 + 架构了解）───

def _dev_out(args) -> Path:
    """dev 产物目录：显式 --out 优先；--project/env → <name>-project/dev/<target名>/；否则 dev_out/<target名>/"""
    if getattr(args, "out", ""):
        return Path(args.out)
    base = Path(args.target).name or "target"
    pname = _project_name(args)
    if pname:
        return _project_root(pname) / "dev" / base
    return Path("dev_out") / base


def cmd_dev_map(args) -> int:
    from .dev import commands
    return _print_lines(*commands.cmd_map(target=args.target, out=_dev_out(args),
                                          depth=args.depth, exclude=args.exclude))


def cmd_dev_audit(args) -> int:
    from .dev import commands
    engine = build_engine()
    return _print_lines(*commands.cmd_audit(engine, target=args.target, out=_dev_out(args),
                                            strategy=args.strategy, exclude=args.exclude,
                                            timeout=args.timeout))


# ─── project（产物目录约定：<name>-project/ 收纳 audit/plan/log 全部产物）───

def cmd_project_init(args) -> int:
    from .project import commands
    return _print_lines(*commands.cmd_init(args.name, git=args.git, base=args.base))


def cmd_project_list(args) -> int:
    from .project import commands
    return _print_lines(*commands.cmd_list(base=args.base))


def cmd_project_root(args) -> int:
    from .project import commands
    return _print_lines(*commands.cmd_root(args.name, base=args.base))


# ─── patch（自演化：插件式修复）───

def cmd_patch_gen(args) -> int:
    """从审计缺陷生成固化补丁脚本（不改原文件；apply 为独立显式操作）。"""
    engine = build_engine()
    from .patch.gen import gen_patches
    out = Path(args.out)
    r = gen_patches(engine, args.db, Path(args.root), out)
    print(f"[macdev patch] issues={r.data['issues']} patches={r.data['patches']}")
    for a in r.artifacts:
        print(f"  patch → {a}")
    return 0 if r.ok else 1


def cmd_patch_apply(args) -> int:
    """应用补丁脚本（带备份，幂等）。"""
    from .patch.apply import apply_patch, apply_patches
    from .patch import load_patch
    root = Path(args.root)
    if args.patch:
        ok, msg, n = apply_patch(Path(args.patch), root, backup=not args.no_backup)
        print(msg)
        return 0 if ok else 1
    if args.dir:
        files = sorted(Path(args.dir).glob("*.py"))
        ok, messages = apply_patches(files, root, backup=not args.no_backup)
        for m in messages:
            print(m)
        return 0 if ok else 1
    print("[patch] 需 --patch 或 --dir")
    return 1


def cmd_patch_verify(args) -> int:
    """自演化闭环验证：补丁前后缺陷集合对比。"""
    from .patch.verify import verify_patches
    engine = build_engine()
    r = verify_patches(engine, args.before, args.after)
    if r.error:
        print(f"[patch] {r.error}")
        return 1
    print(f"[patch] verify 缺陷收敛: {r.data['total_before']} → {r.data['total_after']} "
          f"({'✅ 收敛' if r.ok else '❌ 未收敛'})")
    return 0 if r.ok else 1


def cmd_patch_plugins(args) -> int:
    """列出被抽象接口扫描捕捉的修复插件（插件平级展示）。"""
    from . import patch  # noqa: F401 触发 PatchPlugin 登记
    from .core.plugin import scan_plugins
    for cls in sorted(scan_plugins("patch.generator"), key=lambda c: c.name):
        mark = "🛠 自动修复" if getattr(cls, "auto_fix", False) else "📝 标注"
        print(f"  {mark} {cls.name}  ({cls.qualified_name()})")
    return 0


# ─── doc（自举：底层反射）───

def _registry_doc(reg) -> str:
    lines = ["| 命名空间 | 已注册项 |", "|----------|----------|"]
    for ns in reg.namespaces():
        lines.append(f"| `{ns}` | {', '.join(reg.names(ns))} |")
    return "\n".join(lines)


def _find_subparser(parser: argparse.ArgumentParser, name: str):
    """定位子命令 parser：遍历 _SubParsersAction，返回 (子parser, help_map)。"""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction) and name in action.choices:
            help_map = {c.dest: c.help for c in getattr(action, "_choices_actions", [])}
            return action.choices[name], help_map
    return None


def _arg_tree(parser: argparse.ArgumentParser, sub_path: list | None = None) -> str:
    """argparse 深度反射：递归展开子命令树，输出每条命令的完整参数
    （选项名 / 必填 / 默认值 / 可选值 / 帮助）。
    sub_path 指定子命令路径（如 ["log"] / ["requirement"]）时只渲染该子树——
    使用文档各插件只带自己的命令参数，不再整体重复全部命令树。"""
    lines = []

    def _walk(parser, path, help_text=""):
        cmd = " ".join(["macdev", *path]) if path else "macdev"
        # 命令标题：description 优先，无则用 add_parser(help=...) 的 help 兜底
        doc = parser.description or help_text or ""
        lines.append(f"`{cmd}`" + (f" — {doc}" if doc else ""))
        lines.append("")
        # 参数
        for a in parser._actions:
            if isinstance(a, argparse._SubParsersAction):
                continue
            # 隐藏项（--help 等）不进入文档：default 或 help 为 argparse.SUPPRESS 即跳过
            if a.default is argparse.SUPPRESS or a.help == argparse.SUPPRESS:
                continue
            opts = ", ".join(a.option_strings) if a.option_strings else a.dest
            req = "（必填）" if getattr(a, "required", False) else ""
            dflt = "" if a.default in (None, "", False) else f" 默认=`{a.default}`"
            chc = f" 可选=`{'/'.join(a.choices)}`" if a.choices else ""
            lines.append(f"- `{opts}`{req} — {a.help or ''}{chc}{dflt}")
        # 子命令
        sub = getattr(parser, "_subparsers", None)
        if sub:
            for action in getattr(sub, "_group_actions", []):
                if isinstance(action, argparse._SubParsersAction):
                    help_map = {c.dest: c.help for c in getattr(action, "_choices_actions", [])}
                    for name, p in action.choices.items():
                        if lines and lines[-1] != "":
                            lines.append("")
                        _walk(p, [*path, name], help_map.get(name, ""))
        return lines

    if sub_path:
        # 只渲染子命令子树：沿路径逐层定位，从目标命令开始 walk
        target = parser
        help_map = {}
        for name in sub_path:
            found = _find_subparser(target, name)
            if not found:
                return ""
            target, help_map = found
        _walk(target, sub_path, help_map.get(sub_path[-1], ""))
    else:
        _walk(parser, [])
    return "\n".join(lines)


def _module_funcs(mod) -> list:
    """反射模块所有顶层函数/类（含 _ 私有）：(name, kind, sig, line, doc)。"""
    import inspect
    out = []
    for name, obj in sorted(vars(mod).items()):
        if name == "__builtins__":
            continue
        if inspect.isfunction(obj) and obj.__module__ == mod.__name__:
            try:
                sig = str(inspect.signature(obj))
            except (ValueError, TypeError):
                sig = "(...)"
            doc = (inspect.getdoc(obj) or "").strip().split("\n")[0][:70]
            out.append((name, "def", sig, obj.__code__.co_firstlineno, doc))
        elif inspect.isclass(obj) and obj.__module__ == mod.__name__:
            doc = (inspect.getdoc(obj) or "").strip().split("\n")[0][:70]
            out.append((name, "class", "", 0, doc))
    return out


def _func_index_all(groups: dict, names: list | None = None) -> str:
    """全模块函数索引（底层反射）：{组名: [模块名, ...]} → markdown。
    暴露所有函数与类（含 _ 私有），不筛选、不手工挑选。
    names 给定组名列表时只输出对应组（dev 文档各自插件子集）。"""
    import importlib
    out = []
    items = list(groups.items())
    if names:
        items = [(n, groups[n]) for n in names if n in groups]
    for group, modnames in items:
        out.append(f"### {group}")
        for modname in modnames:
            try:
                mod = importlib.import_module(modname)
            except Exception as e:
                out.append(f"- `{modname}`：导入失败 {e}")
                continue
            short = modname.split(".", 1)[1].replace(".", "/") + ".py"
            out.append(f"\n**{short}**（{len(_module_funcs(mod))} 个顶层函数/类）")
            for name, kind, sig, line, doc in _module_funcs(mod):
                sig_txt = f"`{sig}`" if sig else ""
                out.append(f"- L{line} `{name}` {sig_txt} — {doc}")
        out.append("")
    return "\n".join(out)


def _modules() -> dict:
    """自举扫描目录：macdev 全部能力子模块（新增模块在此登记即被反射）。"""
    return {
        "core 微内核": ["macdev.core.plugin", "macdev.core.registry", "macdev.core.bus",
                       "macdev.core.types", "macdev.core.engine"],
        "audit 静态审计": ["macdev.audit.task", "macdev.audit.strategy", "macdev.audit.parse",
                         "macdev.audit.chain", "macdev.audit.analyze", "macdev.audit.scan",
                         "macdev.audit.report", "macdev.audit.chain_query"],
        "plan 开发流程": ["macdev.plan.model", "macdev.plan.db", "macdev.plan.commands",
                        "macdev.plan.workflow", "macdev.plan.export", "macdev.plan.openspec"],
        "requirement 需求对齐": ["macdev.requirement.db", "macdev.requirement.align",
                               "macdev.requirement.commands"],
        "dev 学习模仿": ["macdev.dev.commands"],
        "log 经验沉淀": ["macdev.log.db", "macdev.log.commands"],
        "project 产物目录": ["macdev.project.commands"],
        "patch 自演化修复": ["macdev.patch.model", "macdev.patch.rules", "macdev.patch.generators",
                          "macdev.patch.gen", "macdev.patch.apply", "macdev.patch.verify"],
    }


def cmd_doc(args) -> int:
    """自举：从 argparse 命令树 + Registry 注册表 + 模块函数底层反射生成使用/开发文档。
    代码为唯一事实源——新增命令/参数/函数，重跑 doc 即同步。"""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    engine = build_engine()
    reg = engine.registry
    ap = build_parser()
    arg_tree = _arg_tree(ap)
    func_index = _func_index_all(_modules())
    # 各插件使用文档只带自己的命令参数子树（不整体重复全部命令树）
    log_tree = _arg_tree(ap, ["log"])
    req_tree = _arg_tree(ap, ["requirement"])
    dev_tree = _arg_tree(ap, ["dev"])

    # AUDIT_DOC.md — 使用文档（audit + patch）
    audit_use = [
        "# macdev audit 使用文档（自举生成）", "",
        "> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。", "",
        "## 宏观用法（先整体，再定向）", "",
        "1. **宏观全景**：`python -m macdev audit --task task.json --root . --out out`",
        "   → INTERFACE_CHAIN.md（§8 亲属追逐依赖链 text 树 + mermaid + 断裂索引）。",
        "2. **定向查询**：`python -m macdev audit chain endpoints|issues|models|drifts|tables`",
        "   → 对 interface_chain.db 做 SQL 级查询，替代 grep-read。",
        "3. **缺陷闭环（附加值）**：缺陷清单用于修复，不是主产品。", "",
        "## 自演化补丁（插件式修复，与工厂平级）", "",
        "patch 不是直接改原文件——修复插件（PatchPlugin 子类）继承统一抽象接口 Plugin，",
        "被 `Registry.discover()` 扫描捕捉（namespace=patch.generator），与 audit.strategy 平级。",
        "审计缺陷 → `patch gen` 生成固化补丁脚本（产物，不改源码）；`patch apply` 显式应用；",
        "`patch verify` 重审计对比缺陷收敛。",
        "```",
        "python -m macdev patch gen --db out/interface_chain.db --root . --out patches/",
        "python -m macdev patch apply --dir patches/ --root .",
        "python -m macdev patch verify --before out/interface_chain.db --after out2/interface_chain.db",
        "python -m macdev patch plugins   # 列出被扫描捕捉的修复插件",
        "```", "",
        "## 命令参数树（argparse 底层反射）", "", "```", arg_tree, "```", "",
        "## 产物清单", "",
    ]
    for name, desc in ARTIFACTS:
        audit_use.append(f"- **{name}**：{desc}")
    audit_use += ["", "## 注册表能力", "", _registry_doc(reg), "",
                  "## 全部函数（模块底层反射）", "",
                  "见 **AUDIT_DEV_DOC.md**（开发文档承载完整函数索引，本文档只负责使用）。"]
    (out / "AUDIT_DOC.md").write_text("\n".join(audit_use) + "\n", encoding="utf-8")

    # PLAN.md — plan 使用文档
    plan_use = [
        "# macdev plan 使用文档（自举生成）", "",
        "> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。", "",
        "## 开发流程闭环", "",
        "```",
        "python -m macdev plan create --title \"接入新端点\" --goal \"目标\" --arch \"方案\" --stack \"FastAPI/JS\"",
        "python -m macdev plan task add --plan 1 --title \"实现后端\" --detail \"...\" --files \"Create: mcp/x.py`nModify: mcp/y.py:10-20\"",
        "python -m macdev plan step add --task 1 --text \"写失败测试\" --action test --code \"def test_x(): pass\" --lang python --run \"pytest -q\" --expected \"FAIL\"",
        "python -m macdev plan step update --id 1 --status done",
        "python -m macdev plan review --task 1 --action request",
        "python -m macdev plan verify --plan 1   # 完成门禁：TDD + 缺陷清零 + 测试就位 + review",
        "python -m macdev plan export --id 1 --out PLAN.md --format writing-plans",
        "python -m macdev plan ledger --plan 1   # 进度台账（resume 用）",
        "```", "",
        "## 命令参数树（argparse 底层反射）", "", "```", arg_tree, "```", "",
        "## 状态机（事件源）", "",
        "- plan: open → active → done → archived",
        "- task: open → in_progress → done；review: pending → review_requested → approved/needs_fix → review_requested",
        "- 状态变更 emit `plan.state.changed`（NDJSON 事件流可重放）", "",
        "## 注册表能力", "", _registry_doc(reg), "",
        "## 全部函数（模块底层反射）", "",
        "见 **PLAN_DEV.md**（开发文档承载完整函数索引，本文档只负责使用）。",
    ]
    (out / "PLAN.md").write_text("\n".join(plan_use) + "\n", encoding="utf-8")

    # LOG_DOC.md — log 使用文档（经验沉淀：与 plan 平级）
    log_use = [
        "# macdev log 使用文档（自举生成）", "",
        "> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。", "",
        "## 经验沉淀约定（不写 SKILL.md）", "",
        "经验/教训/模式/决策沉淀在 log 插件（SQLite logs.db 机器轨 + LOGS.md 人类轨），",
        "SKILL.md 只留指针，避免随包文档膨胀不通用。", "",
        "经验分**随项目**（project，最主要，须指定 `--project`，产物落 `<name>-project/`）与",
        "**随包**（pkg，`--scope pkg`，通用方法论落 macdev-skill/，包内保持干净）双轨；",
        "显式 `--db` 始终优先。", "",
        "## 四分类", "",
        "- **lessons**：工作流/方法论经验",
        "- **pitfalls**：踩坑与陷阱（命名空间、依赖误判、反射噪音等）",
        "- **patterns**：可复用实现模式（双轨产物、插件迁移等）",
        "- **decisions**：关键决策及理由（阈值、约定取舍等）", "",
        "## 命令速览", "",
        "```",
        "python -m macdev log add --project ts2 --title \"...\" --category pitfalls --body \"...\" --tags a,b --refs macdev/x.py",
        "python -m macdev log add --scope pkg --title \"...\" --category patterns --file notes.md   # 随包经验",
        "python -m macdev log list [--category pitfalls] [--tag a] [--scope project|pkg]",
        "python -m macdev log get --id 3",
        "python -m macdev log query --keyword glob [--category pitfalls] [--scope project|pkg]  # 全文检索",
        "python -m macdev log update --id 3 --status done [--scope project|pkg]",
        "python -m macdev log delete --id 3",
        "python -m macdev log export [--out LOGS.md] [--scope project|pkg]                     # 刷新人类轨",
        "```", "",
        "## 产物（双轨）", "",
        "- 机器轨：`logs.db`（SQLite，可 query 全文检索；scope 列区分归属）",
        "- 人类轨：`LOGS.md`（`log export` 生成，按 scope 分组）",
        "- 随项目：`--project <name>` → `<name>-project/logs.db` + `LOGS.md`（缺省会报错，不落 cwd）",
        "- 随包：`--scope pkg` → macdev-skill/logs.db + LOGS.md（随包经验库）", "",
        "## 命令参数树（argparse 底层反射，仅 log 子集）", "", "```", log_tree, "```", "",
        "## 注册表能力", "", _registry_doc(reg), "",
        "## 全部函数（模块底层反射）", "",
        "见 **LOG_DEV.md**（log 开发文档，含 log 组模块函数索引）。",
    ]
    (out / "LOG_DOC.md").write_text("\n".join(log_use) + "\n", encoding="utf-8")

    # REQI_DOC.md — requirement 使用文档（需求管理 + 规范接口对齐，双轨）
    req_use = [
        "# macdev requirement 使用文档（自举生成）", "",
        "> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。", "",
        "## 双轨产物约定（语言环境无关）", "",
        "需求以结构化条目存 `requirements.db`（机器权威）；任何变更自动刷新：",
        "- 人类轨：`REQUIREMENTS.md`",
        "- 机器轨：`requirements.json` / `requirements.csv`（主库快照）",
        "- 时间戳 UTC、编码 utf-8，不依赖宿主时区/locale", "",
        "## 命令速览", "",
        "```",
        "python -m macdev requirement add --kind interface --name createX --detail \"签名说明\"",
        "python -m macdev requirement add --kind path --name /api/agent/chat/stream --detail \"流式聊天\"",
        "python -m macdev requirement list [--kind interface] [--status open|done|missing]",
        "python -m macdev requirement update --id 3 --status done [--name ...] [--detail ...]",
        "python -m macdev requirement delete --id 3",
        "python -m macdev requirement export [--format all]               # 刷新双轨",
        "python -m macdev requirement align --root .                      # DB 需求→代码/端点对齐，回写 missing",
        "python -m macdev requirement scan --req-dirs openspec --root .   # 扫需求文档提取声明并对齐",
        "```", "",
        "## 对齐（参考 audit 扫描健壮性）", "",
        "`align`（结构化 DB 需求）与 `scan`（需求文档目录）共用对齐逻辑：",
        "- 代码 token 索引：os.walk 逐目录容错 + 排除目录剪枝 + >12MB 极端生成产物跳过",
        "- 端点对齐：声明路径 vs interface_chain_index.json 实际端点（missing/prefix/extra）",
        "- 代码存在性：接口/文件名 vs 源码 token（found / not_found）",
        "- 回写：未找到 → `missing`（不覆盖人工标定的 `done`）", "",
        "## 产物（对齐四件套）", "",
        "- `REQUIREMENT_ALIGNMENT.md` + `requirement_alignment.json/csv/db`",
        "- `--project <name>` / env `MACDEV_PROJECT` 收敛到 `<name>-project/requirements.db` 等", "",
        "## 命令参数树（argparse 底层反射，仅 requirement 子集）", "", "```", req_tree, "```", "",
        "## 注册表能力", "", _registry_doc(reg), "",
        "## 全部函数（模块底层反射）", "",
        "见 **REQI_DEV.md**（requirement 开发文档，含 requirement 组模块函数索引）。",
    ]
    (out / "REQI_DOC.md").write_text("\n".join(req_use) + "\n", encoding="utf-8")

    # DEV_DOC.md — dev 使用文档（学习/模仿目标项目）
    dev_use = [
        "# macdev dev 使用文档（自举生成）", "",
        "> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。", "",
        "## 用途（学习/模仿目标项目）", "",
        "用 macdev 了解一个陌生项目怎么做起来的：扫描目标学习项目、编排目录、",
        "了解架构——audit 的「快速探索」用法在 dev 下的显式入口。", "",
        "## 命令速览", "",
        "```",
        "python -m macdev dev map --target <dir> [--depth 3] [--project <name>]",
        "   # 目录编排：树 + 模块地图 + 技术栈线索（双轨产物）",
        "python -m macdev dev audit --target <dir> [--strategy base] [--project <name>]",
        "   # 架构了解：自动编排默认 AuditTask 跑快速探索，复用 audit 双轨产物",
        "```", "",
        "## 产物（双轨）", "",
        "- **map**：`DIR_TREE.md`（人类）+ `dir_tree.json/csv/db`（机器，语言环境无关）",
        "- **audit**：`INTERFACE_CHAIN.md` + `interface_chain.db` + 全维度 CSV + events.ndjson",
        "- 收敛：`--project <name>` → `<name>-project/dev/<目标名>/`；显式 `--out` 优先", "",
        "## 命令参数树（argparse 底层反射，仅 dev 子集）", "", "```", dev_tree, "```", "",
        "## 注册表能力", "", _registry_doc(reg), "",
        "## 全部函数（模块底层反射）", "",
        "见 **DEV_DEV.md**（dev 开发文档，含 dev 组模块函数索引）。",
    ]
    (out / "DEV_DOC.md").write_text("\n".join(dev_use) + "\n", encoding="utf-8")

    # 开发文档
    audit_dev = [
        "# macdev audit 开发文档（自举生成）", "",
        "> 由 `python -m macdev doc` 反射生成。", "",
        "## 架构（插件总线微内核）", "",
        "- **core**：Registry 工厂（按名装配能力）+ EventBus（全量事件，NDJSON 落盘）+ Engine 薄门面",
        "- **Plugin 抽象接口**：一切能力（audit.strategy / patch.generator / 展示/扫描…）继承同一",
        "  抽象基类，声明 namespace+name，被 `Registry.discover()` 扫描捕捉——插件与工厂**平级**。",
        "- **audit**：parse（AST 提取）→ chain（亲属追逐依赖链）→ analyze（6 维分析）→ scan（4 维扫描）→ report（双轨产物）",
        "- **patch**：修复插件（PatchPlugin 子类），审计缺陷 → 固化补丁脚本 → apply/verify 闭环",
        "- 项目语义 = AuditTask JSON + ChainStrategy 子类，**不进内核**", "",
        "## 新增修复插件（与审计策略平级）", "",
        "```python",
        "from macdev.core.plugin import Plugin",
        "from macdev.patch.model import PatchScript",
        "",
        "class FixMyIssue(Plugin):          # 继承抽象接口即被扫描捕捉",
        "    namespace = \"patch.generator\"",
        "    name = \"fix_my_issue\"",
        "    def generate(self, issue, root, rule) -> PatchScript:",
        "        ...",  # 返回固化的 operations",
        "```",
        "`registry.discover()` 自动装配，`patch gen` 按策略名调用。", "",
        "## 扩展新策略（零特化）", "",
        "```python",
        "from macdev.audit.strategy import ChainStrategy",
        "class MyStrategy(ChainStrategy):",
        "    name = \"my\"",
        "    known_type_files = {\"MyType\": \"src/my_type.py\"}",
        "registry.register(\"audit.strategy\", \"my\", MyStrategy)",
        "```", "",
        "## 全部函数（模块底层反射）", "", func_index,
    ]
    (out / "AUDIT_DEV_DOC.md").write_text("\n".join(audit_dev) + "\n", encoding="utf-8")

    plan_dev = [
        "# macdev plan 开发文档（自举生成）", "",
        "> 由 `python -m macdev doc` 反射生成。", "",
        "## 架构", "",
        "- **db.PlanStore**：SQLite 三表（plans/tasks/steps），路径全可配，兼容 plan_cli 表结构",
        "- **commands**：CRUD（create/list/update/delete/task/step）",
        "- **workflow**：verify（完成门禁）/ review（循环状态机）/ ledger（进度台账）/ tdd check",
        "- **export**：writing-plans / table / JSON 三格式",
        "- **openspec**：openspec CLI 桥接（list/status/import/export/sync-specs）",
        "- 状态机事件源：plan.state.changed 落到 events.ndjson", "",
        "## 全部函数（模块底层反射）", "", func_index,
    ]
    (out / "PLAN_DEV.md").write_text("\n".join(plan_dev) + "\n", encoding="utf-8")

    # LOG_DEV.md — log 开发文档（模块函数索引只含 log 组）
    log_dev = [
        "# macdev log 开发文档（自举生成）", "",
        "> 由 `python -m macdev doc` 反射生成。", "",
        "## 架构", "",
        "- **db.LogStore**：SQLite 经验库（四分类 lessons/pitfalls/patterns/decisions + scope 归属），路径全可配",
        "- **commands**：add/list/get/query/export/update/delete，返回 (code, lines) 约定",
        "- **双轨产物**：logs.db（机器，全文检索 query）+ LOGS.md（人类，log export 生成，按 scope 分组）",
        "- **经验双轨**：scope=project（随项目，最主要，须 --project，产物落 <name>-project/）/"
        "  scope=pkg（随包，通用方法论落 macdev-skill/，包内保持干净）",
        "- **经验沉淀约定**：经验写 log 不写 SKILL.md（防随包文档膨胀不通用）",
        "- **产物收敛**：--project/env MACDEV_PROJECT → <name>-project/logs.db；缺省会报错不落 cwd",
        "## 全部函数（模块底层反射，log 组）", "",
        _func_index_all(_modules(), ["log 经验沉淀"]),
    ]
    (out / "LOG_DEV.md").write_text("\n".join(log_dev) + "\n", encoding="utf-8")

    # REQI_DEV.md — requirement 开发文档（模块函数索引只含 requirement 组）
    req_dev = [
        "# macdev requirement 开发文档（自举生成）", "",
        "> 由 `python -m macdev doc` 反射生成。", "",
        "## 架构", "",
        "- **db.RequirementStore**：SQLite requirements 表 CRUD + 双轨产物自动刷新",
        "  （db 权威 → requirements.json/csv 机器快照 + REQUIREMENTS.md 人类，UTC/utf-8 语言环境无关）",
        "- **align**：对齐纯逻辑（需求文档提取声明 interface/path/file → 端点/代码对齐），无硬编码路径",
        "- **commands**：add/list/update/delete/export/scan/align，返回 (code, lines) 约定",
        "- **扫描健壮性（参考 audit）**：os.walk 逐目录容错 + 排除目录剪枝 + >12MB 极端生成产物跳过",
        "- **对齐产物四件套**：REQUIREMENT_ALIGNMENT.md + requirement_alignment.json/csv/db",
        "- **产物收敛**：--project/env MACDEV_PROJECT → <name>-project/requirements.db 等", "",
        "## 全部函数（模块底层反射，requirement 组）", "",
        _func_index_all(_modules(), ["requirement 需求对齐"]),
    ]
    (out / "REQI_DEV.md").write_text("\n".join(req_dev) + "\n", encoding="utf-8")

    # DEV_DEV.md — dev 开发文档（模块函数索引只含 dev 组）
    dev_dev = [
        "# macdev dev 开发文档（自举生成）", "",
        "> 由 `python -m macdev doc` 反射生成。", "",
        "## 架构", "",
        "- **commands**：cmd_map（目录编排：树 + 模块地图 + 技术栈线索，双轨产物）/"
        "  cmd_audit（自动编排默认 AuditTask 跑快速探索，复用 audit 双轨），返回 (code, lines)",
        "- **扫描健壮性（参考 audit）**：os.walk 逐目录容错 + 排除目录剪枝 + >12MB 极端生成产物跳过",
        "- **目录树**：Path.parts 计算层级（跨平台，不依赖 os.sep 拼接），限深渲染、入口文件标 ⭐",
        "- **产物收敛**：--project/env MACDEV_PROJECT → <name>-project/dev/<目标名>/", "",
        "## 全部函数（模块底层反射，dev 组）", "",
        _func_index_all(_modules(), ["dev 学习模仿"]),
    ]
    (out / "DEV_DEV.md").write_text("\n".join(dev_dev) + "\n", encoding="utf-8")

    # 包自包含：同步自举文档到包内 macdev/doc/（任意目录 import macdev 即见文档）
    pkg_doc = Path(__file__).resolve().parent / "doc"
    pkg_doc.mkdir(parents=True, exist_ok=True)
    for name in ("AUDIT_DOC.md", "AUDIT_DEV_DOC.md", "PLAN.md", "PLAN_DEV.md",
                 "LOG_DOC.md", "LOG_DEV.md", "REQI_DOC.md", "REQI_DEV.md",
                 "DEV_DOC.md", "DEV_DEV.md"):
        shutil.copy2(out / name, pkg_doc / name)
        print(f"  pkg doc → {pkg_doc / name}")

    print(f"[doc] 自举文档 → {out}（AUDIT/PLAN/LOG/REQI/DEV 各使用+开发文档，"
          f"使用文档带各自插件命令参数子树，dev 文档带各自模块函数索引）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="macdev", description="机器驱动开发范式库（插件总线微内核）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # audit
    a = sub.add_parser("audit", help="静态接口审计")
    a.add_argument("--task", default="", help="AuditTask JSON")
    a.add_argument("--root", default=".", help="项目根（task 相对路径基准）")
    a.add_argument("--out", default="macdev_out", help="输出目录")
    a.add_argument("--project", default="", help="产物目录名：out 缺省指向 <name>-project/audit（重跑覆写）")
    a.add_argument("--timeout", type=int, default=0,
                   help="扫描超时秒数（覆盖 task.scan_timeout，0=不限；超时截断子集汇报）")
    a.add_argument("--no-progress", action="store_true", help="关闭进度打印")
    a.set_defaults(fn=cmd_audit)
    ac = a.add_subparsers(dest="sub2", required=False)
    acq = ac.add_parser("chain", help="定向查询 interface_chain.db")
    acqs = acq.add_subparsers(dest="sub2", required=True)
    # 过滤选项注册到各自子解析器（argparse 不会回退认父级选项）
    def _chain_parser(name, help_, options=()):
        p = acqs.add_parser(name, help=help_)
        p.add_argument("--db", default="", help="interface_chain.db 路径")
        for opt, kwargs in options:
            p.add_argument(opt, **kwargs)
        return p
    _chain_parser("stats", "统计")
    _chain_parser("issues", "缺陷（--count 分布 / --kind/--file/--attr 过滤）",
                  [("--count", {"action": "store_true", "help": "issues: 类型计数分布"}),
                   ("--kind", {"default": "", "help": "issues: 缺陷类型过滤（逗号分隔）"}),
                   ("--file", {"default": "", "help": "issues: 文件过滤"}),
                   ("--attr", {"default": "", "help": "issues: 属性过滤"})])
    _chain_parser("endpoints", "端点（--by-file/--path/--func/--no-model）",
                  [("--by-file", {"action": "store_true", "help": "endpoints: 按文件分组"}),
                   ("--path", {"default": "", "help": "endpoints: 路径过滤"}),
                   ("--func", {"default": "", "help": "endpoints: 函数过滤"}),
                   ("--no-model", {"action": "store_true", "help": "endpoints: 无请求模型的端点"})])
    _chain_parser("models", "模型（--dup 重复定义 / --name 过滤）",
                  [("--dup", {"action": "store_true", "help": "models: 跨文件重复定义"}),
                   ("--name", {"default": "", "help": "models: 模型名过滤"})])
    _chain_parser("drifts", "语义漂移")
    _chain_parser("tables", "表结构")
    _chain_parser("callers", "按符号追调用链（--func：上游谁调 X + 下游 X 调谁）",
                  [("--func", {"default": "", "help": "callers: 函数名"})])
    _chain_parser("kw", "关键字微扫描（--keyword：refs 引用位置 def/use 标注）",
                  [("--keyword", {"default": "", "help": "kw: 关键字"})])
    acq.set_defaults(fn=cmd_audit_chain)

    # plan
    p = sub.add_parser("plan", help="开发流程机器化")
    ps = p.add_subparsers(dest="sub2", required=True)
    pc = ps.add_parser("create", help="创建 plan")
    pc.add_argument("--title", required=True)
    pc.add_argument("--name", default="", help="计划名（id=YYYYMMDD_<name>；缺省取 title 的 slug）")
    pc.add_argument("--goal", default="")
    pc.add_argument("--arch", default="")
    pc.add_argument("--stack", default="")
    pc.add_argument("--constraints", default="")
    pc.add_argument("--db", default="")
    pc.add_argument("--index", default="", help="audit 缺陷 index.json（defect 状态展示）")
    pc.add_argument("--reqdb", default="", help="requirements.db 路径")
    pc.set_defaults(fn=cmd_plan_create)
    pl = ps.add_parser("list", help="列出 plan")
    pl.add_argument("--db", default="")
    pl.set_defaults(fn=cmd_plan_list)
    pu = ps.add_parser("update", help="更新 plan")
    pu.add_argument("--id", default=None, help="plan id（YYYYMMDD_<name> 或旧数字 id）")
    pu.add_argument("--title", default=None)
    pu.add_argument("--goal", default=None)
    pu.add_argument("--arch", default=None)
    pu.add_argument("--stack", default=None)
    pu.add_argument("--constraints", default=None)
    pu.add_argument("--status", default=None)
    pu.add_argument("--db", default="")
    pu.set_defaults(fn=cmd_plan_update)
    pd = ps.add_parser("delete", help="删除 plan")
    pd.add_argument("--id", required=True)
    pd.add_argument("--db", default="")
    pd.set_defaults(fn=cmd_plan_delete)

    pt = ps.add_parser("task", help="任务管理")
    pts = pt.add_subparsers(dest="sub2", required=True)
    t_add = pts.add_parser("add")
    t_add.add_argument("--plan", required=True, help="plan id")
    t_add.add_argument("--title", required=True)
    t_add.add_argument("--detail", default="")
    t_add.add_argument("--files", default="")
    t_add.add_argument("--req", default="")
    t_add.add_argument("--defect", default="")
    t_add.add_argument("--interfaces", default="")
    t_add.add_argument("--db", default="")
    t_add.set_defaults(fn=cmd_plan_task)
    t_list = pts.add_parser("list")
    t_list.add_argument("--plan", required=True, help="plan id")
    t_list.add_argument("--db", default="")
    t_list.set_defaults(fn=cmd_plan_task)
    t_upd = pts.add_parser("update")
    t_upd.add_argument("--id", type=int, required=True)
    t_upd.add_argument("--title", default=None)
    t_upd.add_argument("--detail", default=None)
    t_upd.add_argument("--files", default=None)
    t_upd.add_argument("--req", default=None)
    t_upd.add_argument("--defect", default=None)
    t_upd.add_argument("--interfaces", default=None)
    t_upd.add_argument("--status", default=None)
    t_upd.add_argument("--review-status", default=None)
    t_upd.add_argument("--findings", default=None)
    t_upd.add_argument("--db", default="")
    t_upd.set_defaults(fn=cmd_plan_task)
    t_del = pts.add_parser("delete")
    t_del.add_argument("--id", type=int, required=True)
    t_del.add_argument("--db", default="")
    t_del.set_defaults(fn=cmd_plan_task)

    pst = ps.add_parser("step", help="步骤管理")
    psts = pst.add_subparsers(dest="sub2", required=True)
    s_add = psts.add_parser("add")
    s_add.add_argument("--task", type=int, required=True)
    s_add.add_argument("--text", required=True)
    s_add.add_argument("--action", default="other", help="test|implement|run|commit|other")
    s_add.add_argument("--code", default="")
    s_add.add_argument("--lang", default="")
    s_add.add_argument("--run", default="")
    s_add.add_argument("--expected", default="")
    s_add.add_argument("--db", default="")
    s_add.set_defaults(fn=cmd_plan_step)
    s_list = psts.add_parser("list")
    s_list.add_argument("--task", type=int, required=True)
    s_list.add_argument("--db", default="")
    s_list.set_defaults(fn=cmd_plan_step)
    s_upd = psts.add_parser("update")
    s_upd.add_argument("--id", type=int, required=True)
    s_upd.add_argument("--text", default=None)
    s_upd.add_argument("--action", default=None)
    s_upd.add_argument("--status", default=None)
    s_upd.add_argument("--db", default="")
    s_upd.set_defaults(fn=cmd_plan_step)
    s_del = psts.add_parser("delete")
    s_del.add_argument("--id", type=int, required=True)
    s_del.add_argument("--db", default="")
    s_del.set_defaults(fn=cmd_plan_step)

    pe = ps.add_parser("export", help="导出 plan（writing-plans/table + json）")
    pe.add_argument("--id", required=True, help="plan id")
    pe.add_argument("--out", default="", help="输出 .md 路径")
    pe.add_argument("--format", default="writing-plans", choices=["writing-plans", "table"])
    pe.add_argument("--db", default="")
    pe.set_defaults(fn=cmd_plan_export)
    pv = ps.add_parser("verify", help="完成门禁")
    pv.add_argument("--plan", default=None, help="plan id（缺省全部）")
    pv.add_argument("--root", default=".", help="项目根（测试文件存在性校验基准）")
    pv.add_argument("--db", default="")
    pv.set_defaults(fn=cmd_plan_verify)
    pr = ps.add_parser("review", help="review 循环")
    pr.add_argument("--task", type=int, required=True)
    pr.add_argument("--action", required=True, choices=["request", "approve", "reject", "fix"])
    pr.add_argument("--findings", default="")
    pr.add_argument("--db", default="")
    pr.set_defaults(fn=cmd_plan_review)
    plg = ps.add_parser("ledger", help="进度台账")
    plg.add_argument("--plan", required=True, help="plan id")
    plg.add_argument("--out", default="")
    plg.add_argument("--db", default="")
    plg.set_defaults(fn=cmd_plan_ledger)
    ptdd = ps.add_parser("tdd", help="TDD 合规检查")
    ptdds = ptdd.add_subparsers(dest="sub2", required=True)
    ptddc = ptdds.add_parser("check")
    ptddc.add_argument("--db", default="")
    ptddc.set_defaults(fn=cmd_plan_tdd)
    pos = ps.add_parser("openspec", help="openspec 桥接")
    poss = pos.add_subparsers(dest="sub2", required=True)
    pos_list = poss.add_parser("list")
    pos_list.add_argument("--cwd", default=".")
    pos_list.set_defaults(fn=cmd_plan_openspec)
    for name in ("status", "import", "export", "sync-specs"):
        pp = poss.add_parser(name)
        pp.add_argument("--change", default="")
        pp.add_argument("--cwd", default=".")
        pp.add_argument("--req-cli", default="", help="sync-specs: 写 requirements 的命令模板")
        pp.set_defaults(fn=cmd_plan_openspec)

    # patch（自演化：插件式修复，与 audit/plan 平级）
    pk = sub.add_parser("patch", help="自演化补丁（插件式修复）")
    pks = pk.add_subparsers(dest="sub2", required=True)
    pg = pks.add_parser("gen", help="从审计缺陷生成固化补丁脚本")
    pg.add_argument("--db", required=True, help="interface_chain.db 路径")
    pg.add_argument("--root", default=".", help="项目根（缺陷 file 相对基准）")
    pg.add_argument("--out", default="patches", help="补丁脚本输出目录")
    pg.set_defaults(fn=cmd_patch_gen)
    pa = pks.add_parser("apply", help="应用补丁（备份 + 幂等，显式操作）")
    pa.add_argument("--patch", default="", help="单个补丁脚本")
    pa.add_argument("--dir", default="", help="补丁目录（*.py）")
    pa.add_argument("--root", default=".", help="项目根")
    pa.add_argument("--no-backup", action="store_true", help="不写 .bak.macdev 备份")
    pa.set_defaults(fn=cmd_patch_apply)
    pv = pks.add_parser("verify", help="自演化闭环验证：补丁前后缺陷对比")
    pv.add_argument("--before", required=True, help="补丁前 interface_chain.db")
    pv.add_argument("--after", required=True, help="重审计后的 interface_chain.db")
    pv.set_defaults(fn=cmd_patch_verify)
    ppl = pks.add_parser("plugins", help="列出被抽象接口扫描捕捉的修复插件")
    ppl.set_defaults(fn=cmd_patch_plugins)

    # log（经验沉淀：与 plan 平级）
    lg = sub.add_parser("log", help="经验沉淀库（文档+db，SKILL.md 经验移入此处）")
    lgs = lg.add_subparsers(dest="sub2", required=True)
    la = lgs.add_parser("add", help="新增一条经验/教训/模式/决策")
    la.add_argument("--title", required=True)
    la.add_argument("--category", required=True,
                    choices=["lessons", "pitfalls", "patterns", "decisions"])
    la.add_argument("--body", default="", help="正文（支持 \\n 转义，或用 --file 从文件读）")
    la.add_argument("--file", default="", help="从文件读正文")
    la.add_argument("--tags", default="", help="逗号分隔标签")
    la.add_argument("--refs", default="", help="关联文件/产物路径")
    la.add_argument("--scope", default="project", choices=["project", "pkg"],
                    help="经验归属：project=随项目（默认，最主要）/ pkg=随包")
    la.add_argument("--project", default="")
    la.add_argument("--db", default="")
    la.set_defaults(fn=cmd_log_add)
    ll = lgs.add_parser("list", help="列出记录")
    ll.add_argument("--category", default="")
    ll.add_argument("--tag", default="")
    ll.add_argument("--scope", default="", choices=["", "project", "pkg"], help="归属过滤（缺省全部）")
    ll.add_argument("--project", default="")
    ll.add_argument("--db", default="")
    ll.set_defaults(fn=cmd_log_list)
    lget = lgs.add_parser("get", help="查看单条")
    lget.add_argument("--id", type=int, required=True)
    lget.add_argument("--project", default="")
    lget.add_argument("--db", default="")
    lget.set_defaults(fn=cmd_log_get)
    lq = lgs.add_parser("query", help="全文检索")
    lq.add_argument("--keyword", required=True)
    lq.add_argument("--category", default="")
    lq.add_argument("--scope", default="", choices=["", "project", "pkg"], help="归属过滤（缺省全部）")
    lq.add_argument("--project", default="")
    lq.add_argument("--db", default="")
    lq.set_defaults(fn=cmd_log_query)
    le = lgs.add_parser("export", help="导出 LOGS.md 人类可读文档")
    le.add_argument("--out", default="", help="输出 .md 路径（缺省 logs.db 同目录 LOGS.md）")
    le.add_argument("--scope", default="", choices=["", "project", "pkg"], help="归属过滤（缺省全部）")
    le.add_argument("--project", default="")
    le.add_argument("--db", default="")
    le.set_defaults(fn=cmd_log_export)
    lu = lgs.add_parser("update", help="更新记录")
    lu.add_argument("--id", type=int, required=True)
    lu.add_argument("--category", default=None, choices=["lessons", "pitfalls", "patterns", "decisions"])
    lu.add_argument("--title", default=None)
    lu.add_argument("--body", default=None)
    lu.add_argument("--tags", default=None)
    lu.add_argument("--refs", default=None)
    lu.add_argument("--scope", default=None, choices=["project", "pkg"], help="调整归属")
    lu.add_argument("--project", default="")
    lu.add_argument("--db", default="")
    lu.set_defaults(fn=cmd_log_update)
    ld = lgs.add_parser("delete", help="删除记录")
    ld.add_argument("--id", type=int, required=True)
    ld.add_argument("--project", default="")
    ld.add_argument("--db", default="")
    ld.set_defaults(fn=cmd_log_delete)

    # requirement（需求管理：CRUD + 规范接口对齐，双轨产物）
    rq = sub.add_parser("requirement", help="需求管理（CRUD + 规范接口对齐，双轨产物）")
    rqs = rq.add_subparsers(dest="sub2", required=True)
    rqa = rqs.add_parser("add", help="新增需求条目")
    rqa.add_argument("--kind", required=True, choices=["interface", "path", "file", "spec"])
    rqa.add_argument("--name", required=True, help="接口/路径/文件名")
    rqa.add_argument("--detail", default="", help="说明")
    rqa.add_argument("--source", default="cli", help="来源（如 brief-1）")
    rqa.add_argument("--db", default="")
    rqa.add_argument("--out", default="")
    rqa.add_argument("--project", default="")
    rqa.set_defaults(fn=cmd_requirement_add)
    rql = rqs.add_parser("list", help="列出需求")
    rql.add_argument("--kind", default="", choices=["interface", "path", "file", "spec"])
    rql.add_argument("--status", default="", choices=["open", "done", "missing"])
    rql.add_argument("--db", default="")
    rql.add_argument("--out", default="")
    rql.add_argument("--project", default="")
    rql.set_defaults(fn=cmd_requirement_list)
    rqu = rqs.add_parser("update", help="更新需求")
    rqu.add_argument("--id", type=int, required=True)
    rqu.add_argument("--kind", default=None, choices=["interface", "path", "file", "spec"])
    rqu.add_argument("--name", default=None)
    rqu.add_argument("--detail", default=None)
    rqu.add_argument("--source", default=None)
    rqu.add_argument("--status", default=None, choices=["open", "done", "missing"])
    rqu.add_argument("--db", default="")
    rqu.add_argument("--out", default="")
    rqu.add_argument("--project", default="")
    rqu.set_defaults(fn=cmd_requirement_update)
    rqd = rqs.add_parser("delete", help="删除需求")
    rqd.add_argument("--id", type=int, required=True)
    rqd.add_argument("--db", default="")
    rqd.add_argument("--out", default="")
    rqd.add_argument("--project", default="")
    rqd.set_defaults(fn=cmd_requirement_delete)
    rqe = rqs.add_parser("export", help="刷新双轨产物（md/json/csv/all）")
    rqe.add_argument("--format", default="all", choices=["md", "json", "csv", "all"])
    rqe.add_argument("--db", default="")
    rqe.add_argument("--out", default="")
    rqe.add_argument("--project", default="")
    rqe.set_defaults(fn=cmd_requirement_export)
    rqc = rqs.add_parser("align", help="DB 需求 → 代码/端点对齐，回写 missing")
    rqc.add_argument("--index", default="", help="interface_chain_index.json 路径")
    rqc.add_argument("--root", default="", help="代码扫描项目根（缺省 cwd）")
    rqc.add_argument("--exclude", default="", help="逗号分隔排除目录（剪枝，如 node_modules,tests）")
    rqc.add_argument("--db", default="")
    rqc.add_argument("--out", default="")
    rqc.add_argument("--project", default="")
    rqc.set_defaults(fn=cmd_requirement_align)
    rqs2 = rqs.add_parser("scan", help="扫描需求文档目录提取声明并对齐")
    rqs2.add_argument("--req-dirs", default="", help="逗号分隔需求文档目录（缺省探测 .opencode/sdd 等）")
    rqs2.add_argument("--code", default="", help="逗号分隔代码扫描扩展名 glob（如 **/*.py）")
    rqs2.add_argument("--index", default="", help="interface_chain_index.json 路径")
    rqs2.add_argument("--root", default="", help="项目根（扫描/代码基准，缺省 cwd）")
    rqs2.add_argument("--exclude", default="", help="逗号分隔排除目录（剪枝）")
    rqs2.add_argument("--db", default="")
    rqs2.add_argument("--out", default="")
    rqs2.add_argument("--project", default="")
    rqs2.set_defaults(fn=cmd_requirement_scan)

    # dev（学习/模仿目标项目：目录编排 + 架构了解）
    dv = sub.add_parser("dev", help="学习/模仿目标项目（目录编排 + 架构了解）")
    dvs = dv.add_subparsers(dest="sub2", required=True)
    dvm = dvs.add_parser("map", help="扫描目标项目编排目录（树 + 模块地图 + 技术栈线索，双轨产物）")
    dvm.add_argument("--target", required=True, help="要学习的目标项目目录")
    dvm.add_argument("--depth", type=int, default=3, help="目录树深度（缺省 3）")
    dvm.add_argument("--exclude", default="", help="逗号分隔排除目录（剪枝）")
    dvm.add_argument("--out", default="", help="产物输出目录")
    dvm.add_argument("--project", default="")
    dvm.set_defaults(fn=cmd_dev_map)
    dva = dvs.add_parser("audit", help="架构了解：自动编排默认 AuditTask 跑快速探索（复用 audit 双轨）")
    dva.add_argument("--target", required=True, help="要学习的目标项目目录")
    dva.add_argument("--strategy", default="base", help="审计策略名（缺省 base）")
    dva.add_argument("--exclude", default="", help="逗号分隔排除目录（剪枝）")
    dva.add_argument("--timeout", type=int, default=0, help="扫描超时秒数（0=不限）")
    dva.add_argument("--out", default="", help="产物输出目录")
    dva.add_argument("--project", default="")
    dva.set_defaults(fn=cmd_dev_audit)

    # project（产物目录约定）
    pj = sub.add_parser("project", help="产物目录约定（<name>-project/ 收纳 audit/plan/log 全部产物）")
    pjs = pj.add_subparsers(dest="sub2", required=True)
    pji = pjs.add_parser("init", help="初始化产物目录（可选 git init）")
    pji.add_argument("--name", required=True, help="项目名（产物目录 = <name>-project/）")
    pji.add_argument("--git", action="store_true", help="同时 git init 追踪")
    pji.add_argument("--base", default="", help="产物目录的父路径（缺省 cwd）")
    pji.set_defaults(fn=cmd_project_init)
    pjl = pjs.add_parser("list", help="列出已初始化的产物目录")
    pjl.add_argument("--base", default="")
    pjl.set_defaults(fn=cmd_project_list)
    pjr = pjs.add_parser("root", help="打印产物目录绝对路径")
    pjr.add_argument("--name", required=True)
    pjr.add_argument("--base", default="")
    pjr.set_defaults(fn=cmd_project_root)

    # doc
    d = sub.add_parser("doc", help="自举生成使用/开发文档")
    d.add_argument("--out", default="macdev-skill", help="自举文档输出目录")
    d.set_defaults(fn=cmd_doc)

    # skill（子技能动态注入：发现/路由/注入，服务 TS2 harness）
    sk = sub.add_parser("skill", help="子技能动态注入（scan/inject/route/list）")
    sks = sk.add_subparsers(dest="sub2", required=True)
    sks_list = sks.add_parser("list", help="列出默认目录下子技能名")
    sks_list.add_argument("--dir", default="", help="技能目录（缺省探测 skills/ 与 skills_market/）")
    sks_list.add_argument("--root", default=".", help="缺省技能目录的基准根")
    sks_list.set_defaults(fn=cmd_skill_list)
    sks_scan = sks.add_parser("scan", help="扫描目录列出子技能含推断字段")
    sks_scan.add_argument("--dir", default="", help="技能目录（缺省探测 skills/ 与 skills_market/）")
    sks_scan.add_argument("--root", default=".", help="缺省技能目录的基准根")
    sks_scan.set_defaults(fn=cmd_skill_scan)
    sks_inj = sks.add_parser("inject", help="整文件内容输出到 stdout（--name 指定子技能）")
    sks_inj.add_argument("--name", required=True, help="子技能名（文件名，不含 .md）")
    sks_inj.add_argument("--dir", default="", help="技能目录（缺省探测 skills/ 与 skills_market/）")
    sks_inj.add_argument("--root", default=".", help="缺省技能目录的基准根")
    sks_inj.set_defaults(fn=cmd_skill_inject)
    sks_route = sks.add_parser("route", help="任务描述 → 自动匹配子技能名（--task）")
    sks_route.add_argument("--task", required=True, help="任务描述")
    sks_route.add_argument("--dir", default="", help="技能目录（缺省探测 skills/ 与 skills_market/）")
    sks_route.add_argument("--root", default=".", help="缺省技能目录的基准根")
    sks_route.set_defaults(fn=cmd_skill_route)
    return ap


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
