"""INDEX.md 自动生成器"""

import re
from pathlib import Path

from ._base import count_chars, count_lines


def detect_status(rmd_path: Path, output_dir: Path) -> str:
    """检测文档状态：pending / drafted / compiled"""
    if not rmd_path.exists():
        return "pending"
    pdf_name = rmd_path.stem + ".pdf"
    if (output_dir / pdf_name).exists():
        return "compiled"
    return "drafted"


def extract_title(rmd_path: Path) -> str:
    """从 Rmd 中提取标题"""
    try:
        with open(rmd_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("title:"):
                    return line.split(":", 1)[1].strip().strip('"').strip("'")
                if line.strip().startswith("subtitle:"):
                    sub = line.split(":", 1)[1].strip().strip('"').strip("'")
                    # 从 subtitle 中提取课时标题
                    match = re.search(r"课时\d+\s+(.+)$", sub)
                    if match:
                        return match.group(1)
    except Exception:
        pass
    return rmd_path.stem


def generate_index(course_dir: str | Path, output_path: str | Path, project_name: str = "") -> str:
    """
    扫描 course_dir 下所有 Rmd，生成 INDEX.md
    """
    course = Path(course_dir)
    out = Path(output_path)

    # 收集所有 Rmd
    rmd_files = sorted(course.rglob("*.Rmd"))
    if not rmd_files:
        rmd_files = sorted(course.rglob("*.rmd"))

    output_dir = out.parent / "output" if out.parent.exists() else course

    rows = []
    for rmd in rmd_files:
        rel = rmd.relative_to(course)
        title = extract_title(rmd)
        status = detect_status(rmd, output_dir)
        chars = count_chars(rmd.read_text(encoding="utf-8"), exclude_code=True) if rmd.exists() else 0
        lines = count_lines(rmd) if rmd.exists() else 0

        status_icon = {"pending": "⏳", "drafted": "📝", "compiled": "✅"}.get(status, "❓")
        section = rel.parts[0] if len(rel.parts) > 1 else "-"

        rows.append(f"| {rel.stem} | {title} | {section} | {status_icon} {status} | {chars:,} | {lines} |")

    # 生成 Markdown
    header = f"""# {project_name} — 大纲索引

> 自动生成于 indexer.py。勿手动编辑。

| 文件 | 标题 | Section | 状态 | 字符数 | 行数 |
|------|------|---------|------|--------|------|
"""
    content = header + "\n".join(rows) + f"\n\n**总计**: {len(rmd_files)} 篇文档\n"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return content
