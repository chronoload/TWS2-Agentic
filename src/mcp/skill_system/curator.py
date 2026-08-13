import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SkillStatus(Enum):
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"
    PINNED = "pinned"


@dataclass
class CuratorConfig:
    stale_days: int = 30
    archived_days: int = 90
    review_interval_hours: int = 24
    dry_run: bool = False
    auto_archive: bool = True
    llm_review_enabled: bool = False


@dataclass
class CuratorAction:
    skill_name: str
    action: str  # "stale", "archive", "consolidate", "prune"
    reason: str = ""
    umbrella_skill: str = ""
    timestamp: float = field(default_factory=time.time)


class Curator:
    def __init__(
        self,
        skills_dir: Path,
        config: Optional[CuratorConfig] = None,
        llm: Optional[Any] = None,
    ):
        self.skills_dir = skills_dir
        self.config = config or CuratorConfig()
        self._llm = llm
        self._status: Dict[str, SkillStatus] = {}
        self._last_access: Dict[str, float] = {}
        self._last_review: float = 0.0
        self._actions_log: List[CuratorAction] = []

        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def _load_state(self):
        state_file = self.skills_dir / ".curator_state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                for name, status_str in data.get("statuses", {}).items():
                    try:
                        self._status[name] = SkillStatus(status_str)
                    except ValueError:
                        self._status[name] = SkillStatus.ACTIVE
                self._last_access = data.get("last_access", {})
                self._last_review = data.get("last_review", 0.0)
            except Exception as e:
                logger.error(f"Curator state load error: {e}")

    def _save_state(self):
        state_file = self.skills_dir / ".curator_state.json"
        data = {
            "statuses": {name: s.value for name, s in self._status.items()},
            "last_access": self._last_access,
            "last_review": self._last_review,
        }
        try:
            state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Curator state save error: {e}")

    def record_access(self, skill_name: str):
        self._last_access[skill_name] = time.time()
        if skill_name not in self._status or self._status[skill_name] == SkillStatus.STALE:
            self._status[skill_name] = SkillStatus.ACTIVE
        self._save_state()

    def get_status(self, skill_name: str) -> SkillStatus:
        return self._status.get(skill_name, SkillStatus.ACTIVE)

    def pin_skill(self, skill_name: str):
        self._status[skill_name] = SkillStatus.PINNED
        self._save_state()

    def unpin_skill(self, skill_name: str):
        self._status[skill_name] = SkillStatus.ACTIVE
        self._save_state()

    def maybe_run_curator(self) -> List[CuratorAction]:
        now = time.time()
        interval_seconds = self.config.review_interval_hours * 3600
        if now - self._last_review < interval_seconds:
            return []

        self._last_review = now
        actions = []

        actions.extend(self.apply_automatic_transitions())

        if self.config.llm_review_enabled and self._llm:
            actions.extend(self._run_llm_review())

        self._save_state()
        return actions

    def apply_automatic_transitions(self) -> List[CuratorAction]:
        actions = []
        now = time.time()
        stale_threshold = self.config.stale_days * 86400
        archived_threshold = self.config.archived_days * 86400

        for skill_name in list(self._status.keys()):
            status = self._status[skill_name]
            if status == SkillStatus.PINNED:
                continue

            last = self._last_access.get(skill_name, now)
            age = now - last

            if status == SkillStatus.ACTIVE and age > stale_threshold:
                action = CuratorAction(
                    skill_name=skill_name,
                    action="stale",
                    reason=f"超过 {self.config.stale_days} 天未使用",
                )
                if not self.config.dry_run:
                    self._status[skill_name] = SkillStatus.STALE
                actions.append(action)
                logger.info(f"Curator: {skill_name} → stale ({action.reason})")

            elif status == SkillStatus.STALE and age > archived_threshold:
                action = CuratorAction(
                    skill_name=skill_name,
                    action="archive",
                    reason=f"超过 {self.config.archived_days} 天未使用",
                )
                if not self.config.dry_run and self.config.auto_archive:
                    self._status[skill_name] = SkillStatus.ARCHIVED
                    self._archive_skill(skill_name)
                actions.append(action)
                logger.info(f"Curator: {skill_name} → archived ({action.reason})")

        self._actions_log.extend(actions)
        return actions

    def _run_llm_review(self) -> List[CuratorAction]:
        if not self._llm:
            return []

        active_skills = [
            name for name, status in self._status.items()
            if status in (SkillStatus.ACTIVE, SkillStatus.STALE)
        ]

        if len(active_skills) < 2:
            return []

        actions = []
        skill_summaries = self._build_skill_summaries(active_skills)

        prompt = self._build_review_prompt(skill_summaries)

        try:
            response = self._llm.chat([
                {"role": "system", "content": CURATOR_REVIEW_SYSTEM},
                {"role": "user", "content": prompt},
            ])

            content = getattr(response, "content", "") or ""
            actions = self._parse_review_response(content, active_skills)

        except Exception as e:
            logger.error(f"Curator LLM review error: {e}")

        self._actions_log.extend(actions)
        return actions

    def _build_skill_summaries(self, skill_names: List[str]) -> str:
        summaries = []
        for name in skill_names:
            status = self._status.get(name, SkillStatus.ACTIVE).value
            last_access = self._last_access.get(name, 0)
            days_since = int((time.time() - last_access) / 86400) if last_access else 0
            summaries.append(f"- {name}: status={status}, last_used={days_since}天前")

        return "\n".join(summaries)

    def _build_review_prompt(self, summaries: str) -> str:
        return f"""请审查以下技能列表，判断是否有可以合并(consolidate)或归档(prune)的技能：

{summaries}

请以YAML格式输出审查结果：
```yaml
actions:
  - skill: <skill_name>
    action: consolidate|prune
    reason: <reason>
    umbrella: <umbrella_skill_name>  # 仅consolidate时需要
```"""

    def _parse_review_response(self, content: str, active_skills: List[str]) -> List[CuratorAction]:
        actions = []
        try:
            import yaml
            yaml_match = content.find("```yaml")
            if yaml_match >= 0:
                yaml_start = yaml_match + 7
                yaml_end = content.find("```", yaml_start)
                if yaml_end > yaml_start:
                    yaml_content = content[yaml_start:yaml_end]
                    data = yaml.safe_load(yaml_content)
                    if isinstance(data, dict) and "actions" in data:
                        for item in data["actions"]:
                            action = CuratorAction(
                                skill_name=item.get("skill", ""),
                                action=item.get("action", ""),
                                reason=item.get("reason", ""),
                                umbrella_skill=item.get("umbrella", ""),
                            )
                            if action.skill_name in active_skills:
                                actions.append(action)
        except Exception as e:
            logger.error(f"Curator parse review error: {e}")

        return actions

    def _archive_skill(self, skill_name: str):
        skill_dir = self.skills_dir / skill_name
        archive_dir = self.skills_dir / ".archived"
        archive_dir.mkdir(exist_ok=True)

        if skill_dir.exists() and skill_dir.is_dir():
            dest = archive_dir / skill_name
            if dest.exists():
                import shutil
                shutil.rmtree(dest)
            try:
                import shutil
                shutil.move(str(skill_dir), str(dest))
                logger.info(f"Curator: archived {skill_name} → {dest}")
            except Exception as e:
                logger.error(f"Curator archive move error: {e}")

    def get_actions_log(self, limit: int = 50) -> List[CuratorAction]:
        return self._actions_log[-limit:]

    def get_stats(self) -> Dict[str, int]:
        stats = {}
        for status in SkillStatus:
            stats[status.value] = sum(
                1 for s in self._status.values() if s == status
            )
        return stats


CURATOR_REVIEW_SYSTEM = """你是 TS2 Curator，负责审查和优化技能库。

你的职责：
1. 识别功能重叠的技能，建议合并为"伞技能"(umbrella skill)
2. 识别过时或不再使用的技能，建议归档(prune)
3. 保持技能库精简和高效

合并(consolidate)规则：
- 多个技能处理相似任务时，合并为一个更通用的伞技能
- 伞技能应覆盖所有子技能的功能

归档(prune)规则：
- 长期未使用且无独特价值的技能
- 已被其他技能完全覆盖的技能

输出格式：严格按照YAML格式输出审查结果。"""
