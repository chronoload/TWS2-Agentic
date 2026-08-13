import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from .base import MemoryProvider, MemoryEntry, MemoryQuery
from .sqlite_provider import SQLiteMemoryProvider

logger = logging.getLogger(__name__)


class CuratedMemoryManager:
    CATEGORIES = {
        "fact": "用户告知的事实和偏好",
        "procedure": "操作步骤和方法",
        "context": "对话上下文和决策",
        "correction": "纠正和反馈",
        "insight": "洞察和发现",
    }

    def __init__(self, db_path):
        if db_path is None:
            self._provider = None
            self._nudge_counter = 0
            self._nudge_interval = 5
            return
        from .sqlite_provider import SQLiteMemoryProvider
        self._provider: MemoryProvider = SQLiteMemoryProvider(Path(db_path))
        self._nudge_counter = 0
        self._nudge_interval = 5

    def store_observation(self, content: str, category: str = "fact",
                          importance: float = 0.5, tags: List[str] = None) -> str:
        if self._provider is None:
            return ""
        entry = MemoryEntry(
            content=content,
            category=category,
            importance=importance,
            tags=tags or [],
            source="agent_observation",
        )
        return self._provider.store(entry)

    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        if self._provider is None:
            return []
        return self._provider.retrieve(MemoryQuery(text=query, limit=limit))

    def should_nudge(self) -> bool:
        self._nudge_counter += 1
        return self._nudge_counter >= self._nudge_interval

    def get_memory_context(self, current_input: str) -> str:
        # 注入白名单：高置信类别 + 上下文摘要（压缩时以 category="context" 存储，必须放行才能读回）
        HIGH_CONFIDENCE = {"fact", "correction", "insight", "context"}
        entries = self.recall(current_input, limit=10)
        if not entries:
            return ""
        filtered = [e for e in entries if e.category in HIGH_CONFIDENCE][:5]
        if not filtered:
            return ""
        lines = ["[相关记忆]"]
        for entry in filtered:
            lines.append(f"- ({entry.category}) {entry.content}")
        return "\n".join(lines)

    def consolidate(self):
        if self._provider is None:
            return
        all_entries = self._provider.retrieve(MemoryQuery(limit=1000, min_importance=0.3))
        for entry in all_entries:
            if entry.access_count == 0 and entry.importance < 0.7:
                self._provider.update(entry.id, importance=entry.importance * 0.9)
