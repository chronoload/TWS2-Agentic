"""audit.scan：4 维度扫描（hardcoded / env_vars / data_pools / static_resources）。
从 extractor 原子重组，函数体保持原样，仅将 _SCAN_DEFAULT_EXCLUDE 等常量内置。
"""
from __future__ import annotations
import ast
import re
from pathlib import Path
from .models import HardcodedItem, EnvVarItem, DataPoolItem, StaticResourceItem
from .parse import _unparse

# 默认排除目录（扫描级）
_SCAN_DEFAULT_EXCLUDE = ("test", "tests", "migrations", "node_modules", ".git", ".venv",
                         "venv", "build", "dist", "site-packages", "__pycache__",
                         "docs", "examples", "assets", "static_arch", "static-branch",
                         "web", "android", "archs", "draft", "static-capacitor")

_JS_SUFFIXES = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".mts")

# 硬编码常量识别
_HARDCODE_KEYWORDS = re.compile(
    r'(api[_-]?key|secret|token|password|passwd|pwd|DB_HOST|DB_PORT|'
    r'database[_-]?url|db[_-]?host|db[_-]?port|connection[_-]?string|'
    r'endpoint|base[_-]?url|api[_-]?url|server[_-]?url)', re.I)
_HARDCODE_URL_RE = re.compile(r'https?://[^\s\'\"<>]+')
_HARDCODE_PORT_RE = re.compile(r':\s*(\d{2,5})')
_HARDCODE_PATH_RE = re.compile(r'["\'](/(?:[\w.\-]+/?)+)["\']')

_ENV_VAR_JS_RE = re.compile(r"process\.env\[['\"]([A-Z0-9_]+)['\"]\]|process\.env\.([A-Z0-9_]+)")

_DATA_POOL_KINDS = {
    "cache": re.compile(r'(?:cache|_cache|Cache)'),
    "pool": re.compile(r'(?:pool|_pool|Pool|PoolManager)'),
    "store": re.compile(r'(?:store|_store|Store|SessionStore)'),
    "agent_pool": re.compile(r'(?:agent_pool|_agent_pool|AgentPool)'),
    "model_cache": re.compile(r'(?:model_cache|_model_cache|ModelCache)'),
    "vector_store": re.compile(r'(?:vector_store|_vector_store|VectorStore|qdrant|chroma|faiss|redis)'),
    "singleton": re.compile(r'(?:singleton|_instance|__instance|Singleton)'),
    "dict": re.compile(r'(?:_dict|registry|_registry|_map|_index)'),
    "list": re.compile(r'(?:_list|_items|_entries)'),
}

_STATIC_FILE_RE = re.compile(
    r'(?:StaticFiles|statics|express\.static|app\.use\(\s*express\.static|mount\s*\(\s*["\']static["\'])')
_IO_PATH_RE = re.compile(r'(?:open|Path\s*\(|Path\([^)]*\))\s*\(\s*["\']([^"\']{3,})["\']')
_PATH_LITERAL_RE = re.compile(r'["\']((?:\.{1,2}/)?(?:[\w.\-]+/)*(?:[\w.\-]+)\.(?:html|htm|jinja2|jinja|'
                              r'css|js|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot|pdf|md|txt))["\']')

_PATH_EXT_KIND = {"html": "template", "htm": "template", "jinja2": "template", "jinja": "template",
                  "css": "css", "js": "js", "png": "image", "jpg": "image",
                  "jpeg": "image", "gif": "image", "svg": "image", "ico": "image",
                  "woff": "font", "woff2": "font", "ttf": "font", "eot": "font"}


# ─── hardcoded ───

def _py_collect_hardcoded(file: Path, tree, rel: str) -> list:
    items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            val_node = node.value
            kind = ""
            val_text = ""
            if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
                val_text = val_node.value
                if _HARDCODE_URL_RE.search(val_text):
                    kind = "url"
                elif _HARDCODE_PORT_RE.search(val_text) and ":" in val_text:
                    kind = "port"
                elif val_text.startswith("/") or ("/" in val_text and not val_text.startswith("http")):
                    kind = "path"
                elif _HARDCODE_KEYWORDS.search(name):
                    kind = "key"
                elif _HARDCODE_KEYWORDS.search(val_text):
                    kind = "secret"
                if kind:
                    items.append(HardcodedItem(
                        file=rel, line=node.lineno, kind=kind,
                        value=val_text[:120], context=name))
            elif isinstance(val_node, ast.Constant) and isinstance(val_node.value, (int, float)):
                if name.endswith(("PORT", "_port")) or "port" in name.lower():
                    items.append(HardcodedItem(
                        file=rel, line=node.lineno, kind="port",
                        value=str(val_node.value), context=name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if node.value:
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    val_text = node.value.value
                    if _HARDCODE_KEYWORDS.search(name):
                        items.append(HardcodedItem(
                            file=rel, line=node.lineno,
                            kind="key" if "key" in name.lower() else "secret",
                            value=val_text[:120], context=name))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args + node.args.kwonlyargs:
                if arg.arg in ("self", "cls"):
                    continue
                default = None
                if arg in node.args.defaults:
                    idx = node.args.defaults.index(arg)
                    default = node.args.defaults[idx]
                elif arg in node.args.kw_defaults:
                    default = node.args.kw_defaults[node.args.kwonlyargs.index(arg)]
                if default and isinstance(default, ast.Constant) and isinstance(default.value, str):
                    val_text = default.value
                    if _HARDCODE_URL_RE.search(val_text) or _HARDCODE_KEYWORDS.search(arg.arg):
                        kind = "url" if _HARDCODE_URL_RE.search(val_text) else "key"
                        items.append(HardcodedItem(
                            file=rel, line=default.lineno or node.lineno,
                            kind=kind, value=val_text[:120], context=f"{node.name}({arg.arg}={val_text[:40]})"))
    return items


def _ts_collect_hardcoded(file: Path, text: str, rel: str) -> list:
    items = []
    for m in _HARDCODE_URL_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        items.append(HardcodedItem(file=rel, line=line, kind="url",
                                   value=m.group(0)[:120], context="url_literal"))
    for m in _HARDCODE_PORT_RE.finditer(text):
        port = m.group(1)
        line = text[:m.start()].count("\n") + 1
        items.append(HardcodedItem(file=rel, line=line, kind="port",
                                   value=port, context="port_literal"))
    for m in _HARDCODE_PATH_RE.finditer(text):
        p = m.group(1)
        line = text[:m.start()].count("\n") + 1
        if len(p) > 3:
            items.append(HardcodedItem(file=rel, line=line, kind="path",
                                       value=p[:120], context="path_literal"))
    for kw in _HARDCODE_KEYWORDS.finditer(text):
        line = text[:kw.start()].count("\n") + 1
        val_match = re.search(rf'{kw.group(0)}["\']?\s*[:=]\s*["\']([^"\']{{4,}})["\']', text[kw.start():kw.start()+100])
        if val_match:
            items.append(HardcodedItem(file=rel, line=line, kind="secret",
                                       value=val_match.group(1)[:120], context=kw.group(0)))
        else:
            items.append(HardcodedItem(file=rel, line=line, kind="key",
                                       value=kw.group(0), context="keyword_literal"))
    return items


def scan_hardcoded(root: Path, files: list, exclude: tuple = _SCAN_DEFAULT_EXCLUDE,
                   budget=None) -> list:
    items = []
    seen = set()
    for f in files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        fp = Path(f)
        if not fp.is_file():
            continue
        if any(part in exclude for part in fp.parts):
            continue
        rel = str(fp.relative_to(root)) if fp.is_relative_to(root) else str(fp)
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        if fp.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(fp))
            except SyntaxError:
                continue
            for item in _py_collect_hardcoded(fp, tree, rel):
                key = (item.file, item.line, item.value)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        elif fp.suffix in _JS_SUFFIXES:
            for item in _ts_collect_hardcoded(fp, text, rel):
                key = (item.file, item.line, item.value)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    return items


# ─── env_vars ───

def _py_collect_env_vars(file: Path, tree, rel: str) -> list:
    items = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute):
            if f.value.attr == "environ" and isinstance(f.value.value, ast.Name) and f.value.value.id == "os":
                if f.attr == "get" and node.args:
                    name = ""
                    default = ""
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        name = node.args[0].value
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        default = str(node.args[1].value)
                    items.append(EnvVarItem(file=rel, line=node.lineno,
                                            name=name, default=default,
                                            context="os.environ.get"))
                elif f.attr == "__getitem__" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        items.append(EnvVarItem(file=rel, line=node.lineno,
                                                name=node.args[0].value, default="",
                                                context="os.environ[...]"))
            elif isinstance(f.value, ast.Name) and f.value.id == "os" and f.attr == "getenv":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    default = ""
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        default = str(node.args[1].value)
                    items.append(EnvVarItem(file=rel, line=node.lineno,
                                            name=node.args[0].value, default=default,
                                            context="os.getenv"))
        elif isinstance(f, ast.Attribute) and f.attr == "get":
            if isinstance(f.value, ast.Attribute) and f.value.attr == "environ":
                if f.value.value and isinstance(f.value.value, ast.Name) and f.value.value.id == "os":
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        default = ""
                        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                            default = str(node.args[1].value)
                        items.append(EnvVarItem(file=rel, line=node.lineno,
                                                name=node.args[0].value, default=default,
                                                context="os.environ.get"))
    return items


def _ts_collect_env_vars(file: Path, text: str, rel: str) -> list:
    items = []
    for m in _ENV_VAR_JS_RE.finditer(text):
        name = m.group(1) or m.group(2)
        line = text[:m.start()].count("\n") + 1
        items.append(EnvVarItem(file=rel, line=line, name=name, default="",
                                context="process.env"))
    return items


def scan_env_vars(root: Path, files: list, exclude: tuple = _SCAN_DEFAULT_EXCLUDE,
                  budget=None) -> list:
    items = []
    seen = set()
    for f in files:
        fp = Path(f)
        if not fp.is_file():
            continue
        if any(part in exclude for part in fp.parts):
            continue
        rel = str(fp.relative_to(root)) if fp.is_relative_to(root) else str(fp)
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        if fp.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(fp))
            except SyntaxError:
                continue
            for item in _py_collect_env_vars(fp, tree, rel):
                key = (item.file, item.line, item.name)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        elif fp.suffix in _JS_SUFFIXES:
            for item in _ts_collect_env_vars(fp, text, rel):
                key = (item.file, item.line, item.name)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    return items


# ─── data_pools ───

def _py_collect_data_pools(file: Path, tree, rel: str) -> list:
    items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            val = node.value
            kind = ""
            size_hint = ""
            for k, pat in _DATA_POOL_KINDS.items():
                if pat.search(name):
                    kind = k
                    break
            if not kind:
                if isinstance(val, ast.Call):
                    f = val.func
                    fname = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                    if fname in ("dict", "list", "set", "OrderedDict", "defaultdict", "Singleton",
                                "AgentPool", "ModelCache", "SessionStore", "VectorStore",
                                "QdrantClient", "ChromaClient", "FaissIndex", "Redis",
                                "ConnectionPool", "asyncio.Queue", "Queue"):
                        kind = "dict" if fname in ("dict", "OrderedDict", "defaultdict") else (
                            "list" if fname in ("list", "set") else "pool")
            if kind:
                size_hint = _unparse(val)[:60]
                items.append(DataPoolItem(file=rel, line=node.lineno, name=name,
                                          kind=kind, size_hint=size_hint,
                                          context="module_level_init"))
        elif isinstance(node, ast.Assign) and len(node.targets) > 1:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name = t.id
                    for k, pat in _DATA_POOL_KINDS.items():
                        if pat.search(name):
                            items.append(DataPoolItem(file=rel, line=node.lineno, name=name,
                                                      kind=k, size_hint="",
                                                      context="module_level_multi_assign"))
                            break
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                                and t.value.id in ("self", "cls"):
                            attr = t.attr
                            for k, pat in _DATA_POOL_KINDS.items():
                                if pat.search(attr):
                                    sh = _unparse(stmt.value)[:60] if stmt.value else ""
                                    items.append(DataPoolItem(file=rel, line=stmt.lineno,
                                                              name=f"{node.name}.{attr}",
                                                              kind=k, size_hint=sh,
                                                              context="class_attr_init"))
                                    break
    return items


def _ts_collect_data_pools(file: Path, text: str, rel: str) -> list:
    items = []
    for pat_name, pat in [
        ("cache", re.compile(r'(?:const|let|var)\s+(\w*[Cc]ache\w*)\s*=')),
        ("pool", re.compile(r'(?:const|let|var)\s+(\w*[Pp]ool\w*)\s*=')),
        ("store", re.compile(r'(?:const|let|var)\s+(\w*[Ss]tore\w*)\s*=')),
        ("agent_pool", re.compile(r'(?:const|let|var)\s+(\w*[Aa]gent[Pp]ool\w*)\s*=')),
        ("model_cache", re.compile(r'(?:const|let|var)\s+(\w*[Mm]odel[Cc]ache\w*)\s*=')),
        ("vector_store", re.compile(r'(?:const|let|var)\s+(\w*[Vv]ector[Ss]tore\w*)\s*=')),
        ("singleton", re.compile(r'(?:const|let|var)\s+(\w*[Ss]ingleton\w*)\s*=')),
    ]:
        for m in pat.finditer(text):
            line = text[:m.start()].count("\n") + 1
            items.append(DataPoolItem(file=rel, line=line, name=m.group(1),
                                      kind=pat_name, size_hint="",
                                      context="variable_init"))
    return items


def scan_data_pools(root: Path, files: list, exclude: tuple = _SCAN_DEFAULT_EXCLUDE,
                    budget=None) -> list:
    items = []
    seen = set()
    for f in files:
        fp = Path(f)
        if not fp.is_file():
            continue
        if any(part in exclude for part in fp.parts):
            continue
        rel = str(fp.relative_to(root)) if fp.is_relative_to(root) else str(fp)
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        if fp.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(fp))
            except SyntaxError:
                continue
            for item in _py_collect_data_pools(fp, tree, rel):
                key = (item.file, item.line, item.name)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        elif fp.suffix in _JS_SUFFIXES:
            for item in _ts_collect_data_pools(fp, text, rel):
                key = (item.file, item.line, item.name)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    return items


# ─── static_resources ───

def _py_collect_static_resources(file: Path, tree, rel: str) -> list:
    items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            sig = _unparse(f)[:60] if f else ""
            if "StaticFiles" in sig or "statics" in sig or "express.static" in sig:
                path_val = ""
                if node.args:
                    a0 = node.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        path_val = a0.value
                kind = "static_files" if "StaticFiles" in sig else "express_static"
                items.append(StaticResourceItem(file=rel, line=node.lineno,
                                                path=path_val or sig, kind=kind,
                                                context="static_mount"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            fname = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if fname in ("open", "read_text", "read_bytes", "write_text", "write_bytes"):
                if node.args:
                    a0 = node.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        items.append(StaticResourceItem(
                            file=rel, line=node.lineno, path=a0.value[:120],
                            kind="io_path", context=fname))
            elif fname == "Path" and node.args:
                a0 = node.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    items.append(StaticResourceItem(
                        file=rel, line=node.lineno, path=a0.value[:120],
                        kind="io_path", context="Path()"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if _PATH_LITERAL_RE.match(v):
                ext = Path(v).suffix.lower().lstrip(".")
                kind = _PATH_EXT_KIND.get(ext, "other")
                items.append(StaticResourceItem(
                    file=rel, line=getattr(node, 'lineno', 0) or 0,
                    path=v[:120], kind=kind, context="path_literal"))
    return items


def _ts_collect_static_resources(file: Path, text: str, rel: str) -> list:
    items = []
    for m in _STATIC_FILE_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        items.append(StaticResourceItem(file=rel, line=line, path=m.group(0)[:120],
                                        kind="express_static", context="static_mount"))
    for m in _IO_PATH_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        items.append(StaticResourceItem(file=rel, line=line, path=m.group(1)[:120],
                                        kind="io_path", context="file_read_write"))
    for m in _PATH_LITERAL_RE.finditer(text):
        path = m.group(1)
        line = text[:m.start()].count("\n") + 1
        ext = Path(path).suffix.lower().lstrip(".")
        kind = _PATH_EXT_KIND.get(ext, "other")
        items.append(StaticResourceItem(file=rel, line=line, path=path[:120],
                                        kind=kind, context="path_literal"))
    return items


def scan_static_resources(root: Path, files: list, exclude: tuple = _SCAN_DEFAULT_EXCLUDE,
                          budget=None) -> list:
    items = []
    seen = set()
    for f in files:
        if budget:
            budget.tick()
            if budget.expired():
                break
        fp = Path(f)
        if not fp.is_file():
            continue
        if any(part in exclude for part in fp.parts):
            continue
        rel = str(fp.relative_to(root)) if fp.is_relative_to(root) else str(fp)
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        if fp.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(fp))
            except SyntaxError:
                continue
            for item in _py_collect_static_resources(fp, tree, rel):
                key = (item.file, item.line, item.path)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        elif fp.suffix in _JS_SUFFIXES:
            for item in _ts_collect_static_resources(fp, text, rel):
                key = (item.file, item.line, item.path)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    return items


# ─── 聚合 ───

def scan_all(root: Path, files: list, exclude: tuple = _SCAN_DEFAULT_EXCLUDE,
             budget=None) -> dict:
    """四维扫描聚合 → {hardcoded, env_vars, data_pools, static_resources}"""
    return {
        "hardcoded": scan_hardcoded(root, files, exclude, budget=budget),
        "env_vars": scan_env_vars(root, files, exclude, budget=budget),
        "data_pools": scan_data_pools(root, files, exclude, budget=budget),
        "static_resources": scan_static_resources(root, files, exclude, budget=budget),
    }
