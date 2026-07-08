#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 Git 搜索工具 — 参考 OpenCode 的 LSP 集成 + Cline 的代码搜索

提供:
  git_grep        文本搜索（支持正则）
  git_history     文件提交历史
  git_blame       行级归属
  git_diff        版本间差异
  git_semantic    语义搜索（embedding）
"""
from __future__ import annotations

import os
import re
import json
import hashlib
import subprocess
import tempfile
import asyncio
import locale
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


def _get_output_encoding() -> str:
    """获取系统首选编码"""
    try:
        return locale.getpreferredencoding(False) or "utf-8"
    except Exception:
        return "utf-8"


@dataclass
class SearchResult:
    repository: str
    file_path: str
    line_number: int
    content: str
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)
    commit_hash: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "repository": self.repository,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "content": self.content,
            "commit_hash": self.commit_hash,
            "author": self.author,
            "date": self.date,
            "context": "\n".join(self.context_before + [f">>> {self.content}"] + self.context_after),
        }


@dataclass
class CommitInfo:
    hash: str
    message: str
    author: str
    date: str
    files_changed: int = 0

    def to_dict(self) -> dict:
        return {
            "hash": self.hash, "message": self.message,
            "author": self.author, "date": self.date,
            "files_changed": self.files_changed,
        }


@dataclass
class BlameLine:
    line_number: int
    commit_hash: str
    author: str
    date: str
    content: str

    def to_dict(self) -> dict:
        return {
            "line": self.line_number, "commit": self.commit_hash,
            "author": self.author, "date": self.date,
            "content": self.content.strip(),
        }


class GitSearcher:
    """Git 仓库搜索器 — 支持本地仓库"""

    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir:
            cache_dir = Path(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = cache_dir
        self._cloned: Dict[str, Path] = {}

    # ---- Text Search (git grep) ----

    def grep(self, repo_path: str, query: str,
             file_patterns: Optional[List[str]] = None,
             max_results: int = 50,
             context_lines: int = 3) -> List[SearchResult]:
        """
        git grep 文本搜索

        Args:
            repo_path: 仓库本地路径
            query: 搜索模式（支持基本正则）
            file_patterns: 文件过滤 ['*.py', '*.ts']
            max_results: 最大结果数
            context_lines: 上下文行数
        """
        repo = Path(repo_path)
        if not (repo / ".git").exists():
            return []

        results: List[SearchResult] = []
        cmd = ["git", "grep", "-n", "--color=never"]

        if context_lines > 0:
            cmd.extend(["-A", str(context_lines), "-B", str(context_lines)])

        cmd.append(query)

        if file_patterns:
            cmd.append("--")
            cmd.extend(file_patterns)

        try:
            encoding = _get_output_encoding()
            output = subprocess.run(
                cmd, cwd=str(repo), capture_output=True, text=True,
                timeout=30, encoding=encoding, errors="replace",
            )
            if output.returncode not in (0, 1):
                return results

            current_file = None
            for line in output.stdout.split("\n")[:max_results * (context_lines * 2 + 1)]:
                if not line.strip():
                    continue
                match = re.match(r"^(.+?)(?:-(\d+)-)?[:=](\d+)[:-](.*)$", line)
                if match:
                    file_path = match.group(1).strip()
                    line_num = int(match.group(3))
                    content = match.group(4)
                    if current_file != file_path:
                        current_file = file_path
                    results.append(SearchResult(
                        repository=str(repo),
                        file_path=file_path,
                        line_number=line_num,
                        content=content.strip(),
                    ))
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            return []

        return results[:max_results]

    # ---- File History ----

    def history(self, repo_path: str, file_path: str,
                max_commits: int = 20) -> List[CommitInfo]:
        """获取文件提交历史"""
        repo = Path(repo_path)
        if not (repo / ".git").exists():
            return []

        try:
            encoding = _get_output_encoding()
            output = subprocess.run(
                ["git", "log", f"--max-count={max_commits}",
                 "--pretty=format:%H|%s|%an|%ad", "--date=short",
                 "--", file_path],
                cwd=str(repo), capture_output=True,
                timeout=15, encoding=encoding, errors="replace",
            )
            commits = []
            for line in output.stdout.strip().split("\n"):
                if not line or "|" not in line:
                    continue
                parts = line.split("|", 3)
                commits.append(CommitInfo(
                    hash=parts[0][:12],
                    message=parts[1] if len(parts) > 1 else "",
                    author=parts[2] if len(parts) > 2 else "",
                    date=parts[3] if len(parts) > 3 else "",
                ))
            return commits
        except Exception:
            return []

    # ---- Blame ----

    def blame(self, repo_path: str, file_path: str) -> List[BlameLine]:
        """获取文件 blame 信息"""
        repo = Path(repo_path)
        if not (repo / ".git").exists():
            return []

        try:
            encoding = _get_output_encoding()
            output = subprocess.run(
                ["git", "blame", "--line-porcelain", file_path],
                cwd=str(repo), capture_output=True,
                timeout=30, encoding=encoding, errors="replace",
            )
            lines: List[BlameLine] = []
            current: Dict[str, str] = {}

            for line in output.stdout.split("\n"):
                if line.startswith("\t"):
                    current["content"] = line[1:]
                    lines.append(BlameLine(
                        line_number=len(lines) + 1,
                        commit_hash=(current.get("commit") or "")[:12],
                        author=current.get("author", ""),
                        date=current.get("author-time", ""),
                        content=current.get("content", ""),
                    ))
                    current = {}
                elif " " in line:
                    k, v = line.split(" ", 1)
                    current[k] = v

            return lines
        except Exception:
            return []

    # ---- Diff ----

    def diff(self, repo_path: str, commit_a: str = "HEAD~1",
             commit_b: str = "HEAD", file_path: str = "") -> str:
        """获取版本间 diff"""
        repo = Path(repo_path)
        if not (repo / ".git").exists():
            return ""

        cmd = ["git", "diff", commit_a, commit_b]
        if file_path:
            cmd.extend(["--", file_path])

        try:
            encoding = _get_output_encoding()
            output = subprocess.run(
                cmd, cwd=str(repo), capture_output=True,
                timeout=30, encoding=encoding, errors="replace",
            )
            return output.stdout[:20000]  # 限制输出
        except Exception:
            return ""

    # ---- Remote Clone + Search ----

    def clone_and_search(self, repo_url: str, query: str,
                         file_patterns: Optional[List[str]] = None,
                         max_results: int = 30) -> List[SearchResult]:
        """克隆远程仓库并搜索（浅克隆）"""
        if not self.cache_dir:
            return []

        repo_key = hashlib.md5(repo_url.encode()).hexdigest()[:12]
        repo_path = self.cache_dir / repo_key

        if repo_path.exists():
            try:
                subprocess.run(
                    ["git", "fetch", "--depth=50", "origin"],
                    cwd=str(repo_path), capture_output=True,
                    timeout=30,
                )
            except Exception:
                pass
        else:
            try:
                subprocess.run(
                    ["git", "clone", "--depth=50", "--single-branch",
                     repo_url, str(repo_path)],
                    capture_output=True, timeout=120,
                )
            except Exception as e:
                return []

        results = self.grep(str(repo_path), query, file_patterns, max_results)
        for r in results:
            r.repository = repo_url
        return results

    # ---- Cleanup ----

    def cleanup_cache(self, max_age_days: int = 7):
        if not self.cache_dir or not self.cache_dir.exists():
            return
        import time
        cutoff = time.time() - max_age_days * 86400
        for d in self.cache_dir.iterdir():
            try:
                if d.stat().st_mtime < cutoff and d.is_dir():
                    import shutil
                    shutil.rmtree(d)
            except Exception:
                pass


# ============================================================
# Singleton
# ============================================================

_git_searcher: Optional[GitSearcher] = None


def get_git_searcher(cache_dir: Optional[Path] = None) -> GitSearcher:
    global _git_searcher
    if _git_searcher is None:
        _git_searcher = GitSearcher(cache_dir)
    return _git_searcher


__all__ = [
    "GitSearcher", "SearchResult", "CommitInfo", "BlameLine",
    "get_git_searcher",
]