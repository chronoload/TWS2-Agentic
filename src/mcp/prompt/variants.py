#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型变体系统 — 参考 Cline 的 Variant 设计
不同模型族有不同提示配置：generic / next-gen / xs (小上下文)
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class ModelFamily(str, Enum):
    GENERIC = "generic"
    NEXT_GEN = "next-gen"
    XS = "xs"


@dataclass
class ConfigOverride:
    template: Optional[str] = None
    enabled: bool = True
    order: Optional[int] = None


@dataclass
class PromptVariant:
    id: str
    family: str
    version: int = 1
    description: str = ""
    tags: List[str] = field(default_factory=list)
    labels: Dict[str, int] = field(default_factory=dict)
    componentOrder: List[str] = field(default_factory=list)
    componentOverrides: Dict[str, Dict] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    baseTemplate: Optional[str] = None

    def get_component_override(self, section: str) -> Optional[ConfigOverride]:
        override = self.componentOverrides.get(section)
        if override:
            return ConfigOverride(**override)
        return None

    def is_component_enabled(self, section: str) -> bool:
        override = self.componentOverrides.get(section, {})
        return override.get("enabled", True)


DEFAULT_COMPONENT_ORDER = [
    "AGENT_ROLE",
    "TOOL_USE",
    "MCP",
    "EDITING_FILES",
    "ACT_VS_PLAN",
    "TODO",
    "CAPABILITIES",
    "FEEDBACK",
    "RULES",
    "SYSTEM_INFO",
    "OBJECTIVE",
    "USER_INSTRUCTIONS",
    "SKILLS",
]

BASE_TEMPLATE = """{{AGENT_ROLE}}

====

{{TOOL_USE}}

====

{{MCP}}

====

{{EDITING_FILES}}

====

{{ACT_VS_PLAN}}

====

{{TODO}}

====

{{CAPABILITIES}}

====

{{FEEDBACK}}

====

{{RULES}}

====

{{SYSTEM_INFO}}

====

{{OBJECTIVE}}

====

{{USER_INSTRUCTIONS}}

====

{{SKILLS}}"""


GENERIC_VARIANT = PromptVariant(
    id="generic",
    family=ModelFamily.GENERIC,
    version=1,
    description="通用回退提示，适用于大多数模型",
    tags=["stable", "fallback"],
    labels={"stable": 1, "fallback": 1},
    componentOrder=DEFAULT_COMPONENT_ORDER,
    componentOverrides={
        "FEEDBACK": {"enabled": False},
    },
    baseTemplate=BASE_TEMPLATE,
)

NEXT_GEN_VARIANT = PromptVariant(
    id="next-gen",
    family=ModelFamily.NEXT_GEN,
    version=1,
    description="为前沿模型优化的提示（Claude 4, GPT-4o, DeepSeek-V3 等）",
    tags=["next-gen", "advanced", "production"],
    labels={"production": 2, "advanced": 1},
    componentOrder=[
        "AGENT_ROLE",
        "TOOL_USE",
        "MCP",
        "EDITING_FILES",
        "ACT_VS_PLAN",
        "TODO",
        "CAPABILITIES",
        "FEEDBACK",
        "RULES",
        "SYSTEM_INFO",
        "OBJECTIVE",
        "USER_INSTRUCTIONS",
        "SKILLS",
    ],
    componentOverrides={},
    baseTemplate=BASE_TEMPLATE,
)

XS_VARIANT = PromptVariant(
    id="xs",
    family=ModelFamily.XS,
    version=1,
    description="为小上下文窗口模型优化的精简提示（Qwen, Ollama 等）",
    tags=["local", "compact", "xs"],
    labels={"compact": 1, "local": 1},
    componentOrder=[
        "AGENT_ROLE",
        "RULES",
        "EDITING_FILES",
        "OBJECTIVE",
        "SYSTEM_INFO",
        "USER_INSTRUCTIONS",
    ],
    componentOverrides={
        "TOOL_USE": {"enabled": False},
        "MCP": {"enabled": False},
        "CAPABILITIES": {"enabled": False},
        "FEEDBACK": {"enabled": False},
        "TODO": {"enabled": False},
        "SKILLS": {"enabled": False},
        "ACT_VS_PLAN": {"enabled": False},
        "AGENT_ROLE": {
            "template": "你是 WS2 Agent，一个 AI 学习助手。帮助管理课程、笔记和项目。"
        },
        "RULES": {
            "template": "RULES\n\n- 用中文回答\n- 使用工具完成任务\n- 保持简洁"
        },
    },
    baseTemplate=None,
)


class VariantRegistry:
    """提示变体注册表 — 参考 Cline 的 PromptRegistry"""

    def __init__(self):
        self._variants: Dict[str, PromptVariant] = {}
        self._default_family = ModelFamily.GENERIC

    def register(self, variant: PromptVariant):
        self._variants[variant.id] = variant

    def get(self, variant_id: str) -> Optional[PromptVariant]:
        return self._variants.get(variant_id)

    def get_by_family(self, family: str) -> Optional[PromptVariant]:
        for v in self._variants.values():
            if v.family == family:
                return v
        return self._variants.get("generic")

    def detect_model_family(self, model_id: str) -> str:
        model_lower = model_id.lower()

        next_gen_prefixes = [
            "gpt-4o", "gpt-4-turbo", "gpt-5", "o1", "o3", "o4",
            "claude-4", "claude-opus-4", "claude-sonnet-4",
            "deepseek-v3", "deepseek-r1",
            "gemini-2.5", "gemini-2.0-flash",
        ]
        for prefix in next_gen_prefixes:
            if model_lower.startswith(prefix):
                return ModelFamily.NEXT_GEN

        xs_prefixes = [
            "qwen", "llama", "mixtral", "mistral", "phi",
            "gemma", "codestral", "yi-", "baichuan",
        ]
        for prefix in xs_prefixes:
            if model_lower.startswith(prefix):
                return ModelFamily.XS

        return ModelFamily.GENERIC

    def get_for_model(self, model_id: str) -> PromptVariant:
        family = self.detect_model_family(model_id)
        return self.get_by_family(family) or self._variants["generic"]

    def list_variants(self) -> List[PromptVariant]:
        return list(self._variants.values())

    @property
    def variant_ids(self) -> List[str]:
        return list(self._variants.keys())


_registry = VariantRegistry()
_registry.register(GENERIC_VARIANT)
_registry.register(NEXT_GEN_VARIANT)
_registry.register(XS_VARIANT)


def get_variant_registry() -> VariantRegistry:
    return _registry