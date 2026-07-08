"""
文件同步引擎
参考思源笔记的同步机制 + better-sync-siyuan 的增量同步模式：
- 同步锁（acquireAllLocks/releaseAllLocks）防止并发
- 同步状态管理（SyncStatus 枚举）
- 冲突检测（基于时间戳比较，创建冲突副本）
- 同步历史记录（记录每次同步时间和变更）
- 增量变更检测（hash + mtime）
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import IntEnum

logger = logging.getLogger(__name__)


# ─── 同步状态枚举（参考 better-sync SyncStatus）──────────────────

class SyncStatus(IntEnum):
    """同步状态"""
    None_ = 0
    InProgress = 1
    Failed = 2
    DoneWithConflict = 3
    Done = 4


class SyncFileOperationType(IntEnum):
    """同步文件操作类型（参考 better-sync SyncFileOperationType）"""
    Sync = 0          # 双向同步
    Delete = 1        # 删除
    DeleteAndSync = 2 # 删除后同步（类型不匹配时）
    HandleConflictAndSync = 3  # 冲突处理后同步
    MoveDocs = 4      # 移动文档


@dataclass
class FileEntry:
    """文件条目"""
    path: str  # 相对于工作区的路径
    name: str
    is_dir: bool
    size: int = 0
    modified: float = 0.0
    hash: str = ""
    ext: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyncEvent:
    """同步事件"""
    event_type: str  # created, modified, deleted, renamed
    path: str
    old_path: str = ""  # 仅用于 renamed
    timestamp: float = 0.0
    hash: str = ""
    size: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyncChange:
    """增量同步变更记录"""
    type: str  # created, modified, deleted, conflict
    path: str
    hash: str = ""
    size: int = 0
    operation: str = ""  # Sync, Delete, HandleConflictAndSync
    conflict_path: str = ""  # 冲突副本路径


@dataclass
class SyncHistoryEntry:
    """同步历史条目"""
    timestamp: float
    status: str  # Done, DoneWithConflict, Failed
    synced_count: int = 0
    conflict_count: int = 0
    deleted_count: int = 0
    duration: float = 0.0
    changes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class FileSyncEngine:
    """
    文件同步引擎

    参考 siyuan-android + better-sync-siyuan 的同步架构：
    1. 文件树扫描和索引
    2. 文件变更检测（基于 hash + mtime）
    3. 文件读写操作
    4. 目录操作
    5. 变更事件分发（通过 WebSocket）
    6. 同步锁（参考 better-sync acquireAllLocks/releaseAllLocks）
    7. 同步状态管理（参考 better-sync SyncStatus）
    8. 冲突检测与处理（参考 better-sync ConflictHandler）
    9. 同步历史记录（参考 better-sync SyncHistory）
    """

    # 支持的文件类型
    EDITABLE_EXTENSIONS = {
        ".md", ".rmd", ".txt", ".tex", ".bib",
        ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml",
        ".r", ".R", ".cpp", ".c", ".h", ".java", ".go", ".rs",
        ".html", ".css", ".xml", ".svg",
        ".sh", ".bat", ".ps1",
        ".sql", ".graphql",
    }

    # 忽略的目录/文件
    IGNORE_PATTERNS = {
        "__pycache__", ".git", ".svn", ".hg", "node_modules",
        ".DS_Store", "Thumbs.db", ".env", ".venv", "venv",
        ".idea", ".vscode", "*.pyc", ".cache",
        "build", ".codex", "Output", "agent_config",
    }

    # 仅暴露这些顶级目录（安全限制，不暴露源代码）
    EXPOSED_DIRS = {"Notes", "bookmarks", "data", "datahub", "projects"}

    # 根目录下允许暴露的特定文件
    EXPOSED_ROOT_FILES = {"bookmarks.json", "courses_structured.json", "task_board.json"}

    # 同步历史文件名
    SYNC_HISTORY_FILE = ".ts2_sync_history.json"

    # 冲突副本后缀
    CONFLICT_SUFFIX = ".conflict"

    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._file_index: Dict[str, FileEntry] = {}
        self._last_scan_time: float = 0.0
        self._watching = False
        self._watch_task: Optional[asyncio.Task] = None
        self._on_change_callback = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        # 同步锁（参考 better-sync acquireAllLocks/releaseAllLocks + siyuan-android syncing 互斥）
        self._sync_lock = asyncio.Lock()
        self._sync_status: SyncStatus = SyncStatus.None_

        # 同步历史（参考 better-sync SyncHistory）
        self._sync_history: List[SyncHistoryEntry] = []
        self._last_sync_time: float = 0.0
        self._load_sync_history()

        # 同步冷却：避免移动端频繁触发同步
        self._min_sync_interval: float = 10.0  # 最小同步间隔（秒）
        self._last_sync_attempt_time: float = 0.0

    # ─── 同步锁管理（参考 better-sync）─────────────────────────

    def acquire_sync_lock(self) -> bool:
        """尝试获取同步锁（非阻塞），参考 siyuan-android 的 syncing 互斥"""
        if self._sync_lock.locked():
            return False
        # 注意：asyncio.Lock 需要 await，这里用状态标记
        if self._sync_status == SyncStatus.InProgress:
            return False
        self._sync_status = SyncStatus.InProgress
        return True

    def release_sync_lock(self):
        """释放同步锁"""
        self._sync_status = SyncStatus.None_

    def get_sync_status(self) -> SyncStatus:
        """获取当前同步状态"""
        return self._sync_status

    def set_sync_status(self, status: SyncStatus):
        """设置同步状态"""
        self._sync_status = status

    # ─── 同步历史管理（参考 better-sync SyncHistory）───────────

    def _load_sync_history(self):
        """加载同步历史"""
        history_path = self.workspace_dir / self.SYNC_HISTORY_FILE
        if not history_path.exists():
            return
        try:
            data = json.loads(history_path.read_text(encoding="utf-8"))
            for entry_data in data.get("history", []):
                self._sync_history.append(SyncHistoryEntry(
                    timestamp=entry_data.get("timestamp", 0),
                    status=entry_data.get("status", ""),
                    synced_count=entry_data.get("synced_count", 0),
                    conflict_count=entry_data.get("conflict_count", 0),
                    deleted_count=entry_data.get("deleted_count", 0),
                    duration=entry_data.get("duration", 0),
                    changes=entry_data.get("changes", []),
                ))
            self._last_sync_time = data.get("last_sync_time", 0)
            # 只保留最近 50 条
            self._sync_history = self._sync_history[-50:]
        except Exception as e:
            logger.warning(f"Load sync history failed: {e}")

    def _save_sync_history(self):
        """保存同步历史"""
        history_path = self.workspace_dir / self.SYNC_HISTORY_FILE
        try:
            data = {
                "last_sync_time": self._last_sync_time,
                "history": [h.to_dict() for h in self._sync_history[-50:]],
            }
            history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Save sync history failed: {e}")

    def add_sync_history(self, entry: SyncHistoryEntry):
        """添加同步历史条目"""
        self._sync_history.append(entry)
        self._last_sync_time = entry.timestamp
        self._save_sync_history()

    def get_sync_history(self, limit: int = 20) -> List[dict]:
        """获取同步历史"""
        return [h.to_dict() for h in self._sync_history[-limit:]]

    # ─── 冲突检测（参考 better-sync ConflictHandler）───────────

    def detect_conflict(self, rel_path: str, client_modified: float) -> bool:
        """
        检测冲突：当客户端修改时间与服务器端修改时间都晚于上次同步时间时，
        且两者不同，则存在冲突。
        
        参考 better-sync detectConflict:
        if file.timestamp > lastSyncTime for BOTH remotes AND timestamps differ => conflict
        """
        old_entry = self._file_index.get(rel_path)
        if old_entry is None:
            return False
        if self._last_sync_time <= 0:
            return False
        # 服务器端文件在上次同步后被修改，客户端也声称修改了
        server_modified = old_entry.modified
        if server_modified > self._last_sync_time and client_modified > self._last_sync_time:
            # 两端都在上次同步后修改了，可能冲突
            return True
        return False

    def create_conflict_copy(self, rel_path: str) -> Optional[str]:
        """
        创建冲突副本文件。
        
        参考 better-sync createConflictFile: 创建一个带时间戳的冲突副本
        """
        abs_path = self._absolute_path(rel_path)
        if not abs_path.exists():
            return None

        timestamp_str = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
        stem = abs_path.stem
        suffix = abs_path.suffix
        conflict_name = f"{stem} - Conflict {timestamp_str}{suffix}{self.CONFLICT_SUFFIX}"
        conflict_path = abs_path.parent / conflict_name

        try:
            shutil.copy2(abs_path, conflict_path)
            conflict_rel = self._relative_path(conflict_path)
            logger.info(f"Created conflict copy: {conflict_rel}")
            return conflict_rel
        except (OSError, PermissionError) as e:
            logger.error(f"Create conflict copy failed: {e}")
            return None

    # ─── 增量同步核心（参考 better-sync syncHandler）───────────

    def perform_incremental_sync(self, mobile_switch: bool = False) -> Tuple[List[SyncChange], SyncStatus]:
        """
        执行增量同步（参考 better-sync syncHandler + siyuan-android syncData）
        
        流程：
        1. 检查同步锁（参考 siyuan-android syncing 互斥）
        2. 扫描变更
        3. 检测冲突（参考 better-sync detectConflict）
        4. 创建冲突副本（参考 better-sync createConflictFile）
        5. 更新索引
        6. 记录同步历史（参考 better-sync SyncHistory）
        
        Args:
            mobile_switch: 是否来自移动端切换（参考 siyuan-android mobileSwitch）
        
        Returns:
            (changes, status) 变更列表和同步状态
        """
        start_time = time.time()

        # 0. 冷却检查：避免移动端频繁触发同步
        now = time.time()
        if mobile_switch and (now - self._last_sync_attempt_time) < self._min_sync_interval:
            logger.info(f"Sync cooldown: {now - self._last_sync_attempt_time:.1f}s < {self._min_sync_interval}s, skipping")
            return [], SyncStatus.None_
        self._last_sync_attempt_time = now

        # 1. 检查同步锁
        if not self.acquire_sync_lock():
            logger.info("Sync already in progress, skipping")
            return [], SyncStatus.InProgress

        conflict_count = 0
        deleted_count = 0
        changes: List[SyncChange] = []

        try:
            # 2. 扫描变更
            current_paths = set()
            target = self.workspace_dir
            if target.exists():
                for item in target.rglob("*"):
                    if self._should_ignore(item):
                        continue
                    rel_path = self._relative_path(item)
                    current_paths.add(rel_path)

                    if item.is_dir():
                        continue

                    try:
                        stat = item.stat()
                        new_hash = self._compute_hash(item)
                        old_entry = self._file_index.get(rel_path)

                        if old_entry is None:
                            # 新文件
                            changes.append(SyncChange(
                                type="created", path=rel_path,
                                hash=new_hash, size=stat.st_size,
                                operation="Sync",
                            ))
                        elif old_entry.hash != new_hash or old_entry.modified != stat.st_mtime:
                            # 3. 冲突检测
                            if self._last_sync_time > 0 and old_entry.modified > self._last_sync_time:
                                # 服务器端文件在上次同步后被修改过，可能是冲突
                                # 参考 better-sync: HandleConflictAndSync
                                conflict_path = self.create_conflict_copy(rel_path)
                                if conflict_path:
                                    conflict_count += 1
                                    changes.append(SyncChange(
                                        type="conflict", path=rel_path,
                                        hash=new_hash, size=stat.st_size,
                                        operation="HandleConflictAndSync",
                                        conflict_path=conflict_path,
                                    ))
                                else:
                                    changes.append(SyncChange(
                                        type="modified", path=rel_path,
                                        hash=new_hash, size=stat.st_size,
                                        operation="Sync",
                                    ))
                            else:
                                changes.append(SyncChange(
                                    type="modified", path=rel_path,
                                    hash=new_hash, size=stat.st_size,
                                    operation="Sync",
                                ))
                    except (OSError, PermissionError):
                        continue

                # 检测删除
                for path in list(self._file_index.keys()):
                    if path not in current_paths:
                        changes.append(SyncChange(
                            type="deleted", path=path,
                            operation="Delete",
                        ))
                        deleted_count += 1
                        del self._file_index[path]

            # 4. 更新索引
            self.scan_file_tree()

            # 5. 确定同步状态
            if conflict_count > 0:
                status = SyncStatus.DoneWithConflict
            else:
                status = SyncStatus.Done

            self._sync_status = status

            # 6. 记录同步历史
            duration = time.time() - start_time
            history_entry = SyncHistoryEntry(
                timestamp=time.time(),
                status=status.name,
                synced_count=len(changes),
                conflict_count=conflict_count,
                deleted_count=deleted_count,
                duration=duration,
                changes=[{"type": c.type, "path": c.path, "operation": c.operation} for c in changes],
            )
            self.add_sync_history(history_entry)

            logger.info(f"Incremental sync completed: {len(changes)} changes, {conflict_count} conflicts, {duration:.1f}s")

            return changes, status

        except Exception as e:
            self._sync_status = SyncStatus.Failed
            logger.error(f"Incremental sync failed: {e}")
            return changes, SyncStatus.Failed

        finally:
            self.release_sync_lock()

    def set_change_callback(self, callback):
        """设置文件变更回调（用于通知 WebSocket）"""
        self._on_change_callback = callback
        # 在设置回调时捕获主事件循环
        if self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def _fire_change_event(self, event):
        """触发变更事件，兼容主线程和线程池调用"""
        if not self._on_change_callback:
            return
        loop = self._main_loop or asyncio.get_event_loop()
        try:
            asyncio.get_running_loop()
            # 已在事件循环中，直接 create_task
            asyncio.create_task(self._on_change_callback(event))
        except RuntimeError:
            # 不在事件循环中（线程池），用 run_coroutine_threadsafe
            asyncio.run_coroutine_threadsafe(self._on_change_callback(event), loop)

    def _should_ignore(self, path: Path) -> bool:
        """检查路径是否应该被忽略"""
        parts = path.parts
        for part in parts:
            if part in self.IGNORE_PATTERNS:
                return True
            for pattern in self.IGNORE_PATTERNS:
                if "*" in pattern:
                    import fnmatch
                    if fnmatch.fnmatch(part, pattern):
                        return True
        return False

    def _is_exposed(self, rel_path: str) -> bool:
        """检查路径是否在暴露范围内"""
        if not self.EXPOSED_DIRS:
            return True
        # 根目录下的特定文件
        if "/" not in rel_path:
            if rel_path in self.EXPOSED_DIRS:
                return True
            if rel_path in self.EXPOSED_ROOT_FILES:
                return True
            return False
        # 子路径：检查顶级目录是否在 EXPOSED_DIRS 中
        top_dir = rel_path.split("/")[0]
        return top_dir in self.EXPOSED_DIRS

    def _relative_path(self, abs_path: Path) -> str:
        """获取相对路径"""
        try:
            return str(abs_path.relative_to(self.workspace_dir)).replace("\\", "/")
        except ValueError:
            return str(abs_path).replace("\\", "/")

    def _absolute_path(self, rel_path: str) -> Path:
        """获取绝对路径。如果 rel_path 本身是绝对路径（资源索引场景），直接返回。"""
        p = Path(rel_path)
        if p.is_absolute():
            return p.resolve()
        # 安全检查：防止路径遍历
        abs_path = (self.workspace_dir / rel_path).resolve()
        try:
            abs_path.relative_to(self.workspace_dir)
        except ValueError:
            raise ValueError(f"Path traversal detected: {rel_path}")
        return abs_path

    def _compute_hash(self, file_path: Path) -> str:
        """计算文件 MD5 hash"""
        try:
            h = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def scan_file_tree(self, subdir: str = "", compute_hash: bool = False) -> List[FileEntry]:
        """扫描文件树（仅暴露允许的目录）"""
        target = self.workspace_dir / subdir if subdir else self.workspace_dir
        if not target.exists():
            return []

        entries = []
        try:
            for item in sorted(target.rglob("*")):
                if self._should_ignore(item):
                    continue
                rel_path = self._relative_path(item)
                if not self._is_exposed(rel_path):
                    continue
                entry = FileEntry(
                    path=rel_path,
                    name=item.name,
                    is_dir=item.is_dir(),
                    ext=item.suffix.lower() if item.suffix else "",
                )
                if not item.is_dir():
                    try:
                        stat = item.stat()
                        entry.size = stat.st_size
                        entry.modified = stat.st_mtime
                        if compute_hash:
                            entry.hash = self._compute_hash(item)
                    except (OSError, PermissionError):
                        continue
                entries.append(entry)
        except (OSError, PermissionError) as e:
            logger.warning(f"Scan error: {e}")

        # 更新索引
        for entry in entries:
            self._file_index[entry.path] = entry
        self._last_scan_time = time.time()

        return entries

    def read_dir(self, rel_path: str = "") -> List[FileEntry]:
        """读取目录内容（仅一层，仅暴露允许的目录）"""
        target = self.workspace_dir / rel_path if rel_path else self.workspace_dir
        if not target.exists() or not target.is_dir():
            return []

        entries = []
        try:
            for item in sorted(target.iterdir()):
                if self._should_ignore(item):
                    continue
                rel = self._relative_path(item)
                if not self._is_exposed(rel):
                    continue
                entry = FileEntry(
                    path=rel,
                    name=item.name,
                    is_dir=item.is_dir(),
                    ext=item.suffix.lower() if item.suffix else "",
                )
                if not item.is_dir():
                    try:
                        stat = item.stat()
                        entry.size = stat.st_size
                        entry.modified = stat.st_mtime
                    except (OSError, PermissionError):
                        continue
                entries.append(entry)
        except (OSError, PermissionError) as e:
            logger.warning(f"Read dir error: {e}")

        return entries

    def get_file(self, rel_path: str) -> Optional[Tuple[str, FileEntry]]:
        """获取文件内容和元信息（仅暴露允许的路径）"""
        if not self._is_exposed(rel_path):
            return None
        abs_path = self._absolute_path(rel_path)
        if not abs_path.exists() or abs_path.is_dir():
            return None

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
            stat = abs_path.stat()
            entry = FileEntry(
                path=rel_path,
                name=abs_path.name,
                is_dir=False,
                size=stat.st_size,
                modified=stat.st_mtime,
                hash=self._compute_hash(abs_path),
                ext=abs_path.suffix.lower(),
            )
            return content, entry
        except (OSError, PermissionError) as e:
            logger.debug(f"Read file error: {e}")
            return None

    def put_file(self, rel_path: str, content: str) -> Optional[FileEntry]:
        """写入文件（仅允许写入暴露范围内的路径）"""
        if not self._is_exposed(rel_path):
            logger.warning(f"Write blocked (not exposed): {rel_path}")
            return None
        abs_path = self._absolute_path(rel_path)

        # 确保父目录存在
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            is_new = not abs_path.exists()
            abs_path.write_text(content, encoding="utf-8")
            stat = abs_path.stat()
            entry = FileEntry(
                path=rel_path,
                name=abs_path.name,
                is_dir=False,
                size=stat.st_size,
                modified=stat.st_mtime,
                hash=self._compute_hash(abs_path),
                ext=abs_path.suffix.lower(),
            )
            self._file_index[rel_path] = entry

            # 触发变更通知
            if self._on_change_callback:
                event = SyncEvent(
                    event_type="created" if is_new else "modified",
                    path=rel_path,
                    timestamp=time.time(),
                    hash=entry.hash,
                    size=entry.size,
                )
                self._fire_change_event(event)

            return entry
        except (OSError, PermissionError) as e:
            logger.error(f"Write file error: {e}")
            return None

    def remove_file(self, rel_path: str) -> bool:
        """删除文件"""
        abs_path = self._absolute_path(rel_path)
        if not abs_path.exists():
            return False

        try:
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
            else:
                abs_path.unlink()

            self._file_index.pop(rel_path, None)

            if self._on_change_callback:
                event = SyncEvent(
                    event_type="deleted",
                    path=rel_path,
                    timestamp=time.time(),
                )
                self._fire_change_event(event)

            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Remove file error: {e}")
            return False

    def rename_file(self, old_path: str, new_path: str) -> bool:
        """重命名/移动文件"""
        old_abs = self._absolute_path(old_path)
        new_abs = self._absolute_path(new_path)

        if not old_abs.exists():
            return False

        # 确保目标父目录存在
        new_abs.parent.mkdir(parents=True, exist_ok=True)

        try:
            old_abs.rename(new_abs)

            # 更新索引
            self._file_index.pop(old_path, None)
            stat = new_abs.stat()
            entry = FileEntry(
                path=new_path,
                name=new_abs.name,
                is_dir=new_abs.is_dir(),
                size=stat.st_size if not new_abs.is_dir() else 0,
                modified=stat.st_mtime,
                ext=new_abs.suffix.lower() if new_abs.suffix else "",
            )
            self._file_index[new_path] = entry

            if self._on_change_callback:
                event = SyncEvent(
                    event_type="renamed",
                    path=new_path,
                    old_path=old_path,
                    timestamp=time.time(),
                )
                self._fire_change_event(event)

            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Rename file error: {e}")
            return False

    def create_dir(self, rel_path: str) -> bool:
        """创建目录"""
        abs_path = self._absolute_path(rel_path)
        try:
            abs_path.mkdir(parents=True, exist_ok=True)
            if self._on_change_callback:
                event = SyncEvent(
                    event_type="created",
                    path=rel_path,
                    timestamp=time.time(),
                )
                self._fire_change_event(event)
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Create dir error: {e}")
            return False

    def search_files(self, query: str, subdir: str = "") -> List[FileEntry]:
        """搜索文件（按名称匹配）"""
        query_lower = query.lower()
        results = []
        entries = self.scan_file_tree(subdir)
        for entry in entries:
            if query_lower in entry.name.lower() or query_lower in entry.path.lower():
                results.append(entry)
        return results

    def get_file_stats(self) -> dict:
        """获取文件统计信息"""
        total_files = 0
        total_dirs = 0
        total_size = 0
        extensions: Dict[str, int] = {}

        for entry in self._file_index.values():
            if entry.is_dir:
                total_dirs += 1
            else:
                total_files += 1
                total_size += entry.size
                ext = entry.ext or "other"
                extensions[ext] = extensions.get(ext, 0) + 1

        return {
            "total_files": total_files,
            "total_dirs": total_dirs,
            "total_size": total_size,
            "total_size_human": self._human_size(total_size),
            "extensions": extensions,
            "last_scan": self._last_scan_time,
        }

    @staticmethod
    def _human_size(size: int) -> str:
        """人类可读的文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    async def start_watching(self, interval: float = 2.0):
        """启动文件变更监听"""
        if self._watching:
            return
        self._watching = True
        self._watch_task = asyncio.create_task(self._watch_loop(interval))
        logger.info(f"File watching started for {self.workspace_dir}")

    async def stop_watching(self):
        """停止文件变更监听"""
        self._watching = False
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        logger.info("File watching stopped")

    async def _watch_loop(self, interval: float):
        """文件变更监听循环"""
        while self._watching:
            try:
                await self._detect_changes()
            except Exception as e:
                logger.error(f"Watch loop error: {e}")
            await asyncio.sleep(interval)

    async def _detect_changes(self):
        """检测文件变更"""
        changes = []
        current_paths = set()

        target = self.workspace_dir
        if not target.exists():
            return

        for item in target.rglob("*"):
            if self._should_ignore(item):
                continue
            rel_path = self._relative_path(item)
            current_paths.add(rel_path)

            if item.is_dir():
                continue

            try:
                stat = item.stat()
                new_hash = self._compute_hash(item)
                old_entry = self._file_index.get(rel_path)

                if old_entry is None:
                    # 新文件
                    changes.append(SyncEvent(
                        event_type="created",
                        path=rel_path,
                        timestamp=time.time(),
                        hash=new_hash,
                        size=stat.st_size,
                    ))
                elif old_entry.hash != new_hash or old_entry.modified != stat.st_mtime:
                    # 修改的文件
                    changes.append(SyncEvent(
                        event_type="modified",
                        path=rel_path,
                        timestamp=time.time(),
                        hash=new_hash,
                        size=stat.st_size,
                    ))
            except (OSError, PermissionError):
                continue

        # 检测删除的文件
        for path in list(self._file_index.keys()):
            if path not in current_paths:
                changes.append(SyncEvent(
                    event_type="deleted",
                    path=path,
                    timestamp=time.time(),
                ))
                del self._file_index[path]

        # 通知变更
        if changes and self._on_change_callback:
            for event in changes:
                await self._on_change_callback(event)
