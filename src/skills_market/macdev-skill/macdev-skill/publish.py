"""发布 macdev-skill → .trae/skills/macdev 与 docs/macdev（独立管理，不走 TS2 同步脚本）。
复制：*.md 文档 + examples/ 示范目录。
"""
from __future__ import annotations
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "macdev-skill"
for dst in (ROOT / ".trae" / "skills" / "macdev", ROOT / "docs" / "macdev"):
    dst.mkdir(parents=True, exist_ok=True)
    for f in SRC.glob("*.md"):
        shutil.copy2(f, dst / f.name)
        print(f"publish → {dst / f.name}")
    # examples 示范目录（sample_project + sample_out）
    examples_dst = dst / "examples"
    if (SRC / "examples").exists():
        shutil.rmtree(examples_dst, ignore_errors=True)
        shutil.copytree(SRC / "examples", examples_dst)
        print(f"publish → {examples_dst}/")
