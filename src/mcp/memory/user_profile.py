import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    preferences: Dict[str, str] = field(default_factory=dict)
    expertise_level: Dict[str, str] = field(default_factory=dict)
    frequent_topics: List[str] = field(default_factory=list)
    communication_style: str = "neutral"
    language: str = "zh"


class UserProfileManager:
    def __init__(self, profile_path: Path):
        if profile_path is None:
            self.profile_path = None
            self._profile = UserProfile()
            return
        self.profile_path = Path(profile_path)
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self._profile = self._load()

    def _load(self) -> UserProfile:
        if self.profile_path is None or not self.profile_path.exists():
            return UserProfile()
        try:
            data = json.loads(self.profile_path.read_text(encoding="utf-8"))
            return UserProfile(**{k: v for k, v in data.items() if k in UserProfile.__dataclass_fields__})
        except Exception:
            pass
        return UserProfile()

    def _save(self):
        if self.profile_path is None:
            return
        self.profile_path.write_text(
            json.dumps(asdict(self._profile), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def profile(self) -> UserProfile:
        return self._profile

    def update_preference(self, key: str, value: str):
        self._profile.preferences[key] = value
        self._save()

    def update_expertise(self, domain: str, level: str):
        self._profile.expertise_level[domain] = level
        self._save()

    def add_frequent_topic(self, topic: str):
        if topic not in self._profile.frequent_topics:
            self._profile.frequent_topics.append(topic)
            if len(self._profile.frequent_topics) > 20:
                self._profile.frequent_topics = self._profile.frequent_topics[-20:]
            self._save()

    def get_system_prompt_injection(self) -> str:
        parts = []
        if self._profile.preferences:
            prefs = "; ".join(f"{k}={v}" for k, v in self._profile.preferences.items())
            parts.append(f"用户偏好: {prefs}")
        if self._profile.expertise_level:
            exp = "; ".join(f"{k}={v}" for k, v in self._profile.expertise_level.items())
            parts.append(f"专业水平: {exp}")
        if self._profile.frequent_topics:
            parts.append(f"常聊话题: {', '.join(self._profile.frequent_topics[:5])}")
        return "\n".join(parts) if parts else ""
