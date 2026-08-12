#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rg_search.py — 基于 ripgrep 的加速搜索模块（零新增 Python 依赖）

系统已装 ripgrep 15.1.0（winget），这里直接 subprocess 调用 rg 二进制，
为 GrepTool / GlobTool / sync.search_files / git_searcher 提供 100~200x 加速。

所有对外函数：
  rg_available()                         → 探测 rg 是否可用（缓存）
  rg_grep(pattern, path, ...)            → 全文搜索，返回 (match_count, file_count, lines) 或 None
  rg_files(pattern, path, ...)           → glob 文件匹配，返回相对路径列表或 None
  rg_filelist(query, path, ...)          → 按名称/路径过滤文件，返回相对路径列表或 None

回退约定：任何函数返回 None 表示 rg 不可用/出错，调用方应回退到 Python 实现。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── rg 探测 ──────────────────────────────────────────────
_RG_PATH: Optional[str] = None
_RG_TRIED = False


def _candidate_rg_paths() -> List[str]:
    """候选 rg 路径（覆盖 winget 安装 + 打包内置 + 系统 PATH）"""
    cands: List[str] = []
    # 1) PATH
    which = shutil.which("rg")
    if which:
        cands.append(which)
    # 2) winget 安装目录（BurntSushi.ripgrep.MSVC/GNU）
    try:
        win_get = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if win_get.exists():
            for d in win_get.iterdir():
                if "BurntSushi.ripgrep" in d.name:
                    rg_exe = d / "rg.exe"
                    if rg_exe.exists():
                        cands.append(str(rg_exe))
    except Exception:
        pass
    # 3) 打包内置（exe 同目录 / dist / resources / _internal）
    try:
        if getattr(sys, "frozen", False):  # PyInstaller
            exe_dir = Path(sys.executable).parent
            for sub in ("", "_internal", "resources", "dist"):
                cands.append(str(exe_dir / sub / "rg.exe"))
    except Exception:
        pass
    # 4) 相对本模块的常见位置
    try:
        here = Path(__file__).resolve().parent
        cands.extend([
            str(here / "rg.exe"),
            str(here.parent / "dist" / "rg.exe"),
            str(here.parent / "bin" / "rg.exe"),
            str(here.parent.parent / "dist" / "rg.exe"),
        ])
    except Exception:
        pass
    return cands


def rg_available() -> bool:
    """
    探测 rg 是否可用（结果缓存）。

    回退保障：环境变量 WS2_NO_RG=1/true 时强制禁用 rg（方便沙箱/无 rg 环境），
    此时所有 rg_* 函数返回 None，调用方自动回退 Python 原实现，功能不受影响。
    """
    global _RG_PATH, _RG_TRIED
    if _RG_TRIED:
        return _RG_PATH is not None
    _RG_TRIED = True
    # 显式禁用开关
    if os.environ.get("WS2_NO_RG", "").strip().lower() in ("1", "true", "yes", "on"):
        logger.debug("WS2_NO_RG 已设置，禁用 ripgrep，回退 Python 搜索")
        return False
    for c in _candidate_rg_paths():
        try:
            if Path(c).is_file() and os.access(c, os.X_OK):
                _RG_PATH = c
                return True
        except Exception:
            continue
    # 最后兜底：裸 rg 命令
    try:
        r = subprocess.run(["rg", "--version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            _RG_PATH = "rg"
            return True
    except Exception:
        pass
    return False


def _rg() -> Optional[str]:
    return _RG_PATH if rg_available() else None


def _run_rg(args: List[str], timeout: float = 30.0) -> Optional[subprocess.CompletedProcess]:
    """执行 rg；失败返回 None"""
    rg = _rg()
    if not rg:
        return None
    try:
        return subprocess.run(
            [rg] + args, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except Exception as e:
        logger.debug("rg 执行失败: %s", e)
        return None


# ── 工具函数 ─────────────────────────────────────────────
def _norm_ext(extension: str) -> Optional[str]:
    """扩展名 → rg glob：'.py' / 'py' → '*.py'；空 → None"""
    ext = (extension or "").strip().lstrip(".")
    if not ext:
        return None
    return f"*.{ext}"


def _escape_glob(query: str) -> str:
    """把用户关键词中的 glob 元字符转义为字面匹配（rg 的转义规则）"""
    return (
        query.replace("[", "[[]")
        .replace("*", "[*]")
        .replace("?", "[?]")
        .replace("{", "[{]")
        .replace("}", "[}]")
    )


# ── 1. 全文搜索（GrepTool 加速）──────────────────────────
def rg_grep(pattern: str, path: str = ".", extension: str = "",
            ignore_case: bool = False, context_lines: int = 0,
            max_results: int = 50,
            globs: Optional[List[str]] = None,
            timeout: float = 30.0) -> Optional[Tuple[int, int, List[str]]]:
    """
    ripgrep 全文搜索。
    返回 (match_count, file_count, lines)，与 GrepTool 输出兼容：
      - 无上下文: 'path:line: content'
      - 有上下文: 'path:\\n  >>>  12 | content\\n       11 | ctx'
    返回 None 表示 rg 不可用/正则不兼容，调用方应回退 Python。
    """
    rg = _rg()
    if not rg:
        return None

    p = Path(path)
    if not p.exists():
        return None

    # 构造参数：--json 输出保证 Windows 路径无歧义
    # -a/--text: 强制文本模式，GBK 等非 UTF-8 文件也能匹配 ASCII 关键词
    args = ["--json", "--color", "never", "--no-heading", "-n", "-a"]
    if ignore_case:
        args.append("-i")
    if context_lines > 0:
        args.extend(["-A", str(context_lines), "-B", str(context_lines)])
    if globs:
        for g in globs:
            args.extend(["-g", g])
    else:
        g = _norm_ext(extension)
        if g:
            args.extend(["-g", g])
    args.append(pattern)
    args.append(str(p))

    proc = _run_rg(args, timeout=timeout)
    if proc is None:
        return None
    # 正则不兼容 → returncode 2，回退
    if proc.returncode not in (0, 1):
        logger.debug("rg 返回 %d（可能正则不兼容），回退 Python: %s", proc.returncode, proc.stderr[:200])
        return None

    match_count = 0
    file_count = 0
    lines: List[str] = []
    current_file: Optional[str] = None
    ctx_buffer: List[str] = []

    try:
        for raw in proc.stdout.splitlines():
            if not raw.strip():
                continue
            obj = json.loads(raw)
            typ = obj.get("type")
            data = obj.get("data") or {}
            if typ == "begin":
                current_file = (data.get("path") or {}).get("text")
                ctx_buffer = []
                file_count += 1  # begin 事件 = 一个含匹配的文件开始
            elif typ == "match":
                fpath = (data.get("path") or {}).get("text") or current_file
                if fpath and fpath != current_file:
                    current_file = fpath
                    ctx_buffer = []
                lineno = data.get("line_number", 0)
                content = (data.get("lines") or {}).get("text", "").rstrip("\r\n")
                match_count += 1
                if len(lines) < max_results:
                    if context_lines > 0:
                        if current_file and (not lines or not lines[-1].startswith(str(current_file) + ":")):
                            lines.append(f"{current_file}:")
                        lines.append(f"  >>> {lineno:4d} | {content}")
                    else:
                        lines.append(f"{fpath}:{lineno}: {content}")
            elif typ == "context" and context_lines > 0:
                if len(lines) < max_results:
                    lineno = data.get("line_number", 0)
                    content = (data.get("lines") or {}).get("text", "").rstrip("\r\n")
                    lines.append(f"       {lineno:4d} | {content}")
            elif typ == "end":
                # 一个文件结束，统计文件数（去重由外部处理）
                pass
    except Exception as e:
        logger.debug("rg --json 解析失败: %s", e)
        return None

    return match_count, file_count, lines


# ── 2. glob 文件匹配（GlobTool 加速）─────────────────────
def rg_files(pattern: str, path: str = ".",
             timeout: float = 30.0) -> Optional[List[str]]:
    """
    ripgrep --files + glob 匹配。
    返回匹配文件路径列表（相对 path）；None 表示 rg 不可用。
    """
    rg = _rg()
    if not rg:
        return None
    p = Path(path)
    if not p.exists():
        return None
    # glob 语义对齐：Python glob('*.py') 仅当前目录层（单层，本就不慢→回退 Python）；
    # '**/*.py' / 'src/*.py' 递归/含路径分隔，rg 按完整相对路径匹配，加速生效。
    if "/" not in pattern and not pattern.startswith("**"):
        return None  # 单层 glob 交给 Python（rg 的 / 前缀在 Windows 会锚定盘符根，不可用）
    proc = _run_rg(["--files", "--color", "never", "-g", pattern, str(p)], timeout=timeout)
    if proc is None or proc.returncode not in (0, 1):
        return None
    out = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return out


# ── 3. 枚举目录下所有文件（search_files 加速的底座）─────
def rg_filelist(query: str, path: str = ".",
                excludes: Optional[List[str]] = None,
                timeout: float = 30.0) -> Optional[List[str]]:
    """
    枚举 path 下所有文件（绝对路径），与 pathlib rglob("*") 语义对齐：
      --no-ignore --hidden：Python 的 glob/rglob 匹配隐藏文件且不读 .gitignore（实测确认）；
      excludes：排除 glob 列表（如 node_modules/.git 等），与调用方 IGNORE_PATTERNS 对齐，
                rg 内部跳过可大幅提速（否则枚举海量忽略文件后仍会被过滤丢弃）。

    注意：query 参数保留仅用于兼容旧调用；本函数不做关键词过滤——
    过滤必须由调用方统一执行（Python 语义：query 匹配 name 或完整 rel_path，
    rg 的 -g glob 只匹配 basename，会漏掉目录名命中，故不在此过滤）。
    返回 None 表示 rg 不可用。
    """
    rg = _rg()
    if not rg:
        return None
    p = Path(path)
    if not p.exists():
        return None
    args: List[str] = ["--files", "--color", "never",
                       "--no-ignore",
                       "--glob-case-insensitive"]  # 对齐 lower() 不敏感语义
    # 注：不加 --hidden —— 文件 nav/搜索均过滤隐藏文件，rg 直接跳过更快；隐藏项由调用方 _is_hidden 兜底
    # 粗过滤（rg 内部，快）：basename 含 query 或路径中某目录名含 query。
    # 注意：不能只匹配 basename（-g '*query*'）——Python 语义是匹配完整 rel_path，
    #   目录名命中（如 .../sync/.gitkeep）必须保留，故补 -g '**/*query*/**'。
    # 精确的完整路径过滤仍由调用方 Python 侧统一执行（保证与回退一致）。
    q = (query or "").strip()
    if q:
        qe = _escape_glob(q)
        args.extend(["-g", f"**/*{qe}*", "-g", f"**/*{qe}*/**"])
    if excludes:
        for g in excludes:
            args.extend(["-g", g])
    args.append(str(p))
    proc = _run_rg(args, timeout=timeout)
    if proc is None or proc.returncode not in (0, 1):
        return None
    out = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return out


# ── 4. 测试辅助 ──────────────────────────────────────────
if __name__ == "__main__":
    import time
    print(f"rg 可用: {rg_available()} ({_RG_PATH})")
    if rg_available():
        t0 = time.perf_counter()
        r = rg_grep("def execute", "mcp", extension=".py", max_results=5)
        t1 = time.perf_counter()
        print(f"rg_grep: {(t1-t0)*1000:.1f}ms, match={r[0] if r else 'None'}, files={r[1] if r else '-'}")
        if r:
            for ln in r[2][:3]:
                print("  ", ln[:100])
        t0 = time.perf_counter()
        fl = rg_files("**/*.py", "mcp")
        t1 = time.perf_counter()
        print(f"rg_files: {(t1-t0)*1000:.1f}ms, {len(fl) if fl else 0} 文件")
        t0 = time.perf_counter()
        fl2 = rg_filelist("search", "mcp")
        t1 = time.perf_counter()
        print(f"rg_filelist('search'): {(t1-t0)*1000:.1f}ms, {len(fl2) if fl2 else 0} 文件")
        if fl2:
            for f in fl2[:3]:
                print("  ", f)
