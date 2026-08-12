"""术语/符号一致性追踪"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TermUsage:
    term: str
    definition: str
    source_file: str
    line: int


@dataclass
class ConsistencyReport:
    consistent_terms: list[str] = field(default_factory=list)
    inconsistent_terms: list[dict] = field(default_factory=list)
    new_terms: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.inconsistent_terms) == 0

    def summary(self) -> str:
        lines = [f"Terminology check: {'PASS' if self.ok else 'FAIL'}"]
        lines.append(f"  Consistent: {len(self.consistent_terms)}")
        lines.append(f"  Inconsistent: {len(self.inconsistent_terms)}")
        for inc in self.inconsistent_terms:
            lines.append(f"    - '{inc['term']}': {len(inc['usages'])} different definitions")
        lines.append(f"  New (not in terminology.json): {len(self.new_terms)}")
        return "\n".join(lines)


def extract_terms(rmd_path: str | Path) -> dict[str, str]:
    """
    从 Rmd 中提取术语
    策略：
    1. ::: definition 块中的加粗术语
    2. # K 节中首次出现的 **加粗** 术语
    """
    path = Path(rmd_path)
    terms = {}

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")

    in_definition = False
    for i, line in enumerate(lines):
        stripped = line.strip()

        # ::: definition 块开始
        if stripped.startswith(":::") and "definition" in stripped:
            in_definition = True
            continue

        # ::: 结束
        if stripped == ":::" and in_definition:
            in_definition = False
            continue

        # 在 definition 块中，提取加粗术语
        if in_definition:
            bold_match = re.search(r"\*\*([^*]+)\*\*", stripped)
            if bold_match:
                term = bold_match.group(1).strip()
                # 跳过通用标记
                if term not in ("定义", "Definition", "定义名称"):
                    terms[term] = f"L{i+1}"

    return terms


def check_consistency(
    rmd_paths: list[str | Path],
    terminology_file: str | Path | None = None,
) -> ConsistencyReport:
    """
    检查跨文档术语一致性
    """
    report = ConsistencyReport()

    # 加载已有的术语表
    existing_terms = {}
    term_file = Path(terminology_file) if terminology_file else None
    if term_file and term_file.exists():
        with open(term_file, "r", encoding="utf-8") as f:
            existing_terms = json.load(f)

    # 从所有 Rmd 提取术语
    all_terms: dict[str, list[TermUsage]] = {}
    for rmd_path in rmd_paths:
        terms = extract_terms(rmd_path)
        for term, source in terms.items():
            if term not in all_terms:
                all_terms[term] = []
            all_terms[term].append(TermUsage(term=term, definition=source, source_file=str(rmd_path), line=0))

    # 检查一致性
    for term, usages in all_terms.items():
        if len(usages) > 1:
            # 同一术语在多个文件中出现——检查定义是否一致
            definitions = set(u.definition for u in usages)
            if len(definitions) > 1:
                report.inconsistent_terms.append({
                    "term": term,
                    "usages": [{"file": u.source_file, "def": u.definition} for u in usages],
                })
            else:
                report.consistent_terms.append(term)
        else:
            report.consistent_terms.append(term)

    # 检查新术语
    for term in all_terms:
        if term not in existing_terms:
            report.new_terms.append({"term": term, "source": all_terms[term][0].source_file})

    return report


def update_terminology(new_terms: dict[str, str], terminology_file: str | Path) -> None:
    """更新 terminology.json"""
    path = Path(terminology_file)
    existing = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing.update(new_terms)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
