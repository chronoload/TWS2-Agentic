"""audit.frontend：TS/前端 subprocess 扫描插件（自演化，零内核改动）。

解决 macdev audit 只扫 .py（前端 .ts/.js/.vue files=0）的缺口：
通过 subprocess 调用外部工具（rg 优先，缺失降级纯 Python glob+regex）
扫描前端源文件，产出 hardcoded（硬编码 URL/密钥/token）与 data_pools
（前端资源池：import/require 引用图）两个审计维度。

用法（注册于 Registry namespace=audit.frontend）：
    python -m macdev audit --task task.json --root .   # 自动装配本插件
"""
from __future__ import annotations
import csv
import json
import re
import subprocess
from pathlib import Path
from typing import List, Dict

from ..core.plugin import Plugin

# 硬编码模式（URL/API 密钥/token/密钥文件引用）
_HARDCODED_PATTERNS = [
    (r"https?://[^\s'\"`\)]+", "url"),
    (r"(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "secret"),
    (r"sk-[A-Za-z0-9]{16,}", "api_key"),
]


class TsSubprocessScan(Plugin):
    """前端扫描插件：subprocess 调 rg → hardcoded/data_pools CSV 产物"""
    namespace = "audit.frontend"
    name = "ts_subprocess"
    description = "TS/JS/Vue 前端扫描：subprocess rg 硬编码 + import 图数据池"

    def scan(self, root: Path, out_dir: Path,
             extensions: tuple = (".ts", ".js", ".tsx", ".jsx", ".vue")) -> dict:
        """扫描前端目录，产物写 out_dir（收敛 <name>-project/audit/）。
        维度：hardcoded（硬编码）+ data_pools（资源池）+ calls（亲属追踪 def-use 链）。"""
        files = self._collect_files(root, extensions)
        hardcoded = self._scan_hardcoded(root, files)
        data_pools = self._scan_data_pools(files)
        calls = self._scan_calls(files)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._write_csv(out_dir / "frontend_hardcoded.csv",
                        ["file", "line", "kind", "text"], hardcoded)
        self._write_csv(out_dir / "frontend_data_pools.csv",
                        ["file", "pool", "refs"], data_pools)
        self._write_csv(out_dir / "frontend_calls.csv",
                        ["file", "line", "fn", "kind"], calls)
        return {"files": len(files), "hardcoded": len(hardcoded),
                "data_pools": len(data_pools), "calls": len(calls)}

    def _collect_files(self, root: Path, extensions: tuple) -> List[Path]:
        """收集前端源文件（os.walk 带权限容错，忽略 node_modules/dist/build）。"""
        import os
        out = []
        skip = ("/node_modules/", "/dist/", "/build/", "/.git/", "/lib/")

        def _onerror(e: OSError) -> None:
            pass  # 权限拒绝等错误静默跳过（Windows node_modules 常见）

        for dirpath, dirnames, filenames in os.walk(root, onerror=_onerror):
            # 剪枝：跳过 node_modules/dist 等大目录（避免深遍历）
            dirnames[:] = [d for d in dirnames
                           if d not in ("node_modules", "dist", "build", ".git", "lib")]
            for fn in filenames:
                if not fn.endswith(extensions):
                    continue
                p = Path(dirpath) / fn
                rel = str(p).replace("\\", "/")
                if any(s in rel for s in skip):
                    continue
                out.append(p)
        return out

    def _scan_hardcoded(self, root: Path, files: List[Path]) -> List[Dict]:
        """① rg 扫描（subprocess，快）+ 降级纯 Python 正则。"""
        try:
            return self._scan_with_rg(root, files)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return self._scan_with_regex(files)

    def _scan_with_rg(self, root: Path, files: List[Path]) -> List[Dict]:
        r = subprocess.run(
            ["rg", "--json", "-n", r"(https?://|api[_-]?key|secret|token|sk-[A-Za-z0-9]{16,})",
             "--glob", "*.ts", "--glob", "*.js", "--glob", "*.tsx", "--glob", "*.jsx",
             "--glob", "*.vue",
             "--glob", "!**/node_modules/**", "--glob", "!**/dist/**",
             "--glob", "!**/build/**", "--glob", "!**/.git/**",
             str(root)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace")
        out = []
        for line in r.stdout.splitlines():
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("type") != "match":
                continue
            d = m["data"]
            out.append({"file": d.get("path", ""), "line": d.get("line_number", 0),
                        "kind": "rg_match",
                        "text": d.get("lines", {}).get("text", "")[:80].strip()})
        return out

    def _scan_with_regex(self, files: List[Path]) -> List[Dict]:
        """降级：纯 Python 逐行正则（rg 缺失时兜底）。"""
        out = []
        for p in files:
            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for i, ln in enumerate(lines, 1):
                for pat, kind in _HARDCODED_PATTERNS:
                    if re.search(pat, ln):
                        out.append({"file": str(p), "line": i,
                                    "kind": kind, "text": ln.strip()[:80]})
                        break
        return out

    def _scan_data_pools(self, files: List[Path]) -> List[Dict]:
        """② import/require 引用图 → 前端资源池（data_pools 维度）。"""
        pools: Dict[str, set] = {}
        for p in files:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in re.finditer(r"(?:import\s+.*?from\s+|require\()['\"]([^'\"]+)['\"]", text):
                mod = m.group(1)
                pools.setdefault(mod, set()).add(str(p))
        return [{"file": sorted(v)[0], "pool": k, "refs": len(v)}
                for k, v in sorted(pools.items())]

    # TS 定义模式（def）：function/async function/export function/const arrow/class method
    _DEF_RE = [
        re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\("),
        re.compile(r"\b(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>"),
        re.compile(r"\b(?:export\s+)?(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]\s*(?:Promise<[^>]+>)?\s*\{"),
        re.compile(r"\b(?:export\s+)?class\s+(\w+)"),
    ]
    # 调用排除关键字（use 过滤噪音）
    _CALL_SKIP = {"if", "for", "while", "switch", "catch", "return", "typeof", "new",
                  "import", "export", "require", "function", "const", "let", "var",
                  "async", "await", "throw", "delete", "yield", "void", "instanceof"}

    def _scan_calls(self, files: List[Path]) -> List[Dict]:
        """③ 亲属追踪：TS/JS 函数定义(def)与调用(use)链（正则近似 best-effort）。
        产出 frontend_calls.csv：file,line,fn,kind —— 完整实现链路（谁定义谁调用）。"""
        calls: List[Dict] = []
        for p in files:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, ln in enumerate(lines, 1):
                # def 优先匹配
                def_fn = None
                for pat in self._DEF_RE:
                    m = pat.search(ln)
                    if m:
                        def_fn = m.group(1)
                        break
                if def_fn:
                    calls.append({"file": str(p), "line": i, "fn": def_fn, "kind": "def"})
                    continue
                # use：标识符( 调用点
                for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*\(", ln):
                    fn = m.group(1)
                    if fn in self._CALL_SKIP:
                        continue
                    calls.append({"file": str(p), "line": i, "fn": fn, "kind": "use"})
        return calls

    @staticmethod
    def _write_csv(path: Path, fields: List[str], rows: List[Dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k, "") for k in fields})
