"""audit.analyze：6 维分析（def-use / behavior / chain_break / flag_lifecycle /
merge_direction / id_source_contract）+ 前后端语义偏移（drift）。
从 extractor 原子重组，函数体保持原样，规则表（behavior_rules / id_source_rules）改为显式参数。
"""
from __future__ import annotations
import ast
import importlib
import re
from pathlib import Path
from .models import (ClientMethod, Drift, Endpoint, RequestModel,
                     DefUseRead, DefUseWrite, DefUseIssue,
                     BehaviorIssue, ChainBreakIssue, FlagLifecycleIssue,
                     MergeDirectionIssue, IdSourceIssue)


def _normalize_path(p: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", p)


# ─── 前端客户端方法提取（JS/TS 正则）───

def extract_client_methods(js_path: Path) -> list:
    if not js_path.exists():
        return []
    text = js_path.read_text(encoding="utf-8")
    methods = []
    # 在 TS2Client class 内部（从 'class TS2Client' 到文件尾 / 下一个顶级 class）
    cls_match = re.search(r"class TS2Client\b", text)
    if not cls_match:
        return []
    cls_start = cls_match.end()
    tail = text[cls_start:]
    end_match = re.search(r"\n(?=[A-Za-z_$][\w$]*\s*\()", tail)
    body = tail[: end_match.start()] if end_match else tail

    for m in re.finditer(r"\b(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{", body):
        name = m.group(1)
        if name in ("constructor",):
            continue
        method_body_start = m.end()
        seg = body[method_body_start: method_body_start + 600]
        ep_match = re.search(r"['\"](/api/[^'\"\s]+)['\"]", seg)
        endpoint = ep_match.group(1) if ep_match else ""
        http_method = "POST"
        if re.search(r"\b(?:fetch|api_get)\(.*['\"]GET['\"]", seg) or (ep_match and re.match(r"GET", seg)):
            http_method = "GET"
        if "api_get(" in seg and ep_match and ep_match.start() < seg.find("api_get(") + 10:
            http_method = "GET"
        payload_keys = []
        payload_m = re.search(r"this\.api\(\s*['\"][^'\"]+['\"]\s*,\s*\{([^}]*)\}", seg)
        if payload_m:
            payload_keys = re.findall(r"([A-Za-z_$][\w$]*)\s*:", payload_m.group(1))
        methods.append(ClientMethod(
            name=name,
            line=text[:cls_start].count("\n") + body[:m.start()].count("\n") + 2,
            endpoint=endpoint,
            http_method=http_method,
            payload_keys=payload_keys,
        ))
    return methods


# ─── 语义偏移（前后端）───

def detect_drift(endpoints: list, models: list, client: list) -> list:
    drifts: list = []
    ep_by_path: dict = {}
    for ep in endpoints:
        ep_by_path.setdefault(ep.method + " " + _normalize_path(ep.path), ep)

    model_by_name = {m.name: m for m in models}

    for cm in client:
        if not cm.endpoint:
            continue
        key = cm.http_method + " " + _normalize_path(cm.endpoint)
        ep = ep_by_path.get(key)
        if ep is None:
            # 允许 method 不匹配时再看路径是否存在
            alt = [v for k, v in ep_by_path.items() if k.split(" ", 1)[1] == _normalize_path(cm.endpoint)]
            ep = alt[0] if alt else None
        if ep is None:
            drifts.append(Drift(kind="endpoint_missing", client=cm.name, endpoint=cm.endpoint,
                                detail="前端调用但后端未找到对应端点（注意：可能位于其他路由/构建产物）"))
            continue

        # 比对 payload 键 ↔ 请求模型字段
        if ep.request_model and cm.payload_keys:
            rm = model_by_name.get(ep.request_model.split(".")[-1])
            if rm:
                model_fields = {f.name for f in rm.fields}
                extra = [k for k in cm.payload_keys if k not in model_fields and k not in ("__dummy__",)]
                required_missing = [f.name for f in rm.fields if f.required and f.name not in cm.payload_keys]
                if extra:
                    drifts.append(Drift(kind="extra_payload_key", client=cm.name, endpoint=cm.endpoint,
                                        detail=f"前端多传字段 {extra}，后端模型 {rm.name} 不含"))
                if required_missing:
                    drifts.append(Drift(kind="missing_required", client=cm.name, endpoint=cm.endpoint,
                                        detail=f"前端缺少必填字段 {required_missing}（模型 {rm.name}）"))
    return drifts


# ─── def-use ───

def _falsy_literal_text(s: str) -> bool:
    """判断默认值源码文本是否为假值常量（False/None/0/''/[]/{} 等）"""
    s = s.strip()
    if s in ("False", "None", "0", "0.0", "''", '""', "[]", "{}", "()"):
        return True
    try:
        v = ast.literal_eval(s)
        return v is None or v is False or v == 0 or v == 0.0 or v == ""
    except Exception:
        return False


def _obj_root(node) -> str:
    """取属性读写对象的最左侧名字：agent.state.x → agent；self → self；Name → id"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _obj_root(node.value)
    return "?"


def _extract_defuse_one(file: Path, reads: list, writes: list) -> None:
    """扫描单个 Python 文件：收集 getattr/hasattr/setattr 调用与 obj.attr 赋值"""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except Exception:
        return
    for node in ast.walk(tree):
        # getattr / hasattr / setattr(obj, 'attr', [default])
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("getattr", "hasattr", "setattr")
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)):
            name, attr, obj = node.func.id, node.args[1].value, _obj_root(node.args[0])
            line = node.lineno
            if name == "getattr":
                default = ast.unparse(node.args[2]) if len(node.args) >= 3 else "—"
                reads.append(DefUseRead(file=file.name, line=line, obj=obj, attr=attr, default=default))
            elif name == "hasattr":
                reads.append(DefUseRead(file=file.name, line=line, obj=obj, attr=attr, default="hasattr"))
            else:  # setattr
                expr = ast.unparse(node.args[2])[:40] if len(node.args) >= 3 else "?"
                writes.append(DefUseWrite(file=file.name, line=line, obj=obj, attr=attr, expr=expr))
        # obj.attr = value（Assign / AnnAssign 目标为 Attribute）
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = getattr(node, "value", None)
            for t in targets:
                if isinstance(t, ast.Attribute):
                    writes.append(DefUseWrite(
                        file=file.name, line=node.lineno,
                        obj=_obj_root(t.value), attr=t.attr,
                        expr=ast.unparse(value)[:40] if value else "?"))
        # 类属性定义（ClassDef body 顶层的 Name 赋值）与类方法名
        elif isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                    value = getattr(stmt, "value", None)
                    for t in targets:
                        if isinstance(t, ast.Name):
                            writes.append(DefUseWrite(
                                file=file.name, line=stmt.lineno,
                                obj=node.name, attr=t.id,
                                expr=ast.unparse(value)[:40] if value else "?"))
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    writes.append(DefUseWrite(
                        file=file.name, line=stmt.lineno,
                        obj=node.name, attr=stmt.name, expr="<method/property>"))


# 外部契约对象启发式：这些名字通常指向第三方 SDK 返回对象 / 动态 Namespace /
# 参数对象，其属性由库或外部框架写入，静态扫描不到赋值点是正常现象。
_EXTERNAL_OBJ_HINTS = {
    "response", "usage", "chunk", "item", "tool", "tc", "tool_call", "step",
    "msg", "event", "req", "request", "args", "mod", "generator",
    "xcode_generator", "msvs_generator", "client", "conn", "obj", "ctx",
    "sys",  # sys.frozen 等由运行时注入
}


def _is_external_obj(obj: str) -> bool:
    if obj in _EXTERNAL_OBJ_HINTS:
        return True
    if obj == "?":  # 复杂表达式对象（如 getattr(x[0].y, ...)）—— 动态，无法静态定位
        return True
    # 单字母变量名（t/s/c/m/r/v/f/e 等）多为临时/库对象
    return len(obj) == 1 and obj.isalpha()


def _verify_module_attr(obj: str, attr: str) -> str:
    """尝试用运行时反射验证「模块级属性」是否真实存在。"""
    try:
        mod = importlib.import_module(obj)
    except Exception:
        for depth in range(max(1, obj.count(".")), -1, -1):
            head = ".".join(obj.split(".")[:depth])
            try:
                mod = importlib.import_module(head)
                break
            except Exception:
                mod = None
        if mod is None:
            return f"对象 `{obj}` 非可导入模块名（疑似 SDK 返回对象/动态实例），无法静态验证，需人工核对是否存在该参数"
    if hasattr(mod, attr):
        return f"模块 `{obj}` 中确实存在属性 `{attr}`（库内定义，正常）"
    return f"模块 `{obj}` 中不存在属性 `{attr}` —— 疑似库 API 变更或运行时注入（如 sys.frozen 由打包器注入），需人工确认"


def analyze_defuse(files: list, budget=None) -> tuple:
    """跨文件 def-use 一致性分析。
    返回 (reads, writes, issues, closed)。"""
    reads: list = []
    writes: list = []
    for f in files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        _extract_defuse_one(Path(f), reads, writes)

    writes_by_attr: dict = {}
    writes_by_obj_attr: dict = {}
    for w in writes:
        writes_by_attr.setdefault(w.attr, []).append(w)
        key = "*" if w.obj == "self" else w.obj
        writes_by_obj_attr.setdefault((key, w.attr), []).append(w)

    issues: list = []
    for r in reads:
        if r.default == "hasattr":
            continue
        if not _falsy_literal_text(r.default):
            continue
        obj_writes = (writes_by_obj_attr.get((r.obj, r.attr))
                      or writes_by_obj_attr.get(("*", r.attr)))
        any_writes = writes_by_attr.get(r.attr, [])
        if not any_writes:
            if _is_external_obj(r.obj):
                issues.append(DefUseIssue(
                    kind="external_contract", attr=r.attr, file=r.file, line=r.line,
                    obj=r.obj, default=r.default, writes=[],
                    detail=f"项目内无赋值点。{_verify_module_attr(r.obj, r.attr)}"))
            else:
                issues.append(DefUseIssue(
                    kind="no_assignment", attr=r.attr, file=r.file, line=r.line,
                    obj=r.obj, default=r.default, writes=[],
                    detail=f"getattr 默认值 {r.default} 恒为 {r.default}：全库无任何 `{r.attr}` 赋值点"))
        elif obj_writes is None:
            issues.append(DefUseIssue(
                kind="loose_match", attr=r.attr, file=r.file, line=r.line,
                obj=r.obj, default=r.default,
                writes=[(w.file, w.line, w.obj, w.expr) for w in any_writes],
                detail=f"对象名 `{r.obj}` 下无 `{r.attr}` 赋值，仅在其他对象/类上找到同名属性"))

    # 已闭合读取（供文档展示赋值链）
    closed = []
    for r in reads:
        if r.default == "hasattr":
            continue
        src = (writes_by_obj_attr.get((r.obj, r.attr))
               or writes_by_obj_attr.get(("*", r.attr))
               or writes_by_attr.get(r.attr, []))
        if src:
            closed.append((r, [(w.file, w.line, w.obj, w.expr) for w in src[:5]]))
    return reads, writes, issues, closed


# ─── 行为契约检查（must-call 路径覆盖）───

def _call_repr(node: ast.AST) -> str:
    """把 ast.Call 的 func 转成可读字符串：store.update / _sync_agent_from_store"""
    f = getattr(node, "func", None)
    if f is None:
        return ""
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        base = _call_repr(f.value) if isinstance(f.value, (ast.Name, ast.Attribute)) else "*"
        return f"{base}.{f.attr}"
    return ""


def _collect_entry_call_reprs(func) -> list:
    """收集入口函数体（含嵌套闭包/回调）内所有调用目标的可读串，供 must-call 匹配。"""
    out = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            r = _call_repr(node)
            if r:
                out.append(r)
    return out


def analyze_behavior(files: list, rules: dict, budget=None) -> list:
    """行为契约检查：入口函数正常完成路径必须触发的副作用调用是否存在。"""
    issues: list = []
    parsed: dict = {}

    def _collect_funcs(node, out):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(child.name, child)
            _collect_funcs(child, out)

    for f in files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        path = Path(f)
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        module_funcs = {}
        _collect_funcs(tree, module_funcs)
        for name, func in module_funcs.items():
            parsed.setdefault(name, []).append((path, func))

    for entry, must_calls in rules.items():
        hits = parsed.get(entry)
        if not hits:
            issues.append(BehaviorIssue(
                entry=entry, missing=list(must_calls),
                file="", detail="入口函数未找到（规则过期或函数已改名）"))
            continue
        for file, func in hits:
            call_reprs = _collect_entry_call_reprs(func)
            missing = [m for m in must_calls
                       if not any(m in r or r in m for r in call_reprs)]
            # OR 语义：任一命中即满足；全部缺失才算缺陷
            if missing and len(missing) == len(must_calls):
                issues.append(BehaviorIssue(
                    entry=entry, missing=missing, file=str(file),
                    detail="正常完成路径缺少必须的副作用调用（如写回会话记录），"
                           "依赖链无法发现——需补齐或在入口断言"))
    return issues


def _is_behavior_defect(b) -> bool:
    """真实行为缺陷判定：must-call 全部缺失才算缺陷；'入口未找到'属规则过期警告。"""
    return bool(getattr(b, "missing", None)) and "未找到" not in (b.detail or "")


# ─── 链路断裂检查（兜底源守卫）───

def _iter_ancestor_ifs(node, tree) -> list:
    """收集 node 的所有祖先 if 条件（ast.If 的 test），按从近到远。"""
    conds = []
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.If):
            continue
        if any(n is node for n in ast.walk(parent)):
            conds.append(ast.unparse(parent.test))
    return conds


def analyze_chain_break(files: list, rules: dict, budget=None) -> list:
    """链路断裂检查：兜底源调用是否被活跃性守卫保护。
    规则：入口函数 → { fallback_sources, guard_terms, detail }"""
    issues: list = []
    for f in files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        path = Path(f)
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        entry_funcs: dict = {}

        def _collect_funcs(node, out):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.setdefault(child.name, child)
                _collect_funcs(child, out)

        _collect_funcs(tree, entry_funcs)

        for entry, rule in rules.items():
            func = entry_funcs.get(entry)
            if func is None:
                issues.append(ChainBreakIssue(
                    entry=entry, fallback="?", file=str(f), line=0,
                    detail="入口函数未找到（规则过期或函数已改名）"))
                continue
            fallbacks = rule.get("fallback_sources", [])
            guards = rule.get("guard_terms", [])
            for node in ast.walk(func):
                if not isinstance(node, ast.Call):
                    continue
                r = _call_repr(node)
                if not r:
                    continue
                if not any(fb in r or r in fb for fb in fallbacks):
                    continue
                conds = _iter_ancestor_ifs(node, func)
                if any(any(g in c for g in guards) for c in conds):
                    continue  # 已被活跃性守卫保护，正常
                issues.append(ChainBreakIssue(
                    entry=entry, fallback=r, file=str(f), line=node.lineno,
                    detail=rule.get("detail", "兜底源调用无活跃性守卫，活跃会话可能读到旧快照")))
    return issues


# ─── 状态标志生命周期 ───

def _flag_attr_of(call) -> str:
    """从 `self._chat_active.clear()` 提取 attr 名；非 self.attr 形式返回 ''"""
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) \
            and isinstance(f.value.value, ast.Name) and f.value.value.id in ("self", "cls"):
        return f.value.attr
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
            and f.value.id in ("self", "cls"):
        return f.attr
    return ""


def _event_flag_attrs(tree) -> set:
    """收集文件中初始化为 threading.Event() 的属性名（只对这些做 clear/set 配对）。"""
    attrs: set = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Assign):
                continue
            if (sub.value and isinstance(sub.value, ast.Call)
                    and isinstance(sub.value.func, ast.Attribute)
                    and sub.value.func.attr == "Event"):
                for t in sub.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                            and t.value.id in ("self", "cls"):
                        attrs.add(t.attr)
            elif (sub.value and isinstance(sub.value, ast.Call)
                  and isinstance(sub.value.func, ast.Name)
                  and sub.value.func.id == "Event"):
                for t in sub.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                            and t.value.id in ("self", "cls"):
                        attrs.add(t.attr)
    return attrs


def analyze_flag_lifecycle(files: list, budget=None) -> list:
    """状态标志生命周期检查：(a) clear_without_set (b) stale_cache。"""
    issues: list = []
    stale_fields = ("_instance_id", "_last_hash", "_initialized", "_snapshot_seq")

    for f in files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        if not Path(f).exists():
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        event_attrs = _event_flag_attrs(tree)
        if not event_attrs:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fn = node

            # (a) clear/set 配对（只对 Event 标志）
            clears: dict = {}
            sets: dict = {}
            for sub in ast.walk(fn):
                if not isinstance(sub, ast.Call):
                    continue
                attr = _flag_attr_of(sub)
                if not attr or attr not in event_attrs:
                    continue
                if isinstance(sub.func, ast.Attribute) and sub.func.attr == "clear":
                    clears.setdefault(attr, sub.lineno)
                elif isinstance(sub.func, ast.Attribute) and sub.func.attr == "set":
                    sets.setdefault(attr, sub.lineno)
            for attr, cline in clears.items():
                if attr not in sets:
                    issues.append(FlagLifecycleIssue(
                        kind="clear_without_set", attr=attr, file=str(f), line=cline,
                        detail="方法内 clear() 该 Event 标志但无 set() 恢复；若该处后续有 wait() 或跨调用依赖，"
                               "可能永久阻塞或状态残留（需 finally 兜底）"))

            # (b) 跨会话缓存重置：多处赋值 _instance_id 但未见缓存字段重置
            assigns: dict = {}
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Attribute) and t.attr in stale_fields:
                            assigns.setdefault(t.attr, []).append(sub.lineno)
            if "_instance_id" in assigns and len(assigns["_instance_id"]) > 1:
                reset_fields = [k for k in ("_last_hash", "_snapshot_seq")
                                if assigns.get(k)]
                if not reset_fields:
                    issues.append(FlagLifecycleIssue(
                        kind="stale_cache", attr="_instance_id", file=str(f),
                        line=assigns["_instance_id"][0],
                        detail="多处赋值 _instance_id，但函数内未见 _last_hash/_snapshot_seq 重置，"
                               "session 切换可能残留旧检查点状态"))
    return issues


# ─── 状态机合并方向仲裁 ───

def _collect_len_compares(fn) -> list:
    """收集函数内所有基于 len() 或 *_count 的数量比较节点。"""
    found = []
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Compare):
            continue
        op = sub.ops[0] if sub.ops else None
        if not isinstance(op, (ast.Gt, ast.Lt, ast.GtE, ast.LtE)):
            continue
        left, right = sub.left, sub.comparators[0]

        def _is_count_expr(e) -> bool:
            if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == "len":
                return True
            if isinstance(e, ast.Name) and ("count" in e.id.lower() or e.id.lower().endswith("_cnt")):
                return True
            if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Sub) \
                    and _is_count_expr(e.left):
                return True
            return False

        if _is_count_expr(left) or _is_count_expr(right):
            found.append(sub)
    return found


def _collect_version_attrs(fn) -> set:
    """收集函数内引用的「版本/时间戳仲裁字段」：updated_at/version/hash/seq 等"""
    VERSION_HINTS = ("updated_at", "updated", "version", "revision",
                     "_last_hash", "checkpoint_hash", "seq", "_snapshot_seq",
                     "created_at", "mtime", "timestamp")
    attrs = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Attribute):
            if sub.attr in VERSION_HINTS or any(
                    h in sub.attr.lower() for h in ("version", "_hash", "_seq")):
                attrs.add(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if sub.value in VERSION_HINTS:
                attrs.add(sub.value)
    return attrs


def _has_content_arbitration(fn) -> bool:
    """检测「内容级仲裁」手段（等效于版本仲裁，可替代数量仲裁）。"""
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Compare):
            if any(isinstance(op, (ast.Eq, ast.NotEq)) for op in sub.ops):
                sides = [sub.left] + list(sub.comparators)
                if any(isinstance(s, (ast.Attribute, ast.Subscript, ast.Slice))
                       for s in sides):
                    return True
        elif isinstance(sub, ast.Call) and isinstance(sub.func, (ast.Name, ast.Attribute)):
            name = sub.func.id if isinstance(sub.func, ast.Name) else sub.func.attr
            if name in ("_is_prefix", "startswith", "endswith",
                        "reconcile", "diverged"):
                return True
    return False


def analyze_merge_direction(files: list, budget=None) -> list:
    """状态机合并方向仲裁检查：(a) count_only_arbitration。"""
    issues: list = []

    def _has_merge_op(fn) -> bool:
        LOAD_OPS = ("restore_messages", "load_messages")
        SAVE_OPS = ("store.update", "create_with_id", "snapshot_messages",
                    "append_message", "merge_sessions")
        has_load = False
        has_save = False
        for sub in ast.walk(fn):
            if not isinstance(sub, ast.Call) or not isinstance(sub.func, ast.Attribute):
                continue
            if sub.func.attr in LOAD_OPS:
                has_load = True
            obj = getattr(sub.func.value, 'id', None) or getattr(sub.func.value, 'attr', '')
            if sub.func.attr in SAVE_OPS or f"{obj}.{sub.func.attr}" in SAVE_OPS:
                has_save = True
        return has_load and has_save

    for f in files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        if not Path(f).exists():
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fn = node
            if not _has_merge_op(fn):
                continue
            cmp_nodes = _collect_len_compares(fn)
            version_attrs = _collect_version_attrs(fn)
            has_content = _has_content_arbitration(fn)

            if cmp_nodes and not version_attrs and not has_content:
                issues.append(MergeDirectionIssue(
                    kind="count_only_arbitration", fn=fn.name, file=str(f),
                    line=cmp_nodes[0].lineno,
                    detail="用消息数量比较决定覆盖方向，但函数内无 updated_at/version/hash/seq "
                           "等版本字段参与仲裁——数量相等而内容不同时新旧无法识别，"
                           "旧存储可能反向覆盖新数据（加载旧会话的根因）。"
                           "建议引入 updated_at/版本号比较。"))
    return issues


# ─── 标识符命名空间来源契约 ───

def _call_fn_name(call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _key_arg_expr(call):
    """取消费者的 key 实参：第一位置参数，或命名的 key/id/checkpoint_id 关键字"""
    if call.args:
        return call.args[0]
    for kw in call.keywords:
        if kw.arg in ("key", "id", "session_id", "checkpoint_id", "checkpoint", "conversation_id"):
            return kw.value
    return None


def _expr_sig(e) -> str:
    """实参表达式 → 签名：req.session_id → session_id；变量 → 变量名；字符串字面量 → str:<值>"""
    if isinstance(e, ast.Attribute):
        return e.attr
    if isinstance(e, ast.Name):
        return e.id
    if isinstance(e, ast.Constant) and isinstance(e.value, str):
        return "str:" + e.value
    if isinstance(e, ast.Starred) and isinstance(e.value, (ast.Name, ast.Attribute)):
        return _expr_sig(e.value)
    return ""


def analyze_id_source_contract(files: list, rules: list, budget=None) -> list:
    """标识符命名空间来源契约检查：(a) cross_namespace_key (b) unguarded_key_consumer。"""
    issues: list = []
    defs_by_file: dict = {}

    for f in files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        if not Path(f).exists():
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        fndefs: dict = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fndefs.setdefault(node.name, node)
        defs_by_file[str(f)] = fndefs

        # (a) 调用点：cross_namespace_key
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = _call_fn_name(node)
            for rule in rules:
                if fname not in rule["consumers"]:
                    continue
                arg = _key_arg_expr(node)
                if arg is None:
                    continue
                sig = _expr_sig(arg)
                if not sig:
                    continue
                if sig.startswith("str:"):
                    val = sig[4:]
                    # 字符串字面量：命中「另一命名空间」前缀 → 违约；自身前缀合法
                    for r2 in rules:
                        if r2 is rule or not r2["prefix"]:
                            continue
                        if val.startswith(r2["prefix"]):
                            issues.append(IdSourceIssue(
                                kind="cross_namespace_key", consumer=fname,
                                key_arg=val, file=str(f), line=node.lineno,
                                detail=(f"把字面量 '{val}'（{r2['ns']} 前缀）传给 {fname}()——"
                                        f"该消费者属于 {rule['ns']}，查询必然 miss 或误删。")))
                            break
                elif sig in rule["conflict_hints"]:
                    issues.append(IdSourceIssue(
                        kind="cross_namespace_key", consumer=fname,
                        key_arg=sig, file=str(f), line=node.lineno,
                        detail=(f"把「{sig}」传给 {fname}()——{rule['ns']} 的 key 参数。"
                                f"该变量/属性名命中另一命名空间的提示词，key 来源必须回溯到"
                                f"本命名空间的创建点（如 cp = reloader.create_checkpoint(...)），"
                                f"否则查询必 miss 或误删。")))

    # (b) 定义点：unguarded_key_consumer（仅对声明 guard 的命名空间）
    for f, fndefs in defs_by_file.items():
        for rule in rules:
            if not rule.get("guard"):
                continue
            prefix = rule["prefix"]
            for fn_name, fn in fndefs.items():
                if fn_name not in rule["consumers"]:
                    continue
                key_params = [a.arg for a in fn.args.args
                              if a.arg in ("key", "id", "checkpoint_id", "checkpoint", "session_id")]
                if not key_params:
                    continue
                kp = key_params[0]
                used_as_key = False
                has_guard = False
                for sub in ast.walk(fn):
                    if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr in ("get", "find", "query", "pop", "delete")):
                        if any(getattr(a, "id", None) == kp for a in sub.args):
                            used_as_key = True
                    if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "startswith"):
                        target = sub.func.value
                        if (isinstance(target, ast.Call) and isinstance(target.func, ast.Name)
                                and target.func.id == "str" and target.args):
                            target = target.args[0]
                        if getattr(target, "id", None) == kp:
                            has_guard = True
                if used_as_key and not has_guard:
                    issues.append(IdSourceIssue(
                        kind="unguarded_key_consumer", consumer=fn_name,
                        key_arg=kp, file=f, line=fn.lineno,
                        detail=(f"{fn_name}({kp}) 直接把 key 用于存储查找（dict.get/store.get），"
                                f"但函数内无 '{prefix}' 前缀守卫；任何命名空间的标识符都会被"
                                f"当作本系统 key 查询——跨命名空间误用的传播土壤。"
                                f"建议入口处校验 key.startswith('{prefix}') 并给出明确错误。")))
    return issues


# ─── 聚合 ───

def analyze_all(files: list, behavior_rules: dict = None,
                id_source_rules: list = None, chain_break_rules: dict = None,
                budget=None) -> dict:
    """6 维分析聚合 → {defuse, behavior, chain_break, flag, merge, id_source}"""
    return {
        "defuse": analyze_defuse(files, budget=budget),
        "behavior": analyze_behavior(files, behavior_rules or {}, budget=budget),
        "chain_break": analyze_chain_break(files, chain_break_rules or {}, budget=budget),
        "flag": analyze_flag_lifecycle(files, budget=budget),
        "merge": analyze_merge_direction(files, budget=budget),
        "id_source": analyze_id_source_contract(files, id_source_rules or [], budget=budget),
    }
