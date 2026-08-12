"""dev.commands：学习/模仿目标项目的命令（map 目录编排 + audit 架构了解）。

命令函数返回 (code, lines)（与 plan/log/requirement 同一约定）。
扫描参考 audit 健壮性：os.walk 逐目录容错 + 排除目录剪枝 + 大文件跳过统计。
"""
from __future__ import annotations
import csv
import json
import os
import sqlite3
from pathlib import Path

# 目录编排跳过（依赖/生成目录，随 --exclude 追加）
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
              "dist", "build", "site-packages", ".pytest_cache", "cache"}

# 技术栈线索文件（命中即在 LEARN 摘要里提示）
_STACK_FILES = ("package.json", "pyproject.toml", "requirements.txt", "go.mod",
                "Cargo.toml", "pom.xml", "build.gradle", "composer.json",
                "Gemfile", "Makefile", "Dockerfile")
# 入口/关键文件（目录编排时标注）
_ENTRY_FILES = ("main.py", "app.py", "server.py", "manage.py", "run.py",
                "index.js", "index.ts", "main.go", "main.rs", "app.js",
                "server.js", "README.md", "readme.md", "LICENSE")


def _collect(root: Path, exclude: tuple) -> list:
    """os.walk 逐目录容错收集文件（参考 audit）：跳过 _SKIP_DIRS + exclude 目录剪枝。"""
    files = []
    excl = set(_SKIP_DIRS) | set(exclude)
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in excl]
            for fn in filenames:
                p = Path(dirpath) / fn
                if any(x in p.parts for x in excl):
                    continue
                try:
                    st = p.stat()
                    files.append({"path": p, "rel": str(p.relative_to(root)),
                                  "size": st.st_size, "lines": 0})
                except OSError:
                    continue
    except OSError:
        pass
    # 行数统计（跳过 >12MB 极端生成产物）
    for f in files:
        if f["size"] > 12 * 1024 * 1024:
            continue
        try:
            with open(f["path"], "rb") as fh:
                f["lines"] = sum(1 for _ in fh)
        except OSError:
            pass
    return files


def _tree_lines(root: Path, files: list, depth: int) -> list:
    """目录树（限深）：按层级缩进渲染，目录优先排序。

    nodes: {rel_dir(Path) -> {"dirs": set, "files": set}}，根目录 key=Path(".")。
    用 Path.parts 计算层级，跨平台（不依赖 os.sep 拼接）。
    """
    nodes: dict = {}

    def _key(parent: Path) -> Path:
        return parent.relative_to(root) if parent != root else Path(".")

    for f in files:
        k = _key(f["path"].parent)
        nodes.setdefault(k, {"dirs": set(), "files": set()})["files"].add(f["rel"])
    # 补齐中间目录
    for k in list(nodes):
        for i in range(1, len(k.parts) + 1):
            nodes.setdefault(Path(*k.parts[:i]), {"dirs": set(), "files": set()})
    # 填充各目录的直接子目录
    for k, node in nodes.items():
        for other in nodes:
            if len(other.parts) == len(k.parts) + 1 and other.parts[:-1] == k.parts:
                node["dirs"].add(other.parts[-1])

    lines = [f"📁 {root.name}/"]

    def _render(key: Path, depth_left: int, prefix: str):
        node = nodes[key]
        for d in sorted(node["dirs"]):
            lines.append(f"{prefix}📁 {d}/")
            if depth_left > 0:
                _render(key / d, depth_left - 1, prefix + "  ")
        for fn in sorted(node["files"]):
            mark = " ⭐" if Path(fn).name in _ENTRY_FILES else ""
            lines.append(f"{prefix}📄 {Path(fn).name}{mark}")

    _render(Path("."), max(int(depth), 1), "  ")
    return lines


def _stats(files: list) -> dict:
    """摘要：文件数 / 类型分布 / 总行数 / 行数 top / 模块分布 / 技术栈线索。"""
    kinds = {}
    by_dir = {}
    total_lines = 0
    stack = set()
    top = sorted(files, key=lambda f: f["lines"], reverse=True)[:15]
    for f in files:
        ext = Path(f["rel"]).suffix or "(none)"
        kinds[ext] = kinds.get(ext, 0) + 1
        d = Path(f["rel"]).parent.as_posix()
        by_dir[d] = by_dir.get(d, 0) + 1
        total_lines += f["lines"]
        if Path(f["rel"]).name in _STACK_FILES:
            stack.add(f["rel"])
    return {
        "total_files": len(files),
        "total_lines": total_lines,
        "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
        "modules": dict(sorted(by_dir.items(), key=lambda kv: -kv[1])),
        "top_files": [{"rel": f["rel"], "lines": f["lines"], "size": f["size"]} for f in top],
        "stack_clues": sorted(stack),
    }


def cmd_map(target: str = "", out: str = "", depth: int = 3,
            exclude: str = "") -> tuple:
    """扫描目标学习项目，编排目录（树 + 模块地图 + 技术栈线索），双轨产物。"""
    root = Path(target)
    if not root.is_dir():
        return 1, [f"[dev] 目标目录不存在: {root}"]
    out_dir = Path(out) if out else root
    out_dir.mkdir(parents=True, exist_ok=True)

    files = _collect(root, tuple(e.strip() for e in exclude.split(",") if e.strip()))
    tree = _tree_lines(root, files, int(depth))
    stats = _stats(files)

    # 人类轨：DIR_TREE.md
    md = [f"# 目标项目目录编排：{root.name}", "",
          f"> 由 `macdev dev map` 生成（学习/模仿用）· 目标: `{root}` · 共 {stats['total_files']} 文件 / {stats['total_lines']} 行", "",
          "## 目录树", "", "```", *tree, "```", "",
          "## 模块地图（目录文件数 top）", "",
          "| 目录 | 文件数 |", "|------|--------|"]
    for d, n in list(stats["modules"].items())[:20]:
        md.append(f"| `{d}` | {n} |")
    md += ["", "## 文件类型分布", "", "| 类型 | 数量 |", "|------|------|"]
    for k, n in list(stats["kinds"].items())[:15]:
        md.append(f"| `{k}` | {n} |")
    md += ["", "## 行数 top 文件（最可能的核心实现）", "",
           "| 文件 | 行数 | 大小(KB) |", "|------|------|---------|"]
    for t in stats["top_files"]:
        md.append(f"| `{t['rel']}` | {t['lines']} | {t['size'] // 1024} |")
    if stats["stack_clues"]:
        md += ["", "## 技术栈线索", ""]
        for s in stats["stack_clues"]:
            md.append(f"- `{s}`")
    (out_dir / "DIR_TREE.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # 机器轨：json + csv + db
    (out_dir / "dir_tree.json").write_text(
        json.dumps({"target": str(root), "tree": tree, "stats": stats},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out_dir / "dir_tree.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rel", "lines", "size"])
        for f_ in sorted(files, key=lambda x: x["rel"]):
            w.writerow([f_["rel"], f_["lines"], f_["size"]])
    db = out_dir / "dir_tree.db"
    conn = sqlite3.connect(str(db))
    try:
        c = conn.cursor()
        c.execute("DROP TABLE IF EXISTS files")
        c.execute("CREATE TABLE files(rel TEXT, lines INT, size INT)")
        c.executemany("INSERT INTO files VALUES (?,?,?)",
                      [(f_["rel"], f_["lines"], f_["size"]) for f_ in files])
        c.execute("DROP TABLE IF EXISTS stats")
        c.execute("CREATE TABLE stats(key TEXT, value TEXT)")
        c.executemany("INSERT INTO stats VALUES (?,?)",
                      [("total_files", str(stats["total_files"])),
                       ("total_lines", str(stats["total_lines"])),
                       ("target", str(root))] +
                      [("module:" + k, str(v)) for k, v in stats["modules"].items()])
        conn.commit()
    finally:
        conn.close()

    lines = [f"[dev] map {root.name} 文件={stats['total_files']} 行={stats['total_lines']}",
             "  artifacts → DIR_TREE.md / dir_tree.json / dir_tree.csv / dir_tree.db"]
    for t in stats["top_files"][:5]:
        lines.append(f"  ⭐ {t['rel']}（{t['lines']} 行）")
    return 0, lines


def cmd_audit(engine, target: str = "", out: str = "",
              strategy: str = "base", exclude: str = "", timeout: int = 0) -> tuple:
    """架构了解：自动编排默认 AuditTask 跑快速探索，复用 audit 双轨产物。"""
    root = Path(target)
    if not root.is_dir():
        return 1, [f"[dev] 目标目录不存在: {root}"]
    from ..audit.task import AuditTask
    out_dir = Path(out) if out else root
    ex = tuple(e.strip() for e in exclude.split(",") if e.strip())
    task = AuditTask(root=root, strategy=strategy or "base",
                     exclude=AuditTask.exclude + ex,
                     scan_timeout=int(timeout))
    result = engine.run_audit(task, out_dir)
    data = " ".join(f"{k}={v}" for k, v in result.data.items())
    lines = [f"[dev] audit {root.name} ok={result.ok} {data}",
             "  artifacts → INTERFACE_CHAIN.md / interface_chain.db / *.csv / events.ndjson"]
    if result.data.get("truncated"):
        lines.append("  ⚠ 超时截断：仅已扫描子集，结果不完整")
    return (0, lines) if result.ok else (1, lines)
