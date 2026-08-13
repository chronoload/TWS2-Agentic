"""requirement.align：需求规范接口对齐纯逻辑（自演化迁移自 mcp/requirement_align.py）。

无硬编码路径：需求目录 / 代码扫描 glob / 接口索引全部由调用方传入（CLI 按 <name>-project 收敛）。
仅使用 Python 内置模块（re/json/pathlib），语言环境无关。
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path

PATH_RE = re.compile(r"""`?((?:/api|/ws|/media)[^\s`"'，,)\]）；;]+)""", re.UNICODE)
INTERFACE_SECTION_RE = re.compile(r"^\s*(?:\*\*Interfaces\*\*|##\s*Interfaces)\s*:?\s*$", re.I)
SECTION_HEADING_RE = re.compile(r"^\s*(#{1,4}\s|\*\*[^*]+\*\*\s*$)")
FUNC_RE = re.compile(r"([A-Za-z_$][\w$]*(?:\.[\w$]+)?)\s*\(")
EXPORT_RE = re.compile(r"(?:Export|导出|window\.|module\.exports)\s*:?\s*`?([A-Za-z_$][\w$]*(?:\.[\w$]+)?)", re.I)
FILE_LINE_RE = re.compile(r"^\s*[-*]\s*(?:Create|Modify|新建|修改)[:：]?\s*`?([^\s`]+)`?", re.I)

# 接口名黑名单（关键字/控制流/内置）
_FUNC_BLACKLIST = {
    "function", "require", "return", "console", "const", "let", "var", "if",
    "for", "while", "switch", "async", "await", "import", "export", "new",
    "this", "true", "false", "null", "undefined", "typeof", "window",
}


def norm_path(path: str) -> str:
    """归一化路径：剥离 query、模板变量（${x}、:param、{id}）统一为 {}"""
    p = path.strip().rstrip("/")
    p = p.split("?", 1)[0]
    p = re.sub(r"\$\{[^}]*\}", "{}", p)
    p = re.sub(r"\{[^}]*\}", "{}", p)
    p = re.sub(r":[A-Za-z_][\w]*", "{}", p)
    return p


def extract_doc(path: Path) -> list:
    """从单个需求文档提取声明（interface/path/file）"""
    items = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return items
    in_interface_section = False
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("```"):
            continue
        if INTERFACE_SECTION_RE.match(s):
            in_interface_section = True
            continue
        if SECTION_HEADING_RE.match(s) and not in_interface_section:
            in_interface_section = False
            continue
        # 文件声明
        m = FILE_LINE_RE.match(s)
        if m:
            items.append({"kind": "file", "name": m.group(1), "detail": s[:160], "line": lineno})
            continue
        # URL 路径声明
        for pm in PATH_RE.finditer(s):
            p = norm_path(pm.group(1))
            # 过滤目录树噪声（.gitkeep 等文件条目 / 纯 /api 无子路径）
            if not p or p == "/api" or p.endswith("/") or p.split("/")[-1].startswith("."):
                continue
            items.append({"kind": "path", "name": p, "detail": s[:160], "line": lineno})
        # 接口声明：Interfaces 段落内取函数签名；段落外仅取显式 Export/window. 行
        if in_interface_section:
            fm = FUNC_RE.search(s)
            if fm and fm.group(1) not in _FUNC_BLACKLIST:
                items.append({"kind": "interface", "name": fm.group(1), "detail": s[:200], "line": lineno})
        elif EXPORT_RE.search(s):
            em = EXPORT_RE.search(s)
            if em and em.group(1) not in _FUNC_BLACKLIST:
                items.append({"kind": "interface", "name": em.group(1), "detail": s[:200], "line": lineno})
    return items


def scan_dirs(dirs: list, root: Path) -> list:
    """扫描所有需求目录，返回带 source（相对 root）的声明列表。"""
    out = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            for it in extract_doc(f):
                it["source"] = f"{f.relative_to(root) if f.is_relative_to(root) else f}"
                out.append(it)
    return out


# 依赖/生成目录跳过（递归扫描时避免扫入 node_modules/venv 等）
_SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist",
              "build", "site-packages", ".trae-cn", ".pytest_cache"}


def build_code_index(root: Path, globs: list, exclude: tuple = ()) -> dict:
    """预构建代码 token 索引：token -> [file,...]，供存在性快速检查。

    参考 audit._iter_py_files / collect_files 的健壮性约定：
    - os.walk 逐目录容错（断链/权限目录只跳过该目录，不会整批丢失）
    - 排除目录剪枝（默认 _SKIP_DIRS + 显式 exclude），大文件（>1MB 生成产物）跳过
    - globs 用于推导扫描扩展名（如 "**/*.py" → py），不依赖 rglob 递归
    """
    exts = {p.rsplit(".", 1)[-1] for p in globs if "*." in p}
    index = {}
    excl = tuple(_SKIP_DIRS) + tuple(exclude)
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # 剪枝：目录名命中排除集的跳过整棵子树
            dirnames[:] = [d for d in dirnames if d not in excl]
            for fn in filenames:
                if exts and not any(fn.endswith("." + e) for e in exts):
                    continue
                p = Path(dirpath) / fn
                if any(x in p.parts for x in excl):
                    continue
                try:
                    if p.stat().st_size > 12 * 1024 * 1024:  # 仅极端的生成产物跳过
                        continue
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                # 词边界 token 集合（含 . 分隔的整体与末段）
                for m in re.finditer(r"[A-Za-z_$][\w$]*(?:\.[\w$]+)*", text):
                    tok = m.group(0)
                    index.setdefault(tok, []).append(p.name)
                    # 也索引末段（window.parseChunkHeader -> parseChunkHeader）
                    leaf = tok.split(".")[-1]
                    if leaf != tok:
                        index.setdefault(leaf, []).append(p.name)
    except OSError:
        pass
    return index


def align(items: list, index: dict, endpoints: list) -> dict:
    """执行对齐：端点路径 + 代码存在性"""
    # 1. 路径对齐
    declared_paths = {it["name"] for it in items if it["kind"] == "path"}
    actual_paths = {norm_path(e["path"]) for e in endpoints}
    missing_paths, prefix_matches = [], []
    for p in sorted(declared_paths - actual_paths):
        if any(a.startswith(p.rstrip("/") + "/") for a in actual_paths):
            prefix_matches.append(p)  # 声明为某实际端点的前缀，可能合理
        else:
            missing_paths.append(p)
    extra_paths = sorted(actual_paths - declared_paths)

    # 2. 接口/文件存在性
    alignment = []
    for it in items:
        if it["kind"] in ("interface", "file"):
            name = it["name"]
            # 取末段做存在性检查（window.xxx -> xxx）
            leaf = name.split(".")[-1].split("(")[0]
            files = sorted(set(index.get(leaf, []) or index.get(name, [])))[:5]
            found = len(files) > 0
            alignment.append({**it, "found": found, "found_in": ",".join(files) if found else ""})
        else:  # path
            alignment.append({**it, "found": it["name"] in actual_paths,
                              "found_in": next((e["path"] for e in endpoints
                                                if norm_path(e["path"]) == it["name"]), "")})

    not_found = [a for a in alignment if not a["found"]]
    return {
        "alignment": alignment,
        "declared_paths": sorted(declared_paths),
        "actual_paths": sorted(actual_paths),
        "missing_paths": missing_paths,
        "prefix_matches": prefix_matches,
        "extra_paths": extra_paths,
        "not_found": not_found,
    }


def load_endpoints(index_json: str) -> list:
    """读取接口索引 JSON，返回端点列表（缺失/解析失败返回空 + warn 打印）。"""
    if not index_json:
        return []
    try:
        return json.loads(Path(index_json).read_text(encoding="utf-8")).get("endpoints", [])
    except Exception as e:
        print(f"[warn] 读取接口索引失败: {e}")
        return []


def gen_markdown(res: dict, req_dirs: list, index: dict) -> str:
    L = ["# 需求规范接口对齐报告（自动生成）\n"]
    L.append("> 由 `macdev requirement scan/align` 生成。扫描需求文档，与代码实现/实际端点对齐。\n")
    L.append(f"- 扫描目录: `{', '.join(str(d) for d in req_dirs)}`\n")
    L.append(f"- 声明条目: **{len(res['alignment'])}**（路径 {len(res['declared_paths'])} · "
             f"接口/文件 {sum(1 for a in res['alignment'] if a['kind'] != 'path')}）\n")
    L.append(f"- 代码中未找到: **{len(res['not_found'])}** 条\n")
    L.append(f"- 端点缺失(声明未实现): **{len(res['missing_paths'])}** · "
             f"前缀匹配: **{len(res['prefix_matches'])}** · 实现未声明: **{len(res['extra_paths'])}**\n")

    if res["not_found"]:
        L.append("\n## 🔴 声明但代码中不存在\n")
        L.append("| 类型 | 声明 | 来源文档 | 行 | 声明内容 |")
        L.append("|------|------|----------|----|----------|")
        for a in res["not_found"][:60]:
            detail = a["detail"].replace("|", "\\|")[:120]
            L.append(f"| {a['kind']} | `{a['name']}` | {a['source']} | {a['line']} | {detail} |")
    if res["missing_paths"]:
        L.append("\n## 🟠 声明路径未实现\n")
        for p in res["missing_paths"][:40]:
            L.append(f"- `{p}`")
    if res["prefix_matches"]:
        L.append("\n## 🟡 声明路径为某实际端点的前缀（可能合理，人工确认）\n")
        for p in res["prefix_matches"][:20]:
            L.append(f"- `{p}`")
    if res["extra_paths"]:
        L.append("\n## 🟡 已实现但需求未声明（可能为迭代新增）\n")
        L.append(f"共 {len(res['extra_paths'])} 条，见 CSV/SQLite。示例：\n")
        for p in res["extra_paths"][:20]:
            L.append(f"- `{p}`")
    if not res["not_found"] and not res["missing_paths"]:
        L.append("\n✅ 需求声明的接口与代码实现一致。\n")
    return "\n".join(L)
