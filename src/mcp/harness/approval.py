import time
import uuid
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


class ApprovalDecision(Enum):
    APPROVE = "approve"
    DENY = "deny"
    ALWAYS_APPROVE = "always_approve"


class ApprovalMode(Enum):
    SUGGEST = "suggest"
    AUTO_EDIT = "auto_edit"
    FULL_AUTO = "full_auto"


@dataclass
class ApprovalRequest:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    tool_name: str = ""
    tool_input: Dict = field(default_factory=dict)
    reason: str = ""
    risk_level: str = "medium"
    created_at: float = field(default_factory=time.time)
    _decision: Optional[ApprovalDecision] = None
    _event: threading.Event = field(default_factory=threading.Event)

    def decide(self, decision: ApprovalDecision):
        self._decision = decision
        self._event.set()

    def wait(self, timeout: float = 300) -> bool:
        return self._event.wait(timeout=timeout)

    @property
    def decided(self) -> bool:
        return self._decision is not None


class ApprovalManager:
    def __init__(self, mode: ApprovalMode = ApprovalMode.SUGGEST):
        self._mode = mode
        self._always_approved: set = set()
        self._always_denied: set = set()
        self._pending: Dict[str, ApprovalRequest] = {}
        self._callbacks: List[Callable] = []
        self._lock = threading.Lock()

    def on_request(self, callback: Callable):
        self._callbacks.append(callback)

    def request_approval(
        self,
        tool_name: str,
        tool_input: Dict,
        reason: str = "",
        risk_level: str = "medium",
    ) -> ApprovalDecision:
        if tool_name in self._always_approved:
            return ApprovalDecision.APPROVE
        if tool_name in self._always_denied:
            return ApprovalDecision.DENY
        if self._mode == ApprovalMode.FULL_AUTO:
            return ApprovalDecision.APPROVE
        request = ApprovalRequest(
            tool_name=tool_name,
            tool_input=tool_input,
            reason=reason,
            risk_level=risk_level,
        )
        with self._lock:
            self._pending[request.id] = request
        for callback in self._callbacks:
            try:
                callback(request)
            except Exception:
                pass
        request.wait(timeout=300)
        with self._lock:
            self._pending.pop(request.id, None)
        if request._decision is None:
            return ApprovalDecision.DENY
        if request._decision == ApprovalDecision.ALWAYS_APPROVE:
            self._always_approved.add(tool_name)
            return ApprovalDecision.APPROVE
        return request._decision

    def decide(self, request_id: str, decision: ApprovalDecision):
        with self._lock:
            request = self._pending.get(request_id)
        if request:
            request.decide(decision)

    def get_pending(self) -> List[ApprovalRequest]:
        with self._lock:
            return list(self._pending.values())

    def reset_permissions(self):
        self._always_approved.clear()
        self._always_denied.clear()
