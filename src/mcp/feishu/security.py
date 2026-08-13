from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def verify_webhook_signature(
    timestamp: str,
    nonce: str,
    encrypt_key: str,
    body: str,
    signature: str,
) -> bool:
    if not encrypt_key:
        return True
    content = timestamp + nonce + encrypt_key + body
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_verification_token(payload: Dict[str, Any], token: str) -> bool:
    if not token:
        return True
    header = payload.get("header", {})
    payload_token = header.get("token", "")
    return hmac.compare_digest(payload_token, token)


def check_user_allowed(sender_id: str, allowed_users: Optional[Set[str]] = None) -> bool:
    if not allowed_users:
        return True
    return sender_id in allowed_users


class FeishuSecurityConfig:
    def __init__(self) -> None:
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.domain = os.getenv("FEISHU_DOMAIN", "feishu")
        self.encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
        self.verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
        self.allowed_users: Set[str] = set()
        raw = os.getenv("FEISHU_ALLOWED_USERS", "")
        if raw:
            self.allowed_users = {u.strip() for u in raw.split(",") if u.strip()}
        self.connection_mode = os.getenv("FEISHU_CONNECTION_MODE", "websocket")
        self.home_channel = os.getenv("FEISHU_HOME_CHANNEL", "")
        self.group_policy = os.getenv("FEISHU_GROUP_POLICY", "allowlist")
        self.require_mention = os.getenv("FEISHU_REQUIRE_MENTION", "true").lower() == "true"
        self.allow_bots = os.getenv("FEISHU_ALLOW_BOTS", "none").lower()
        self.bot_open_id = os.getenv("FEISHU_BOT_OPEN_ID", "")
        self.bot_user_id = os.getenv("FEISHU_BOT_USER_ID", "")
        self.bot_name = os.getenv("FEISHU_BOT_NAME", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "domain": self.domain,
            "connection_mode": self.connection_mode,
            "has_secret": bool(self.app_secret),
            "has_encrypt_key": bool(self.encrypt_key),
            "has_verification_token": bool(self.verification_token),
            "allowed_users_count": len(self.allowed_users),
            "group_policy": self.group_policy,
            "require_mention": self.require_mention,
            "allow_bots": self.allow_bots,
            "home_channel": self.home_channel,
        }
