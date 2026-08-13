"""audit.parse：从 extractor 原子组装（extract_imports/extract_func_map/extract_endpoints/
extract_python_models + 辅助），函数体保持原子原样，仅调整依赖为 macdev 内部。"""
from __future__ import annotations
import ast
from pathlib import Path
from .models import Endpoint, RequestModel, ModelField

HTTP_METHODS = ("get", "post", "put", "delete", "patch", "websocket", "api_route", "route")


# ---------- 辅助原子 ----------

def _unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def _get_doc(body: list) -> str:
    for stmt in body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            return stmt.value.value.strip().split("\n")[0][:100]
    return ""


def _collect_response_keys(func: ast.FunctionDef) -> list[str]:
    """静态提取 ok(data={...}) / ok(data=dict(...)) 的顶层键"""
    keys: list[str] = []

    def _walk_dict(d: ast.Dict):
        for k in d.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.append(k.value)

    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ok":
            for kw in node.keywords:
                if kw.arg == "data":
                    if isinstance(kw.value, ast.Dict):
                        _walk_dict(kw.value)
                    elif isinstance(kw.value, ast.Call) and isinstance(kw.value.func, ast.Name) and kw.value.func.id == "dict":
                        for a in kw.value.args:
                            if isinstance(a, ast.Dict):
                                _walk_dict(a)
    # 去重保序
    seen = set()
    out = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _extract_model_class(cls: ast.ClassDef, file: str, models: list):
    base_names = []
    for b in cls.bases:
        bn = _unparse(b)
        base_names.append(bn)
    if not any("BaseModel" in b for b in base_names):
        return  # 只提取 Pydantic 模型
    m = RequestModel(name=cls.name, file=file, line=cls.lineno, doc=_get_doc(cls.body))
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            typ = _unparse(stmt.annotation)
            default = None
            required = True
            if stmt.value is not None:
                default = _unparse(stmt.value)
                required = False
            m.fields.append(ModelField(name=name, type=typ, default=default or "", required=required))
    models.append(m)


def _type_short(t: str) -> str:
    import re
    t = t.replace("typing.", "")
    # 逐层剥掉泛型包裹（Optional/List/Dict/Tuple）
    prev = None
    while prev != t:
        prev = t
        t = (t.replace("Optional[", "")
               .replace("List[", "list[")
               .replace("Dict[", "dict[")
               .replace("Tuple[", "tuple["))
    # 修复多余右括号：如 "list[str]]" → "list[str]"
    t = re.sub(r"\]+$", "]", t)
    return t


# ---------- 解析原子 ----------

def extract_imports(path: Path) -> dict:
    """提取模块内所有 import（含函数内），返回 {名称: 模块路径}"""
    if not path.exists():
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return {}
    imports: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                imports[a.asname or a.name] = mod
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports[a.asname or a.name] = a.name
    return imports


def extract_func_map(path: Path) -> dict:
    """提取模块内所有函数定义（含嵌套），返回 {函数名: FunctionDef}"""
    if not path.exists():
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return {}
    fmap: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fmap.setdefault(node.name, node)
    return fmap


def extract_endpoints(path: Path, decorator_names: tuple, endpoints: list, prefix: str = "",
                      loose: bool = False):
    """提取 FastAPI/APIRouter 端点。decorator_names: ('app.get', 'app.post', ...)
    prefix: 路由前缀（如 saber 的 '/api/saber'）
    loose=True：通用模式——decorator_names 传 HTTP 方法名（'get','post',…），
    只要装饰器是 `X.<method>('path')`（X 为任意对象）即提取，不限 app/router 变量名。"""
    if not path.exists():
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if loose:
                    matched = dec.func.attr in decorator_names
                else:
                    qual = f"{dec.func.value.id}.{dec.func.attr}" if isinstance(dec.func.value, ast.Name) else ""
                    matched = qual in decorator_names
                if matched and dec.args:
                    path_expr = dec.args[0]
                    if isinstance(path_expr, ast.Constant) and isinstance(path_expr.value, str):
                        ep = Endpoint(
                            method=dec.func.attr.upper(),
                            path=prefix + path_expr.value,
                            func=node.name,
                            file=path.name,
                            line=dec.lineno,
                            doc=_get_doc(node.body),
                            response_keys=_collect_response_keys(node),
                        )
                        # 函数参数（跳过 self/cls/request）
                        for a in node.args.args:
                            if a.arg in ("self", "cls"):
                                continue
                            ep.params.append(a.arg)
                        # 请求模型：从类型注解中找 *Request
                        for a in node.args.args:
                            if a.annotation:
                                ann = _unparse(a.annotation)
                                if ann.endswith("Request") or "BaseModel" in ann:
                                    ep.request_model = ann
                        endpoints.append(ep)


def extract_python_models(path: Path, models: list):
    if not path.exists():
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            _extract_model_class(node, path.name, models)


# ---------- 任务级组装 ----------

def extract_all(task) -> tuple:
    """按 AuditTask 配置提取端点 + 请求模型 → (endpoints, models)"""
    endpoints: list = []
    models: list = []
    files = task.files or {}
    for ep_cfg in task.endpoints:
        fkey = ep_cfg.get("file", "app")
        # 兼容两种写法：直接文件名（a.py）或 task.files 的 key（app → server/app.py）
        rel = fkey if fkey.endswith(".py") else files.get(fkey) or f"server/{fkey}.py"
        p = task.root / rel
        module = ep_cfg.get("module", "app")
        decs = tuple(f"{module}.{m}" for m in ep_cfg.get("methods", []))
        extract_endpoints(p, decs, endpoints, prefix=ep_cfg.get("prefix", ""))
        extract_python_models(p, models)
    # 扫描目录（loose 通用模式）
    for rel_dir in task.scan_dirs:
        d = task.root / rel_dir
        if d.is_dir():
            for p in sorted(d.glob("*.py")):
                if p.name == "__init__.py":
                    continue
                extract_endpoints(p, HTTP_METHODS, endpoints, loose=True)
                extract_python_models(p, models)
    return endpoints, models
