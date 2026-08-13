#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 数据枢纽核心
统一管理 Agent、Web Crawler、文本分析、网络书签、RSS 订阅
贯通网络与本地资源库，同时暴露给 GUI 和 MCP

架构: Hub-and-Spoke + EventBus
DataHub 为中心枢纽，各数据源为 Spoke，通过 EventBus 解耦通信
"""

import json
import sqlite3
import threading
import hashlib
import time
import re
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import Counter
import uuid
import logging

logger = logging.getLogger(__name__)


class SourceType(Enum):
    CRAWLER = "crawler"
    RSS = "rss"
    AGENT = "agent"
    BOOKMARK = "bookmark"
    ANALYSIS = "analysis"
    MANUAL = "manual"
    LOCAL_FILE = "local_file"


class ItemType(Enum):
    WEBPAGE = "webpage"
    PAPER = "paper"
    GITHUB_REPO = "github_repo"
    RSS_ENTRY = "rss_entry"
    BOOKMARK = "bookmark"
    NOTE = "note"
    FILE = "file"
    ANALYSIS_RESULT = "analysis_result"


class EventBus:
    """发布/订阅事件总线 — 解耦 DataHub 与各 Spoke"""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable):
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    cb for cb in self._subscribers[event_type] if cb != callback
                ]

    def publish(self, event_type: str, data: Any = None):
        with self._lock:
            callbacks = self._subscribers.get(event_type, []).copy()
            callbacks += self._subscribers.get("*", []).copy()
        for cb in callbacks:
            try:
                cb(event_type, data)
            except Exception as e:
                logger.warning(f"EventBus callback error: {e}")


@dataclass
class HubItem:
    """数据枢纽中的统一数据项"""
    id: str = ""
    title: str = ""
    url: str = ""
    content: str = ""
    summary: str = ""
    source_type: str = SourceType.MANUAL.value
    item_type: str = ItemType.WEBPAGE.value
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    related_ids: List[str] = field(default_factory=list)
    collection_ids: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    accessed_at: str = ""
    is_read: bool = False
    is_starred: bool = False
    is_archived: bool = False
    pipeline_stage: str = "ingested"
    quality_score: float = 0.0
    last_enriched: str = ""
    content_hash: str = ""
    needs_review: bool = False
    auto_scan_source: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(
                f"{self.url or self.title}{time.time()}".encode()
            ).hexdigest()[:16]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.accessed_at:
            self.accessed_at = self.created_at

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "HubItem":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RSSSubscription:
    """RSS 订阅源"""
    id: str = ""
    title: str = ""
    url: str = ""
    category: str = ""
    poll_interval_minutes: int = 60
    last_polled: str = ""
    last_etag: str = ""
    last_modified: str = ""
    active: bool = True
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(self.url.encode()).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class DataCollection:
    """数据集合（类似文件夹/播放列表）"""
    id: str = ""
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    item_ids: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:12]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


class QualityScorer:
    """数据项质量评分器 — 自动评估数据项的完整性和价值"""

    def score(self, item: HubItem) -> float:
        s = 0.0
        if item.title and len(item.title.strip()) > 3:
            s += 0.2
        if item.url:
            s += 0.1
        if item.content:
            s += min(len(item.content) / 5000, 1.0) * 0.3
        if item.summary and len(item.summary.strip()) > 10:
            s += 0.1
        if item.tags:
            s += 0.1
        if item.keywords:
            s += 0.1
        if item.is_read:
            s += 0.05
        if item.is_starred:
            s += 0.05
        return min(s, 1.0)

    def needs_enrichment(self, item: HubItem) -> bool:
        if not item.url:
            return False
        if not item.content or len(item.content) < 100:
            return True
        if not item.summary:
            return True
        if not item.keywords and not item.tags:
            return True
        return False

    def is_stale(self, item: HubItem, max_age_hours: int = 24) -> bool:
        if not item.url:
            return False
        try:
            updated = datetime.fromisoformat(item.updated_at)
            return (datetime.now() - updated) > timedelta(hours=max_age_hours)
        except (ValueError, TypeError):
            return False


PIPELINE_STAGES = ["scanned", "ingested", "enriched", "filtered", "updated"]


class PipelineEngine:
    """六阶段数据管道引擎 — Scan→Ingest→Enrich→Filter→Update→SyncBack

    核心设计原则:
    - 每个阶段独立可恢复，异常不会中断整个管道
    - 通过 EventBus 发布进度事件
    - 定时运行，形成持续反馈流
    """

    def __init__(self, hub: "DataHub"):
        self.hub = hub
        self.scorer = QualityScorer()
        self._running = False
        self._timer = None
        self._last_run = None
        self._last_status = {}
        self._run_count = 0
        self._lock = threading.Lock()

    def run_full_pipeline(self) -> Dict[str, Any]:
        with self._lock:
            self._run_count += 1
            run_id = self._run_count

        status = {
            "run_id": run_id,
            "started_at": datetime.now().isoformat(),
            "scan": {}, "enrich": {}, "filter": {}, "update": {}, "syncback": {},
            "errors": []
        }
        self.hub.event_bus.publish("pipeline.start", {"run_id": run_id})

        try:
            status["scan"] = self._stage_scan()
        except Exception as e:
            status["errors"].append(f"scan: {e}")
            logger.warning(f"Pipeline scan error: {e}")

        try:
            status["enrich"] = self._stage_enrich()
        except Exception as e:
            status["errors"].append(f"enrich: {e}")
            logger.warning(f"Pipeline enrich error: {e}")

        try:
            status["filter"] = self._stage_filter()
        except Exception as e:
            status["errors"].append(f"filter: {e}")
            logger.warning(f"Pipeline filter error: {e}")

        try:
            status["update"] = self._stage_update()
        except Exception as e:
            status["errors"].append(f"update: {e}")
            logger.warning(f"Pipeline update error: {e}")

        try:
            status["syncback"] = self._stage_syncback()
        except Exception as e:
            status["errors"].append(f"syncback: {e}")
            logger.warning(f"Pipeline syncback error: {e}")

        status["completed_at"] = datetime.now().isoformat()
        status["success"] = len(status["errors"]) == 0

        self._last_run = datetime.now().isoformat()
        self._last_status = status

        self.hub.event_bus.publish("pipeline.complete", status)
        return status

    def _stage_scan(self) -> Dict[str, Any]:
        results = self.hub.auto_scan_all_sources()
        total = sum(results.values())
        self.hub.event_bus.publish("pipeline.scan_complete", results)

        if total > 0:
            with self.hub._get_conn() as conn:
                conn.execute(
                    "UPDATE items SET pipeline_stage = 'scanned' WHERE pipeline_stage = 'ingested' AND auto_scan_source != ''"
                )

        return {"new_items": total, "sources": results}

    def _stage_enrich(self, limit: int = 20) -> Dict[str, Any]:
        items = self.hub.query_items(limit=limit, sort_by="quality_score", sort_desc=False)
        enriched = 0
        skipped = 0
        failed = 0

        for item in items:
            if not self.scorer.needs_enrichment(item):
                skipped += 1
                continue

            try:
                result = self.hub.pipeline_bookmark_crawl(item.id)
                if result:
                    content_hash = hashlib.md5(result.content.encode()).hexdigest()[:12] if result.content else ""
                    self.hub.update_item(
                        item.id,
                        pipeline_stage="enriched",
                        last_enriched=datetime.now().isoformat(),
                        content_hash=content_hash,
                    )
                    enriched += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.warning(f"Enrich failed for {item.id}: {e}")

        self.hub.event_bus.publish("pipeline.enrich_complete", {
            "enriched": enriched, "skipped": skipped, "failed": failed
        })
        return {"enriched": enriched, "skipped": skipped, "failed": failed}

    def _stage_filter(self) -> Dict[str, Any]:
        items = self.hub.query_items(limit=1000)
        scored = 0
        promoted = 0
        flagged = 0

        for item in items:
            new_score = self.scorer.score(item)
            if abs(new_score - item.quality_score) > 0.01:
                needs_review = new_score < 0.3 and item.pipeline_stage in ("enriched", "scanned")
                self.hub.update_item(
                    item.id,
                    quality_score=new_score,
                    pipeline_stage="filtered",
                    needs_review=needs_review,
                )
                scored += 1
                if needs_review:
                    flagged += 1
                if new_score > 0.7:
                    promoted += 1

        self.hub.event_bus.publish("pipeline.filter_complete", {
            "scored": scored, "promoted": promoted, "flagged": flagged
        })
        return {"scored": scored, "promoted": promoted, "flagged": flagged}

    def _stage_update(self, max_age_hours: int = 24, limit: int = 30) -> Dict[str, Any]:
        items = self.hub.query_items(limit=limit, sort_by="updated_at", sort_desc=False)
        updated = 0
        unchanged = 0
        failed = 0

        for item in items:
            if not self.scorer.is_stale(item, max_age_hours):
                continue
            if not item.url:
                continue

            try:
                old_hash = item.content_hash
                result = self.hub.pipeline_bookmark_crawl(item.id)
                if result:
                    new_hash = hashlib.md5(result.content.encode()).hexdigest()[:12] if result.content else ""
                    if new_hash and new_hash != old_hash:
                        self.hub.update_item(
                            item.id,
                            content_hash=new_hash,
                            pipeline_stage="updated",
                        )
                        updated += 1
                    else:
                        unchanged += 1
                        self.hub.update_item(item.id, updated_at=datetime.now().isoformat())
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.warning(f"Update failed for {item.id}: {e}")

        self.hub.event_bus.publish("pipeline.update_complete", {
            "updated": updated, "unchanged": unchanged, "failed": failed
        })
        return {"updated": updated, "unchanged": unchanged, "failed": failed}

    def _stage_syncback(self) -> Dict[str, Any]:
        results = {}
        try:
            results["bookmarks_json"] = self.hub.sync_back_to_bookmarks_json()
        except Exception as e:
            results["bookmarks_json"] = -1
            logger.warning(f"SyncBack bookmarks failed: {e}")

        self.hub.event_bus.publish("pipeline.syncback_complete", results)
        return results

    def start_periodic_pipeline(self, interval_minutes: int = 30):
        if self._running:
            return
        self._running = True
        self._run_periodic(interval_minutes)

    def stop_periodic_pipeline(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _run_periodic(self, interval_minutes: int):
        if not self._running:
            return
        try:
            self.run_full_pipeline()
        except Exception as e:
            self.hub.event_bus.publish("pipeline.error", str(e))
            logger.warning(f"Periodic pipeline error: {e}")
        self._timer = threading.Timer(interval_minutes * 60, self._run_periodic, args=[interval_minutes])
        self._timer.daemon = True
        self._timer.start()

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "run_count": self._run_count,
            "last_run": self._last_run,
            "last_status": self._last_status,
        }


class DataHub:
    """WS2 数据枢纽 - 终极数据管理核心

    SQLite 持久化 + EventBus 事件驱动 + 数据管道
    同时暴露给 GUI（Tkinter）和 MCP（Agent 工具）
    """

    VERSION = 1

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data_hub"
        self.data_dir.mkdir(exist_ok=True)

        self.db_path = self.data_dir / "data_hub.db"
        self.event_bus = EventBus()
        self._lock = threading.RLock()

        self._init_db()

        self._rss_poller_running = False
        self._rss_poller_thread = None
        self._pipeline_engine = PipelineEngine(self)

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    url TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    source_type TEXT DEFAULT 'manual',
                    item_type TEXT DEFAULT 'webpage',
                    tags TEXT DEFAULT '[]',
                    keywords TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    related_ids TEXT DEFAULT '[]',
                    collection_ids TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT '',
                    accessed_at TEXT DEFAULT '',
                    is_read INTEGER DEFAULT 0,
                    is_starred INTEGER DEFAULT 0,
                    is_archived INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS rss_subscriptions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    poll_interval_minutes INTEGER DEFAULT 60,
                    last_polled TEXT DEFAULT '',
                    last_etag TEXT DEFAULT '',
                    last_modified TEXT DEFAULT '',
                    active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    item_ids TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS pipeline_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT '',
                    pipeline_name TEXT DEFAULT '',
                    source_type TEXT DEFAULT '',
                    action TEXT DEFAULT '',
                    item_id TEXT DEFAULT '',
                    status TEXT DEFAULT '',
                    message TEXT DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_type);
                CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type);
                CREATE INDEX IF NOT EXISTS idx_items_starred ON items(is_starred);
                CREATE INDEX IF NOT EXISTS idx_items_updated ON items(updated_at);
                CREATE INDEX IF NOT EXISTS idx_items_url ON items(url);
            """)

            for col, col_type, default in [
                ("pipeline_stage", "TEXT", "'ingested'"),
                ("quality_score", "REAL", "0.0"),
                ("last_enriched", "TEXT", "''"),
                ("content_hash", "TEXT", "''"),
                ("needs_review", "INTEGER", "0"),
                ("auto_scan_source", "TEXT", "''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE items ADD COLUMN {col} {col_type} DEFAULT {default}")
                except sqlite3.OperationalError:
                    pass

            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_items_pipeline ON items(pipeline_stage);
                CREATE INDEX IF NOT EXISTS idx_items_quality ON items(quality_score);
            """)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ========== Item CRUD ==========

    def add_item(self, item: HubItem, _skip_event: bool = False) -> HubItem:
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO items
                    (id, title, url, content, summary, source_type, item_type,
                     tags, keywords, metadata, related_ids, collection_ids,
                     created_at, updated_at, accessed_at,
                     is_read, is_starred, is_archived,
                     pipeline_stage, quality_score, last_enriched,
                     content_hash, needs_review, auto_scan_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?)
                """, (
                    item.id, item.title, item.url, item.content, item.summary,
                    item.source_type, item.item_type,
                    json.dumps(item.tags, ensure_ascii=False),
                    json.dumps(item.keywords, ensure_ascii=False),
                    json.dumps(item.metadata, ensure_ascii=False),
                    json.dumps(item.related_ids, ensure_ascii=False),
                    json.dumps(item.collection_ids, ensure_ascii=False),
                    item.created_at, item.updated_at, item.accessed_at,
                    int(item.is_read), int(item.is_starred), int(item.is_archived),
                    item.pipeline_stage, item.quality_score, item.last_enriched,
                    item.content_hash, int(item.needs_review), item.auto_scan_source
                ))
        if not _skip_event:
            self.event_bus.publish("item.added", item)
        self._log_pipeline("add", item.source_type, "add_item", item.id, "success")
        return item

    def get_item(self, item_id: str) -> Optional[HubItem]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if row:
                return self._row_to_item(row)
        return None

    def update_item(self, item_id: str, **kwargs) -> bool:
        with self._lock:
            item = self.get_item(item_id)
            if not item:
                return False
            for k, v in kwargs.items():
                if hasattr(item, k):
                    setattr(item, k, v)
            item.updated_at = datetime.now().isoformat()
            self.add_item(item, _skip_event=True)
        self.event_bus.publish("item.updated", item)
        return True

    def delete_item(self, item_id: str) -> bool:
        existed = self.get_item(item_id) is not None
        if not existed:
            return False
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self.event_bus.publish("item.deleted", {"id": item_id})
        return True

    def query_items(self, source_type: str = None, item_type: str = None,
                    tag: str = None, starred_only: bool = False,
                    unread_only: bool = False, search: str = None,
                    limit: int = 100, offset: int = 0,
                    sort_by: str = "updated_at", sort_desc: bool = True) -> List[HubItem]:
        conditions = []
        params = []

        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        if item_type:
            conditions.append("item_type = ?")
            params.append(item_type)
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tag}"%')
        if starred_only:
            conditions.append("is_starred = 1")
        if unread_only:
            conditions.append("is_read = 0")
        if search:
            conditions.append("(title LIKE ? OR content LIKE ? OR summary LIKE ?)")
            q = f"%{search}%"
            params.extend([q, q, q])

        where = " AND ".join(conditions) if conditions else "1=1"
        order = f"{sort_by} {'DESC' if sort_desc else 'ASC'}"

        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM items WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                params + [limit, offset]
            ).fetchall()
            return [self._row_to_item(r) for r in rows]

    def get_item_count(self, source_type: str = None) -> int:
        with self._get_conn() as conn:
            if source_type:
                row = conn.execute("SELECT COUNT(*) FROM items WHERE source_type = ?", (source_type,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM items").fetchone()
            return row[0]

    def _row_to_item(self, row) -> HubItem:
        def _safe_col(r, col, default=""):
            try:
                return r[col]
            except (IndexError, KeyError):
                return default

        return HubItem(
            id=row["id"], title=row["title"], url=row["url"],
            content=row["content"], summary=row["summary"],
            source_type=row["source_type"], item_type=row["item_type"],
            tags=json.loads(row["tags"]), keywords=json.loads(row["keywords"]),
            metadata=json.loads(row["metadata"]),
            related_ids=json.loads(row["related_ids"]),
            collection_ids=json.loads(row["collection_ids"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
            accessed_at=row["accessed_at"],
            is_read=bool(row["is_read"]), is_starred=bool(row["is_starred"]),
            is_archived=bool(row["is_archived"]),
            pipeline_stage=_safe_col(row, "pipeline_stage", "ingested"),
            quality_score=float(_safe_col(row, "quality_score", 0.0)),
            last_enriched=_safe_col(row, "last_enriched", ""),
            content_hash=_safe_col(row, "content_hash", ""),
            needs_review=bool(_safe_col(row, "needs_review", 0)),
            auto_scan_source=_safe_col(row, "auto_scan_source", ""),
        )

    # ========== RSS 管理 ==========

    def add_rss_subscription(self, sub: RSSSubscription) -> RSSSubscription:
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO rss_subscriptions
                (id, title, url, category, poll_interval_minutes,
                 last_polled, last_etag, last_modified, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sub.id, sub.title, sub.url, sub.category,
                  sub.poll_interval_minutes, sub.last_polled,
                  sub.last_etag, sub.last_modified, int(sub.active), sub.created_at))
        self.event_bus.publish("rss.subscription_added", sub)
        return sub

    def remove_rss_subscription(self, sub_id: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM rss_subscriptions WHERE id = ?", (sub_id,))
        self.event_bus.publish("rss.subscription_removed", {"id": sub_id})
        return True

    def get_rss_subscriptions(self, active_only: bool = False) -> List[RSSSubscription]:
        with self._get_conn() as conn:
            q = "SELECT * FROM rss_subscriptions"
            if active_only:
                q += " WHERE active = 1"
            rows = conn.execute(q).fetchall()
            return [RSSSubscription(
                id=r["id"], title=r["title"], url=r["url"],
                category=r["category"], poll_interval_minutes=r["poll_interval_minutes"],
                last_polled=r["last_polled"], last_etag=r["last_etag"],
                last_modified=r["last_modified"], active=bool(r["active"]),
                created_at=r["created_at"]
            ) for r in rows]

    def update_rss_subscription(self, sub_id: str, **kwargs) -> bool:
        subs = self.get_rss_subscriptions()
        sub = next((s for s in subs if s.id == sub_id), None)
        if not sub:
            return False
        for k, v in kwargs.items():
            if hasattr(sub, k):
                setattr(sub, k, v)
        self.add_rss_subscription(sub)
        return True

    def poll_rss_feed(self, sub_id: str) -> List[HubItem]:
        subs = self.get_rss_subscriptions()
        sub = next((s for s in subs if s.id == sub_id), None)
        if not sub:
            return []

        try:
            new_items = self._fetch_rss(sub)
            sub.last_polled = datetime.now().isoformat()
            with self._get_conn() as conn:
                conn.execute("""
                    UPDATE rss_subscriptions SET last_polled = ?, last_etag = ?, last_modified = ?
                    WHERE id = ?
                """, (sub.last_polled, sub.last_etag, sub.last_modified, sub.id))

            if new_items:
                self.event_bus.publish("rss.new_entries", {"sub_id": sub_id, "count": len(new_items)})
            return new_items
        except Exception as e:
            self._log_pipeline("rss", "rss", "poll_failed", sub_id, "error", str(e))
            return []

    def poll_all_rss_feeds(self) -> Dict[str, int]:
        results = {}
        for sub in self.get_rss_subscriptions(active_only=True):
            try:
                new_items = self.poll_rss_feed(sub.id)
                results[sub.title or sub.url] = len(new_items)
            except Exception as e:
                results[sub.title or sub.url] = -1
                logger.warning(f"RSS poll failed for {sub.url}: {e}")
        self.event_bus.publish("rss.poll_complete", results)
        return results

    def _fetch_rss(self, sub: RSSSubscription) -> List[HubItem]:
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser not installed, trying basic XML parse")
            return self._fetch_rss_basic(sub)

        try:
            feed = feedparser.parse(sub.url)
        except Exception as e:
            logger.warning(f"feedparser parse failed for {sub.url}: {e}")
            return self._fetch_rss_basic(sub)

        if feed.bozo and not feed.entries:
            logger.warning(f"feedparser got malformed feed from {sub.url}: {feed.bozo_exception}")
            return self._fetch_rss_basic(sub)
        new_items = []

        for entry in feed.entries:
            entry_url = getattr(entry, 'link', '')
            if not entry_url:
                continue

            existing = None
            with self._get_conn() as conn:
                row = conn.execute("SELECT id FROM items WHERE url = ? LIMIT 1", (entry_url,)).fetchone()
                existing = row is not None
            if existing:
                continue

            content = ""
            if hasattr(entry, 'summary'):
                content = entry.summary
            elif hasattr(entry, 'content'):
                content = entry.content[0].value if entry.content else ""

            entry_keywords = []
            if hasattr(entry, 'tags') and entry.tags:
                entry_keywords = [getattr(t, 'term', str(t)) for t in entry.tags]

            item = HubItem(
                title=getattr(entry, 'title', 'Untitled'),
                url=entry_url,
                content=self._strip_html(content),
                summary=self._strip_html(content)[:500],
                source_type=SourceType.RSS.value,
                item_type=ItemType.RSS_ENTRY.value,
                tags=[sub.category] if sub.category else [],
                keywords=entry_keywords,
                metadata={
                    "rss_sub_id": sub.id,
                    "rss_sub_title": sub.title,
                    "author": getattr(entry, 'author', ''),
                    "published": getattr(entry, 'published', ''),
                }
            )
            self.add_item(item)
            new_items.append(item)

        return new_items

    def _fetch_rss_basic(self, sub: RSSSubscription) -> List[HubItem]:
        try:
            req = urllib.request.Request(sub.url, headers={
                "User-Agent": "WS2-DataHub/1.0"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_content = resp.read().decode("utf-8", errors="ignore")

            items = []
            for match in re.finditer(r'<item[^>]*>(.*?)</item>', xml_content, re.DOTALL):
                item_xml = match.group(1)
                title = self._extract_xml(item_xml, 'title')
                link = self._extract_xml(item_xml, 'link')
                desc = self._extract_xml(item_xml, 'description')

                if link:
                    hub_item = HubItem(
                        title=title, url=link,
                        content=self._strip_html(desc),
                        summary=self._strip_html(desc)[:500],
                        source_type=SourceType.RSS.value,
                        item_type=ItemType.RSS_ENTRY.value,
                        tags=[sub.category] if sub.category else [],
                        metadata={"rss_sub_id": sub.id}
                    )
                    self.add_item(hub_item)
                    items.append(hub_item)
            return items
        except Exception as e:
            logger.warning(f"Basic RSS fetch failed: {e}")
            return []

    def start_rss_poller(self, interval_seconds: int = 300):
        if self._rss_poller_running:
            return
        self._rss_poller_running = True

        def poller():
            while self._rss_poller_running:
                try:
                    self.poll_all_rss_feeds()
                except Exception as e:
                    logger.warning(f"RSS poller error: {e}")
                for _ in range(interval_seconds):
                    if not self._rss_poller_running:
                        break
                    time.sleep(1)

        self._rss_poller_thread = threading.Thread(target=poller, daemon=True)
        self._rss_poller_thread.start()

    def stop_rss_poller(self):
        self._rss_poller_running = False
        if self._rss_poller_thread and self._rss_poller_thread.is_alive():
            self._rss_poller_thread.join(timeout=5)
        self._rss_poller_thread = None

    # ========== Collection 管理 ==========

    def create_collection(self, coll: DataCollection) -> DataCollection:
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO collections
                (id, title, description, tags, item_ids, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (coll.id, coll.title, coll.description,
                  json.dumps(coll.tags, ensure_ascii=False),
                  json.dumps(coll.item_ids, ensure_ascii=False),
                  coll.created_at, coll.updated_at))
        self.event_bus.publish("collection.created", coll)
        return coll

    def get_collections(self) -> List[DataCollection]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM collections ORDER BY updated_at DESC").fetchall()
            return [DataCollection(
                id=r["id"], title=r["title"], description=r["description"],
                tags=json.loads(r["tags"]), item_ids=json.loads(r["item_ids"]),
                created_at=r["created_at"], updated_at=r["updated_at"]
            ) for r in rows]

    def get_collection(self, coll_id: str) -> Optional[DataCollection]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM collections WHERE id = ?", (coll_id,)).fetchone()
            if row:
                return DataCollection(
                    id=row["id"], title=row["title"], description=row["description"],
                    tags=json.loads(row["tags"]), item_ids=json.loads(row["item_ids"]),
                    created_at=row["created_at"], updated_at=row["updated_at"]
                )
        return None

    def update_collection(self, coll_id: str, **kwargs) -> bool:
        coll = self.get_collection(coll_id)
        if not coll:
            return False
        for k, v in kwargs.items():
            if hasattr(coll, k):
                setattr(coll, k, v)
        coll.updated_at = datetime.now().isoformat()
        self.create_collection(coll)
        return True

    def delete_collection(self, coll_id: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM collections WHERE id = ?", (coll_id,))
        self.event_bus.publish("collection.deleted", {"id": coll_id})
        return True

    def add_to_collection(self, coll_id: str, item_id: str) -> bool:
        coll = self.get_collection(coll_id)
        if not coll:
            return False
        if item_id not in coll.item_ids:
            coll.item_ids.append(item_id)
            coll.updated_at = datetime.now().isoformat()
            self.create_collection(coll)

            item = self.get_item(item_id)
            if item and coll_id not in item.collection_ids:
                item.collection_ids.append(coll_id)
                self.add_item(item, _skip_event=True)
                self.event_bus.publish("item.updated", item)
        return True

    def remove_from_collection(self, coll_id: str, item_id: str) -> bool:
        coll = self.get_collection(coll_id)
        if not coll:
            return False
        if item_id in coll.item_ids:
            coll.item_ids.remove(item_id)
            coll.updated_at = datetime.now().isoformat()
            self.create_collection(coll)

            item = self.get_item(item_id)
            if item and coll_id in item.collection_ids:
                item.collection_ids.remove(coll_id)
                self.add_item(item, _skip_event=True)
                self.event_bus.publish("item.updated", item)
        return True

    # ========== 数据管道 ==========

    def pipeline_crawl_to_hub(self, url: str, title: str = "", content: str = "",
                               keywords: List[str] = None) -> HubItem:
        item = HubItem(
            title=title or url, url=url, content=content,
            source_type=SourceType.CRAWLER.value,
            item_type=ItemType.WEBPAGE.value,
            keywords=keywords or []
        )
        self.add_item(item)
        self._log_pipeline("crawl_to_hub", "crawler", "ingest", item.id, "success")
        return item

    def pipeline_bookmark_to_hub(self, name: str, url: str, category: str = "",
                                  description: str = "") -> HubItem:
        item = HubItem(
            title=name, url=url, content=description,
            summary=description[:500],
            source_type=SourceType.BOOKMARK.value,
            item_type=ItemType.BOOKMARK.value,
            tags=[category] if category else [],
            metadata={"category": category}
        )
        self.add_item(item)
        self._log_pipeline("bookmark_to_hub", "bookmark", "ingest", item.id, "success")
        return item

    def pipeline_analysis_to_hub(self, title: str, content: str,
                                  keywords: List[str] = None) -> HubItem:
        item = HubItem(
            title=title, content=content,
            summary=content[:500],
            source_type=SourceType.ANALYSIS.value,
            item_type=ItemType.ANALYSIS_RESULT.value,
            keywords=keywords or []
        )
        self.add_item(item)
        self._log_pipeline("analysis_to_hub", "analysis", "ingest", item.id, "success")
        return item

    def pipeline_agent_to_hub(self, title: str, content: str,
                               url: str = "", metadata: Dict = None) -> HubItem:
        item = HubItem(
            title=title, url=url, content=content,
            summary=content[:500],
            source_type=SourceType.AGENT.value,
            item_type=ItemType.WEBPAGE.value,
            metadata=metadata or {}
        )
        self.add_item(item)
        self._log_pipeline("agent_to_hub", "agent", "ingest", item.id, "success")
        return item

    def pipeline_local_file_to_hub(self, file_path: str, title: str = "") -> HubItem:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        content = path.read_text(encoding="utf-8", errors="ignore")
        item = HubItem(
            title=title or path.name, url=str(path),
            content=content, summary=content[:500],
            source_type=SourceType.LOCAL_FILE.value,
            item_type=ItemType.FILE.value,
            metadata={"file_size": path.stat().st_size, "file_ext": path.suffix}
        )
        self.add_item(item)
        self._log_pipeline("local_to_hub", "local_file", "ingest", item.id, "success")
        return item

    def pipeline_rss_to_hub(self, sub_id: str) -> List[HubItem]:
        return self.poll_rss_feed(sub_id)

    def pipeline_bookmark_crawl(self, item_id: str) -> Optional[HubItem]:
        """管道：书签 → 爬取网页内容 → 更新枢纽项

        以书签的 URL 为爬虫起始点，抓取网页内容后自动回流到枢纽
        """
        item = self.get_item(item_id)
        if not item or not item.url:
            self._log_pipeline("bookmark_crawl", "bookmark", "crawl_failed", item_id, "error",
                               "item not found or no URL")
            return None

        try:
            content = self.fetch_url_content(item.url)
            if content:
                self.update_item(item_id, content=content, summary=content[:500])
                self._log_pipeline("bookmark_crawl", "bookmark", "crawl", item_id, "success",
                                   f"crawled {len(content)} chars from {item.url}")
                return self.get_item(item_id)
            else:
                self._log_pipeline("bookmark_crawl", "bookmark", "crawl_empty", item_id, "warning",
                                   f"no content from {item.url}")
                return None
        except Exception as e:
            self._log_pipeline("bookmark_crawl", "bookmark", "crawl_error", item_id, "error", str(e))
            return None

    def pipeline_crawl_bookmarks_batch(self, source_type: str = "bookmark",
                                        limit: int = 20) -> Dict[str, Any]:
        """批量爬取书签类型的数据项的 URL 内容

        将所有书签项的 URL 作为爬虫起始点，抓取内容后自动回流
        """
        items = self.query_items(source_type=source_type, limit=limit)
        results = {"crawled": 0, "failed": 0, "skipped": 0, "details": []}

        for item in items:
            if not item.url:
                results["skipped"] += 1
                continue
            if item.content and len(item.content) > 200:
                results["skipped"] += 1
                continue

            result = self.pipeline_bookmark_crawl(item.id)
            if result:
                results["crawled"] += 1
                results["details"].append({"id": item.id, "title": item.title, "status": "crawled"})
            else:
                results["failed"] += 1
                results["details"].append({"id": item.id, "title": item.title, "status": "failed"})

        self.event_bus.publish("pipeline.bookmark_crawl_batch", results)
        return results

    def generate_rss_feed(self, collection_id: str = None, source_type: str = None,
                           tag: str = None, limit: int = 50,
                           feed_title: str = "WS2 DataHub Feed",
                           feed_description: str = "",
                           feed_url: str = "") -> str:
        """RSS 制作法：从数据枢纽中的数据项生成 RSS XML feed

        可以按集合、来源类型或标签筛选数据项，生成标准 RSS 2.0 XML
        """
        if collection_id:
            coll = self.get_collection(collection_id)
            if not coll:
                return ""
            items = []
            for iid in coll.item_ids[:limit]:
                item = self.get_item(iid)
                if item:
                    items.append(item)
        else:
            items = self.query_items(source_type=source_type, tag=tag, limit=limit)

        if not feed_description:
            feed_description = f"Generated from WS2 DataHub - {len(items)} items"

        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<rss version="2.0">')
        xml_parts.append('  <channel>')
        xml_parts.append(f'    <title>{self._xml_escape(feed_title)}</title>')
        xml_parts.append(f'    <description>{self._xml_escape(feed_description)}</description>')
        if feed_url:
            xml_parts.append(f'    <link>{self._xml_escape(feed_url)}</link>')
        xml_parts.append(f'    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>')
        xml_parts.append(f'    <generator>WS2-DataHub/1.0</generator>')

        for item in items:
            xml_parts.append('    <item>')
            xml_parts.append(f'      <title>{self._xml_escape(item.title)}</title>')
            if item.url:
                xml_parts.append(f'      <link>{self._xml_escape(item.url)}</link>')
            desc = item.summary or item.content[:500] if item.content else ""
            xml_parts.append(f'      <description>{self._xml_escape(desc)}</description>')
            xml_parts.append(f'      <pubDate>{self._xml_escape(item.created_at[:19])}</pubDate>')
            xml_parts.append(f'      <guid>{self._xml_escape(item.id)}</guid>')
            if item.tags:
                for t in item.tags[:5]:
                    xml_parts.append(f'      <category>{self._xml_escape(t)}</category>')
            if item.metadata.get("author"):
                xml_parts.append(f'      <author>{self._xml_escape(item.metadata["author"])}</author>')
            xml_parts.append('    </item>')

        xml_parts.append('  </channel>')
        xml_parts.append('</rss>')

        feed_xml = "\n".join(xml_parts)
        self._log_pipeline("rss_generate", source_type or "all", "generate", "", "success",
                           f"generated RSS with {len(items)} items")
        return feed_xml

    def export_rss_feed_to_file(self, filepath: str, **kwargs) -> str:
        """将生成的 RSS feed 导出为文件"""
        feed_xml = self.generate_rss_feed(**kwargs)
        if feed_xml:
            Path(filepath).write_text(feed_xml, encoding="utf-8")
            self._log_pipeline("rss_export", "rss", "export", filepath, "success",
                               f"exported to {filepath}")
        return feed_xml

    def parse_item_content(self, item_id: str, parser: str = "auto") -> Dict[str, Any]:
        """解析数据项内容

        支持多种解析模式：
        - auto: 自动检测内容类型
        - html: HTML → 纯文本
        - json: JSON 结构化解析
        - markdown: Markdown 结构提取
        - url_list: 提取所有 URL
        - keywords: 提取关键词/标签
        """
        item = self.get_item(item_id)
        if not item:
            return {"error": "item not found"}

        content = item.content or ""
        result = {"item_id": item_id, "parser": parser, "parsed": {}}

        if parser == "auto":
            if content.strip().startswith("{") or content.strip().startswith("["):
                parser = "json"
            elif "<html" in content.lower() or "<body" in content.lower():
                parser = "html"
            elif content.count("#") > 3 and ("##" in content or "###" in content):
                parser = "markdown"
            else:
                parser = "text"

        if parser == "html":
            text = self._strip_html(content)
            urls = re.findall(r'https?://[^\s<>"\']+', content)
            result["parsed"] = {"text": text[:5000], "urls": list(set(urls))[:50],
                                "text_length": len(text)}

        elif parser == "json":
            try:
                data = json.loads(content)
                result["parsed"] = {"type": type(data).__name__,
                                    "keys": list(data.keys()) if isinstance(data, dict) else [],
                                    "length": len(data) if isinstance(data, (list, dict)) else 0,
                                    "preview": json.dumps(data, ensure_ascii=False)[:2000]}
            except json.JSONDecodeError as e:
                result["parsed"] = {"error": f"JSON parse failed: {e}"}

        elif parser == "markdown":
            headers = re.findall(r'^(#{1,6})\s+(.+)$', content, re.MULTILINE)
            links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
            code_blocks = re.findall(r'```(\w*)\n(.*?)```', content, re.DOTALL)
            result["parsed"] = {
                "headers": [(len(h), t) for h, t in headers],
                "links": [(text, url) for text, url in links][:30],
                "code_blocks": [{"lang": lang, "lines": code.count("\n") + 1} for lang, code in code_blocks],
                "word_count": len(content.split()),
            }

        elif parser == "url_list":
            urls = re.findall(r'https?://[^\s<>"\'\])]+', content)
            result["parsed"] = {"urls": list(set(urls))[:100], "count": len(set(urls))}

        elif parser == "keywords":
            words = re.findall(r'[a-zA-Z\u4e00-\u9fff]{2,}', content.lower())
            word_freq = Counter(words)
            stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                          'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                          'would', 'could', 'should', 'may', 'might', 'can', 'shall',
                          'this', 'that', 'these', 'those', 'and', 'or', 'but', 'not',
                          'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from',
                          'as', 'into', 'through', 'during', 'before', 'after', 'it',
                          'its', 'he', 'she', 'they', 'we', 'you', 'i', 'me', 'my',
                          '的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
                          '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去'}
            keywords = [(w, c) for w, c in word_freq.most_common(30) if w not in stop_words]
            result["parsed"] = {"keywords": keywords, "total_words": len(words)}

        else:
            result["parsed"] = {"text_length": len(content), "preview": content[:2000]}

        self._log_pipeline("parse_content", item.source_type, "parse", item_id, "success",
                           f"parsed with {parser}")
        return result

    def fetch_url_content(self, url: str) -> str:
        """抓取 URL 内容，返回纯文本"""
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "WS2-DataHub/1.0 (compatible; research bot)"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)
            except ImportError:
                return self._strip_html(html)
        except Exception as e:
            logger.warning(f"URL fetch failed for {url}: {e}")
            return ""

    def lightweight_crawl(self, url: str) -> Dict[str, Any]:
        """轻度爬取：只获取元信息和RSS/Atom订阅链接，不下载全文

        返回:
            {
                "url": str, "title": str, "description": str,
                "keywords": list, "author": str, "favicon": str,
                "feeds": [{"url": str, "type": "rss"/"atom", "title": str}],
                "links": [str],  # 页面内重要链接(最多20)
                "status": int, "content_type": str,
            }
        """
        result = {
            "url": url, "title": "", "description": "",
            "keywords": [], "author": "", "favicon": "",
            "feeds": [], "links": [], "status": 0, "content_type": "",
        }
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "WS2-DataHub/1.0 (compatible; research bot)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                result["status"] = resp.status
                result["content_type"] = resp.headers.get("Content-Type", "")
                html = resp.read(65536).decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Lightweight crawl failed for {url}: {e}")
            return result

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            soup = None

        if soup:
            title_tag = soup.find("title")
            if title_tag:
                result["title"] = title_tag.get_text(strip=True)

            for meta in soup.find_all("meta"):
                name = meta.get("name", "").lower()
                prop = meta.get("property", "").lower()
                content = meta.get("content", "")
                if name == "description" or prop == "og:description":
                    if content and not result["description"]:
                        result["description"] = content[:500]
                elif name == "keywords":
                    if content:
                        result["keywords"] = [k.strip() for k in content.split(",") if k.strip()][:10]
                elif name == "author":
                    result["author"] = content
                elif prop == "og:title" and not result["title"]:
                    result["title"] = content

            link_tag = soup.find("link", rel=lambda x: x and "icon" in " ".join(x) if isinstance(x, list) else "icon" in (x or ""))
            if link_tag:
                href = link_tag.get("href", "")
                if href:
                    if href.startswith("/"):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    result["favicon"] = href

            for link in soup.find_all("link", rel=lambda x: x and ("alternate" in " ".join(x) if isinstance(x, list) else "alternate" in (x or ""))):
                href = link.get("href", "")
                link_type = link.get("type", "")
                link_title = link.get("title", "")
                if not href:
                    continue
                if href.startswith("/"):
                    from urllib.parse import urljoin
                    href = urljoin(url, href)
                feed_type = "rss"
                if "atom" in link_type or "atom" in href.lower():
                    feed_type = "atom"
                result["feeds"].append({"url": href, "type": feed_type, "title": link_title})

            seen = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("/") or href.startswith("http"):
                    if href.startswith("/"):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    if href not in seen and href != url:
                        seen.add(href)
                        if len(seen) > 20:
                            break
            result["links"] = list(seen)
        else:
            title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
            if title_m:
                result["title"] = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html, re.IGNORECASE)
            if desc_m:
                result["description"] = desc_m.group(1)[:500]
            for feed_m in re.finditer(r'<link[^>]+rel=["\']alternate["\'][^>]+href=["\'](.*?)["\']', html, re.IGNORECASE):
                feed_url = feed_m.group(1)
                if feed_url.startswith("/"):
                    from urllib.parse import urljoin
                    feed_url = urljoin(url, feed_url)
                feed_type = "atom" if "atom" in feed_url.lower() else "rss"
                result["feeds"].append({"url": feed_url, "type": feed_type, "title": ""})

        return result

    def lightweight_crawl_batch(self, urls: List[str] = None,
                                 source_type: str = None,
                                 limit: int = 20) -> List[Dict[str, Any]]:
        """批量轻度爬取，返回元信息列表

        Args:
            urls: 指定URL列表，为空则从DataHub中按source_type取
            source_type: 从DataHub取此来源的URL
            limit: 最大爬取数量
        """
        if not urls:
            items = self.query_items(
                source_type=source_type, limit=limit,
                sort_by="quality_score", sort_desc=False,
            )
            urls = [item.url for item in items if item.url]
            urls = urls[:limit]

        results = []
        for u in urls:
            info = self.lightweight_crawl(u)
            results.append(info)
            if info.get("feeds"):
                for feed in info["feeds"]:
                    self._log_pipeline("lightweight_crawl", "discovery", "feed_found",
                                       feed["url"], "info",
                                       f"{feed['type']} from {u[:50]}")
        return results

    def discover_subscriptions(self, urls: List[str] = None,
                                source_type: str = "bookmark",
                                limit: int = 30) -> List[Dict[str, Any]]:
        """从URL列表中发现所有RSS/Atom订阅源，返回可导入的订阅列表

        Returns:
            [{"url": str, "type": "rss"/"atom", "title": str, "source_url": str}]
        """
        results = self.lightweight_crawl_batch(urls=urls, source_type=source_type, limit=limit)
        subscriptions = []
        seen_urls = set()
        existing_subs = {s.url for s in self.get_rss_subscriptions()}

        for info in results:
            for feed in info.get("feeds", []):
                feed_url = feed["url"]
                if feed_url in seen_urls or feed_url in existing_subs:
                    continue
                seen_urls.add(feed_url)
                subscriptions.append({
                    "url": feed_url,
                    "type": feed["type"],
                    "title": feed.get("title") or info.get("title", ""),
                    "source_url": info["url"],
                    "source_title": info.get("title", ""),
                })

        return subscriptions

    def import_discovered_subscriptions(self, subscriptions: List[Dict[str, Any]]) -> int:
        """将发现的订阅源批量导入为RSS订阅"""
        count = 0
        for sub_info in subscriptions:
            try:
                sub = RSSSubscription(
                    url=sub_info["url"],
                    title=sub_info.get("title", ""),
                    category=sub_info.get("type", "rss"),
                )
                self.add_rss_subscription(sub)
                count += 1
            except Exception as e:
                logger.warning(f"Import subscription failed for {sub_info['url']}: {e}")
        return count

    @staticmethod
    def _xml_escape(text: str) -> str:
        if not text:
            return ""
        return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))

    # ========== 统计 ==========

    def get_statistics(self) -> Dict:
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            starred = conn.execute("SELECT COUNT(*) FROM items WHERE is_starred = 1").fetchone()[0]
            unread = conn.execute("SELECT COUNT(*) FROM items WHERE is_read = 0").fetchone()[0]

            source_dist = {}
            for row in conn.execute("SELECT source_type, COUNT(*) as cnt FROM items GROUP BY source_type"):
                source_dist[row[0]] = row[1]

            type_dist = {}
            for row in conn.execute("SELECT item_type, COUNT(*) as cnt FROM items GROUP BY item_type"):
                type_dist[row[0]] = row[1]

            rss_count = conn.execute("SELECT COUNT(*) FROM rss_subscriptions WHERE active = 1").fetchone()[0]
            coll_count = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]

        return {
            "total_items": total, "starred": starred, "unread": unread,
            "source_distribution": source_dist, "type_distribution": type_dist,
            "rss_subscriptions": rss_count, "collections": coll_count,
            "pipeline_stages": self.get_pipeline_stage_stats(),
        }

    def get_pipeline_logs(self, limit: int = 50) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pipeline_logs ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ========== 工具方法 ==========

    def _log_pipeline(self, pipeline_name: str, source_type: str, action: str,
                       item_id: str, status: str, message: str = ""):
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO pipeline_logs (timestamp, pipeline_name, source_type, action, item_id, status, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), pipeline_name, source_type, action, item_id, status, message))
        except Exception as e:
            logger.warning(f"Pipeline log write failed: {e}")

    @staticmethod
    def _strip_html(text: str) -> str:
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def _extract_xml(xml: str, tag: str) -> str:
        match = re.search(f'<{tag}[^>]*>(.*?)</{tag}>', xml, re.DOTALL)
        if match:
            content = match.group(1)
            if content.startswith('<![CDATA['):
                content = content[9:-3]
            return content.strip()
        return ""

    def migrate_from_synergy(self, synergy_manager) -> int:
        """从旧的 SynergyManager 迁移数据到 DataHub"""
        if not synergy_manager:
            return 0
        count = 0
        source_map = {
            "crawler": SourceType.CRAWLER,
            "search": SourceType.BOOKMARK,
            "analysis": SourceType.ANALYSIS,
            "manual": SourceType.MANUAL,
        }
        type_map = {
            "webpage": ItemType.WEBPAGE,
            "paper": ItemType.PAPER,
            "github_repo": ItemType.GITHUB_REPO,
        }
        for item in synergy_manager.get_all_items():
            existing = self.get_item(item.id)
            if existing:
                continue
            hub_item = HubItem(
                id=item.id,
                title=item.title,
                url=item.url,
                content=item.content,
                source_type=source_map.get(item.source, SourceType.MANUAL).value,
                item_type=type_map.get(item.content_type, ItemType.WEBPAGE).value,
                tags=item.tags,
                keywords=item.keywords,
                metadata=item.metadata,
                related_ids=item.related,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            self.add_item(hub_item)
            count += 1
        self._log_pipeline("migration", "synergy", "migrate", "", "success", f"migrated {count} items")
        return count

    def get_pipeline_engine(self) -> PipelineEngine:
        return self._pipeline_engine

    def get_pipeline_status(self) -> Dict[str, Any]:
        return self._pipeline_engine.get_status()

    def get_pipeline_stage_stats(self) -> Dict[str, int]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT pipeline_stage, COUNT(*) as cnt FROM items GROUP BY pipeline_stage"
            ).fetchall()
            stages = {r["pipeline_stage"]: r["cnt"] for r in rows}
        for stage in PIPELINE_STAGES:
            if stage not in stages:
                stages[stage] = 0
        needs_review = 0
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM items WHERE needs_review = 1").fetchone()
            if row:
                needs_review = row[0]
        stages["needs_review"] = needs_review
        return stages

    def sync_back_to_bookmarks_json(self) -> int:
        filepath = self.base_dir / "bookmarks.json"
        if not filepath.exists():
            return 0

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"SyncBack: cannot read bookmarks.json: {e}")
            return 0

        if not isinstance(data, list):
            return 0

        bookmark_items = self.query_items(source_type="bookmark", limit=1000)
        url_to_item = {item.url: item for item in bookmark_items if item.url}

        updated = 0
        for bm in data:
            bm_url = bm.get("url", "")
            if not bm_url:
                continue
            hub_item = url_to_item.get(bm_url)
            if not hub_item:
                continue
            if not hub_item.content or len(hub_item.content) < 50:
                continue

            changed = False
            if hub_item.summary and not bm.get("description"):
                bm["description"] = hub_item.summary[:500]
                changed = True

            bm_keywords = hub_item.keywords or []
            if bm_keywords and not bm.get("keywords"):
                bm["keywords"] = bm_keywords
                changed = True

            if hub_item.tags and not bm.get("category"):
                bm["category"] = hub_item.tags[0]
                changed = True

            if changed:
                updated += 1

            for child in bm.get("children", []):
                child_url = child.get("url", "")
                if not child_url:
                    continue
                child_item = url_to_item.get(child_url)
                if not child_item or not child_item.content:
                    continue
                if child_item.summary and not child.get("description"):
                    child["description"] = child_item.summary[:500]
                    updated += 1

        if updated > 0:
            try:
                filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                self._log_pipeline("syncback", "bookmark", "sync_back", "", "success",
                                   f"updated {updated} bookmarks")
            except Exception as e:
                logger.warning(f"SyncBack write failed: {e}")
                return 0

        return updated

    def auto_scan_all_sources(self) -> Dict[str, int]:
        """自动扫描所有已知数据源并导入到枢纽

        扫描范围：
        - bookmarks.json（网络探研书签，365个）
        - data/pages/pages_index.json（WebAnalyseII 已爬取页面，109个）
        - resource_index.json（课程资源索引，23个课程）
        - data/workflow.db（工作流 artifact）
        - data/bookmarks.json（书签管理器数据）
        """
        results = {}

        results["bookmarks"] = self._scan_bookmarks_json()
        results["pages"] = self._scan_pages_index()
        results["resources"] = self._scan_resource_index()
        results["workflow"] = self._scan_workflow_db()
        results["bookmark_mgr"] = self._scan_bookmark_manager_data()

        total = sum(results.values())
        self._log_pipeline("auto_scan", "all", "scan", "", "success",
                           f"scanned all sources, total {total} new items")
        self.event_bus.publish("auto_scan.complete", results)
        return results

    def _scan_bookmarks_json(self) -> int:
        """扫描根目录 bookmarks.json（网络探研书签）"""
        filepath = self.base_dir / "bookmarks.json"
        if not filepath.exists():
            return 0

        count = 0
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for bm in data:
                    url = bm.get("url", "")
                    if not url:
                        continue
                    with self._get_conn() as conn:
                        existing = conn.execute("SELECT id FROM items WHERE url = ?", (url,)).fetchone()
                    if existing:
                        continue

                    item = HubItem(
                        title=bm.get("name", ""),
                        url=url,
                        source_type=SourceType.BOOKMARK.value,
                        item_type=ItemType.BOOKMARK.value,
                        tags=[bm.get("category", "")] if bm.get("category") else [],
                        pipeline_stage="scanned",
                        auto_scan_source="bookmarks_json",
                        metadata={
                            "icon": bm.get("icon", ""),
                            "color": bm.get("color", ""),
                            "bm_id": bm.get("id", ""),
                            "children_count": len(bm.get("children", [])),
                        }
                    )
                    self.add_item(item, _skip_event=True)
                    count += 1

                    for child in bm.get("children", []):
                        child_url = child.get("url", "")
                        if not child_url:
                            continue
                        with self._get_conn() as conn:
                            existing = conn.execute("SELECT id FROM items WHERE url = ?", (child_url,)).fetchone()
                        if existing:
                            continue
                        child_item = HubItem(
                            title=child.get("name", ""),
                            url=child_url,
                            source_type=SourceType.BOOKMARK.value,
                            item_type=ItemType.BOOKMARK.value,
                            tags=[bm.get("category", ""), child.get("category", "")],
                            pipeline_stage="scanned",
                            auto_scan_source="bookmarks_json",
                            metadata={"parent_bm_id": bm.get("id", "")}
                        )
                        self.add_item(child_item, _skip_event=True)
                        count += 1
        except Exception as e:
            logger.warning(f"Scan bookmarks.json failed: {e}")

        if count:
            self._log_pipeline("auto_scan", "bookmark", "scan_bookmarks", "", "success", f"{count} items")
            self.event_bus.publish("item.added", None)
        return count

    def _scan_pages_index(self) -> int:
        """扫描 data/pages/pages_index.json（WebAnalyseII 已爬取页面）"""
        filepath = self.base_dir / "data" / "pages" / "pages_index.json"
        if not filepath.exists():
            return 0

        count = 0
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            for url, info in data.items():
                with self._get_conn() as conn:
                    existing = conn.execute("SELECT id FROM items WHERE url = ?", (url,)).fetchone()
                if existing:
                    continue

                html_path = self.base_dir / info.get("filepath", "")
                content = ""
                if html_path.exists():
                    try:
                        raw = html_path.read_text(encoding="utf-8", errors="ignore")
                        content = self._strip_html(raw)[:5000]
                    except Exception:
                        pass

                item = HubItem(
                    title=url.split("/")[-1] or url,
                    url=url,
                    content=content,
                    summary=content[:500] if content else "",
                    source_type=SourceType.CRAWLER.value,
                    item_type=ItemType.WEBPAGE.value,
                    pipeline_stage="scanned",
                    auto_scan_source="pages_index",
                    metadata={
                        "html_file": info.get("filepath", ""),
                        "saved_time": info.get("saved_time", ""),
                        "depth": info.get("metadata", {}).get("depth", 0),
                    }
                )
                self.add_item(item, _skip_event=True)
                count += 1
        except Exception as e:
            logger.warning(f"Scan pages_index.json failed: {e}")

        if count:
            self._log_pipeline("auto_scan", "crawler", "scan_pages", "", "success", f"{count} items")
            self.event_bus.publish("item.added", None)
        return count

    def _scan_resource_index(self) -> int:
        """扫描 resource_index.json（课程资源索引）"""
        filepath = self.base_dir / "resource_index.json"
        if not filepath.exists():
            return 0

        count = 0
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            for course_id, resources in data.items():
                if not isinstance(resources, list):
                    continue
                for res in resources:
                    res_path = res.get("path", "")
                    res_label = res.get("label", "")
                    res_type = res.get("type", "")

                    if not res_path and not res_label:
                        continue

                    check_key = res_path or res_label
                    with self._get_conn() as conn:
                        existing = conn.execute(
                            "SELECT id FROM items WHERE url = ? OR title = ?",
                            (res_path, res_label)
                        ).fetchone()
                    if existing:
                        continue

                    item = HubItem(
                        title=re.sub(r'^[📄🎬🎵📦💻🔤⚙️🖼️]+\s*', '', res_label) if res_label else Path(res_path).name if res_path else "",
                        url=res_path,
                        source_type=SourceType.LOCAL_FILE.value,
                        item_type=ItemType.FILE.value,
                        tags=[course_id, res_type],
                        pipeline_stage="scanned",
                        auto_scan_source="resource_index",
                        metadata={
                            "course_id": course_id,
                            "resource_type": res_type,
                            "lesson_number": res.get("lesson_number"),
                        }
                    )
                    self.add_item(item, _skip_event=True)
                    count += 1
        except Exception as e:
            logger.warning(f"Scan resource_index.json failed: {e}")

        if count:
            self._log_pipeline("auto_scan", "local_file", "scan_resources", "", "success", f"{count} items")
            self.event_bus.publish("item.added", None)
        return count

    def _scan_workflow_db(self) -> int:
        """扫描 data/workflow.db（工作流 artifact）"""
        db_path = self.base_dir / "data" / "workflow.db"
        if not db_path.exists():
            return 0

        count = 0
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT artifact_id, artifact_type, name, content, file_path, size_bytes, created_at FROM workflow_artifacts"
            ).fetchall()
            for row in rows:
                title = row["name"] or row["artifact_id"]
                with self._get_conn() as hub_conn:
                    existing = hub_conn.execute(
                        "SELECT id FROM items WHERE title = ? AND source_type = ?",
                        (title, "analysis")
                    ).fetchone()
                if existing:
                    continue

                content = row["content"] or ""
                if content and len(content) > 5000:
                    content = content[:5000]

                item = HubItem(
                    title=title,
                    url=row["file_path"] or "",
                    content=content,
                    summary=content[:500] if content else "",
                    source_type=SourceType.ANALYSIS.value,
                    item_type=ItemType.ANALYSIS_RESULT.value,
                    pipeline_stage="scanned",
                    auto_scan_source="workflow_db",
                    metadata={
                        "artifact_id": row["artifact_id"],
                        "artifact_type": row["artifact_type"],
                        "size_bytes": row["size_bytes"],
                        "workflow_created_at": row["created_at"],
                    }
                )
                self.add_item(item, _skip_event=True)
                count += 1
            conn.close()
        except Exception as e:
            logger.warning(f"Scan workflow.db failed: {e}")

        if count:
            self._log_pipeline("auto_scan", "analysis", "scan_workflow", "", "success", f"{count} items")
            self.event_bus.publish("item.added", None)
        return count

    def _scan_bookmark_manager_data(self) -> int:
        """扫描 data/bookmarks.json（书签管理器数据）"""
        filepath = self.base_dir / "data" / "bookmarks.json"
        if not filepath.exists():
            return 0

        count = 0
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            bookmarks = data.get("bookmarks", []) if isinstance(data, dict) else data
            if isinstance(bookmarks, list):
                for bm in bookmarks:
                    url = bm.get("url", "")
                    if not url:
                        continue
                    with self._get_conn() as conn:
                        existing = conn.execute("SELECT id FROM items WHERE url = ?", (url,)).fetchone()
                    if existing:
                        continue

                    item = HubItem(
                        title=bm.get("title", bm.get("name", "")),
                        url=url,
                        content=bm.get("fetched_content", "")[:5000] if bm.get("fetched_content") else "",
                        summary=bm.get("description", "")[:500],
                        source_type=SourceType.BOOKMARK.value,
                        item_type=ItemType.BOOKMARK.value,
                        tags=[bm.get("category", "")] if bm.get("category") else [],
                        pipeline_stage="scanned",
                        auto_scan_source="bookmark_manager",
                        metadata={
                            "is_rss": bm.get("is_rss", False),
                            "bm_id": bm.get("id", ""),
                        }
                    )
                    self.add_item(item, _skip_event=True)
                    count += 1
        except Exception as e:
            logger.warning(f"Scan data/bookmarks.json failed: {e}")

        if count:
            self._log_pipeline("auto_scan", "bookmark", "scan_bm_mgr", "", "success", f"{count} items")
            self.event_bus.publish("item.added", None)
        return count


# ========== 全局实例 ==========

_g_data_hub: Optional[DataHub] = None


def init_data_hub(base_dir: Path, force: bool = False) -> DataHub:
    global _g_data_hub
    if _g_data_hub is not None and not force:
        return _g_data_hub
    _g_data_hub = DataHub(base_dir)
    return _g_data_hub


def get_data_hub() -> Optional[DataHub]:
    return _g_data_hub
