import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ScanFinding:
    rule_id: str
    severity: Severity
    message: str
    file_path: str = ""
    line_number: int = 0
    context: str = ""


@dataclass
class ScanResult:
    skill_name: str
    findings: List[ScanFinding] = field(default_factory=list)
    passed: bool = True

    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @property
    def has_warning(self) -> bool:
        return any(f.severity == Severity.WARNING for f in self.findings)


_DANGEROUS_PATTERNS = [
    (r"os\.system\s*\(", "R001", Severity.CRITICAL, "os.system() 调用可能执行任意命令"),
    (r"subprocess\.(call|run|Popen)\s*\(", "R002", Severity.WARNING, "subprocess 调用需审查"),
    (r"eval\s*\(", "R003", Severity.CRITICAL, "eval() 可能执行任意代码"),
    (r"exec\s*\(", "R004", Severity.CRITICAL, "exec() 可能执行任意代码"),
    (r"__import__\s*\(", "R005", Severity.WARNING, "动态导入需审查"),
    (r"open\s*\(.*['\"]w", "R006", Severity.INFO, "文件写入操作"),
    (r"shutil\.rmtree", "R007", Severity.CRITICAL, "递归删除目录"),
    (r"os\.remove\s*\(", "R008", Severity.WARNING, "删除文件操作"),
    (r"requests\.(post|put|delete|patch)", "R009", Severity.WARNING, "HTTP 写操作"),
    (r"\.env|API_KEY|SECRET|PASSWORD|TOKEN", "R010", Severity.CRITICAL, "硬编码密钥/凭证"),
    (r"socket\s*\(", "R011", Severity.WARNING, "网络 socket 操作"),
    (r"pickle\.loads?\s*\(", "R012", Severity.CRITICAL, "pickle 反序列化不安全"),
]


class SecurityScanner:
    def __init__(self, custom_rules: Optional[List] = None):
        self._patterns = list(_DANGEROUS_PATTERNS)
        if custom_rules:
            self._patterns.extend(custom_rules)

    def scan_skill(self, skill_dir: Path) -> ScanResult:
        result = ScanResult(skill_name=skill_dir.name)

        if not skill_dir.exists() or not skill_dir.is_dir():
            result.findings.append(ScanFinding(
                rule_id="S001",
                severity=Severity.WARNING,
                message=f"技能目录不存在: {skill_dir}",
            ))
            result.passed = False
            return result

        for py_file in skill_dir.rglob("*.py"):
            self._scan_file(py_file, result)

        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            self._scan_skill_md(skill_md, result)

        if result.has_critical:
            result.passed = False

        return result

    def scan_content(self, content: str, name: str = "unknown") -> ScanResult:
        result = ScanResult(skill_name=name)
        for line_no, line in enumerate(content.split("\n"), 1):
            for pattern, rule_id, severity, message in self._patterns:
                if re.search(pattern, line):
                    result.findings.append(ScanFinding(
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        line_number=line_no,
                        context=line.strip()[:100],
                    ))
        if result.has_critical:
            result.passed = False
        return result

    def _scan_file(self, file_path: Path, result: ScanResult):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            result.findings.append(ScanFinding(
                rule_id="S002",
                severity=Severity.WARNING,
                message=f"无法读取文件: {e}",
                file_path=str(file_path),
            ))
            return

        rel_path = str(file_path.relative_to(Path(result.skill_name))) if result.skill_name else str(file_path)

        for line_no, line in enumerate(content.split("\n"), 1):
            for pattern, rule_id, severity, message in self._patterns:
                if re.search(pattern, line):
                    result.findings.append(ScanFinding(
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        file_path=rel_path,
                        line_number=line_no,
                        context=line.strip()[:100],
                    ))

    def _scan_skill_md(self, skill_md: Path, result: ScanResult):
        try:
            content = skill_md.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return

        for pattern, rule_id, severity, message in self._patterns:
            matches = list(re.finditer(pattern, content))
            for match in matches:
                line_no = content[:match.start()].count("\n") + 1
                result.findings.append(ScanFinding(
                    rule_id=rule_id,
                    severity=severity,
                    message=f"SKILL.md: {message}",
                    file_path="SKILL.md",
                    line_number=line_no,
                ))
