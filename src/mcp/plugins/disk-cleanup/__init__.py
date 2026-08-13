import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

_recent_test_tracks: Dict[str, Set[str]] = {}
_lock = threading.Lock()

_TEMP_PATTERNS = [
    re.compile(r"(?:test_|_test\.|temp_|tmp_)", re.IGNORECASE),
    re.compile(r"\.(log|tmp|bak|swp)$", re.IGNORECASE),
    re.compile(r"__pycache__", re.IGNORECASE),
]

_SAFE_EXTENSIONS = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".csv", ".log", ".tmp", ".bak"}


def guess_category(path: Path) -> Optional[str]:
    name = path.name
    for pattern in _TEMP_PATTERNS:
        if pattern.search(name):
            return "test"
    if path.suffix in (".log", ".tmp", ".bak", ".swp"):
        return "temp"
    return None


def is_safe_path(path: Path, base_dir: Path) -> bool:
    try:
        path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        return False
    return True


def track(path_str: str, category: str, *, silent: bool = False) -> bool:
    return True


def quick_cleanup(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    summary = {"deleted": 0, "empty_dirs": 0, "freed": 0, "errors": []}
    if base_dir is None:
        return summary

    try:
        for item in base_dir.rglob("__pycache__"):
            if item.is_dir():
                import shutil
                shutil.rmtree(item, ignore_errors=True)
                summary["deleted"] += 1

        for item in base_dir.rglob("*.pyc"):
            try:
                size = item.stat().st_size
                item.unlink()
                summary["deleted"] += 1
                summary["freed"] += size
            except Exception:
                pass

        for item in base_dir.rglob("*.tmp"):
            try:
                size = item.stat().st_size
                item.unlink()
                summary["deleted"] += 1
                summary["freed"] += size
            except Exception:
                pass

    except Exception as e:
        summary["errors"].append(str(e))

    return summary


def _tracker_key(task_id: str, session_id: str) -> str:
    return task_id or session_id or "default"


def _record_track(task_id: str, session_id: str, path: Path, category: str) -> None:
    if category != "test":
        return
    key = _tracker_key(task_id, session_id)
    with _lock:
        _recent_test_tracks.setdefault(key, set()).add(str(path))


def _drain(task_id: str, session_id: str) -> Set[str]:
    key = _tracker_key(task_id, session_id)
    with _lock:
        return _recent_test_tracks.pop(key, set())


def _on_post_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    **_: Any,
) -> None:
    if not isinstance(args, dict):
        return

    if tool_name == "write_file":
        path_str = args.get("path", "")
        if path_str:
            try:
                p = Path(path_str)
                category = guess_category(p)
                if category:
                    _record_track(task_id, session_id, p, category)
            except Exception:
                pass


def _on_session_end(
    session_id: str = "",
    completed: bool = True,
    interrupted: bool = False,
    **_: Any,
) -> None:
    drained = _drain("", session_id)
    if not drained:
        return
    logger.info(f"disk-cleanup: session {session_id} tracked {len(drained)} test files")


def register(ctx) -> None:
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("on_session_end", _on_session_end)
    logger.info("disk-cleanup plugin registered")
