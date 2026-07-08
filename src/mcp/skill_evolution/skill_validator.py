import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class SkillValidator:
    REQUIRED_FRONTMATTER_FIELDS = {"name", "version", "description", "category", "enabled"}

    def validate_skill_md(self, skill_md_path: Path) -> Tuple[bool, List[str]]:
        errors = []
        if not skill_md_path.exists():
            return False, ["SKILL.md 不存在"]
        content = skill_md_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            errors.append("SKILL.md 必须以 frontmatter (---) 开头")
        else:
            end = content.find("---", 3)
            if end < 0:
                errors.append("Frontmatter 未正确关闭")
            else:
                frontmatter = content[3:end]
                for field_name in self.REQUIRED_FRONTMATTER_FIELDS:
                    if f"{field_name}:" not in frontmatter:
                        errors.append(f"缺少必需字段: {field_name}")
        return len(errors) == 0, errors

    def validate_skill_dir(self, skill_dir: Path) -> Tuple[bool, List[str]]:
        errors = []
        if not skill_dir.is_dir():
            return False, [f"不是目录: {skill_dir}"]
        skill_md = skill_dir / "SKILL.md"
        valid, md_errors = self.validate_skill_md(skill_md)
        errors.extend(md_errors)
        return len(errors) == 0, errors
