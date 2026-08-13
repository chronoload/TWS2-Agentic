from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Set

from .message import FeishuNormalizedMessage, normalize_feishu_message, build_markdown_post_payload
from .security import FeishuSecurityConfig, verify_webhook_signature, verify_verification_token, check_user_allowed

logger = logging.getLogger(__name__)


class FeishuAdapter:
    """飞书/Lark 适配器，支持 WebSocket 和 Webhook 两种连接模式。

    WebSocket 模式（推荐）: 主动建立长连接，无需公网地址
    Webhook 模式: 飞书推送事件到 HTTP 端点
    """

    MAX_MESSAGE_LENGTH = 8000

    def __init__(
        self,
        config: Optional[FeishuSecurityConfig] = None,
        on_message: Optional[Callable] = None,
    ) -> None:
        self.config = config or FeishuSecurityConfig()
        self.on_message = on_message
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._seen_message_ids: Dict[str, float] = {}
        self._seen_message_order: List[str] = []
        self._dedup_max = 2048
        self._chat_locks: Dict[str, asyncio.Lock] = {}
        self._sender_name_cache: Dict[str, tuple] = {}

    @property
    def is_connected(self) -> bool:
        if self.config.connection_mode == "websocket":
            return self._ws_client is not None
        return self._running

    def _build_client(self) -> Any:
        try:
            import lark_oapi as lark
            return (
                lark.Client.builder()
                .app_id(self.config.app_id)
                .app_secret(self.config.app_secret)
                .domain(self.config.domain)
                .build()
            )
        except ImportError:
            logger.error("lark_oapi not installed, cannot build Feishu client")
            return None

    def connect(self) -> bool:
        if not self.config.is_configured:
            logger.error("Feishu not configured (missing FEISHU_APP_ID/FEISHU_APP_SECRET)")
            return False

        self._client = self._build_client()
        if self._client is None:
            return False

        if self.config.connection_mode == "websocket":
            return self._connect_websocket()
        else:
            return self._start_webhook()

    def disconnect(self) -> None:
        self._running = False
        if self._ws_client:
            try:
                self._ws_client.stop()
            except Exception:
                pass
            self._ws_client = None
        logger.info("[Feishu] Adapter disconnected")

    def _connect_websocket(self) -> bool:
        try:
            import lark_oapi as lark
            from lark_oapi.adapter.ws import WsClient
        except ImportError:
            logger.error("lark_oapi websockets not available; install lark_oapi[ws]")
            return False

        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._on_message_event) \
            .build()

        self._ws_client = WsClient.builder(
            self.config.app_id,
            self.config.app_secret,
            event_handler,
            domain=self.config.domain,
        ).build()

        thread = threading.Thread(target=self._ws_client.start, daemon=True)
        thread.start()
        self._running = True
        logger.info("[Feishu] WebSocket client started")
        return True

    def _start_webhook(self) -> bool:
        try:
            import aiohttp
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp not installed; required for webhook mode")
            return False

        self._running = True
        logger.info(f"[Feishu] Webhook mode ready (start with serve_webhook)")
        return True

    async def serve_webhook(self, host: str = "127.0.0.1", port: int = 8765, path: str = "/feishu/webhook") -> None:
        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp not installed")
            return

        app = web.Application()
        app.router.add_post(path, self._handle_webhook)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"[Feishu] Webhook server started on {host}:{port}{path}")

    async def _handle_webhook(self, request: Any) -> Any:
        from aiohttp import web as aio_web

        body = await request.text()
        timestamp = request.headers.get("x-lark-request-timestamp", "")
        nonce = request.headers.get("x-lark-request-nonce", "")
        signature = request.headers.get("x-lark-signature", "")

        if self.config.encrypt_key:
            if not verify_webhook_signature(timestamp, nonce, self.config.encrypt_key, body, signature):
                return aio_web.Response(status=401, text="Invalid signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return aio_web.Response(status=400, text="Invalid JSON")

        if self.config.verification_token:
            if not verify_verification_token(payload, self.config.verification_token):
                return aio_web.Response(status=401, text="Invalid verification token")

        header = payload.get("header", {})
        event_type = header.get("event_type", "")

        if event_type == "url_verification":
            challenge = payload.get("challenge", "")
            return aio_web.json_response({"challenge": challenge})

        if event_type == "im.message.receive_v1":
            event = payload.get("event", {})
            message = event.get("message", {})
            sender = event.get("sender", {})
            sender_id = sender.get("sender_id", {}).get("open_id", "")
            sender_type = sender.get("sender_type", "")

            if sender_type == "bot" and self.config.allow_bots == "none":
                return aio_web.json_response({"code": 0})

            if not check_user_allowed(sender_id, self.config.allowed_users):
                return aio_web.json_response({"code": 0})

            msg = normalize_feishu_message(
                message_type=message.get("message_type", "text"),
                content=message.get("content", ""),
                message_id=message.get("message_id", ""),
                chat_id=message.get("chat_id", ""),
                sender_id=sender_id,
                sender_type=sender_type,
                mentions=message.get("mentions", []),
            )

            if self.on_message:
                await self._dispatch_message(msg)

        return aio_web.json_response({"code": 0})

    def _on_message_event(self, ctx: Any, event: Any, *args: Any) -> None:
        try:
            msg = event.event.message if hasattr(event, "event") else getattr(event, "message", {})
            sender = event.event.sender if hasattr(event, "event") else getattr(event, "sender", {})

            message_type = getattr(msg, "message_type", "text")
            content = getattr(msg, "content", "")
            message_id = getattr(msg, "message_id", "")
            chat_id = getattr(msg, "chat_id", "")
            sender_id = getattr(sender, "sender_id", {})
            if isinstance(sender_id, dict):
                sender_id = sender_id.get("open_id", "")
            sender_type = getattr(sender, "sender_type", "")

            if message_id in self._seen_message_ids:
                return
            self._record_message_id(message_id)

            if sender_type == "bot" and self.config.allow_bots == "none":
                return

            if not check_user_allowed(sender_id, self.config.allowed_users):
                return

            mentions_raw = getattr(msg, "mentions", None)
            mentions = []
            if mentions_raw:
                for m in mentions_raw:
                    mentions.append({
                        "id": getattr(m, "id", {}),
                        "name": getattr(m, "name", ""),
                    })

            normalized = normalize_feishu_message(
                message_type=message_type,
                content=content,
                message_id=message_id,
                chat_id=chat_id,
                sender_id=sender_id,
                sender_type=sender_type,
                mentions=mentions,
            )

            if self.on_message:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._dispatch_message(normalized))
                except RuntimeError:
                    threading.Thread(
                        target=lambda: asyncio.run(self._dispatch_message(normalized)),
                        daemon=True,
                    ).start()
        except Exception as e:
            logger.error(f"[Feishu] Error processing message event: {e}")

    async def _dispatch_message(self, msg: FeishuNormalizedMessage) -> None:
        if self.on_message:
            if asyncio.iscoroutinefunction(self.on_message):
                await self.on_message(msg)
            else:
                self.on_message(msg)

    def _record_message_id(self, message_id: str) -> None:
        now = time.time()
        self._seen_message_ids[message_id] = now
        self._seen_message_order.append(message_id)
        while len(self._seen_message_ids) > self._dedup_max:
            oldest = self._seen_message_order.pop(0)
            self._seen_message_ids.pop(oldest, None)

    async def send_message(self, chat_id: str, text: str, msg_type: str = "auto") -> Dict[str, Any]:
        if self._client is None:
            return {"error": "Feishu client not initialized"}

        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        except ImportError:
            return {"error": "lark_oapi not installed"}

        if msg_type == "auto":
            has_md = bool(hashlib.md5(text.encode()).hexdigest()) and any(c in text for c in "#*`[]|>-")
            msg_type = "post" if has_md else "text"

        if msg_type == "post":
            content = build_markdown_post_payload(text)
        else:
            content = json.dumps({"text": text}, ensure_ascii=False)

        try:
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                ).build()

            response = self._client.im.v1.message.create(request)
            code = getattr(response, "code", None)
            if code != 0:
                msg = getattr(response, "msg", "unknown error")
                return {"error": f"Send failed: code={code} msg={msg}"}
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    async def reply_message(self, message_id: str, text: str) -> Dict[str, Any]:
        if self._client is None:
            return {"error": "Feishu client not initialized"}

        try:
            from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
        except ImportError:
            return {"error": "lark_oapi not installed"}

        has_md = any(c in text for c in "#*`[]|>-")
        msg_type = "post" if has_md else "text"
        content = build_markdown_post_payload(text) if msg_type == "post" else json.dumps({"text": text}, ensure_ascii=False)

        try:
            request = ReplyMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                ).build()

            response = self._client.im.v1.message.reply(request)
            code = getattr(response, "code", None)
            if code != 0:
                msg = getattr(response, "msg", "unknown error")
                return {"error": f"Reply failed: code={code} msg={msg}"}
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "mode": self.config.connection_mode,
            "configured": self.config.is_configured,
            "config": self.config.to_dict(),
        }
