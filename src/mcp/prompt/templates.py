#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模板引擎 — 参考 Cline 的 TemplateEngine 设计
支持 {{PLACEHOLDER}} 语法和嵌套对象访问
"""

import re
import json
from typing import Any, Dict, Optional
from datetime import datetime
import os


class StandardPlaceholders:
    AGENT_ROLE = "AGENT_ROLE"
    TOOL_USE = "TOOL_USE"
    MCP = "MCP"
    EDITING_FILES = "EDITING_FILES"
    ACT_VS_PLAN = "ACT_VS_PLAN"
    TODO = "TODO"
    CAPABILITIES = "CAPABILITIES"
    FEEDBACK = "FEEDBACK"
    RULES = "RULES"
    SYSTEM_INFO = "SYSTEM_INFO"
    OBJECTIVE = "OBJECTIVE"
    USER_INSTRUCTIONS = "USER_INSTRUCTIONS"
    SKILLS = "SKILLS"
    TASK_PROGRESS = "TASK_PROGRESS"
    CWD = "CWD"
    CURRENT_DATE = "CURRENT_DATE"
    MODEL_FAMILY = "MODEL_FAMILY"
    AGENT_NAME = "AGENT_NAME"
    WORKSPACE_CONTEXT = "WORKSPACE_CONTEXT"


STANDARD_PLACEHOLDERS = StandardPlaceholders()


class TemplateEngine:
    """{{PLACEHOLDER}} 模板引擎，支持点号嵌套访问"""

    @staticmethod
    def resolve(template: str, placeholders: Dict[str, Any],
                context: Optional[Dict[str, Any]] = None) -> str:
        if not template:
            return ""

        combined = {}
        if context:
            combined.update(context)
        combined.update(placeholders)

        result = re.sub(
            r'\{\{([^}]+)\}\}',
            lambda m: TemplateEngine._resolve_placeholder(m, combined),
            template
        )

        return result

    @staticmethod
    def _resolve_placeholder(match: re.Match, values: Dict[str, Any]) -> str:
        key = match.group(1).strip()
        value = TemplateEngine._get_nested(values, key)

        if value is None:
            return match.group(0)

        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _get_nested(data: Dict[str, Any], key: str) -> Any:
        parts = key.split(".")
        current: Any = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    @staticmethod
    def extract_placeholders(template: str) -> list:
        return [m.group(1).strip() for m in re.finditer(r'\{\{([^}]+)\}\}', template)]

    @staticmethod
    def resolve_standard(context: Dict[str, Any]) -> Dict[str, str]:
        return {
            STANDARD_PLACEHOLDERS.CWD: context.get("cwd", os.getcwd()),
            STANDARD_PLACEHOLDERS.CURRENT_DATE: datetime.now().strftime("%Y-%m-%d"),
            STANDARD_PLACEHOLDERS.MODEL_FAMILY: context.get("model_family", "generic"),
            STANDARD_PLACEHOLDERS.AGENT_NAME: context.get("agent_name", "WS2 Agent"),
        }

    @staticmethod
    def post_process(prompt: str) -> str:
        if not prompt:
            return ""

        prompt = re.sub(r'\n\s*\n\s*\n', '\n\n', prompt)
        prompt = prompt.strip()
        prompt = re.sub(r'====\s*$', '', prompt)
        prompt = re.sub(r'====\n([^\n])', r'====\n\n\1', prompt)
        prompt = re.sub(r'([^\n])\n====', r'\1\n\n====', prompt)

        return prompt