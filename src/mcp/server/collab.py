"""协同 WebSocket 服务（正式项目，服务端 Loro 权威）。

架构：FastAPI 单进程内按文件路径常驻 LoroDoc，作为 CRDT 权威。
- 客户端本地 Loro wasm 编辑 → 发 update → 服务端 import 到权威 LoroDoc → 广播给其他客户端
- 新客户端加入 → 服务端发权威 LoroDoc 快照 → 客户端 import 初始化
- 持久化：权威 LoroDoc 文本变化后 debounce 写回文件

依赖：pip install loro（PyO3，非 loro-cffi）
注意：loro 的 subscribe_local_update 需保存返回的 Subscription 引用，回调必须返回 True。

消息协议（{cmd, code, msg, data}）：
  客户端 → 服务端：
    {cmd: "collab_update", data: {bytes}}          本地 Loro update（base64）
    {cmd: "collab_awareness", data: {bytes}}       本地 Awareness 状态（base64，光标）
  服务端 → 客户端：
    {cmd: "collab_connected", data: {path, peers}}
    {cmd: "collab_snapshot", data: {bytes}}         权威 LoroDoc 快照（base64）
    {cmd: "collab_update", data: {bytes}}           广播远端 update（base64）
    {cmd: "collab_awareness", data: {bytes}}        广播远端 Awareness（base64）
    {cmd: "collab_peer_count", data: {peers}}
"""
import asyncio
import base64
import json
import logging
import time
from typing import Any, Callable, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

import loro

logger = logging.getLogger(__name__)

_PERSIST_DEBOUNCE_MS = 600


def create_copy(src: str, read_text, write_text) -> dict:
    """为协同打开创建物理副本文件（若已存在直接返回，不覆盖已有副本）。

    副本命名：{dir}/{basename}.collab.{ext}
    例如 Notes/note.md -> Notes/note.collab.md
    返回 {path: 副本路径, content: 副本内容, created: 是否新建}
    """
    name = src.rsplit("/", 1)[-1]
    if "." in name:
        base, ext = name.rsplit(".", 1)
        dst_name = f"{base}.collab.{ext}"
    else:
        dst_name = f"{name}.collab"
    dir_prefix = src[: src.rfind("/") + 1] if "/" in src else ""
    dst = dir_prefix + dst_name

    # 副本已存在：直接返回其内容
    existing = read_text(dst)
    if existing is not None:
        return {"path": dst, "content": existing, "created": False}

    # 从源文件创建副本
    src_text = read_text(src) or ""
    write_text(dst, src_text)
    return {"path": dst, "content": src_text, "created": True}


class CollabRoom:
    """单个文件的权威 LoroDoc 与客户端集合。"""

    def __init__(self, path: str):
        self.path = path
        self.doc = loro.LoroDoc()
        self.clients: Dict[str, WebSocket] = {}
        self.initialized = False
        self.had_multiple = False  # 是否出现过 ≥2 实例（真正协同）才做服务端持久化
        self._sub = None  # 保存 Subscription 引用，避免被 GC 后订阅失效
        self._persist_task: Optional[asyncio.Task] = None

    @property
    def peer_count(self) -> int:
        return len(self.clients)

    def current_text(self) -> str:
        return self.doc.get_text("md").to_string()


class CollabManager:
    def __init__(self,
                 load_text: Optional[Callable[[str], Optional[str]]] = None,
                 persist_text: Optional[Callable[[str, str], None]] = None):
        self.rooms: Dict[str, CollabRoom] = {}
        self._load_text = load_text
        self._persist_text = persist_text

    def _room(self, path: str) -> CollabRoom:
        room = self.rooms.get(path)
        if room is None:
            room = CollabRoom(path)
            self.rooms[path] = room
        return room

    def _ensure_initialized(self, room: CollabRoom):
        if room.initialized:
            return
        room.initialized = True
        init_text = self._load_text(room.path) if self._load_text else None
        if init_text:
            room.doc.get_text("md").insert(0, init_text)
            room.doc.commit()
        # 订阅权威 LoroDoc 本地变化，用于 debounce 持久化
        def _on_change(update: bytes):
            self._schedule_persist(room)
            return True
        room._sub = room.doc.subscribe_local_update(_on_change)

    def _schedule_persist(self, room: CollabRoom):
        # 仅真正协同（≥2 实例）才由服务端持久化；单实例由 app 的 putFile 负责保存，
        # 否则服务端 LoroDoc（可能滞后）写回会覆盖 app 的保存导致丢数据。
        if not self._persist_text or room.peer_count < 2:
            return
        if room._persist_task and not room._persist_task.done():
            room._persist_task.cancel()
        async def _do():
            await asyncio.sleep(_PERSIST_DEBOUNCE_MS / 1000)
            try:
                self._persist_text(room.path, room.current_text())
            except Exception as e:
                logger.error(f"collab persist failed {room.path}: {e}")
        room._persist_task = asyncio.create_task(_do())

    async def handle(self, websocket: WebSocket, path: str, send_json: Callable[[dict], Any]):
        logger.info(f"collab handle v2 awareness-ready path={path}")  # 版本标记：确认跑的是含 awareness 转发的代码
        room = self._room(path)
        self._ensure_initialized(room)
        client_id = str(int(time.time() * 1000)) + "-" + str(id(websocket))[-4:]
        room.clients[client_id] = websocket
        if room.peer_count >= 2:
            room.had_multiple = True

        try:
            await send_json({"cmd": "collab_connected", "data": {"path": path, "peers": room.peer_count}})
            # 发权威快照初始化新客户端
            snap = room.doc.export(loro.ExportMode.Snapshot())
            await send_json({"cmd": "collab_snapshot", "data": {"bytes": base64.b64encode(snap).decode()}})
            await self._broadcast(room, {"cmd": "collab_peer_count", "data": {"peers": room.peer_count}}, exclude=client_id)

            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                cmd = msg.get("cmd", "")
                data = msg.get("data", {})
                if cmd == "collab_update":
                    b64 = data.get("bytes", "")
                    try:
                        room.doc.import_(base64.b64decode(b64))
                    except Exception as e:
                        logger.warning(f"collab import error {path}: {e}")
                        continue
                    await self._broadcast(room, {"cmd": "collab_update", "data": {"bytes": b64}}, exclude=client_id)
                elif cmd == "collab_awareness":
                    # 光标状态：纯转发，服务端不解析 Awareness 二进制
                    b64 = data.get("bytes", "")
                    logger.info(f"collab awareness forward path={path} clients={len(room.clients)} bytes={len(b64)}")
                    if b64:
                        await self._broadcast(room, {"cmd": "collab_awareness", "data": {"bytes": b64}}, exclude=client_id)
        except WebSocketDisconnect:
            pass
        finally:
            room.clients.pop(client_id, None)
            await self._broadcast(room, {"cmd": "collab_peer_count", "data": {"peers": room.peer_count}}, exclude=client_id)
            if not room.clients:
                # 最后一个客户端离开：仅当确实发生过多人协同才写回（避免覆盖 app 的 putFile 保存）
                if self._persist_text and room.had_multiple:
                    try:
                        self._persist_text(room.path, room.current_text())
                    except Exception as e:
                        logger.error(f"collab final persist failed {room.path}: {e}")
                self.rooms.pop(path, None)

    async def _broadcast(self, room: CollabRoom, msg: dict, exclude: Optional[str] = None):
        text = json.dumps(msg)
        for cid, ws in list(room.clients.items()):
            if cid == exclude:
                continue
            try:
                await ws.send_text(text)
            except Exception:
                pass
