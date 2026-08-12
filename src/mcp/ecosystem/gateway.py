"""
TS2 → Ecosystem 事件网关

职责：
  1. 订阅 EventBus（自动化/任务/课程事件）
  2. 轮询 EventLogger（用户操作事件：文件/工具/导航）
  3. push_event() 供其他组件直接注入
  4. 分类原始事件 → EcosystemActionType
  5. 队列供 observe 算子消费

使用：
    from mcp.ecosystem import get_gateway
    gateway = get_gateway()
    gateway.start()
    events = gateway.consume_unprocessed()
"""

import logging
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set

logger = logging.getLogger(__name__)


class EcosystemActionType(str, Enum):
    """生态系统能理解的学术行动类型"""
    READING = "reading"          # 阅读（PDF、笔记、代码）
    WRITING = "writing"          # 写作（笔记、论文、文档）
    CODING = "coding"            # 编码（实验、脚本、项目）
    EXPERIMENT = "experiment"    # 实验（运行代码、测试）
    DISCUSSION = "discussion"    # 讨论（Agent 对话）
    CHECKPOINT = "checkpoint"    # 里程碑保存
    COURSE = "course"            # 课程活动
    EXPLORATION = "exploration"  # 浏览/搜索/文件树导航
    PROJECT = "project"          # 项目/任务变更
    RECORD = "record"            # 用户主动 record 输入
    SYSTEM = "system"            # 系统事件


# 文件扩展名 → 行动类型
_EXT_TO_TYPE = {
    ".pdf": EcosystemActionType.READING,
    ".md": EcosystemActionType.WRITING,
    ".rmd": EcosystemActionType.WRITING,
    ".tex": EcosystemActionType.WRITING,
    ".txt": EcosystemActionType.READING,
    ".py": EcosystemActionType.CODING,
    ".js": EcosystemActionType.CODING,
    ".ts": EcosystemActionType.CODING,
    ".rs": EcosystemActionType.CODING,
    ".go": EcosystemActionType.CODING,
    ".vue": EcosystemActionType.CODING,
    ".css": EcosystemActionType.CODING,
    ".R": EcosystemActionType.CODING,
    ".ipynb": EcosystemActionType.EXPERIMENT,
}

# 工具名 → 行动类型
_TOOL_TO_TYPE = {
    "bash": EcosystemActionType.EXPERIMENT,
    "python": EcosystemActionType.EXPERIMENT,
    "pytest": EcosystemActionType.EXPERIMENT,
    "ruff": EcosystemActionType.EXPERIMENT,
    "node": EcosystemActionType.EXPERIMENT,
    "read_file": EcosystemActionType.READING,
    "read": EcosystemActionType.READING,
    "glob": EcosystemActionType.EXPLORATION,
    "grep": EcosystemActionType.EXPLORATION,
    "web_search": EcosystemActionType.READING,
    "web_fetch": EcosystemActionType.READING,
    "edit": EcosystemActionType.WRITING,
    "write": EcosystemActionType.WRITING,
}


from .models import GatewayEvent


class EcosystemGateway:
    """
    事件网关（单例）

    数据流：
        EventBus(pub/sub) ──→ Gateway ──→ Queue ──→ observe 算子
        EventLogger(poll)  ──→ Gateway ──→ Queue ──→ observe 算子
        push_event(direct) ──→ Gateway ──→ Queue ──→ observe 算子
    """

    _instance: Optional['EcosystemGateway'] = None
    _init_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.RLock()
        self._queue: List[GatewayEvent] = []
        self._processed_ids: Set[str] = set()
        self._max_queue = 500
        self._running = False

        # EventBus 相关
        self._eventbus = None
        self._eventbus_sub_id: Optional[str] = None

        # EventLogger 相关
        self._event_logger = None
        self._last_logger_poll: str = ""  # ISO timestamp

        # 轮询线程
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_interval = 5.0

    @classmethod
    def get_instance(cls) -> 'EcosystemGateway':
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 生命周期 ──

    def start(self):
        """启动网关"""
        if self._running:
            return
        self._running = True

        self._try_subscribe_eventbus()
        self._try_connect_logger()

        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="ecosystem-gateway"
        )
        self._poll_thread.start()
        logger.info("EcosystemGateway started")

    def stop(self):
        """停止网关"""
        self._running = False
        if self._eventbus and self._eventbus_sub_id:
            try:
                self._eventbus.unsubscribe(self._eventbus_sub_id)
            except Exception:
                pass
            self._eventbus_sub_id = None
        logger.info("EcosystemGateway stopped")

    # ── 事件注入 ──

    def push_event(
        self,
        action_type: str,
        summary: str,
        detail: Optional[Dict[str, Any]] = None,
        source: str = "direct",
        source_event_id: str = "",
    ) -> str:
        """供其他组件直接注入事件"""
        if not source_event_id:
            import uuid
            source_event_id = uuid.uuid4().hex[:12]
        event = GatewayEvent(
            action_type=EcosystemActionType(action_type),
            source=source,
            source_event_id=source_event_id,
            timestamp=time.time(),
            summary=summary,
            detail=detail,
        )
        self._enqueue(event)
        return source_event_id

    def consume_unprocessed(self, limit: int = 20) -> List[GatewayEvent]:
        """返回未处理事件（被 observe 算子消费）"""
        with self._lock:
            events = self._queue[:limit]
            self._queue = self._queue[limit:]
            return events

    def unprocessed_count(self) -> int:
        with self._lock:
            return len(self._queue)

    # ── 内部 ──

    def _enqueue(self, event: GatewayEvent):
        with self._lock:
            if event.source_event_id in self._processed_ids:
                return
            self._processed_ids.add(event.source_event_id)
            self._queue.append(event)
            if len(self._queue) > self._max_queue:
                self._queue = self._queue[-self._max_queue:]

    def _try_subscribe_eventbus(self):
        try:
            from mcp.automation.event_bus import get_event_bus
            self._eventbus = get_event_bus()
            self._eventbus_sub_id = self._eventbus.subscribe(
                "automation.*", self._on_eventbus_event
            )
            self._eventbus.subscribe("course.*", self._on_eventbus_event)
            logger.info("Gateway subscribed to EventBus")
        except Exception as e:
            logger.warning(f"Gateway EventBus subscribe failed: {e}")

    def _try_connect_logger(self):
        try:
            from mcp.event_logger import EventLogger
            self._event_logger = EventLogger.get_instance()
            if self._event_logger:
                events = self._event_logger.get_recent_events(count=1)
                if events:
                    self._last_logger_poll = events[0].timestamp
                logger.info("Gateway connected to EventLogger")
        except Exception as e:
            logger.warning(f"Gateway EventLogger connect failed: {e}")

    def _poll_loop(self):
        while self._running:
            try:
                self._poll_eventbus_history()
                self._poll_eventlogger()
            except Exception:
                logger.exception("Gateway poll error")
            time.sleep(self._poll_interval)

    def _poll_eventbus_history(self):
        if not self._eventbus:
            return
        try:
            events = self._eventbus.get_history(limit=20, event_type="*")
            for ev in events:
                if ev.id in self._processed_ids:
                    continue
                eco_ev = self._classify_eventbus_event(ev)
                if eco_ev:
                    self._enqueue(eco_ev)
        except Exception:
            pass

    def _poll_eventlogger(self):
        if not self._event_logger:
            return
        try:
            since = self._last_logger_poll or datetime.fromtimestamp(0).isoformat()
            events = self._event_logger.get_recent_events(
                count=50, since_timestamp=since
            )
            if events:
                self._last_logger_poll = events[0].timestamp
            for ev in reversed(events):
                if ev.event_id in self._processed_ids:
                    continue
                eco_ev = self._classify_logger_event(ev)
                if eco_ev:
                    self._enqueue(eco_ev)
        except Exception:
            pass

    # ── 事件分类 ──

    def _on_eventbus_event(self, event):
        """EventBus 实时回调"""
        eco_ev = self._classify_eventbus_event(event)
        if eco_ev:
            self._enqueue(eco_ev)

    def _classify_eventbus_event(self, event) -> Optional[GatewayEvent]:
        etype = event.event_type
        data = event.data or {}

        if etype == "automation.task_started":
            return GatewayEvent(
                action_type=EcosystemActionType.PROJECT,
                source="eventbus",
                source_event_id=event.id,
                timestamp=event.timestamp,
                summary=f"任务开始: {data.get('name', '')}",
                detail=data,
            )

        if etype == "automation.task_completed":
            return GatewayEvent(
                action_type=EcosystemActionType.PROJECT,
                source="eventbus",
                source_event_id=event.id,
                timestamp=event.timestamp,
                summary=f"任务完成: {data.get('name', '')}",
                detail=data,
            )

        if etype == "automation.task_failed":
            return GatewayEvent(
                action_type=EcosystemActionType.PROJECT,
                source="eventbus",
                source_event_id=event.id,
                timestamp=event.timestamp,
                summary=f"任务失败: {data.get('name', '')}",
                detail=data,
                importance=0.8,
            )

        if etype == "course.slot_entered":
            return GatewayEvent(
                action_type=EcosystemActionType.COURSE,
                source="eventbus",
                source_event_id=event.id,
                timestamp=event.timestamp,
                summary=f"课程时段: {data.get('slot_name', '')}",
                detail=data,
                importance=0.7,
            )

        return None

    def _classify_logger_event(self, ev) -> Optional[GatewayEvent]:
        etype = ev.event_type
        subtype = ev.event_subtype

        if etype == "file":
            return self._classify_file_event(ev)

        if etype == "tool":
            return self._classify_tool_event(ev)

        if etype == "navigation":
            importance = 0.3
            if subtype == "tab_switch":
                importance = 0.2
            return GatewayEvent(
                action_type=EcosystemActionType.EXPLORATION,
                source="eventlogger",
                source_event_id=ev.event_id,
                timestamp=self._parse_timestamp(ev.timestamp),
                summary=f"导航: {subtype or ''} → {ev.new_value or ''}",
                detail={"target": ev.new_value, "ui_element": ev.ui_element},
                importance=importance,
            )

        if etype == "input":
            return GatewayEvent(
                action_type=EcosystemActionType.RECORD,
                source="eventlogger",
                source_event_id=ev.event_id,
                timestamp=self._parse_timestamp(ev.timestamp),
                summary=f"输入: {subtype or ''}",
                detail={"content": ev.new_value, "context": ev.context_info},
                importance=0.6,
            )

        if etype == "action" and subtype == "checkpoint":
            return GatewayEvent(
                action_type=EcosystemActionType.CHECKPOINT,
                source="eventlogger",
                source_event_id=ev.event_id,
                timestamp=self._parse_timestamp(ev.timestamp),
                summary=f"检查点: {ev.context_info or ''}",
                detail={"context": ev.context_info, "element": ev.ui_element},
                importance=0.9,
            )

        return None

    def _classify_file_event(self, ev) -> Optional[GatewayEvent]:
        ext = (ev.file_path or "").lower()
        for suffix, atype in _EXT_TO_TYPE.items():
            if ext.endswith(suffix):
                return GatewayEvent(
                    action_type=atype,
                    source="eventlogger",
                    source_event_id=ev.event_id,
                    timestamp=self._parse_timestamp(ev.timestamp),
                    summary=f"{ev.file_operation or '访问'} {ev.file_name or ''}",
                    detail={
                        "path": ev.file_path,
                        "operation": ev.file_operation,
                        "ext": suffix,
                        "context": ev.context_info,
                    },
                    importance=0.4 if ev.file_operation == "read" else 0.6,
                )
        # 未知扩展名 → 也记录但重要性低
        return GatewayEvent(
            action_type=EcosystemActionType.EXPLORATION,
            source="eventlogger",
            source_event_id=ev.event_id,
            timestamp=self._parse_timestamp(ev.timestamp),
            summary=f"文件: {ev.file_operation or ''} {ev.file_name or ''}",
            detail={
                "path": ev.file_path,
                "operation": ev.file_operation,
                "context": ev.context_info,
            },
            importance=0.2,
        )

    def _classify_tool_event(self, ev) -> Optional[GatewayEvent]:
        tool_name = ev.ui_element or ""
        atype = _TOOL_TO_TYPE.get(tool_name)
        if atype:
            return GatewayEvent(
                action_type=atype,
                source="eventlogger",
                source_event_id=ev.event_id,
                timestamp=self._parse_timestamp(ev.timestamp),
                summary=f"工具: {tool_name}",
                detail={
                    "tool": tool_name,
                    "args": ev.event_data.get("args"),
                    "result": ev.event_data.get("result"),
                    "duration_ms": ev.duration_ms,
                },
                importance=0.5,
            )
        return None

    # ── 辅助 ──

    @staticmethod
    def _parse_timestamp(ts: str) -> float:
        if not ts:
            return time.time()
        try:
            dt = datetime.fromisoformat(ts)
            return dt.timestamp()
        except (ValueError, TypeError):
            return time.time()


def get_gateway() -> EcosystemGateway:
    return EcosystemGateway.get_instance()
