#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作区注入 — 参考 OpenClaw 的 workspace + skills 设计
从工作区加载 AGENTS.md / TOOLS.md / SOUL.md 等文件注入到系统提示
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class WorkspaceFiles:
    agents_md: Optional[str] = None
    tools_md: Optional[str] = None
    soul_md: Optional[str] = None
    skills: List[str] = field(default_factory=list)

    def to_injection(self) -> str:
        parts = []
        if self.soul_md:
            parts.append(f"## 角色设定\n{self.soul_md}")
        if self.agents_md:
            parts.append(f"## 项目导引\n{self.agents_md}")
        if self.tools_md:
            parts.append(f"## 可用工具\n{self.tools_md}")
        if self.skills:
            skills_text = "\n\n".join(self.skills)
            parts.append(f"## 技能\n{skills_text}")
        return "\n\n---\n\n".join(parts)


WORKSPACE_FILES = ["AGENTS.md", "TOOLS.md", "SOUL.md"]


def load_workspace_files(workspace_root: str) -> WorkspaceFiles:
    result = WorkspaceFiles()
    root = Path(workspace_root)

    if not root.exists():
        return result

    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        try:
            result.agents_md = agents_path.read_text(encoding="utf-8")
        except Exception:
            pass

    tools_path = root / "TOOLS.md"
    if tools_path.exists():
        try:
            result.tools_md = tools_path.read_text(encoding="utf-8")
        except Exception:
            pass

    soul_path = root / "SOUL.md"
    if soul_path.exists():
        try:
            result.soul_md = soul_path.read_text(encoding="utf-8")
        except Exception:
            pass

    skills_dir = root / "skills"
    if skills_dir.exists() and skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    try:
                        result.skills.append(skill_md.read_text(encoding="utf-8"))
                    except Exception:
                        pass

    return result


def resolve_workspace_injection(
    workspace_root: Optional[str] = None,
    additional_paths: Optional[List[str]] = None,
) -> str:
    workspace_files = None
    if workspace_root:
        workspace_files = load_workspace_files(workspace_root)

    extra_content = []
    if additional_paths:
        for path in additional_paths:
            p = Path(path)
            if p.exists() and p.is_file():
                try:
                    content = p.read_text(encoding="utf-8")
                    extra_content.append(f"## {p.name}\n{content}")
                except Exception:
                    pass
            elif p.exists() and p.is_dir():
                for f in sorted(p.iterdir()):
                    if f.suffix.lower() in (".md", ".txt"):
                        try:
                            content = f.read_text(encoding="utf-8")
                            extra_content.append(f"## {f.name}\n{content}")
                        except Exception:
                            pass

    parts = []
    if workspace_files:
        injection = workspace_files.to_injection()
        if injection:
            parts.append(injection)

    if extra_content:
        parts.append("\n\n---\n\n".join(extra_content))

    return "\n\n".join(parts)