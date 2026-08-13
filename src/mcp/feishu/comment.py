from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from .adapter import FeishuAdapter
from .message import normalize_feishu_message
from .security import FeishuSecurityConfig

logger = logging.getLogger(__name__)


class FeishuCommentHandler:
    """处理飞书文档评论事件，自动生成智能回复。

    流程:
    1. 解析 drive.notice.comment_add_v1 事件
    2. 并行获取文档内容和评论详情
    3. 构建 prompt，调用 Agent 生成回复
    4. 将回复发送到评论线程
    """

    def __init__(self, adapter: FeishuAdapter, agent: Any = None) -> None:
        self.adapter = adapter
        self.agent = agent
        self._doc_sessions: Dict[str, Dict[str, Any]] = {}
        self._session_max_age = 3600
        self._session_max_messages = 50

    async def handle_comment_event(self, event: Dict[str, Any]) -> None:
        event_data = event.get("event", {})
        comment = event_data.get("comment", {})
        file_token = comment.get("file_token", "")
        comment_id = comment.get("comment_id", "")
        reply_id = comment.get("reply_id", "")
        is_whole = comment.get("is_whole", False)
        creator = comment.get("creator", {})
        user_open_id = creator.get("open_id", "")

        if not file_token or not comment_id:
            logger.warning("[Feishu-Comment] Missing file_token or comment_id")
            return

        doc_content = await self._fetch_doc_content(file_token)
        comment_thread = await self._fetch_comment_thread(file_token, comment_id, is_whole)

        if not doc_content and not comment_thread:
            logger.warning("[Feishu-Comment] Could not fetch document or comment context")
            return

        prompt = self._build_comment_prompt(doc_content, comment_thread, is_whole)
        reply_text = await self._generate_reply(prompt)

        if reply_text:
            await self._post_reply(file_token, comment_id, reply_text, is_whole)

    async def _fetch_doc_content(self, file_token: str) -> str:
        if self.adapter._client is None:
            return ""

        try:
            from lark_oapi import AccessTokenType
            from lark_oapi.core.enum import HttpMethod
            from lark_oapi.core.model.base_request import BaseRequest

            request = (
                BaseRequest.builder()
                .http_method(HttpMethod.GET)
                .uri("/open-apis/docx/v1/documents/:document_id/raw_content")
                .token_types({AccessTokenType.TENANT})
                .paths({"document_id": file_token})
                .build()
            )

            response = await asyncio.to_thread(self.adapter._client.request, request)
            code = getattr(response, "code", None)
            if code != 0:
                return ""

            raw = getattr(response, "raw", None)
            if raw and hasattr(raw, "content"):
                try:
                    body = json.loads(raw.content)
                    return body.get("data", {}).get("content", "")
                except (json.JSONDecodeError, AttributeError):
                    pass
            return ""
        except Exception as e:
            logger.debug(f"[Feishu-Comment] Failed to fetch doc content: {e}")
            return ""

    async def _fetch_comment_thread(self, file_token: str, comment_id: str, is_whole: bool) -> str:
        if self.adapter._client is None:
            return ""

        try:
            from lark_oapi import AccessTokenType
            from lark_oapi.core.enum import HttpMethod
            from lark_oapi.core.model.base_request import BaseRequest

            if is_whole:
                uri = "/open-apis/drive/v1/files/:file_token/comments"
                paths = {"file_token": file_token}
                queries = [("file_type", "docx"), ("user_id_type", "open_id"), ("page_size", "20")]
            else:
                uri = "/open-apis/drive/v1/files/:file_token/comments/:comment_id/replies"
                paths = {"file_token": file_token, "comment_id": comment_id}
                queries = [("file_type", "docx"), ("user_id_type", "open_id"), ("page_size", "12")]

            request = (
                BaseRequest.builder()
                .http_method(HttpMethod.GET)
                .uri(uri)
                .token_types({AccessTokenType.TENANT})
                .paths(paths)
                .queries(queries)
                .build()
            )

            response = await asyncio.to_thread(self.adapter._client.request, request)
            code = getattr(response, "code", None)
            if code != 0:
                return ""

            raw = getattr(response, "raw", None)
            if raw and hasattr(raw, "content"):
                try:
                    body = json.loads(raw.content)
                    return json.dumps(body.get("data", {}), ensure_ascii=False, indent=2)
                except (json.JSONDecodeError, AttributeError):
                    pass
            return ""
        except Exception as e:
            logger.debug(f"[Feishu-Comment] Failed to fetch comment thread: {e}")
            return ""

    def _build_comment_prompt(self, doc_content: str, comment_thread: str, is_whole: bool) -> str:
        parts = [
            "You are an intelligent assistant responding to a comment on a Feishu/Lark document.",
            "",
            "## Document Content",
            doc_content[:8000] if doc_content else "(Document content not available)",
            "",
            "## Comment Thread",
            comment_thread if comment_thread else "(No comment thread available)",
            "",
            "Please provide a helpful, concise reply to the latest comment. "
            "If the comment is a question, answer it. If it's feedback, acknowledge it constructively.",
        ]
        return "\n".join(parts)

    async def _generate_reply(self, prompt: str) -> str:
        if self.agent is None:
            return ""

        try:
            if hasattr(self.agent, "chat"):
                response = await asyncio.to_thread(self.agent.chat, prompt)
                return str(response) if response else ""
            elif hasattr(self.agent, "run"):
                response = await asyncio.to_thread(self.agent.run, prompt)
                return str(response) if response else ""
            return ""
        except Exception as e:
            logger.error(f"[Feishu-Comment] Failed to generate reply: {e}")
            return ""

    async def _post_reply(self, file_token: str, comment_id: str, content: str, is_whole: bool) -> bool:
        if self.adapter._client is None:
            return False

        try:
            from lark_oapi import AccessTokenType
            from lark_oapi.core.enum import HttpMethod
            from lark_oapi.core.model.base_request import BaseRequest

            chunk_size = 4000
            chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]

            for chunk in chunks:
                if is_whole:
                    uri = "/open-apis/drive/v1/files/:file_token/new_comments"
                    body = {
                        "file_type": "docx",
                        "reply_elements": [{"type": "text", "text": chunk}],
                    }
                    paths = {"file_token": file_token}
                else:
                    uri = "/open-apis/drive/v1/files/:file_token/comments/:comment_id/replies"
                    body = {
                        "content": {
                            "elements": [{"type": "text_run", "text_run": {"text": chunk}}]
                        }
                    }
                    paths = {"file_token": file_token, "comment_id": comment_id}

                request = (
                    BaseRequest.builder()
                    .http_method(HttpMethod.POST)
                    .uri(uri)
                    .token_types({AccessTokenType.TENANT})
                    .paths(paths)
                    .queries([("file_type", "docx")])
                    .body(body)
                    .build()
                )

                response = await asyncio.to_thread(self.adapter._client.request, request)
                code = getattr(response, "code", None)
                if code != 0:
                    msg = getattr(response, "msg", "")
                    if code == 1069302 and not is_whole:
                        logger.info("[Feishu-Comment] Reply failed with 1069302, falling back to add_comment")
                        return await self._post_reply(file_token, comment_id, chunk, is_whole=True)
                    logger.warning(f"[Feishu-Comment] Post reply failed: code={code} msg={msg}")
                    return False

            return True
        except Exception as e:
            logger.error(f"[Feishu-Comment] Failed to post reply: {e}")
            return False
