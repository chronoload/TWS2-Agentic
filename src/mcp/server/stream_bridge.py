import asyncio
import json
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncGenerator, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class StreamBridge:
    """SSE 流式桥接 — 封装 Agent → SSE 的完整生命周期

    职责:
    - 管理 per-session 的 asyncio.Queue
    - 生成线程安全的回调函数 (_on_token/_on_tool/_on_tool_result)
    - 在 ThreadPoolExecutor 中运行 agent.chat()
    - 提供异步生成器 _stream() 用于 StreamingResponse
    - 处理取消、超时、客户端断开
    """

    def __init__(self, executor: Optional[ThreadPoolExecutor] = None, queue_timeout: float = 300.0):
        self._executor = executor or ThreadPoolExecutor(max_workers=2)
        self._queue_timeout = queue_timeout
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, session_id: str, agent: Any, message: str) -> "StreamSession":
        session = StreamSession(
            session_id=session_id,
            agent=agent,
            message=message,
            executor=self._executor,
            queue_timeout=self._queue_timeout,
        )
        self._active_sessions[session_id] = {
            "session": session,
            "created_at": time.time(),
        }
        return session

    def close_session(self, session_id: str):
        self._active_sessions.pop(session_id, None)

    def get_session_count(self) -> int:
        return len(self._active_sessions)

    def cleanup_stale_sessions(self, max_age: float = 300.0):
        now = time.time()
        stale = [sid for sid, info in self._active_sessions.items()
                 if now - info["created_at"] > max_age]
        for sid in stale:
            logger.info(f"StreamBridge: cleaning stale session {sid}")
            try:
                info = self._active_sessions.pop(sid, None)
                if info:
                    info["session"].cancel()
            except Exception:
                pass


class StreamSession:
    """单次 SSE 流式会话的生命周期管理"""

    def __init__(self, session_id: str, agent: Any, message: str,
                 executor: ThreadPoolExecutor, queue_timeout: float = 90.0):
        self.session_id = session_id
        self.agent = agent
        self.message = message
        self._executor = executor
        self._queue_timeout = queue_timeout
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._main_loop = asyncio.get_event_loop()
        self._cancelled = False
        self._started_at = time.time()
        self._token_count = 0
        self._tool_count = 0

    @property
    def elapsed(self) -> float:
        return time.time() - self._started_at

    def _put(self, data: dict):
        try:
            self._main_loop.call_soon_threadsafe(
                self._message_queue.put_nowait, data
            )
        except Exception as e:
            logger.warning(f"StreamSession._put error: {e}")

    def make_on_token(self) -> Callable[[str], None]:
        def _on_token(token: str):
            if self._cancelled:
                return
            self._token_count += 1
            self._put({"type": "token", "content": token})
        return _on_token

    def make_on_tool(self) -> Callable[[str, dict], None]:
        def _on_tool(name: str, args: dict):
            if self._cancelled:
                return
            self._tool_count += 1
            self._put({"type": "tool_call", "name": name, "args": args})
        return _on_tool

    def make_on_tool_result(self) -> Callable[[str, str], None]:
        def _on_tool_result(name: str, result: str):
            if self._cancelled:
                return
            cp_hash = ""
            try:
                if hasattr(self.agent, '_middleware_chain') and self.agent._middleware_chain:
                    for mw in self.agent._middleware_chain._middlewares:
                        from ..middleware.shadow_checkpoint import CheckpointMiddleware
                        if isinstance(mw, CheckpointMiddleware):
                            cp_id = getattr(mw, '_last_checkpoint_id', 0)
                            if cp_id and cp_id > 0:
                                cp_hash = str(cp_id)
                            break
            except Exception:
                pass
            self._put({
                "type": "tool_result",
                "name": name,
                "result": result[:500],
                "checkpoint_hash": cp_hash,
            })
        return _on_tool_result

    def cancel(self):
        self._cancelled = True
        try:
            if hasattr(self.agent, 'cancel'):
                self.agent.cancel()
        except Exception:
            pass

    async def stream(self) -> AsyncGenerator:
        """异步生成器 — 产生 SSE 格式化事件字符串"""
        agent_future = self._main_loop.run_in_executor(
            self._executor, self._run_agent
        )
        try:
            while not self._cancelled:
                try:
                    msg = await asyncio.wait_for(
                        self._message_queue.get(), timeout=self._queue_timeout
                    )
                except asyncio.TimeoutError:
                    yield self._format_event({"type": "error", "content": "超时"})
                    yield "[DONE]"
                    break

                if msg.get("type") == "done":
                    yield self._format_event(msg)
                    yield "[DONE]"
                    break
                elif msg.get("type") == "error":
                    yield self._format_event(msg)
                    yield "[DONE]"
                    break
                else:
                    yield self._format_event(msg)
        except asyncio.CancelledError:
            self.cancel()
        finally:
            if not agent_future.done():
                agent_future.cancel()

    def _run_agent(self):
        """在 executor 线程中运行 agent.chat()"""
        try:
            logger.info(
                f"StreamSession[{self.session_id}]: starting, "
                f"message={self.message[:50]}..."
            )
            reply = self.agent.chat(
                self.message,
                on_token=self.make_on_token(),
                on_tool=self.make_on_tool(),
                on_tool_result=self.make_on_tool_result(),
                session_id=self.session_id,
            )
            logger.info(
                f"StreamSession[{self.session_id}]: completed, "
                f"reply_len={len(reply) if reply else 0}, "
                f"tokens={self._token_count}, tools={self._tool_count}, "
                f"elapsed={self.elapsed:.1f}s"
            )
            self._put({"type": "done", "content": reply})
        except Exception as e:
            logger.error(f"StreamSession[{self.session_id}]: error: {e}")
            traceback.print_exc()
            self._put({"type": "error", "content": str(e)})

    @staticmethod
    def _format_event(data: dict) -> str:
        """将 dict 格式化为 SSE data: 行"""
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"data: {raw}\n\n"

    def get_stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "elapsed": self.elapsed,
            "token_count": self._token_count,
            "tool_count": self._tool_count,
            "cancelled": self._cancelled,
        }


try:
    from typing import AsyncGenerator
except ImportError:
    AsyncGenerator = Any
