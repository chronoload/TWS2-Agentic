#!/usr/bin/env python3
"""需求规范接口对齐器 — 从 superpowers/spec/plan 文档提取接口声明，与代码/实际端点比对。

用途：
  1. 扫描需求文档（.opencode/sdd、.superpowers/sdd、openspec 及自定义目录），提取：
     - 接口声明（Interfaces 段落的函数/导出）
     - URL 路径声明（/api/...、/ws/...）
     - 文件声明（Create/Modify: xxx）
  2. 对齐检查：
     - 端点对齐：需求声明的路径 vs interface_chain_index.json 中的实际端点
       → declared_but_missing（声明了未实现）/ implemented_not_declared（实现未声明）
     - 代码存在性：接口函数名 vs 源码文件（词边界匹配）
       → found / not_found（声明的接口在代码中不存在）
  3. 输出：requirements.json / requirements.csv / requirement_alignment.db / requirement_alignment.md

用法：
  python mcp/requirement_align.py [--req-dirs DIR [DIR ...]] [--out DIR] [--index path]
仅使用 Python 内置模块（re/json/csv/sqlite3/pathlib）。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = MCP_ROOT.parent

DEFAULT_REQ_DIRS = [
    PROJECT_ROOT / ".opencode" / "sdd",
    MCP_ROOT / "server" / ".superpowers" / "sdd",
    PROJECT_ROOT / "openspec",
]
DEFAULT_INDEX = MCP_ROOT / "docs" / "interface_chain_index.json"
DEFAULT_OUT = MCP_ROOT / "docs"

# 代码存在性搜索范围（前端 JS + 后端 Python）
CODE_SEARCH_GLOBS = [
    MCP_ROOT / "server" / "static" / "*.js",
    MCP_ROOT / "server" / "saber" / "*.py",
    MCP_ROOT / "*.py",
]

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


def scan_dirs(dirs: list) -> list:
    """扫描所有需求目录，返回带 source 的声明列表"""
    out = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            for it in extract_doc(f):
                it["source"] = f"{f.relative_to(PROJECT_ROOT) if f.is_relative_to(PROJECT_ROOT) else f}"
                out.append(it)
    return out


def build_code_index() -> dict:
    """预构建代码 token 索引：token -> [file,...]，供存在性快速检查"""
    index = {}
    for glob in CODE_SEARCH_GLOBS:
        for f in sorted(Path(glob).parent.glob(Path(glob).name)):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            # 词边界 token 集合（含 . 分隔的整体与末段）
            for m in re.finditer(r"[A-Za-z_$][\w$]*(?:\.[\w$]+)*", text):
                tok = m.group(0)
                index.setdefault(tok, []).append(f.name)
                # 也索引末段（window.parseChunkHeader -> parseChunkHeader）
                leaf = tok.split(".")[-1]
                if leaf != tok:
                    index.setdefault(leaf, []).append(f.name)
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
            alignment.append({
                **it,
                "found": found,
                "found_in": ",".join(files) if found else "",
            })
        else:  # path
            alignment.append({**it, "found": it["name"] in actual_paths,
                              "found_in": next((e["path"] for e in endpoints if norm_path(e["path"]) == it["name"]), "")})

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


def gen_markdown(res: dict, req_dirs: list, index: dict) -> str:
    L = ["# 需求规范接口对齐报告（自动生成）\n"]
    L.append("> 由 `mcp/requirement_align.py` 生成。扫描需求文档，与代码实现/实际端点对齐。\n")
    L.append(f"- 扫描目录: `{', '.join(str(d) for d in req_dirs)}`\n")
    L.append(f"- 声明条目: **{len(res['alignment'])}**（路径 {len(res['declared_paths'])} · 接口/文件 {sum(1 for a in res['alignment'] if a['kind'] != 'path')}）\n")
    L.append(f"- 代码中未找到: **{len(res['not_found'])}** 条\n")
    L.append(f"- 端点缺失(声明未实现): **{len(res['missing_paths'])}** · 前缀匹配: **{len(res['prefix_matches'])}** · 实现未声明: **{len(res['extra_paths'])}**\n")

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


def main():
    ap = argparse.ArgumentParser(description="需求规范接口对齐器")
    ap.add_argument("--req-dirs", nargs="*", default=None, help="需求文档目录（默认 superpowers/sdd/openspec）")
    ap.add_argument("--out", type=str, default=str(DEFAULT_OUT), help="输出目录")
    ap.add_argument("--index", type=str, default=str(DEFAULT_INDEX), help="接口索引 JSON 路径")
    args = ap.parse_args()

    req_dirs = [Path(d) for d in args.req_dirs] if args.req_dirs else DEFAULT_REQ_DIRS
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    items = scan_dirs(req_dirs)
    endpoints = []
    try:
        idx = json.loads(Path(args.index).read_text(encoding="utf-8"))
        endpoints = idx.get("endpoints", [])
    except Exception as e:
        print(f"[warn] 读取接口索引失败: {e}")

    code_index = build_code_index()
    res = align(items, code_index, endpoints)

    # JSON
    (out_dir / "requirements.json").write_text(
        json.dumps({"scanned_dirs": [str(d) for d in req_dirs],
                    "items": res["alignment"],
                    "missing_paths": res["missing_paths"],
                    "prefix_matches": res["prefix_matches"],
                    "extra_paths": res["extra_paths"]},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    # CSV
    with open(out_dir / "requirements.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["source", "line", "kind", "name", "found", "found_in", "detail"])
        for a in res["alignment"]:
            w.writerow([a["source"], a["line"], a["kind"], a["name"], a["found"], a["found_in"], a["detail"]])
    # SQLite
    conn = sqlite3.connect(str(out_dir / "requirement_alignment.db"))
    try:
        c = conn.cursor()
        c.execute("DROP TABLE IF EXISTS requirements")
        c.execute("""CREATE TABLE requirements(
            source TEXT, line INT, kind TEXT, name TEXT,
            found INT, found_in TEXT, detail TEXT)""")
        c.executemany("INSERT INTO requirements VALUES (?,?,?,?,?,?,?)",
                      [(a["source"], a["line"], a["kind"], a["name"],
                        int(a["found"]), a["found_in"], a["detail"]) for a in res["alignment"]])
        c.execute("DROP TABLE IF EXISTS path_alignment")
        c.execute("CREATE TABLE path_alignment(status TEXT, path TEXT)")
        c.executemany("INSERT INTO path_alignment VALUES (?,?)",
                      [("missing", p) for p in res["missing_paths"]] +
                      [("prefix", p) for p in res["prefix_matches"]] +
                      [("extra", p) for p in res["extra_paths"]] +
                      [("matched", p) for p in res["declared_paths"] if p in set(res["actual_paths"])])
        conn.commit()
    finally:
        conn.close()
    # Markdown
    (out_dir / "REQUIREMENT_ALIGNMENT.md").write_text(gen_markdown(res, req_dirs, code_index), encoding="utf-8")

    print(f"[OK] 需求对齐报告 → {out_dir / 'REQUIREMENT_ALIGNMENT.md'}")
    print(f"声明={len(res['alignment'])} 未找到={len(res['not_found'])} "
          f"端点缺失={len(res['missing_paths'])} 实现未声明={len(res['extra_paths'])}")
    for a in res["not_found"][:10]:
        print(f"  ⚠ [not_found] {a['kind']} `{a['name']}` @ {a['source']}:{a['line']}")
    for p in res["missing_paths"][:10]:
        print(f"  ⚠ [missing] {p}")


if __name__ == "__main__":
    main()
