# -*- coding: utf-8 -*-
"""轻量 NDJSON 事件流。

T4 事件化：skill.registry.changed / context.compacted 等结构化事件以 NDJSON
追加落盘，每行一个事件，便于审计与重放。

行格式:
    {"ts": "2026-08-11T19:00:00", "event": "skill.registry.changed", "data": {...}}
"""
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

_lock = threading.Lock()
_default_path: Optional[Path] = None


def set_events_path(path: Path) -> None:
    """设置全局默认事件文件路径（供宿主程序注入）。"""
    global _default_path
    _default_path = Path(path)


def emit(event: str, data: Dict[str, Any], path: Optional[Path] = None) -> None:
    """追加一条 NDJSON 事件。

    Args:
        event: 事件名，如 "skill.registry.changed" / "context.compacted"
        data: 事件负载（必须可 JSON 序列化）
        path: 目标文件；缺省用全局默认路径或 mcp/data/events.ndjson
    """
    target = path or _default_path
    if target is None:
        target = Path(__file__).parent / "data" / "events.ndjson"
    line = json.dumps(
        {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "data": data,
        },
        ensure_ascii=False,
    )
    try:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with _lock, target.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        # 事件记录失败不应影响业务主流程
        pass
