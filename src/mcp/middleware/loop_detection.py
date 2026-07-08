import json
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import AgentMiddleware, MiddlewareContext, MiddlewareResult, MiddlewareAction

logger = logging.getLogger(__name__)


@dataclass
class LoopDetectionConfig:
    """循环检测配置 — 完全相同请求重复执行时才计数"""
    # 完全相同请求连续失败达到此次数时发出警告
    consecutive_loop_warn: int = 3
    # 完全相同请求连续失败达到此次数时强制停止
    consecutive_loop_stop: int = 5
    # 最大追踪会话数
    max_tracked_sessions: int = 100


def _is_tool_error(tool_result: Any) -> bool:
    """判断工具返回是否为错误"""
    if isinstance(tool_result, str):
        lower = tool_result.lower().strip()
        if lower.startswith('{"success":false'):
            return True
        if lower.startswith('{"success": false'):
            return True
        if '"error"' in lower[:100]:
            return True
        if lower.startswith('error') or lower.startswith('exception'):
            return True
        if 'traceback' in lower[:200]:
            return True
        if 'failed' in lower[:50] or '失败' in lower[:50]:
            return True
    elif isinstance(tool_result, dict):
        if tool_result.get('success') is False:
            return True
        if 'error' in tool_result:
            return True
    return False


def _request_key(tool_name: str, tool_args: dict) -> str:
    """生成请求唯一标识 key，用于判断是否是"完全相同"的请求"""
    try:
        args_str = json.dumps(tool_args, sort_keys=True, ensure_ascii=False)
    except Exception:
        args_str = str(tool_args)
    return f"{tool_name}::{args_str}"


class _SessionTracker:
    """追踪单个会话的循环请求
    
    只有"完全相同请求"（同一工具+同一参数）连续失败才计数。
    不同请求/成功请求都会重置计数。
    """

    def __init__(self, config: LoopDetectionConfig):
        self.config = config
        self._loop_count: int = 0          # 当前循环请求连续失败次数
        self._last_request_key: str = ""    # 上一个请求的标志
        self._total_errors: int = 0
        self._pending_inject: Optional[str] = None

    def record_tool_result(self, tool_name: str, tool_args: dict, tool_result: Any) -> Optional[str]:
        """记录工具执行结果，返回停止原因（相同请求循环时）
        
        计数规则：
        - 和上次请求相同（同一工具+同一参数）且失败 → loop_count +1
        - 和上次请求不同 → loop_count 重置为 1（新请求首次失败）
        - 请求成功 → loop_count 重置为 0
        """
        is_error = _is_tool_error(tool_result)
        current_key = _request_key(tool_name, tool_args) if is_error else ""

        if is_error:
            self._total_errors += 1

            if current_key == self._last_request_key:
                # 完全相同请求再次失败 → 循环计数递增
                self._loop_count += 1
            else:
                # 新请求首次失败 → 重置循环计数为 1
                self._loop_count = 1
                self._last_request_key = current_key

            if self._loop_count >= self.config.consecutive_loop_stop:
                return (
                    f"LOOP_DETECTED: 完全相同请求 [{tool_name}] 连续失败 "
                    f"{self._loop_count} 次，强制停止"
                )

            if self._loop_count >= self.config.consecutive_loop_warn:
                self._pending_inject = (
                    f"[循环检测警告] 完全相同请求 [{tool_name}] 已连续失败 "
                    f"{self._loop_count} 次，请换一种方法。"
                    f"再重复 {self.config.consecutive_loop_stop - self._loop_count} 次将强制停止。"
                )
        else:
            # 工具成功，重置所有循环计数
            if self._loop_count > 0:
                logger.debug(f"循环计数重置（之前: {self._loop_count}，工具 {tool_name} 成功）")
            self._loop_count = 0
            self._last_request_key = ""

        return None

    @property
    def pending_inject(self) -> Optional[str]:
        inject = self._pending_inject
        self._pending_inject = None
        return inject


class LoopDetectionMiddleware(AgentMiddleware):
    """
    循环请求检测中间件 — 仅当"完全相同请求"（同一工具+同一参数）连续失败时才干预
    
    不同请求或成功的请求都会重置循环计数。
    """
    name = "loop_detection"
    order = 12

    def __init__(self, config: Optional[LoopDetectionConfig] = None):
        self.config = config or LoopDetectionConfig()
        self._trackers: OrderedDict[str, _SessionTracker] = OrderedDict()

    def _get_tracker(self, context: MiddlewareContext) -> _SessionTracker:
        key = context.session_id or context.thread_id or "default"
        if key not in self._trackers:
            if len(self._trackers) >= self.config.max_tracked_sessions:
                self._trackers.popitem(last=False)
            self._trackers[key] = _SessionTracker(self.config)
        self._trackers.move_to_end(key)
        return self._trackers[key]

    def after_tool(self, tool_name: str, tool_args: dict, tool_result: str, context: MiddlewareContext) -> MiddlewareResult:
        """工具执行后检测循环请求"""
        tracker = self._get_tracker(context)

        stop_reason = tracker.record_tool_result(tool_name, tool_args or {}, tool_result)
        if stop_reason:
            logger.warning(f"LoopDetection: {stop_reason}")
            return MiddlewareResult(
                action=MiddlewareAction.STOP,
                reason=stop_reason,
                force_stop=True,
            )

        return MiddlewareResult()

    def wrap_model_call(self, request_messages: List[Dict[str, Any]], handler, context: MiddlewareContext) -> Any:
        """在模型调用前注入警告信息"""
        tracker = self._get_tracker(context)
        inject = tracker.pending_inject

        if inject:
            augmented = list(request_messages)
            augmented.append({"role": "user", "content": inject})
            return handler(augmented)

        return handler(request_messages)

    def before_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        """新对话开始时重置追踪器"""
        key = context.session_id or context.thread_id or "default"
        if key in self._trackers:
            del self._trackers[key]
        return MiddlewareResult()

    def reset(self, session_id: str = ""):
        if session_id and session_id in self._trackers:
            del self._trackers[session_id]
        elif not session_id:
            self._trackers.clear()
