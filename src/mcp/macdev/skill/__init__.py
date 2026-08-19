#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill 插件 — 子技能动态注入（发现/路由/注入，服务 TS2 harness）

Plugin 平级哲学：register(registry) 注册 "skill.catalog" 命名空间；
CLI 子命令 scan/inject/route/list 由 cli.py 挂载，处理函数在本模块。
"""
import json
from pathlib import Path
from typing import List, Optional

from ..core.registry import Registry
from .catalog import SkillDoc, parse, route, scan

DEFAULT_DIRS = ["skills", "skills_market"]


def register(registry: Registry) -> None:
    registry.register("skill.catalog", "base", scan)


def _resolve_dir(extra: str, root: str = ".") -> Path:
    """技能目录：显式 --dir 优先，缺省探测 <root>/skills 与 <root>/skills_market，空则回退 <root>/src/skills。"""
    if extra:
        p = Path(extra)
        if p.is_absolute() or p.exists():
            return p
        return Path(root) / extra
    root_p = Path(root)
    for cand in DEFAULT_DIRS:
        c = root_p / cand
        if c.exists() and c.is_dir() and any(c.rglob("*.md")):
            return c
    src_skills = root_p / "src" / "skills"
    if src_skills.exists() and src_skills.is_dir() and any(src_skills.rglob("*.md")):
        return src_skills
    return root_p


def cmd_skill_scan(args) -> int:
    """扫描目录列出可发现子技能（含推断字段）"""
    d = _resolve_dir(args.dir, args.root)
    docs = scan(d)
    lines = [f"[skill] scan {d} -> {len(docs)} docs"]
    for doc in docs:
        lines.append(f"  - {doc.name} | {doc.description or '(无标题)'} | keywords={','.join(doc.keywords[:8])}")
    _print(args, "\n".join(lines))
    return 0


def cmd_skill_inject(args) -> int:
    """整文件内容输出到 stdout（供 harness 注入 system prompt）"""
    d = _resolve_dir(args.dir, args.root)
    docs = scan(d)
    hit = next((x for x in docs if x.name == args.name), None)
    if hit is None:
        _print(args, f"[skill] 未找到 {args.name}；可用: {', '.join(x.name for x in docs)}", err=True)
        return 2
    _print(args, hit.content)
    return 0


def cmd_skill_route(args) -> int:
    """任务描述 → 自动匹配子技能名（供 harness 按需注入）"""
    d = _resolve_dir(args.dir, args.root)
    docs = scan(d)
    hit = route(args.task, docs)
    if hit is None:
        _print(args, json.dumps({"matched": None, "fallback": "all"}, ensure_ascii=False))
        return 0
    _print(args, json.dumps({"matched": hit.name, "description": hit.description}, ensure_ascii=False))
    return 0


def cmd_skill_list(args) -> int:
    """默认目录列表"""
    d = _resolve_dir(args.dir, args.root)
    docs = scan(d)
    lines = [f"[skill] {d}"]
    for doc in docs:
        lines.append(doc.name)
    _print(args, "\n".join(lines))
    return 0


def _print(args, text: str, err: bool = False) -> None:
    out = __import__("sys").stderr if err else __import__("sys").stdout
    try:
        print(text, file=out)
    except UnicodeEncodeError:
        out.buffer.write((text + "\n").encode("utf-8", errors="backslashreplace"))
        out.buffer.flush()