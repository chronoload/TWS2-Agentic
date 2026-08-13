from .engine import AutomationEngine, AutomationType, TaskStatus, get_automation_engine
from .event_bus import EventBus, Event, Subscription, get_event_bus
from .persistence import AutomationPersistence, AutomationTask, AutomationRun, MIN_INTERVAL_SECONDS
from .triggers import (
    TriggerType, TriggerResult,
    CronTrigger, IntervalTrigger, EventTrigger, CourseScheduleTrigger,
    create_trigger,
)

try:
    from .popup_manager import PopupManager, LearningAssistantPopup, SYSTEM_PROMPT
    HAS_POPUP = True
except ImportError:
    HAS_POPUP = False
    PopupManager = None
    LearningAssistantPopup = None
    SYSTEM_PROMPT = ""

__all__ = [
    "AutomationEngine", "AutomationType", "TaskStatus", "get_automation_engine",
    "EventBus", "Event", "Subscription", "get_event_bus",
    "AutomationPersistence", "AutomationTask", "AutomationRun", "MIN_INTERVAL_SECONDS",
    "TriggerType", "TriggerResult",
    "CronTrigger", "IntervalTrigger", "EventTrigger", "CourseScheduleTrigger",
    "create_trigger",
    "PopupManager", "LearningAssistantPopup", "SYSTEM_PROMPT",
]
