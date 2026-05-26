#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提示构建器 — 参考 Cline 的 PromptBuilder 设计
编排组件构建、模板解析、最终组装
"""

from typing import Any, Dict, List, Optional
import logging

from .components import get_component_registry, PromptComponent
from .templates import TemplateEngine, STANDARD_PLACEHOLDERS
from .variants import PromptVariant, get_variant_registry

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    PromptBuilder 负责将组件组装成最终的系统提示
    参考 Cline 的 PromptBuilder.build() 流程：
    1. 构建所有组件
    2. 准备占位符值
    3. 解析模板
    4. 后处理
    """

    def __init__(self, variant: Optional[PromptVariant] = None,
                 context: Optional[Dict[str, Any]] = None):
        self.variant = variant
        self.context = context or {}
        self.template_engine = TemplateEngine()
        self.registry = get_component_registry()

    def build(self) -> str:
        if not self.variant:
            registry = get_variant_registry()
            model_id = self.context.get("model_id", "gpt-4o")
            self.variant = registry.get_for_model(model_id)
            logger.debug(f"自动选择变体: {self.variant.id} (模型: {model_id})")

        component_sections = self._build_components()

        placeholder_values = self._prepare_placeholders(component_sections)

        template = self.variant.baseTemplate

        if template:
            prompt = self.template_engine.resolve(template, placeholder_values)
        else:
            prompt = self._assemble_without_template(component_sections)

        return self.template_engine.post_process(prompt)

    def _build_components(self) -> Dict[str, str]:
        sections: Dict[str, str] = {}

        for component_id in self.variant.componentOrder:
            if not self.variant.is_component_enabled(component_id):
                continue

            component = self.registry.get(component_id)
            if not component:
                logger.warning(f"组件 '{component_id}' 未注册")
                continue

            try:
                result = component.generator(self.variant, self.context)
                if result and result.strip():
                    sections[component_id] = result
            except Exception as e:
                logger.warning(f"构建组件 '{component_id}' 失败: {e}")

        return sections

    def _prepare_placeholders(self,
                              component_sections: Dict[str, str]) -> Dict[str, str]:
        placeholders: Dict[str, str] = {}

        standard = self.template_engine.resolve_standard(self.context)
        placeholders.update(standard)

        for component_id, content in component_sections.items():
            placeholders[component_id] = content

        runtime = self.context.get("runtime_placeholders", {})
        if runtime:
            placeholders.update(runtime)

        return placeholders

    def _assemble_without_template(self,
                                    component_sections: Dict[str, str]) -> str:
        parts = []
        for component_id in self.variant.componentOrder:
            if component_id in component_sections:
                parts.append(component_sections[component_id])
        return "\n\n".join(parts)


def build_system_prompt(
    model_id: Optional[str] = None,
    variant_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs
) -> str:
    """便捷函数：构建系统提示"""
    ctx = context or {}
    ctx.update(kwargs)

    registry = get_variant_registry()

    if variant_id:
        variant = registry.get(variant_id)
    elif model_id:
        variant = registry.get_for_model(model_id)
    else:
        variant = registry.get_for_model(ctx.get("model_id", "generic"))

    if not variant:
        variant = registry.get("generic")

    ctx["model_id"] = model_id or ctx.get("model_id", "")

    builder = PromptBuilder(variant=variant, context=ctx)
    return builder.build()