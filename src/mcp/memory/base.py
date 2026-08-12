from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class MemoryEntry:
    id: str = ""
    content: str = ""
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5
    source: str = "agent"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    accessed_at: str = ""
    access_count: int = 0


@dataclass
class MemoryQuery:
    text: str = ""
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    min_importance: float = 0.0
    limit: int = 10


class MemoryProvider(ABC):
    @abstractmethod
    def store(self, entry: MemoryEntry) -> str: ...

    @abstractmethod
    def retrieve(self, query: MemoryQuery) -> List[MemoryEntry]: ...

    @abstractmethod
    def delete(self, entry_id: str) -> bool: ...

    @abstractmethod
    def update(self, entry_id: str, **fields) -> bool: ...
