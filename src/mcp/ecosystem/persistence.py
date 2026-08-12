"""
生态系统持久化 —— save/load 到 JSON 文件。

使用 TS2 的 AtomicWriter 确保崩溃安全写入。
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import asdict

from .models import (
    EcosystemState, Concept, ResearchThread, Artifact,
    ActionRecord, Observation, PlayerState, SourceRef,
)

logger = logging.getLogger(__name__)

_DEFAULT_FILENAME = "ecosystem_state.json"


def _encode(obj: Any) -> Any:
    """JSON 编码辅助——处理 dataclass → dict，set → list"""
    if isinstance(obj, set):
        return list(obj)
    if hasattr(obj, '__dataclass_fields__'):
        return asdict(obj)
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


def _decode_concept(d: dict) -> Concept:
    kw = dict(d)
    kw['source_refs'] = [SourceRef(**s) for s in kw.get('source_refs', [])]
    return Concept(**kw)


def _decode_thread(d: dict) -> ResearchThread:
    return ResearchThread(**d)


def _decode_artifact(d: dict) -> Artifact:
    return Artifact(**d)


def _decode_action(d: dict) -> ActionRecord:
    return ActionRecord(**d)


def _decode_observation(d: dict) -> Observation:
    return Observation(**d)


def _decode_player(d: dict) -> PlayerState:
    return PlayerState(**d)


def _decode_ecosystem_state(d: dict) -> EcosystemState:
    kw = dict(d)
    kw['concepts'] = {k: _decode_concept(v) for k, v in d.get('concepts', {}).items()}
    kw['threads'] = {k: _decode_thread(v) for k, v in d.get('threads', {}).items()}
    kw['artifacts'] = {k: _decode_artifact(v) for k, v in d.get('artifacts', {}).items()}
    kw['actions'] = [_decode_action(a) for a in d.get('actions', [])]
    kw['observations'] = [_decode_observation(o) for o in d.get('observations', [])]
    kw['player'] = _decode_player(d.get('player', {}))
    # parsed_notes 序列化为 list，反序列化为 set
    if 'parsed_notes' in d and isinstance(d['parsed_notes'], list):
        kw['parsed_notes'] = set(d['parsed_notes'])
    del kw['version']
    del kw['saved_at']
    return EcosystemState(**kw)


def save(state: EcosystemState, path: Optional[Path] = None) -> Path:
    """
    将生态系统状态保存到 JSON 文件。

    Args:
        state: 要保存的 EcosystemState
        path: 保存路径（默认 ~/.ts2/cache_data/ecosystem_state.json）

    Returns:
        写入的文件路径
    """
    if path is None:
        path = Path.home() / ".ts2" / "cache_data" / _DEFAULT_FILENAME

    state.version = 3
    state.saved_at = __import__('time').time()

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from mcp.cache.disk import AtomicWriter
    except ImportError:
        json_str = json.dumps(asdict(state), ensure_ascii=False, indent=2, default=_encode)
        path.write_text(json_str, encoding='utf-8')
        logger.info(f"Ecosystem state saved to {path}  ({len(state.concepts)} concepts)")
        return path

    payload = json.dumps(asdict(state), ensure_ascii=False, indent=2, default=_encode)
    AtomicWriter.write(path, payload)
    logger.info(f"Ecosystem state saved (AtomicWriter) to {path}  ({len(state.concepts)} concepts)")
    return path


def load(path: Optional[Path] = None) -> Optional[EcosystemState]:
    """
    从 JSON 文件加载生态系统状态。

    Args:
        path: 加载路径（默认 ~/.ts2/cache_data/ecosystem_state.json）

    Returns:
        EcosystemState 或 None（文件不存在时）
    """
    if path is None:
        path = Path.home() / ".ts2" / "cache_data" / _DEFAULT_FILENAME

    if not path.exists():
        logger.info(f"No ecosystem state file at {path}")
        return None

    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load ecosystem state: {e}")
        return None

    state = _decode_ecosystem_state(data)
    logger.info(
        f"Ecosystem state loaded from {path}: "
        f"{len(state.concepts)} concepts, {len(state.threads)} threads, "
        f"tick={state.tick}, era={state.era}"
    )
    return state


def auto_save_path() -> Path:
    """返回默认的自动保存路径"""
    return Path.home() / ".ts2" / "cache_data" / _DEFAULT_FILENAME
