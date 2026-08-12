import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


STAGE_NAME_TO_NUMBER: Dict[str, int] = {
    "topic_init": 1,
    "problem_decompose": 2,
    "search_strategy": 3,
    "literature_collect": 4,
    "literature_screen": 5,
    "knowledge_extract": 6,
    "synthesis": 7,
    "hypothesis_gen": 8,
    "experiment_design": 9,
    "code_generation": 10,
    "resource_planning": 11,
    "experiment_run": 12,
    "iterative_refine": 13,
    "result_analysis": 14,
    "research_decision": 15,
    "paper_outline": 16,
    "paper_draft": 17,
    "peer_review": 18,
    "paper_revision": 19,
    "quality_gate": 20,
    "knowledge_archive": 21,
    "export_publish": 22,
    "citation_verify": 23,
}


class Skill:
    def __init__(
        self,
        name: str = "",
        description: str = "",
        body: str = "",
        metadata: Optional[Dict[str, str]] = None,
        source_dir: Optional[Path] = None,
    ):
        self.name = name
        self.description = description
        self.body = body
        self.metadata = metadata or {}
        self.source_dir = source_dir

    @property
    def category(self) -> str:
        return self.metadata.get("category", "domain")

    @property
    def trigger_keywords(self) -> List[str]:
        raw = self.metadata.get("trigger-keywords", "")
        return [k.strip().lower() for k in raw.split(",") if k.strip()] if raw else []

    @property
    def applicable_stages(self) -> List[int]:
        raw = self.metadata.get("applicable-stages", "")
        if not raw:
            return []
        result = []
        for tok in raw.split(","):
            tok = tok.strip()
            try:
                result.append(int(tok))
            except ValueError:
                pass
        return result

    @property
    def priority(self) -> int:
        try:
            return int(self.metadata.get("priority", "5"))
        except (ValueError, TypeError):
            return 5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "trigger_keywords": self.trigger_keywords,
            "applicable_stages": self.applicable_stages,
            "priority": self.priority,
        }


def _load_skill_from_skillmd(path: Path) -> Optional[Skill]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read SKILL.md at %s: %s", path, exc)
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning("SKILL.md missing frontmatter delimiters: %s", path)
        return None

    try:
        import yaml
        header = yaml.safe_load(parts[1])
    except Exception:
        try:
            header = json.loads(parts[1])
        except Exception as exc:
            logger.warning("Invalid frontmatter in %s: %s", path, exc)
            return None

    if not isinstance(header, dict):
        logger.warning("Frontmatter is not a dict in %s", path)
        return None

    if header.get("enabled") is False or str(header.get("enabled", "")).lower() == "false":
        logger.debug("Skill disabled via frontmatter: %s", path)
        return None

    name = str(header.get("name", ""))
    if not name:
        logger.warning("SKILL.md missing 'name' field: %s", path)
        return None

    description = str(header.get("description", ""))
    body = parts[2].strip()

    metadata: Dict[str, str] = {}
    raw_meta = header.get("metadata")
    if isinstance(raw_meta, dict):
        for k, v in raw_meta.items():
            metadata[str(k)] = str(v)

    for key in ("category", "license", "compatibility", "version", "author"):
        if key in header and key not in metadata:
            metadata[key] = str(header[key])

    return Skill(
        name=name,
        description=description,
        body=body,
        metadata=metadata,
        source_dir=path.parent,
    )


def _load_skills_from_directory(directory: Path) -> List[Skill]:
    skills: List[Skill] = []
    if not directory.exists():
        return skills

    for skill_md in sorted(directory.rglob("SKILL.md")):
        skill = _load_skill_from_skillmd(skill_md)
        if skill:
            skills.append(skill)

    return skills


def _match_skills(
    skills: List[Skill],
    context: str,
    stage: str = "",
    top_k: int = 3,
    fallback_matching: bool = True,
) -> List[Skill]:
    context_lower = context.lower()
    stage_num = STAGE_NAME_TO_NUMBER.get(stage, 0)

    scored: List[Tuple[Skill, int]] = []
    for skill in skills:
        score = 0

        if stage_num and skill.applicable_stages:
            if stage_num in skill.applicable_stages:
                score += 100

        if skill.trigger_keywords:
            for kw in skill.trigger_keywords:
                if kw.lower() in context_lower:
                    score += 10

        words = set(re.findall(r'\w+', context_lower))
        desc_words = set(re.findall(r'\w+', skill.description.lower()))
        overlap = len(words & desc_words)
        score += overlap * 2

        body_words = set(re.findall(r'\w+', skill.body.lower()[:500]))
        body_overlap = len(words & body_words)
        score += body_overlap

        score += skill.priority

        if score > 0:
            scored.append((skill, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    result = [s for s, _ in scored[:top_k]]

    if not result and fallback_matching:
        result = sorted(skills, key=lambda s: s.priority, reverse=True)[:top_k]

    return result


def _format_skills_for_prompt(skills: List[Skill], max_chars: int = 4000) -> str:
    lines: List[str] = []
    total = 0

    for skill in skills:
        header = f"## {skill.name}"
        lines.append(header)
        total += len(header) + 1

        desc = f"**{skill.description}**"
        if total + len(desc) + 1 <= max_chars:
            lines.append(desc)
            total += len(desc) + 1

        if skill.body:
            body_trimmed = skill.body[:500]
            if total + len(body_trimmed) + 2 > max_chars:
                remaining = max_chars - total - 2
                if remaining > 100:
                    body_trimmed = skill.body[:remaining] + "..."
                else:
                    break
            lines.append("")
            lines.append(body_trimmed)
            total += len(body_trimmed) + 2

        lines.append("")
        total += 1

        if total >= max_chars:
            break

    return "\n".join(lines)


class SkillRegistry:
    def __init__(
        self,
        builtin_dir: str = "",
        auto_match: bool = True,
        max_skills_per_stage: int = 3,
        fallback_matching: bool = True,
    ):
        self._skills: Dict[str, Skill] = {}
        self._auto_match = auto_match
        self._max_skills = max_skills_per_stage
        self._fallback_matching = fallback_matching

        if builtin_dir:
            self._load_from_dir(Path(builtin_dir))

    def _load_from_dir(self, directory: Path):
        skills = _load_skills_from_directory(directory)
        for skill in skills:
            self.register(skill)
        logger.info("Loaded %d skills from %s", len(skills), directory)

    def register(self, skill: Skill):
        self._skills[skill.name] = skill

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def list_all(self) -> List[Skill]:
        return list(self._skills.values())

    def list_by_category(self, category: str) -> List[Skill]:
        return [s for s in self._skills.values() if s.category == category]

    def list_by_stage(self, stage: int) -> List[Skill]:
        return [
            s for s in self._skills.values()
            if not s.applicable_stages or stage in s.applicable_stages
        ]

    def match(
        self,
        context: str,
        stage: str = "",
        top_k: int = None,
    ) -> List[Skill]:
        k = top_k or self._max_skills
        return _match_skills(
            list(self._skills.values()),
            context,
            stage,
            top_k=k,
            fallback_matching=self._fallback_matching,
        )

    def export_for_prompt(self, skills: List[Skill], max_chars: int = 4000) -> str:
        return _format_skills_for_prompt(skills, max_chars=max_chars)

    def count(self) -> int:
        return len(self._skills)