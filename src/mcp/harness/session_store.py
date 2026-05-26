import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SessionRecord:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    total_tokens: int = 0
    turn_count: int = 0


class SessionStore:
    def __init__(self, store_dir: Optional[str] = None):
        if store_dir is None:
            self.store_dir = Path(__file__).parent.parent / "cache_data" / "sessions"
        else:
            self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, SessionRecord] = {}

    def create(self, name: str = "", metadata: Optional[Dict] = None) -> SessionRecord:
        record = SessionRecord(name=name, metadata=metadata or {})
        self._cache[record.id] = record
        self._save(record)
        return record

    def get(self, session_id: str) -> Optional[SessionRecord]:
        if session_id in self._cache:
            return self._cache[session_id]
        record = self._load(session_id)
        if record:
            self._cache[session_id] = record
        return record

    def update(self, session_id: str, **kwargs) -> bool:
        record = self.get(session_id)
        if record is None:
            return False
        for k, v in kwargs.items():
            if hasattr(record, k):
                setattr(record, k, v)
        record.updated_at = time.time()
        self._save(record)
        return True

    def append_message(self, session_id: str, message: Dict):
        record = self.get(session_id)
        if record is None:
            return
        record.messages.append(message)
        record.updated_at = time.time()
        self._save(record)

    def list_sessions(self, limit: int = 50) -> List[SessionRecord]:
        records = []
        for f in self.store_dir.glob("*.json"):
            record = self._load(f.stem)
            if record:
                records.append(record)
        records.sort(key=lambda r: r.updated_at, reverse=True)
        return records[:limit]

    def delete(self, session_id: str) -> bool:
        self._cache.pop(session_id, None)
        path = self.store_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def _save(self, record: SessionRecord):
        path = self.store_dir / f"{record.id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(record), f, ensure_ascii=False, indent=2)

    def _load(self, session_id: str) -> Optional[SessionRecord]:
        path = self.store_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionRecord(**data)
        except Exception:
            return None
