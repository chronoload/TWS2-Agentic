import sqlite3
import uuid
import json
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .base import MemoryProvider, MemoryEntry, MemoryQuery

logger = logging.getLogger(__name__)


class SQLiteMemoryProvider(MemoryProvider):
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    tags TEXT DEFAULT '[]',
                    importance REAL DEFAULT 0.5,
                    source TEXT DEFAULT 'agent',
                    created_at TEXT NOT NULL,
                    accessed_at TEXT,
                    access_count INTEGER DEFAULT 0
                )
            """)
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                    USING fts5(id, content, tags, category)
                """)
            except sqlite3.OperationalError:
                pass

    def store(self, entry: MemoryEntry) -> str:
        entry_id = entry.id or uuid.uuid4().hex[:12]
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO memories
                (id, content, category, tags, importance, source, created_at, accessed_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry_id, entry.content, entry.category,
                json.dumps(entry.tags, ensure_ascii=False),
                entry.importance, entry.source,
                entry.created_at, entry.accessed_at or entry.created_at,
                entry.access_count,
            ))
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO memories_fts (id, content, tags, category)
                    VALUES (?, ?, ?, ?)
                """, (entry_id, entry.content, " ".join(entry.tags), entry.category))
            except sqlite3.OperationalError:
                pass
        return entry_id

    def retrieve(self, query: MemoryQuery) -> List[MemoryEntry]:
        results = []
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if query.text:
                try:
                    rows = conn.execute("""
                        SELECT m.* FROM memories m
                        JOIN memories_fts f ON m.id = f.id
                        WHERE memories_fts MATCH ?
                        ORDER BY rank LIMIT ?
                    """, (query.text, query.limit)).fetchall()
                except sqlite3.OperationalError:
                    rows = conn.execute("""
                        SELECT * FROM memories WHERE content LIKE ?
                        ORDER BY importance DESC LIMIT ?
                    """, (f"%{query.text}%", query.limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM memories
                    WHERE importance >= ?
                    ORDER BY importance DESC LIMIT ?
                """, (query.min_importance, query.limit)).fetchall()
            for row in rows:
                results.append(MemoryEntry(
                    id=row["id"],
                    content=row["content"],
                    category=row["category"],
                    tags=json.loads(row["tags"]),
                    importance=row["importance"],
                    source=row["source"],
                    created_at=row["created_at"],
                    accessed_at=row["accessed_at"],
                    access_count=row["access_count"],
                ))
        return results

    def delete(self, entry_id: str) -> bool:
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id=?", (entry_id,))
            try:
                conn.execute("DELETE FROM memories_fts WHERE id=?", (entry_id,))
            except sqlite3.OperationalError:
                pass
            return cursor.rowcount > 0

    def update(self, entry_id: str, **fields) -> bool:
        if not fields:
            return False
        if "accessed_at" not in fields:
            fields["accessed_at"] = datetime.now().isoformat()
        if "access_count" not in fields:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT access_count FROM memories WHERE id=?", (entry_id,)
                ).fetchone()
                if row:
                    fields["access_count"] = (row[0] or 0) + 1
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [entry_id]
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                f"UPDATE memories SET {set_clause} WHERE id=?", values
            )
            return cursor.rowcount > 0
