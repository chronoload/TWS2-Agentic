"""
WebSocket 实时推送管理器
参考思源笔记 melody WebSocket 架构：按 app/type 分组会话，支持广播/定向推送
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ClientSession:
    """WebSocket 客户端会话"""
    ws: Any  # WebSocket 连接对象
    app_id: str = ""
    session_id: str = ""
    client_type: str = "main"  # main, filetree, editor, sync
    connected_at: float = 0.0
    subscriptions: Set[str] = field(default_factory=set)  # 订阅的路径/事件

    def to_dict(self) -> dict:
        return {
            "app_id": self.app_id,
            "session_id": self.session_id,
            "client_type": self.client_type,
            "connected_at": self.connected_at,
            "subscriptions": list(self.subscriptions),
        }


class WebSocketManager:
    """
    WebSocket 连接管理器

    参考思源笔记的 WebSocket 架构：
    - 按 app_id 分组管理会话
    - 支持按 type 广播（main, filetree, editor, sync）
    - 支持定向推送和排除自身广播
    - 事件格式：{"cmd": "...", "code": 0, "msg": "", "data": {}}
    """

    def __init__(self):
        # {app_id: {session_id: ClientSession}}
        self._sessions: Dict[str, Dict[str, ClientSession]] = {}
        self._lock = asyncio.Lock()

    async def add_session(self, ws, app_id: str, session_id: str, client_type: str = "main") -> ClientSession:
        """添加 WebSocket 会话"""
        session = ClientSession(
            ws=ws,
            app_id=app_id,
            session_id=session_id,
            client_type=client_type,
            connected_at=time.time(),
        )
        async with self._lock:
            if app_id not in self._sessions:
                self._sessions[app_id] = {}
            self._sessions[app_id][session_id] = session
        logger.info(f"WS session added: app={app_id}, id={session_id}, type={client_type}")
        return session

    async def remove_session(self, app_id: str, session_id: str):
        """移除 WebSocket 会话"""
        async with self._lock:
            if app_id in self._sessions:
                self._sessions[app_id].pop(session_id, None)
                if not self._sessions[app_id]:
                    del self._sessions[app_id]
        logger.info(f"WS session removed: app={app_id}, id={session_id}")

    async def subscribe(self, app_id: str, session_id: str, path: str):
        """订阅路径变更通知"""
        async with self._lock:
            if app_id in self._sessions and session_id in self._sessions[app_id]:
                self._sessions[app_id][session_id].subscriptions.add(path)

    async def unsubscribe(self, app_id: str, session_id: str, path: str):
        """取消订阅"""
        async with self._lock:
            if app_id in self._sessions and session_id in self._sessions[app_id]:
                self._sessions[app_id][session_id].subscriptions.discard(path)

    def _build_event(self, cmd: str, code: int = 0, msg: str = "", data: Any = None) -> dict:
        """构建事件消息"""
        return {"cmd": cmd, "code": code, "msg": msg, "data": data}

    async def _send_to_session(self, session: ClientSession, event: dict):
        """发送事件到指定会话"""
        try:
            await session.ws.send_text(json.dumps(event, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Failed to send to session {session.session_id}: {e}")

    async def broadcast(self, cmd: str, code: int = 0, msg: str = "", data: Any = None):
        """广播到所有会话"""
        event = self._build_event(cmd, code, msg, data)
        async with self._lock:
            for app_sessions in self._sessions.values():
                for session in app_sessions.values():
                    await self._send_to_session(session, event)

    async def broadcast_by_type(self, client_type: str, cmd: str, code: int = 0,
                                 msg: str = "", data: Any = None):
        """按类型广播"""
        event = self._build_event(cmd, code, msg, data)
        async with self._lock:
            for app_sessions in self._sessions.values():
                for session in app_sessions.values():
                    if session.client_type == client_type:
                        await self._send_to_session(session, event)

    async def broadcast_by_app(self, app_id: str, cmd: str, code: int = 0,
                                msg: str = "", data: Any = None):
        """按 app 广播"""
        event = self._build_event(cmd, code, msg, data)
        async with self._lock:
            if app_id in self._sessions:
                for session in self._sessions[app_id].values():
                    await self._send_to_session(session, event)

    async def broadcast_exclude_session(self, exclude_app_id: str, exclude_session_id: str,
                                         cmd: str, code: int = 0, msg: str = "",
                                         data: Any = None):
        """广播排除指定会话（用于编辑同步：通知其他客户端）"""
        event = self._build_event(cmd, code, msg, data)
        async with self._lock:
            for app_id, app_sessions in self._sessions.items():
                for session_id, session in app_sessions.items():
                    if app_id == exclude_app_id and session_id == exclude_session_id:
                        continue
                    await self._send_to_session(session, event)

    async def notify_path_change(self, path: str, change_type: str, source_app: str = "",
                                  source_session: str = "", data: Any = None):
        """
        通知路径变更（文件修改/新增/删除）

        只推送给订阅了该路径的会话，排除变更源
        """
        event = self._build_event("filechange", 0, "", {
            "path": path,
            "type": change_type,  # created, modified, deleted, renamed
            "data": data,
            "timestamp": time.time(),
        })
        async with self._lock:
            for app_id, app_sessions in self._sessions.items():
                for session_id, session in app_sessions.items():
                    # 排除变更源
                    if app_id == source_app and session_id == source_session:
                        continue
                    # 检查订阅匹配
                    if self._match_subscription(path, session.subscriptions):
                        await self._send_to_session(session, event)

    def _match_subscription(self, path: str, subscriptions: Set[str]) -> bool:
        """检查路径是否匹配订阅"""
        if not subscriptions:
            return True  # 无订阅 = 接收所有
        for sub in subscriptions:
            if path.startswith(sub) or sub in path:
                return True
        return False

    async def push_msg(self, msg: str, timeout: int = 5000):
        """推送消息通知"""
        await self.broadcast("msg", 0, msg, {"id": f"msg_{int(time.time()*1000)}", "closeTimeout": timeout})

    async def push_err_msg(self, msg: str, timeout: int = 7000):
        """推送错误消息"""
        await self.broadcast("msg", -1, msg, {"id": f"err_{int(time.time()*1000)}", "closeTimeout": timeout})

    async def push_progress(self, code: int, current: int, total: int, msg: str = ""):
        """推送进度"""
        await self.broadcast("progress", code, msg, {"current": current, "total": total})

    async def push_statusbar(self, msg: str):
        """推送状态栏消息"""
        await self.broadcast("statusbar", 0, msg)

    async def push_reload_filetree(self):
        """推送文件树刷新"""
        await self.broadcast_by_type("filetree", "reloadFiletree")

    async def push_reload_editor(self, path: str):
        """推送编辑器刷新"""
        await self.broadcast_by_type("editor", "reloadEditor", data={"path": path})

    def get_session_count(self) -> int:
        """获取当前连接数"""
        count = 0
        for app_sessions in self._sessions.values():
            count += len(app_sessions)
        return count

    def get_sessions_info(self) -> List[dict]:
        """获取所有会话信息"""
        result = []
        for app_id, app_sessions in self._sessions.items():
            for session_id, session in app_sessions.items():
                result.append(session.to_dict())
        return result


# 全局 WebSocket 管理器
_ws_manager: Optional[WebSocketManager] = None


def get_ws_manager() -> WebSocketManager:
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
