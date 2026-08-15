import json
import time
import uuid
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SessionRecord:
    id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    name: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    messages: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    total_tokens: int = 0
    turn_count: int = 0
    # 状态容器相关字段
    session_type: str = "chat"  # chat, task, topic
    merged_ids: List[str] = field(default_factory=list)  # 合并过的会话 ID


class SessionStore:
    """会话状态容器存储 - 支持会话合并、去重和缓存"""

    def __init__(self, store_dir: Optional[str] = None):
        if store_dir is None:
            self.store_dir = Path(__file__).parent.parent / "cache_data" / "sessions"
        else:
            self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, SessionRecord] = {}
        self._name_index: Dict[str, str] = {}  # 名称哈希 -> session_id 索引
        self._dirty = True  # 缓存脏标记
        self._last_list_time = 0
        self._list_cache: List[SessionRecord] = []

    def create(self, name: str = "", metadata: Optional[Dict] = None,
               session_type: str = "chat") -> SessionRecord:
        """创建新会话 - 如果有同名会话则返回已存在的"""
        # 检查是否有同名会话可以合并
        name_hash = self._compute_name_hash(name)
        if name_hash and name_hash in self._name_index:
            existing_id = self._name_index[name_hash]
            existing = self._cache.get(existing_id)
            if existing is None:
                existing = self._load(existing_id)
                if existing:
                    self._cache[existing_id] = existing
            if existing:
                # 更新现有会话的时间戳，返回已有会话
                existing.updated_at = time.time()
                existing.last_accessed_at = time.time()
                self._save(existing)
                self._dirty = True
                logger = __import__('logging').getLogger(__name__)
                logger.info(f"SessionStore: 复用已有会话 '{name}' (id={existing_id[:12]})")
                return existing

        # 创建新会话
        record = SessionRecord(
            name=name,
            metadata=metadata or {},
            session_type=session_type,
        )
        self._cache[record.id] = record
        # 添加名称索引
        if name_hash:
            self._name_index[name_hash] = record.id
        self._save(record)
        self._dirty = True
        return record

    def create_with_id(self, session_id: str, name: str = "",
                       metadata: Optional[Dict] = None,
                       session_type: str = "chat") -> SessionRecord:
        """使用指定 ID 创建新会话（用于迁移旧会话）"""
        # 检查是否已存在
        existing = self.get(session_id)
        if existing:
            return existing
        
        # 创建新会话，使用指定 ID
        record = SessionRecord(
            id=session_id,
            name=name,
            metadata=metadata or {},
            session_type=session_type,
        )
        self._cache[record.id] = record
        # 添加名称索引
        name_hash = self._compute_name_hash(name)
        if name_hash:
            self._name_index[name_hash] = record.id
        self._save(record)
        self._dirty = True
        return record

    def get(self, session_id: str) -> Optional[SessionRecord]:
        """获取会话 - 更新最后访问时间"""
        if session_id in self._cache:
            record = self._cache[session_id]
            record.last_accessed_at = time.time()
            return record
        record = self._load(session_id)
        if record:
            self._cache[session_id] = record
            record.last_accessed_at = time.time()
            # 更新名称索引
            name_hash = self._compute_name_hash(record.name)
            if name_hash:
                self._name_index[name_hash] = record.id
        return record

    def update(self, session_id: str, **kwargs) -> bool:
        """更新会话"""
        record = self.get(session_id)
        if record is None:
            return False
        for k, v in kwargs.items():
            if hasattr(record, k):
                setattr(record, k, v)
        record.updated_at = time.time()
        self._save(record)
        self._dirty = True
        return True

    def append_message(self, session_id: str, message: Dict):
        """追加消息"""
        record = self.get(session_id)
        if record is None:
            return
        record.messages.append(message)
        record.updated_at = time.time()
        record.last_accessed_at = time.time()
        self._save(record)
        self._dirty = True

    # ── 普通模式待发送队列（spec id=7）：metadata['pending_queue'] 持久化，刷新/多标签共享 ──

    def _pending_queue(self, record: SessionRecord) -> list:
        """读取会话待发送队列（缺省空列表，容错非 list 值）"""
        q = (record.metadata or {}).get("pending_queue")
        return list(q) if isinstance(q, list) else []

    def enqueue_pending(self, session_id: str, content: str) -> int:
        """追加一条待发送消息到队列（FIFO），返回队列长度"""
        record = self.get(session_id)
        if record is None:
            return 0
        metadata = dict(record.metadata or {})
        q = self._pending_queue(record)
        q.append(content)
        metadata["pending_queue"] = q
        record.metadata = metadata
        record.updated_at = time.time()
        self._save(record)
        self._dirty = True
        return len(q)

    def pending_queue_dequeue(self, session_id: str) -> Optional[str]:
        """弹出队首（FIFO），空队列返回 None"""
        record = self.get(session_id)
        if record is None:
            return None
        q = self._pending_queue(record)
        if not q:
            return None
        item = q.pop(0)
        metadata = dict(record.metadata or {})
        metadata["pending_queue"] = q
        record.metadata = metadata
        record.updated_at = time.time()
        self._save(record)
        self._dirty = True
        return item

    def pending_queue_peek(self, session_id: str) -> Optional[str]:
        """查看队首（不弹出），空队列返回 None"""
        record = self.get(session_id)
        if record is None:
            return None
        q = self._pending_queue(record)
        return q[0] if q else None

    def pending_queue_len(self, session_id: str) -> int:
        """队列长度（会话不存在返回 0，不报错）"""
        record = self.get(session_id)
        if record is None:
            return 0
        return len(self._pending_queue(record))

    def clear_pending_queue(self, session_id: str) -> int:
        """清空队列，返回清空条数"""
        record = self.get(session_id)
        if record is None:
            return 0
        q = self._pending_queue(record)
        n = len(q)
        if n == 0:
            return 0
        metadata = dict(record.metadata or {})
        metadata["pending_queue"] = []
        record.metadata = metadata
        record.updated_at = time.time()
        self._save(record)
        self._dirty = True
        return n

    def merge_sessions(self, source_id: str, target_id: str) -> bool:
        """合并会话 - 将 source 的消息合并到 target，然后删除 source"""
        source = self.get(source_id)
        target = self.get(target_id)
        if source is None or target is None:
            return False

        # 合并消息
        source_msgs = source.messages
        if source_msgs:
            if not target.messages:
                target.messages = source_msgs
            else:
                # 按时间顺序合并
                target.messages.extend(source_msgs)

        # 更新元数据
        target.merged_ids.append(source_id)
        target.turn_count += source.turn_count
        target.total_tokens += source.total_tokens
        target.updated_at = time.time()
        target.last_accessed_at = time.time()

        # 保存目标会话
        self._save(target)

        # 删除源会话
        self.delete(source_id)

        self._dirty = True
        logger = __import__('logging').getLogger(__name__)
        logger.info(f"SessionStore: 合并会话 {source_id[:8]} -> {target_id[:8]}")
        return True

    def _is_checkpoint_session(self, record: SessionRecord) -> bool:
        """判断是否为检查点会话（需要过滤，不作为独立会话展示）
        
        检查点是绑定在工具调用上的，不应该作为独立会话存在。
        
        迁移说明：
        - 迁移后的会话使用标准会话 ID（sess_* 格式），metadata.source = "checkpoint_migrated"
        - 迁移后的会话应该正常显示，不再被过滤
        - 只有真正的"检查点专用会话"才需要过滤（这些是重构前的异常数据）
        """
        name = record.name or ""
        metadata = record.metadata or {}
        sid = record.id or ""
        
        # 迁移后的会话：source = "checkpoint_migrated" 且 migration_type = "one_time"
        # 这些是已经迁移完成的有效会话，应该正常显示
        if metadata and metadata.get("migration_type") == "one_time":
            return False
        
        # 真正的检查点会话：metadata.source == "checkpoint_migrated" 但没有 migration_type
        # 这些是重构过程中自动生成的临时会话，应该过滤
        if metadata and metadata.get("source") == "checkpoint_migrated":
            return True
        
        # 检查名称是否包含"检查点"（明确是检查点会话）
        if "检查点" in name or "checkpoint" in name.lower():
            return True
        
        # 检查名称是否以 "cp-" 开头（旧格式检查点命名）
        if name.startswith("cp-"):
            return True
        
        # 检查 ID 是否以 "cp-" 开头（未迁移的旧格式会话 ID）
        if sid.startswith("cp-"):
            return True
        
        # 检查 ID 是否为短哈希格式（8位十六进制，无连字符，旧格式会话 ID）
        # 这些通常是检查点 ID 被错误用作会话 ID
        import re
        if re.match(r'^[0-9a-f]{8}$', sid):
            return True
        
        return False

    def list_sessions(self, limit: int = 50, force_refresh: bool = False,
                      include_checkpoint: bool = False) -> List[SessionRecord]:
        """列出会话 - 使用缓存优化性能
        
        Args:
            limit: 最大返回数量
            force_refresh: 强制刷新缓存
            include_checkpoint: 是否包含检查点会话（默认False，过滤掉）
        """
        now = time.time()

        # 使用缓存（10秒内不重复扫描）
        if not force_refresh and not self._dirty and (now - self._last_list_time < 10):
            cached = self._list_cache
            if not include_checkpoint:
                cached = [r for r in cached if not self._is_checkpoint_session(r)]
            return cached[:limit]

        records = []
        # 从磁盘加载
        for f in self.store_dir.glob("*.json"):
            record = self._load(f.stem)
            if record:
                records.append(record)
                self._cache[record.id] = record
                # 更新名称索引
                name_hash = self._compute_name_hash(record.name)
                if name_hash:
                    self._name_index[name_hash] = record.id

        # 按最后访问时间排序（最近使用的在前）
        records.sort(key=lambda r: max(r.updated_at, r.last_accessed_at), reverse=True)

        # 缓存完整列表（包含所有记录）
        self._list_cache = list(records)
        self._last_list_time = now
        self._dirty = False

        # 过滤检查点会话
        if not include_checkpoint:
            records = [r for r in records if not self._is_checkpoint_session(r)]

        return records[:limit]

    def search_sessions(self, query: str, limit: int = 20) -> List[SessionRecord]:
        """搜索会话"""
        results = []
        query_lower = query.lower()
        for record in self._list_cache:
            if (query_lower in record.name.lower() or
                query_lower in json.dumps(record.messages, ensure_ascii=False).lower()):
                results.append(record)
                if len(results) >= limit:
                    break
        if not results:
            # 如果缓存没命中，直接扫描
            for f in self.store_dir.glob("*.json"):
                record = self._load(f.stem)
                if record and (query_lower in record.name.lower()):
                    results.append(record)
                    if len(results) >= limit:
                        break
        return results

    def delete(self, session_id: str) -> bool:
        """删除会话"""
        record = self._cache.get(session_id)
        if record:
            # 清理名称索引
            name_hash = self._compute_name_hash(record.name)
            if name_hash and self._name_index.get(name_hash) == session_id:
                del self._name_index[name_hash]

        self._cache.pop(session_id, None)
        path = self.store_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            self._dirty = True
            return True
        return False

    def get_active_sessions(self, max_age: float = 3600) -> List[SessionRecord]:
        """获取活跃会话（最近 max_age 秒内使用过的）"""
        now = time.time()
        active = []
        for record in self._list_cache:
            if (now - record.last_accessed_at) < max_age:
                active.append(record)
        return active

    def cleanup_orphaned_sessions(self) -> int:
        """清理孤立会话（没有用户消息的空会话）"""
        cleaned = 0
        for f in self.store_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                messages = data.get("messages", [])
                user_msgs = [m for m in messages if m.get("role") == "user"]
                if len(user_msgs) == 0 and len(messages) < 3:
                    # 空会话，删除
                    f.unlink()
                    sid = f.stem
                    self._cache.pop(sid, None)
                    cleaned += 1
            except Exception:
                continue
        if cleaned > 0:
            self._dirty = True
            logger = __import__('logging').getLogger(__name__)
            logger.info(f"SessionStore: 清理了 {cleaned} 个孤立会话")
        return cleaned

    def cleanup_checkpoint_sessions(self) -> int:
        """统计检查点会话数量（仅统计，不删除）
        
        检查点是绑定在工具调用上的，不应该作为独立会话存在。
        但旧数据保留，仅在列表中过滤掉。
        """
        count = 0
        for f in self.store_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                
                name = data.get("name", "")
                metadata = data.get("metadata", {})
                
                is_checkpoint_migrated = metadata and metadata.get("source") == "checkpoint_migrated"
                has_checkpoint_name = "检查点" in name or "checkpoint" in name.lower()
                is_cp_prefixed = name.startswith("cp-")
                
                if is_checkpoint_migrated or has_checkpoint_name or is_cp_prefixed:
                    count += 1
            except Exception:
                continue
        
        return count

    def _compute_name_hash(self, name: str) -> str:
        """计算名称的规范化哈希（用于去重）"""
        if not name:
            return ""
        # 规范化：去除空白、转小写
        normalized = " ".join(name.lower().split())
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

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
