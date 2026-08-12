"""Rmd 格式扫描器：编译前检查格式问题"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScanError:
    line: int
    type: str  # "unclosed_div" | "unclosed_math" | "unclosed_code" | "invalid_yaml" | "template_placeholder"
    message: str


@dataclass
class ScanWarning:
    line: int
    type: str  # "empty_section" | "long_paragraph" | "missing_visual"
    message: str


@dataclass
class ScanReport:
    file_path: str
    errors: list[ScanError] = field(default_factory=list)
    warnings: list[ScanWarning] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [f"Scan: {self.file_path} — {status}"]
        for e in self.errors:
            lines.append(f"  ERROR L{e.line} [{e.type}]: {e.message}")
        for w in self.warnings:
            lines.append(f"  WARN  L{w.line} [{w.type}]: {w.message}")
        return "\n".join(lines)


def scan_rmd(file_path: str | Path) -> ScanReport:
    """扫描 Rmd 文件格式问题"""
    path = Path(file_path)
    report = ScanReport(file_path=str(path))

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1. 检查 ::: fenced div 闭合
    _check_div_closure(lines, report)

    # 2. 检查 $ 行内数学 / $$ 块数学配对
    _check_math_pairs(lines, report)

    # 3. 检查 ``` 代码块闭合
    _check_code_block_closure(lines, report)

    # 4. 检查 YAML 头格式
    _check_yaml_header(lines, report)

    # 5. 检查 {{placeholder}} 残留
    _check_template_placeholders(lines, report)

    # 6. 检查空节
    _check_empty_sections(lines, report)

    return report


def _check_div_closure(lines: list[str], report: ScanReport) -> None:
    """检查 ::: fenced div 是否闭合"""
    stack = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith(":::"):
            parts = stripped.split()
            if len(parts) >= 2:
                if parts[1].startswith("{"):  # ::: {.class} 开始
                    stack.append((i, parts[1] if len(parts) > 1 else "div"))
                elif stripped == ":::":  # 闭合
                    if stack:
                        stack.pop()
                    else:
                        report.errors.append(ScanError(i, "unclosed_div", "多余的 ::: 闭合（无匹配的开始）"))
    for line_no, div_type in stack:
        report.errors.append(ScanError(line_no, "unclosed_div", f"未闭合的 ::: 块 ({div_type})"))


def _check_math_pairs(lines: list[str], report: ScanReport) -> None:
    """检查 $ 和 $$ 配对"""
    in_code_block = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        # $$ 块数学
        dd_count = stripped.count("$$")
        if dd_count % 2 != 0:
            report.errors.append(ScanError(i, "unclosed_math", f"$$ 未配对（本行 {dd_count} 个）"))
        # $ 行内数学（排除 $$ 和转义 \$）
        clean = stripped.replace("$$", "").replace("\\$", "")
        dollar_count = clean.count("$")
        if dollar_count % 2 != 0:
            report.warnings.append(ScanWarning(i, "unclosed_math", "$ 行内数学可能未配对"))


def _check_code_block_closure(lines: list[str], report: ScanReport) -> None:
    """检查 ``` 代码块闭合"""
    in_code = False
    code_start = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_start = i
            else:
                in_code = False
    if in_code:
        report.errors.append(ScanError(code_start, "unclosed_code", f"代码块从 L{code_start} 开始未闭合"))


def _check_yaml_header(lines: list[str], report: ScanReport) -> None:
    """检查 YAML 头格式"""
    if not lines or not lines[0].strip() == "---":
        report.warnings.append(ScanWarning(1, "invalid_yaml", "缺少 YAML 头开始标记 ---"))
        return
    end_idx = -1
    for i, line in enumerate(lines[1:], 2):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx == -1:
        report.errors.append(ScanError(1, "invalid_yaml", "YAML 头未闭合（缺少第二个 ---）"))
        return
    # 检查关键字段
    yaml_content = "".join(lines[1 : end_idx - 1])
    if "title:" not in yaml_content:
        report.warnings.append(ScanWarning(1, "invalid_yaml", "YAML 缺少 title 字段"))
    if "output:" not in yaml_content:
        report.warnings.append(ScanWarning(1, "invalid_yaml", "YAML 缺少 output 字段"))


def _check_template_placeholders(lines: list[str], report: ScanReport) -> None:
    """检查未替换的 {{placeholder}}"""
    for i, line in enumerate(lines, 1):
        matches = re.findall(r"\{\{(\w+)\}\}", line)
        for m in matches:
            report.errors.append(ScanError(i, "template_placeholder", f"未替换的模板变量 {{{{{m}}}}}"))


def _check_empty_sections(lines: list[str], report: ScanReport) -> None:
    """检查空节（# X：后无内容）"""
    section_re = re.compile(r"^#\s+[A-Z][A-Za-z]*[：:]")
    last_section_line = 0
    last_section_name = ""
    for i, line in enumerate(lines, 1):
        if section_re.match(line.strip()):
            if last_section_line > 0:
                # 检查上一个节是否有内容
                content_between = [l for l in lines[last_section_line:i] if l.strip() and not l.strip().startswith("#")]
                if not content_between:
                    report.warnings.append(ScanWarning(last_section_line, "empty_section", f"节 '{last_section_name.strip()}' 无实质内容"))
            last_section_line = i
            last_section_name = line
