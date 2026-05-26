#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上下文重载器 — 参考 Cline ContextManager 设计
会话检查点、增量恢复、上下文历史追踪
"""

import time
import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from .disk import get_disk_store

logger = logging.getLogger(__name__)


@dataclass
class ContextUpdate:
    timestamp: float
    update_type: str  # "text", "tool_call", "tool_result", "reasoning"
    data: Any
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "update_type": self.update_type,
            "data": self.data,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ContextUpdate":
        return cls(
            timestamp=d.get("timestamp", 0),
            update_type=d.get("update_type", "text"),
            data=d.get("data", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass
class ContextCheckpoint:
    checkpoint_id: str
    timestamp: float
    message_index: int
    total_messages: int
    total_tokens: int
    summary: str = ""
    messages_snapshot: List[Dict] = field(default_factory=list)
    context_updates: List[ContextUpdate] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "message_index": self.message_index,
            "total_messages": self.total_messages,
            "total_tokens": self.total_tokens,
            "summary": self.summary,
            "messages_snapshot": self.messages_snapshot,
            "context_updates": [u.to_dict() for u in self.context_updates],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ContextCheckpoint":
        return cls(
            checkpoint_id=d.get("checkpoint_id", ""),
            timestamp=d.get("timestamp", 0),
            message_index=d.get("message_index", 0),
            total_messages=d.get("total_messages", 0),
            total_tokens=d.get("total_tokens", 0),
            summary=d.get("summary", ""),
            messages_snapshot=d.get("messages_snapshot", []),
            context_updates=[
                ContextUpdate.from_dict(u) for u in d.get("context_updates", [])
            ],
        )


@dataclass
class ConversationSnapshot:
    conversation_id: str
    title: str
    created_at: str
    last_checkpoint_id: str = ""
    total_rounds: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "created_at": self.created_at,
            "last_checkpoint_id": self.last_checkpoint_id,
            "total_rounds": self.total_rounds,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_cost": self.total_cost,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ConversationSnapshot":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ContextReloader:
    """
    上下文重载器 — 类似 Cline ContextManager

    功能：
    - 创建/恢复检查点
    - 增量上下文更新
    - 会话快照管理
    - checkpoint 持久化
    """

    def __init__(self):
        self._disk = get_disk_store()
        self._active_checkpoints: Dict[str, ContextCheckpoint] = {}
        self._pending_updates: Dict[int, Dict[int, List[ContextUpdate]]] = {}
        self._conversation_snapshots: Dict[str, ConversationSnapshot] = {}
        self._lock = __import__("threading").RLock()

    def create_checkpoint(
        self,
        messages: List[Dict],
        message_index: int = 0,
        total_tokens: int = 0,
        summary: str = "",
    ) -> ContextCheckpoint:
        cid = f"cp-{int(time.time() * 1000)}"
        checkpoint = ContextCheckpoint(
            checkpoint_id=cid,
            timestamp=time.time(),
            message_index=message_index,
            total_messages=len(messages),
            total_tokens=total_tokens,
            summary=summary,
            messages_snapshot=deepcopy(messages),
        )
        self._active_checkpoints[cid] = checkpoint
        return checkpoint

    def restore_checkpoint(
        self, checkpoint_id: str
    ) -> Optional[ContextCheckpoint]:
        checkpoint = self._active_checkpoints.get(checkpoint_id)
        if checkpoint:
            logger.info(f"恢复检查点: {checkpoint_id} (消息索引={checkpoint.message_index})")
            return checkpoint

        data = self._disk.checkpoint_store.get(checkpoint_id)
        if data:
            checkpoint = ContextCheckpoint.from_dict(data)
            self._active_checkpoints[checkpoint_id] = checkpoint
            logger.info(f"从磁盘恢复检查点: {checkpoint_id}")
            return checkpoint

        logger.warning(f"检查点不存在: {checkpoint_id}")
        return None

    def save_checkpoint(self, checkpoint: ContextCheckpoint):
        self._active_checkpoints[checkpoint.checkpoint_id] = checkpoint
        self._disk.checkpoint_store.set(
            checkpoint.checkpoint_id, checkpoint.to_dict()
        )

    def delete_checkpoint(self, checkpoint_id: str):
        self._active_checkpoints.pop(checkpoint_id, None)
        self._disk.checkpoint_store.delete(checkpoint_id)

    def list_checkpoints(self) -> List[str]:
        disk_keys = self._disk.checkpoint_store.list_keys()
        all_keys = set(disk_keys) | set(self._active_checkpoints.keys())
        return sorted(all_keys, reverse=True)

    def add_context_update(
        self,
        message_index: int,
        block_index: int,
        update: ContextUpdate,
    ):
        if message_index not in self._pending_updates:
            self._pending_updates[message_index] = {}
        if block_index not in self._pending_updates[message_index]:
            self._pending_updates[message_index][block_index] = []
        self._pending_updates[message_index][block_index].append(update)

    def get_context_updates(
        self, message_index: int, block_index: int
    ) -> List[ContextUpdate]:
        return self._pending_updates.get(message_index, {}).get(block_index, [])

    def get_latest_update(
        self, message_index: int, block_index: int
    ) -> Optional[ContextUpdate]:
        updates = self.get_context_updates(message_index, block_index)
        return updates[-1] if updates else None

    def truncate_updates(self, max_timestamp: float):
        for msg_idx, blocks in list(self._pending_updates.items()):
            for blk_idx, updates in list(blocks.items()):
                cutoff = 0
                while cutoff < len(updates) and updates[cutoff].timestamp <= max_timestamp:
                    cutoff += 1
                if cutoff < len(updates):
                    updates[:] = updates[:cutoff]
                if not updates:
                    del blocks[blk_idx]
            if not blocks:
                del self._pending_updates[msg_idx]

    def create_conversation_snapshot(
        self,
        conversation_id: str,
        title: str = "",
        checkpoint_id: str = "",
    ) -> ConversationSnapshot:
        snapshot = ConversationSnapshot(
            conversation_id=conversation_id,
            title=title,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            last_checkpoint_id=checkpoint_id,
        )
        self._conversation_snapshots[conversation_id] = snapshot
        return snapshot

    def update_conversation_snapshot(
        self, conversation_id: str, **kwargs
    ):
        if conversation_id in self._conversation_snapshots:
            for key, value in kwargs.items():
                if hasattr(self._conversation_snapshots[conversation_id], key):
                    setattr(self._conversation_snapshots[conversation_id], key, value)

    def get_conversation_snapshot(
        self, conversation_id: str
    ) -> Optional[ConversationSnapshot]:
        return self._conversation_snapshots.get(conversation_id)

    def rollback_to_checkpoint(
        self, checkpoint_id: str
    ) -> Optional[List[Dict]]:
        checkpoint = self.restore_checkpoint(checkpoint_id)
        if checkpoint is None:
            return None

        max_ts = checkpoint.timestamp
        self.truncate_updates(max_ts)

        return deepcopy(checkpoint.messages_snapshot)

    def clear(self):
        self._active_checkpoints.clear()
        self._pending_updates.clear()
        self._conversation_snapshots.clear()