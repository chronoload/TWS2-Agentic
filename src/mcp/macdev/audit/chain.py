"""audit.chain：从 extractor 原子组装（build_global_symbol_index/trace_chain/
chain_text/chain_mermaid/collect_broken_refs/build_dep_sections + write_db）。

函数体保持原子原样，仅将 TS2 特化全局（MCP_ROOT/ACTIVE_STRATEGY/CHAINS_CFG/
DEFAULT_EXCLUDE）改为显式参数；语言级噪声常量保留为通用模块常量。
"""
from __future__ import annotations
import ast
import json
import os
import sqlite3
from pathlib import Path
from .models import ChainNode
from .strategy import ChainStrategy
from .parse import extract_func_map, extract_imports, _type_short

# ---------- 语言级噪声（通用，非项目特化） ----------

_BUILTIN_NAMES = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))

NOISE_CALLS = {
    "logger", "log", "logging", "len", "str", "int", "float", "bool", "list", "dict", "set",
    "getattr", "setattr", "hasattr", "isinstance", "issubclass", "sum", "min", "max", "sorted",
    "abs", "round", "print", "open", "super", "type", "iter", "next", "enumerate", "zip", "map",
    "filter", "any", "all", "reversed", "repr", "Path", "os", "time", "json", "re", "asyncio",
    "traceback", "import", "sys", "copy", "threading", "uuid", "datetime", "random", "struct",
    "StringIO", "tempfile", "shutil", "glob", "fnmatch", "hashlib", "base64", "urllib", "requests",
    "ok", "err",  # API 响应封装，无依赖追踪价值
}

NOISE_ATTRS = {
    "get", "set", "append", "extend", "insert", "pop", "remove", "update", "items", "keys",
    "values", "join", "split", "replace", "strip", "format", "startswith", "endswith", "json",
}

HTTP_ATTRS = {"get", "post", "put", "delete", "patch", "websocket"}


# ---------- 追踪辅助原子 ----------

def _walk_own(node):
    """遍历节点自身 body，跳过嵌套函数/类定义（避免闭包内部调用混入父函数）"""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield from _walk_own(child)


def extract_var_bindings(func) -> dict:
    """提取函数体内变量 → 类型名/来源（Assign/AnnAssign 直接赋值）"""
    binds: dict = {}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var = node.targets[0].id
            if isinstance(node.value, ast.Call):
                f = node.value.func
                if isinstance(f, ast.Name):
                    binds[var] = f.id  # x = helper(...) → 类型=helper（用 HELPER_RETURN_TYPES 解析）
                elif isinstance(f, ast.Attribute):
                    binds[var] = f.attr  # x = obj.method(...)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            var = node.target.id
            if isinstance(node.value, ast.Call):
                f = node.value.func
                if isinstance(f, ast.Name):
                    binds[var] = f.id
    return binds


def collect_call_targets(func) -> list:
    """收集函数体（不含嵌套定义）内的直接调用目标，过滤装饰器与噪声"""
    targets = []
    seen = set()
    deco_lines = set()
    for node in _walk_own(func):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                deco_lines.add(d.lineno)
    for node in _walk_own(func):
        if not isinstance(node, ast.Call):
            continue
        if node.lineno in deco_lines:
            continue
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in NOISE_CALLS:
                continue
            key = (f.id, node.lineno)
            if key not in seen:
                seen.add(key)
                targets.append((f.id, "name", node.lineno))
        elif isinstance(f, ast.Attribute):
            obj = f.value
            obj_name = obj.id if isinstance(obj, ast.Name) else "*"
            method = f.attr
            if obj_name in ("app", "router") and method in HTTP_ATTRS:
                continue  # 路由装饰器
            if obj_name in NOISE_CALLS:
                continue  # logger.info / time.sleep 等
            if (obj_name == "*" or obj_name.startswith("_")) and method in NOISE_ATTRS:
                continue  # dict/list 方法（_agent_pool.get 等全局容器）
            key = (f"{obj_name}.{method}", node.lineno)
            if key not in seen:
                seen.add(key)
                targets.append((f"{obj_name}.{method}", "attr", node.lineno))
            # 线程池回调：run_in_executor(None, _func) / executor.submit(_func) 中的函数引用
            if method in ("run_in_executor", "submit", "create_task") or f.attr in ("call_soon_threadsafe",):
                for a in node.args:
                    if isinstance(a, ast.Name) and a.id not in NOISE_CALLS:
                        tkey = (a.id, node.lineno)
                        if tkey not in seen:
                            seen.add(tkey)
                            targets.append((a.id, "name", node.lineno))
    return targets


def _method_calls_of(module_path: Path, cls_name: str, method_name: str) -> list:
    """提取类方法内部的调用目标（1 层）"""
    if not module_path.exists():
        return []
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == method_name:
                    for t in collect_call_targets(sub):
                        out.append(t)
                    return out
    return out


# ---------- 亲属追逐核心原子 ----------

def _iter_py_files(root: Path, exclude: tuple) -> list:
    """遍历项目内 *.py，跳过排除目录；逐目录容错（断链目录只跳过该目录，
    不会像 rglob 整体失败导致整批文件丢失），排除目录剪枝加速。"""
    excl = tuple(exclude)
    files: list = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # 剪枝：目录名直接命中 exclude 的跳过整棵子树
            dirnames[:] = [d for d in dirnames if d not in excl]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                p = Path(dirpath) / fn
                if any(x in p.parts for x in excl):
                    continue
                files.append(p)
    except OSError:
        pass
    return files


def build_global_symbol_index(root: Path, exclude: tuple = (), budget=None) -> dict:
    """全局符号索引（亲属反射表）：{符号名: [(相对文件, 行号, 种类)]}
    种类: func | class | var | method（类方法）
    用于跨文件反射核查：trace_chain 遇到本文件未解析的目标时，反射全项目
    是否有定义——有则定位（亲属已找到），无则判为链路断裂（broken）。
    """
    index: dict[str, list] = {}
    if not root.is_dir():
        return index
    extra_exclude = ("web", "android", "archs", "static_capacitor", "static_electron",
                     "staticselfcontaine", "static-branch", "static_arch", "draft")
    py_files = _iter_py_files(root, tuple(exclude) + extra_exclude)
    for p in py_files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                index.setdefault(node.name, []).append((rel, node.lineno, "func"))
            elif isinstance(node, ast.ClassDef):
                index.setdefault(node.name, []).append((rel, node.lineno, "class"))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        index.setdefault(f"{node.name}.{sub.name}", []).append(
                            (rel, sub.lineno, "method"))
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        index.setdefault(t.id, []).append((rel, node.lineno, "var"))
    return index


def trace_chain(start_name: str, func_map: dict, import_map: dict, path: Path,
                depth: int = 0, seen=None, max_depth: int = 3,
                global_index: dict = None, strategy: ChainStrategy = None) -> ChainNode:
    """从函数名开始递归展开调用链（亲属追逐 → 亲属反射）
    规则：同文件 helper 递归展开；跨模块类方法仅标记为叶子（标注源文件）。
    亲属反射：name 目标在本文件未解析时，查全项目符号索引（global_index）——
      命中 → cross_file（亲属已定位，标注定义位置）；是内置/导入 → builtin；
      全项目无定义 → broken（🔴 链路断裂，一步定位 bug）。
    """
    strategy = strategy or ChainStrategy()
    seen = seen or set()
    node = ChainNode(name=start_name, kind="unknown", file=path.name)
    if start_name in seen:
        node.kind = "recursive"
        return node
    if depth > max_depth:
        node.kind = "depth_limit"
        return node
    seen.add(start_name)
    func = func_map.get(start_name)
    if func is None:
        return node
    node.kind = "helper"
    node.line = func.lineno
    binds = extract_var_bindings(func)
    # 形参类型提示：store/agent 等按语义绑定
    for pname, ptype in strategy.param_type_hints.get(start_name, {}).items():
        binds.setdefault(pname, ptype)
    for target, kind, lineno in collect_call_targets(func):
        if kind == "name":
            if target in func_map and target != start_name:
                child = trace_chain(target, func_map, import_map, path,
                                    depth + 1, seen, max_depth, global_index, strategy)
                child.line = lineno
                node.children.append(child)
            elif target in strategy.helper_return_types:
                node.children.append(ChainNode(name=target, kind="helper",
                                               file=path.name, line=lineno))
            elif target in strategy.known_type_files:
                # 类实例化（如 MultiProviderManager / SimulatorLLM / CourseSystem）
                node.children.append(ChainNode(name=target, kind="class",
                                               file=strategy.known_type_files[target], line=lineno))
            else:
                # 亲属反射核查：本文件无此函数 → 全项目索引 / 内置 / 导入 / 断裂
                locs = (global_index or {}).get(target)
                # 强命中：func/class/method（可定位）；弱命中：仅 var（存在性已知，降级为 builtin，不误报断裂）
                strong = [l for l in (locs or []) if l[2] in ("func", "class", "method")]
                if strong:
                    # 同文件优先，否则取首个强命中
                    cur = path.name
                    pick = next((l for l in strong if l[0].split("/")[-1] == cur), strong[0])
                    rel, ln, knd = pick
                    child = ChainNode(name=target, kind="cross_file",
                                      file=rel, line=ln)
                    child.detail = f"定义于 {rel}:{ln}（{knd}）"
                    node.children.append(child)
                elif locs or target in _BUILTIN_NAMES or target in import_map:
                    # var 弱命中 / 内置 / 导入：引用存在但非本文件函数，保持 builtin
                    node.children.append(ChainNode(name=target, kind="builtin",
                                                   line=lineno))
                else:
                    # 项目内无任何定义 → 链路断裂（可能是改名/漏实现/拼写错误）
                    child = ChainNode(name=target, kind="broken", line=lineno)
                    child.detail = "项目内未找到定义（疑似改名/漏实现/拼写错误）"
                    node.children.append(child)
        else:  # attr: obj.method
            obj, method = target.split(".", 1)
            type_name = ""
            if obj in binds:
                t = binds[obj]
                if t in strategy.known_type_files:
                    type_name = t
                elif t in strategy.helper_return_types:
                    type_name = strategy.helper_return_types[t]
            elif obj in strategy.type_aliases:
                type_name = strategy.type_aliases[obj]
            if type_name:
                f = strategy.resolve_type_file(type_name, import_map)
                child = ChainNode(name=f"{type_name}.{method}", kind="class_method",
                                  file=f or path.name, line=lineno)
                # 1 层跨文件展开：类方法内部的 self 调用
                if f:
                    fp = Path(f)
                    if not fp.is_absolute():
                        fp = path.parent.parent / f
                    for inner_target, inner_kind, inner_line in _method_calls_of(fp, type_name, method):
                        child.children.append(ChainNode(name=inner_target, kind="class_method",
                                                        file=f, line=inner_line))
                node.children.append(child)
            elif method in NOISE_ATTRS:
                continue  # 未知对象的序列方法（msg.get / body.get 等），无追踪价值
            else:
                # 对象类型未知：可能是库对象（conn.execute / loop.run_in_executor /
                # ws_mgr.broadcast），无法可靠判定断裂 → 保持 unknown。
                # 仅当方法名恰为项目内某类的同名方法时给出候选归属提示。
                method_hits = [(rel, ln) for rel, ln, knd in (global_index or {}).get(method, [])
                               if knd == "method"]
                if method_hits:
                    rel, ln = method_hits[0]
                    child = ChainNode(name=target, kind="unknown", line=lineno)
                    child.detail = f"对象类型未知，方法同名定义于 {rel}:{ln}"
                    node.children.append(child)
                else:
                    node.children.append(ChainNode(name=target, kind="unknown",
                                                   line=lineno))
    return node


# ---------- 展示原子 ----------

def chain_text(node: ChainNode, indent: int = 0) -> list:
    """调用链 → 文本树（broken 断裂节点标红 🔴，cross_file 显示定义位置）"""
    pad = "  " * indent
    loc = f" [{node.file}:{node.line}]" if node.file and node.line else ""
    kind = f" ({node.kind})" if node.kind not in ("helper",) else ""
    if node.kind == "broken":
        kind = " (🔴 broken)"
    elif node.kind == "cross_file":
        kind = " (↦ 亲属)" if not node.detail else f" (↦ {node.detail})"
    lines = [f"{pad}└ {node.name}{kind}{loc}"]
    for c in node.children:
        lines.extend(chain_text(c, indent + 1))
    return lines


def chain_mermaid(node: ChainNode, parent_id: str = "") -> list:
    """调用链 → mermaid graph 语句（broken 节点标红，cross_file 显示定义位置）"""
    lines = []
    mid = node.name.replace("/", "_").replace("-", "_").replace("{", "").replace("}", "")
    mid = f"n_{mid}_{abs(hash(mid)) % 100000}"
    label = node.name
    if node.kind == "broken":
        label += " 🔴"
    if node.file:
        label += f"<br/><small>{node.file}:{node.line}</small>"
    lines.append(f'    {mid}["{label}"]')
    if node.kind == "broken":
        lines.append(f"    class {mid} broken;")
    if parent_id:
        lines.append(f"    {parent_id} --> {mid}")
    for c in node.children:
        lines.extend(chain_mermaid(c, mid))
    return lines


def collect_broken_refs(node: ChainNode, out: list) -> list:
    """递归收集链路中的断裂引用（broken 节点），返回 [(目标, 调用行)]"""
    if node.kind == "broken":
        out.append((node.name, node.line, node.detail))
    for c in node.children:
        collect_broken_refs(c, out)
    return out


# ---------- 任务级组装 ----------

def build_dep_sections(endpoints: list, root: Path, chains_cfg: dict = None,
                       strategy: ChainStrategy = None, exclude: tuple = (),
                       budget=None) -> str:
    """关键端点依赖链（亲属追逐 → 跨模块/存储）。

    入口泛化：任务配置 chains_cfg.entries（{kind: endpoint, prefix} 或 {kind: function, name}），
    全部走同一 trace_chain 引擎 + 全局符号索引（亲属反射定位），展示（text + mermaid + 断裂索引）通用；
    预置链路（chains_cfg.preset，静态文本）作为补充块渲染，不硬编码。
    """
    strategy = strategy or ChainStrategy()
    cfg = chains_cfg or {}
    max_depth = int(cfg.get("max_depth", 3))
    entries = cfg.get("entries") or [{"kind": "endpoint", "prefix": "/api/agent/"}]

    # func → 定义文件索引（泛化归属，消除同名文件歧义）
    func_file: dict[str, Path] = {}
    for p in _iter_py_files(root, exclude):
        if budget:
            budget.tick()
            if budget.expired():
                break
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
                    global_index = build_global_symbol_index(root, exclude, budget=budget)
                for rel, ln, kind in global_index.get(name, []):
                    if kind == "method":
                        todo.append((f"function `{name}`", name.split(".")[-1], root / rel))
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
        global_index = build_global_symbol_index(root, exclude)
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
            root_node = trace_chain(func, fmap, imports, p, max_depth=max_depth,
                                    global_index=global_index, strategy=strategy)
            L.append(f"### {label}\n")
            L.append("```text")
            L.extend(chain_text(root_node))
            L.append("```")
            L.append("```mermaid")
            L.append("graph TD")
            L.append("classDef broken fill:#f8d7da,stroke:#dc3545;")
            L.extend(chain_mermaid(root_node))
            L.append("```\n")
            for tgt, ln, detail in collect_broken_refs(root_node, []):
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


def write_db(db_path: Path, endpoints: list, models: list) -> None:
    """写 SQLite：endpoints / models / stats 三表（机器可读轨，最小闭环）。"""
    conn = sqlite3.connect(str(db_path))
    try:
        c = conn.cursor()
        c.execute("DROP TABLE IF EXISTS endpoints")
        c.execute("""CREATE TABLE endpoints(
            method TEXT, path TEXT, func TEXT, request_model TEXT,
            response_keys TEXT, file TEXT, line INT, doc TEXT)""")
        c.executemany(
            "INSERT INTO endpoints VALUES (?,?,?,?,?,?,?,?)",
            [(e.method, e.path, e.func, e.request_model,
              "|".join(e.response_keys), e.file, e.line, e.doc) for e in endpoints])

        c.execute("DROP TABLE IF EXISTS models")
        c.execute("""CREATE TABLE models(
            name TEXT, file TEXT, line INT, field TEXT,
            type TEXT, required INT, default_value TEXT)""")
        c.executemany(
            "INSERT INTO models VALUES (?,?,?,?,?,?,?)",
            [(m.name, m.file, m.line, f.name, _type_short(f.type),
              int(f.required), f.default) for m in models for f in m.fields])

        c.execute("DROP TABLE IF EXISTS stats")
        c.execute("CREATE TABLE stats(key TEXT, value TEXT)")
        stats = {"endpoints": len(endpoints), "models": len(models)}
        c.executemany("INSERT INTO stats VALUES (?,?)",
                      [(k, str(v)) for k, v in stats.items()])
        conn.commit()
    finally:
        conn.close()
