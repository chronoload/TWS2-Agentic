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

    def __post_init__(self):
        if self.tool_input is None:
            self.tool_input = {}

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

    def remove_request_callback(self, callback: Callable):
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def set_mode(self, mode: ApprovalMode):
        with self._lock:
            self._mode = mode

    def get_mode(self) -> ApprovalMode:
        return self._mode

    def add_approved_tool(self, tool_name: str):
        with self._lock:
            self._always_approved.add(tool_name)

    def remove_approved_tool(self, tool_name: str):
        with self._lock:
            self._always_approved.discard(tool_name)

    def get_approved_tools(self) -> set:
        with self._lock:
            return set(self._always_approved)

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
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[审批请求] {tool_name} - 回调数量: {len(self._callbacks)}")
        
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            try:
                callback(request)
            except Exception as e:
                logger.error(f"审批回调执行失败: {e}")
        request.wait(timeout=300)
        with self._lock:
            self._pending.pop(request.id, None)
        if request._decision is None:
            return ApprovalDecision.DENY
        if request._decision == ApprovalDecision.ALWAYS_APPROVE:
            self._always_approved.add(tool_name)
            try:
                from ..config import get_config_manager
                config_manager = get_config_manager()
                config_manager.add_always_approved_tool(tool_name)
            except Exception:
                pass
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
        with self._lock:
            self._always_approved.clear()
            self._always_denied.clear()


_global_approval_manager: Optional[ApprovalManager] = None


def get_global_approval_manager() -> ApprovalManager:
    """获取全局共享的审批管理器实例"""
    global _global_approval_manager
    if _global_approval_manager is None:
        _global_approval_manager = ApprovalManager()
        
        try:
            from ..config import get_config_manager
            config_manager = get_config_manager()
            always_approved = config_manager.get_always_approved_tools()
            for tool in always_approved:
                _global_approval_manager._always_approved.add(tool)
            
            mode_str = config_manager.get_approval_mode()
            mode_map = {
                "suggest": ApprovalMode.SUGGEST,
                "auto_edit": ApprovalMode.AUTO_EDIT,
                "full_auto": ApprovalMode.FULL_AUTO,
            }
            _global_approval_manager._mode = mode_map.get(mode_str, ApprovalMode.SUGGEST)
        except Exception:
            pass
    
    return _global_approval_manager


def reset_global_approval_manager():
    """重置全局审批管理器"""
    global _global_approval_manager
    _global_approval_manager = None
