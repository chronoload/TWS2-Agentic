from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FeishuMentionRef:
    id: str = ""
    name: str = ""
    user_type: str = ""


@dataclass
class FeishuNormalizedMessage:
    text: str = ""
    message_id: str = ""
    chat_id: str = ""
    sender_id: str = ""
    sender_name: str = ""
    sender_type: str = ""
    message_type: str = "text"
    mentions: List[FeishuMentionRef] = field(default_factory=list)
    is_bot: bool = False
    media_files: List[Dict[str, str]] = field(default_factory=list)
    parent_id: str = ""
    root_id: str = ""


def normalize_text_message(content: str) -> str:
    try:
        data = json.loads(content)
        return data.get("text", content)
    except (json.JSONDecodeError, TypeError):
        return content


def normalize_post_message(content: str) -> str:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content

    for locale_key in ("zh_cn", "en_us", "ja_jp"):
        locale_data = data.get(locale_key)
        if not locale_data:
            continue
        title = locale_data.get("title", "")
        rows = locale_data.get("content", [])
        parts = []
        if title:
            parts.append(f"## {title}")
        for row in rows:
            for element in row:
                tag = element.get("tag", "")
                if tag == "text":
                    parts.append(element.get("text", ""))
                elif tag == "a":
                    parts.append(f"[{element.get('text', '')}]({element.get('href', '')})")
                elif tag == "at":
                    parts.append(f"@{element.get('user_name', element.get('user_id', ''))}")
                elif tag == "md":
                    parts.append(element.get("text", ""))
                elif tag == "code":
                    parts.append(f"`{element.get('text', '')}`")
                elif tag == "equation":
                    parts.append(f"${element.get('text', '')}$")
        return "\n".join(parts)

    return content


def normalize_interactive_message(content: str) -> str:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content

    elements = data.get("elements", [])
    parts = []
    for element in elements:
        tag = element.get("tag", "")
        if tag == "div":
            text = element.get("text", {})
            if isinstance(text, dict):
                parts.append(text.get("content", text.get("text", "")))
            else:
                parts.append(str(text))
        elif tag == "markdown":
            parts.append(element.get("content", ""))
        elif tag == "action":
            for action in element.get("actions", []):
                if action.get("tag") == "button":
                    parts.append(f"[Button: {action.get('text', {}).get('content', action.get('text', ''))}]")

    header = data.get("header", {})
    if header:
        title = header.get("title", {})
        if isinstance(title, dict):
            title_text = title.get("content", title.get("text", ""))
            if title_text:
                parts.insert(0, f"## {title_text}")

    return "\n".join(parts)


def normalize_feishu_message(
    message_type: str,
    content: str,
    message_id: str = "",
    chat_id: str = "",
    sender_id: str = "",
    sender_name: str = "",
    sender_type: str = "",
    mentions: Optional[List[Dict]] = None,
    parent_id: str = "",
    root_id: str = "",
) -> FeishuNormalizedMessage:
    mention_refs = []
    if mentions:
        for m in mentions:
            mention_refs.append(FeishuMentionRef(
                id=m.get("id", m.get("open_id", "")),
                name=m.get("name", ""),
                user_type=m.get("user_type", ""),
            ))

    is_bot = sender_type == "bot" if sender_type else False

    if message_type == "text":
        text = normalize_text_message(content)
    elif message_type == "post":
        text = normalize_post_message(content)
    elif message_type in ("interactive",):
        text = normalize_interactive_message(content)
    elif message_type == "image":
        text = "[Image]"
    elif message_type == "audio":
        text = "[Audio]"
    elif message_type == "media_video":
        text = "[Video]"
    elif message_type == "file":
        text = "[File]"
    elif message_type == "share_chat":
        text = "[Group Share]"
    elif message_type == "share_user":
        text = "[User Share]"
    else:
        text = content

    return FeishuNormalizedMessage(
        text=text,
        message_id=message_id,
        chat_id=chat_id,
        sender_id=sender_id,
        sender_name=sender_name,
        sender_type=sender_type,
        message_type=message_type,
        mentions=mention_refs,
        is_bot=is_bot,
        parent_id=parent_id,
        root_id=root_id,
    )


def build_markdown_post_payload(content: str) -> str:
    has_markdown = bool(re.search(r"[#*`\[\]|>-]", content))
    if not has_markdown:
        return json.dumps({"text": content}, ensure_ascii=False)

    rows = _build_markdown_post_rows(content)
    return json.dumps({
        "zh_cn": {
            "title": "",
            "content": rows,
        }
    }, ensure_ascii=False)


def _build_markdown_post_rows(content: str) -> List[List[Dict[str, str]]]:
    lines = content.split("\n")
    rows: List[List[Dict[str, str]]] = []
    for line in lines:
        if line.strip():
            rows.append([{"tag": "md", "text": line}])
        else:
            rows.append([{"tag": "md", "text": ""}])
    return rows
