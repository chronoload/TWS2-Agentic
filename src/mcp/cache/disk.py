#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
磁盘持久化层 — 参考 Cline 的 disk.ts (StorageContext)
JSON 文件存储、KeyValue 存储、原子写入
"""

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional


class AtomicWriter:
    """原子写入：先写临时文件，再 replace"""

    @staticmethod
    def write(path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=path.name + ".",
            dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def read(path: Path) -> Optional[str]:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")


class JSONFileStore:
    """JSON 文件存储 — 线程安全，支持旧位置回退读取"""

    _legacy_base_dirs = None

    @classmethod
    def _get_legacy_dirs(cls):
        if cls._legacy_base_dirs is None:
            cls._legacy_base_dirs = []
            try:
                import sys
                if getattr(sys, 'frozen', False):
                    base = Path(sys.executable).parent
                else:
                    base = Path(__file__).resolve().parent.parent.parent
                for candidate in [base / "cache_data", base / "mcp" / "cache_data"]:
                    if candidate.exists():
                        cls._legacy_base_dirs.append(candidate)
            except Exception:
                pass
        return cls._legacy_base_dirs

    def __init__(self, file_path: Path):
        self._file_path = file_path
        self._resolved_path = self._resolve_path()
        self._lock = threading.RLock()
        self._cache: Dict[str, Any] = {}
        self._loaded = False

    def _resolve_path(self) -> Path:
        """查找文件路径，优先原位置，回退旧位置"""
        if self._file_path.exists():
            return self._file_path
        filename = self._file_path.name
        for legacy_dir in self._get_legacy_dirs():
            legacy_path = legacy_dir / filename
            if legacy_path.exists():
                return legacy_path
        return self._file_path

    def _ensure_loaded(self):
        if self._loaded:
            return
        content = AtomicWriter.read(self._resolved_path)
        if content:
            try:
                self._cache = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                self._cache = {}
        self._loaded = True

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._ensure_loaded()
            return self._cache.get(key, default)

    def set(self, key: str, value: Any):
        with self._lock:
            self._ensure_loaded()
            self._cache[key] = value
            self._persist()

    def set_batch(self, updates: Dict[str, Any]):
        with self._lock:
            self._ensure_loaded()
            self._cache.update(updates)
            self._persist()

    def delete(self, key: str):
        with self._lock:
            self._ensure_loaded()
            self._cache.pop(key, None)
            self._persist()

    def all(self) -> Dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            return dict(self._cache)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._persist()

    def _persist(self):
        content = json.dumps(self._cache, ensure_ascii=False, indent=2)
        AtomicWriter.write(self._file_path, content)

    def reload(self):
        with self._lock:
            self._loaded = False
            self._ensure_loaded()


class KeyValueStore:
    """多文件 KeyValue 存储 — 每个 key 一个 JSON 文件，支持旧位置回退"""

    _legacy_kv_dirs = None

    @classmethod
    def _get_legacy_kv_dirs(cls):
        if cls._legacy_kv_dirs is None:
            cls._legacy_kv_dirs = []
            try:
                import sys
                if getattr(sys, 'frozen', False):
                    base = Path(sys.executable).parent
                else:
                    base = Path(__file__).resolve().parent.parent.parent
                for candidate in [base / "cache_data", base / "mcp" / "cache_data"]:
                    if candidate.exists():
                        cls._legacy_kv_dirs.append(candidate)
            except Exception:
                pass
        return cls._legacy_kv_dirs

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._subdir_name = base_dir.name

    def _path_for(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in key)
        return self._base_dir / f"{safe}.json"

    def _resolve_path(self, path: Path) -> Path:
        """查找文件路径，优先原位置，回退旧位置"""
        if path.exists():
            return path
        filename = path.name
        for legacy_base in self._get_legacy_kv_dirs():
            legacy_path = legacy_base / self._subdir_name / filename
            if legacy_path.exists():
                return legacy_path
        return path

    def get(self, key: str, default: Any = None) -> Any:
        path = self._resolve_path(self._path_for(key))
        content = AtomicWriter.read(path)
        if content is None:
            return default
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return default

    def set(self, key: str, value: Any):
        path = self._path_for(key)
        content = json.dumps(value, ensure_ascii=False, indent=2)
        AtomicWriter.write(path, content)

    def delete(self, key: str):
        path = self._path_for(key)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass

    def list_keys(self) -> list:
        keys = []
        for f in self._base_dir.glob("*.json"):
            name = f.stem
            keys.append(name)
        return sorted(keys)

    def clear(self):
        for f in self._base_dir.glob("*.json"):
            try:
                os.unlink(f)
            except OSError:
                pass


class DiskStore:
    """统一磁盘存储 — 管理多个存储后端"""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

        self.global_state = JSONFileStore(base_dir / "global_state.json")
        self.workspace_state = JSONFileStore(base_dir / "workspace_state.json")
        self.secrets = JSONFileStore(base_dir / "secrets.json")
        self.model_cache_store = JSONFileStore(base_dir / "model_cache.json")
        self.ui_state_store = JSONFileStore(base_dir / "ui_state.json")
        self.session_store = KeyValueStore(base_dir / "sessions")
        self.checkpoint_store = KeyValueStore(base_dir / "checkpoints")
        self.settings = JSONFileStore(base_dir / "settings.json")

    def flush_all(self):
        for store in [
            self.global_state, self.workspace_state, self.secrets,
            self.model_cache_store, self.ui_state_store, self.settings,
        ]:
            store._persist()


_disk_store: Optional[DiskStore] = None


def get_disk_store(base_dir: Optional[Path] = None) -> DiskStore:
    global _disk_store
    if _disk_store is None:
        if base_dir is None:
            base_dir = Path.home() / ".ts2" / "cache_data"
        _disk_store = DiskStore(base_dir)
    return _disk_store