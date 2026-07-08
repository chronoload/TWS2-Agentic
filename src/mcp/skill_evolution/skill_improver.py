import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ImprovementSuggestion:
    skill_name: str
    field: str
    current_value: str
    suggested_value: str
    reason: str


class SkillImprover:
    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)

    def analyze_usage(self, skill_name: str, usage_log: List[Dict]) -> List[ImprovementSuggestion]:
        suggestions = []
        if not usage_log:
            return suggestions
        failures = [u for u in usage_log if not u.get("success", True)]
        if len(failures) > len(usage_log) * 0.3:
            suggestions.append(ImprovementSuggestion(
                skill_name=skill_name,
                field="description",
                current_value="",
                suggested_value="",
                reason=f"失败率过高 ({len(failures)}/{len(usage_log)})，需要改进描述或步骤",
            ))
        avg_duration = sum(u.get("duration_ms", 0) for u in usage_log) / max(len(usage_log), 1)
        if avg_duration > 30000:
            suggestions.append(ImprovementSuggestion(
                skill_name=skill_name,
                field="steps",
                current_value="",
                suggested_value="",
                reason=f"平均执行时间过长 ({avg_duration/1000:.1f}s)，考虑优化步骤",
            ))
        return suggestions

    def apply_improvement(self, skill_dir: Path, suggestion: ImprovementSuggestion) -> bool:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return False
        try:
            content = skill_md.read_text(encoding="utf-8")
            content = re.sub(
                r'version:\s*"(\d+)\.(\d+)\.(\d+)"',
                lambda m: f'version: "{m.group(1)}.{int(m.group(2))+1}.0"',
                content,
            )
            content += f"\n\n## 改进记录\n- {suggestion.reason}\n"
            skill_md.write_text(content, encoding="utf-8")
            logger.info(f"技能 {suggestion.skill_name} 已改进: {suggestion.reason}")
            return True
        except Exception as e:
            logger.error(f"改进技能失败: {e}")
            return False
