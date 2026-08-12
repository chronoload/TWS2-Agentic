from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentRole(str, Enum):
    CODER = "coder"
    TASK = "task"
    RESEARCH = "research"
    REVIEW = "review"
    SABER_ADVISOR = "saber_advisor"
    CUSTOM = "custom"


class SubAgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentConfig:
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = "inherit"
    max_turns: int = 20
    timeout_seconds: int = 1800
    allowed_tools: Optional[List[str]] = None
    disallowed_tools: Optional[List[str]] = None
    skills: Optional[List[str]] = None


@dataclass
class AgentSpec:
    role: AgentRole
    name: str
    system_prompt: str = ""
    model: str = ""
    max_turns: int = 20
    timeout_seconds: int = 1800
    allowed_tools: Optional[List[str]] = None
    denied_tools: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubAgentResult:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = ""
    role: AgentRole = AgentRole.CUSTOM
    status: SubAgentStatus = SubAgentStatus.PENDING
    content: str = ""
    reasoning_content: str = ""
    tool_calls_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    # 新增：子代理的完整历史消息，用于持久化和回退
    messages: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at) * 1000)
        return 0

    def mark_started(self):
        self.status = SubAgentStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self, content: str = "", messages: List[Dict[str, Any]] = None, **kwargs):
        self.status = SubAgentStatus.COMPLETED
        self.content = content
        if messages is not None:
            self.messages = messages
        self.completed_at = time.time()
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def mark_failed(self, error: str, messages: List[Dict[str, Any]] = None):
        self.status = SubAgentStatus.FAILED
        self.error = error
        if messages is not None:
            self.messages = messages
        self.completed_at = time.time()

    def mark_cancelled(self, messages: List[Dict[str, Any]] = None):
        self.status = SubAgentStatus.CANCELLED
        if messages is not None:
            self.messages = messages
        self.completed_at = time.time()
