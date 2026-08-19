#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill-dynamic-inject catalog — 纯函数核心

发现器/解析器/路由器全部无 I/O 副作用，TDD 单测覆盖。
- scan(dir)  → List[SkillDoc]    发现目录下技能文档
- parse(...) → SkillDoc          单文件解码（无 frontmatter 多级回退）
- route(desc, docs) → SkillDoc|None  关键词打分路由
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class SkillDoc:
    """技能文档值对象（ADT）。macdev 子技能为无 frontmatter 纯 md。"""
    name: str
    description: str
    content: str
    keywords: List[str] = field(default_factory=list)
    source: str = ""


_ZH_MAP = {
    "修": "bug",
    "修复": "bug",
    "bug": "bug",
    "错误": "bug",
    "故障": "bug",
    "设计": "design",
    "新功能": "feature",
    "功能": "feature",
    "需求": "requirement",
    "测试": "test",
    "审计": "audit",
    "审查": "audit",
    "规划": "plan",
    "计划": "plan",
    "排查": "debug",
    "架构": "architecture",
}


def _extend_cn(desc: str) -> List[str]:
    """中文任务描述 → 扩展英文关键词（低配机器翻译，仅路由打分用）"""
    out = []
    for cn, en in _ZH_MAP.items():
        if cn in desc:
            out.append(en)
    return out


def _first_h1(content: str) -> str:
    """取首行 # 标题作为 description（无 frontmatter 回退）"""
    for line in content.splitlines():
        if line.lstrip().startswith("# "):
            return line.lstrip()[2:].strip()
    return ""


_STOPWORDS = {
    "use", "when", "with", "the", "for", "and", "any", "that", "this",
    "from", "will", "can", "should", "your", "you", "are", "not", "etc",
    "all", "has", "have", "its", "into", "over", "than", "then", "was",
    "were", "what", "which", "who", "whom",
}


def _infer_keywords(name: str, title: str, content: str = "") -> List[str]:
    """从文件名/标题/正文提取触发关键词（英文词 + use-when 短语）"""
    tokens = set()
    for text in (name, title):
        for part in re.split(r"[_\-\s]+", text):
            part = part.strip().lower()
            if len(part) >= 3 and part not in tokens:
                tokens.add(part)
    for w in re.findall(r"[a-z][a-z0-9-]{2,}", content.lower()):
        if w in _STOPWORDS:
            continue
        if w not in tokens:
            tokens.add(w)
    return sorted(tokens)


def parse(name: str, source: str, content: str) -> SkillDoc:
    """解码单个技能文档：优先 frontmatter，无则回退首行标题/文件名。"""
    title = ""
    manifest = _parse_frontmatter(content)
    real_name = name
    if manifest:
        real_name = manifest.get("name", name)
        title = manifest.get("description", "") or _first_h1(content)
    else:
        title = _first_h1(content)
    return SkillDoc(
        name=real_name,
        description=title,
        content=content,
        keywords=_infer_keywords(real_name, title, content),
        source=source,
    )


def _parse_frontmatter(content: str) -> Optional[dict]:
    """宽松 frontmatter 解析：--- 包裹的 YAML/键值。无则 None。"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None
    data = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data or None


_NON_SKILL_DIRS = {
    "examples", "sample_out", "sample_project", "doc", "docs", "tests",
    "__pycache__", ".git", ".opencode", "scripts", "node_modules",
}


def scan(skill_dir: Path) -> List[SkillDoc]:
    """递归扫描目录下技能 md 为 SkillDoc。目录不存在 → 空列表。

    规则：`<any>/skills/*.md`（macdev 子技能）或 `*/SKILL.md`（标准技能）。
    排除 examples/doc/产物等非技能目录。name 用相对 skills 目录的路径。
    """
    if not skill_dir.exists() or not skill_dir.is_dir():
        return []
    docs = []
    seen: set = set()

    def is_skill_md(md: Path) -> bool:
        # 子技能：父目录名为 "skills"（macdev-skill/skills/*.md）
        return md.parent.name == "skills"

    for md in sorted(skill_dir.rglob("*.md")):
        rel = md.relative_to(skill_dir)
        if any(part in _NON_SKILL_DIRS for part in rel.parts[:-1]):
            continue
        if not is_skill_md(md):
            continue
        if rel.parts and rel.parts[-1] == "SKILL.md":
            continue  # SKILL.md 由 from_skill_md 处理，scan 专注子技能
        name = md.stem
        if name in seen:
            continue
        seen.add(name)
        try:
            content = md.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        docs.append(parse(name, str(md), content))
    return docs


def route(desc: str, docs: List[SkillDoc]) -> Optional[SkillDoc]:
    """任务描述 → 关键词打分 → 命中最高者；无命中返 None（fallback 全量注入）。"""
    if not docs:
        return None
    haystack = set(_extend_cn(desc)) | set(re.findall(r"[a-z][a-z0-9-]{2,}", desc.lower()))

    def score(doc: SkillDoc) -> int:
        s = 0
        for kw in doc.keywords:
            if kw in haystack:
                s += 2
            elif len(kw) >= 4 and any(
                len(h) >= 4 and (kw.startswith(h[:4]) or h.startswith(kw[:4])) for h in haystack
            ):
                s += 1
        for w in re.findall(r"[a-z][a-z0-9-]*", doc.name.lower()):
            if w in desc.lower():
                s += 1
        return s

    best = max(docs, key=score)
    return best if score(best) > 0 else None