#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上下文提供者框架 — 参考 Cline 的 .clinerules 三层上下文注入设计

三层上下文架构：
1. Rules 层 — 行为规则与约束（全局 + 项目级 + 会话级）
2. Files 层 — 项目文件上下文（AGENTS.md / TOOLS.md / SOUL.md / .ts2rules/）
3. Others 层 — 动态上下文（学习状态、用户画像、外部注入器等）

参考 Cline 的 cline-rules.ts：
- 全局规则: ~/.ts2/rules/
- 项目规则: <workspace>/.ts2rules/
- 外部规则: 兼容 .cursorrules / .windsurfrules 等
- 条件规则: YAML frontmatter 中的条件判断
"""

import os
import re
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─── 数据结构 ────────────────────────────────────────────────

@dataclass
class ContextSection:
    """上下文段落"""
    source: str       # 来源标识（如 "global_rules", "project_agents_md"）
    label: str        # 显示标签（如 "全局规则", "项目导引"）
    content: str      # 段落内容
    priority: int = 0 # 优先级（越大越靠前）
    layer: str = "rules"  # 所属层: rules / files / others


@dataclass
class ContextBundle:
    """上下文包 — 聚合所有来源的上下文段落"""
    sections: List[ContextSection] = field(default_factory=list)

    def add(self, section: ContextSection):
        self.sections.append(section)

    def get_by_layer(self, layer: str) -> List[ContextSection]:
        return [s for s in self.sections if s.layer == layer]

    def to_prompt(self) -> str:
        """将所有段落组装为系统提示文本"""
        if not self.sections:
            return ""

        # 按层分组，层内按优先级排序
        layer_order = {"rules": 1, "files": 2, "others": 3}
        sorted_sections = sorted(
            self.sections,
            key=lambda s: (layer_order.get(s.layer, 99), -s.priority)
        )

        parts = []
        current_layer = None
        for section in sorted_sections:
            if section.layer != current_layer:
                layer_labels = {"rules": "规则与约束", "files": "项目上下文", "others": "动态上下文"}
                if current_layer is not None:
                    parts.append("")  # 层间空行
                parts.append(f"{'=' * 40}")
                parts.append(f"  {layer_labels.get(section.layer, '其他')} ({section.layer})")
                parts.append(f"{'=' * 40}")
                current_layer = section.layer
            parts.append(f"\n## {section.label}")
            parts.append(section.content)

        return "\n".join(parts)

    def to_injection(self) -> str:
        """生成注入到 system prompt 的文本（带标记注释）"""
        prompt = self.to_prompt()
        if not prompt:
            return ""
        return f"\n\n<!-- BEGIN_CONTEXT_SOURCES -->\n{prompt}\n<!-- END_CONTEXT_SOURCES -->"


# ─── 规则文件解析 ────────────────────────────────────────────

def _parse_yaml_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """解析 YAML frontmatter（如 Cline 的 parseYamlFrontmatter）

    Returns:
        (frontmatter_dict, body_content)
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    frontmatter_str = content[3:end].strip()
    body = content[end + 3:].strip()

    # 简易 YAML 解析（不引入 pyyaml 依赖）
    fm: Dict[str, Any] = {}
    for line in frontmatter_str.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # 布尔值
            if val.lower() in ("true", "yes"):
                fm[key] = True
            elif val.lower() in ("false", "no"):
                fm[key] = False
            else:
                fm[key] = val

    return fm, body


def _evaluate_conditionals(
    frontmatter: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    """评估条件规则（参考 Cline 的 evaluateRuleConditionals）

    支持的条件：
    - alwaysApply: true — 始终应用
    - globs: "*.py" — 文件匹配时应用
    - description: 描述文本（仅用于 UI 展示）
    """
    if not frontmatter:
        return True  # 无 frontmatter 则默认应用

    # alwaysApply 为 True 时始终应用
    if frontmatter.get("alwaysApply", False):
        return True

    # 无条件字段时默认应用
    has_condition = any(k in frontmatter for k in ("globs", "files", "paths", "when"))
    if not has_condition:
        return True

    # 有条件但无上下文时不应用（保守策略）
    ctx = context or {}
    if not ctx:
        return False

    # globs 匹配
    globs = frontmatter.get("globs", "")
    if globs:
        target = ctx.get("current_file", ctx.get("cwd", ""))
        if target:
            import fnmatch
            patterns = [p.strip() for p in globs.split(",")]
            for pattern in patterns:
                if fnmatch.fnmatch(target, pattern):
                    return True
        return False

    return True


# ─── 上下文提供者 ────────────────────────────────────────────

class ContextProvider:
    """
    上下文提供者 — 负责从各来源收集上下文并组装为 ContextBundle

    参考 Cline 的三层规则加载：
    1. 全局规则: ~/.ts2/rules/
    2. 项目规则: <workspace>/.ts2rules/
    3. 外部规则: .cursorrules / .windsurfrules / AGENTS.md
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root
        self._dynamic_providers: List[Callable[..., Optional[ContextSection]]] = []
        # 用户可控的上下文层开关和 token 预算覆盖
        self._enabled_layers: Optional[set] = None  # None=全部启用, set()=全部禁用
        self._token_budget_override: int = 0  # 0=使用默认, -1=无限制, >0=指定值

    def register_dynamic(self, provider: Callable[..., Optional[ContextSection]]):
        """注册动态上下文提供者（Others 层）

        Args:
            provider: callable(agent, user_input) -> Optional[ContextSection]
        """
        self._dynamic_providers.append(provider)

    # ─── Rules 层 ──────────────────────────────────────────

    def collect_rules(self, context: Optional[Dict] = None) -> List[ContextSection]:
        """收集所有规则上下文"""
        sections = []

        # 1. 全局规则: ~/.ts2/rules/
        global_sections = self._load_rules_from_dir(
            self._get_global_rules_dir(),
            source="global_rules",
            label_prefix="全局规则",
            context=context,
        )
        sections.extend(global_sections)

        # 2. 项目规则: <workspace>/.ts2rules/
        if self.workspace_root:
            project_sections = self._load_rules_from_dir(
                Path(self.workspace_root) / ".ts2rules",
                source="project_rules",
                label_prefix="项目规则",
                context=context,
            )
            sections.extend(project_sections)

            # 3. 兼容外部规则文件
            external_sections = self._load_external_rules(
                self.workspace_root, context=context,
            )
            sections.extend(external_sections)

        return sections

    def _get_global_rules_dir(self) -> Path:
        """获取全局规则目录"""
        return Path.home() / ".ts2" / "rules"

    def _load_rules_from_dir(
        self,
        rules_dir: Path,
        source: str,
        label_prefix: str,
        context: Optional[Dict] = None,
    ) -> List[ContextSection]:
        """从规则目录加载所有规则文件"""
        sections = []

        if not rules_dir.exists():
            return sections

        if rules_dir.is_dir():
            # 排除子目录（workflows/hooks/skills 是独立概念）
            excluded = {"workflows", "hooks", "skills", "cache"}
            for f in sorted(rules_dir.iterdir()):
                if f.name.startswith(".") or f.name in excluded:
                    continue
                if f.is_file() and f.suffix.lower() in (".md", ".txt", ".mdc"):
                    section = self._load_rule_file(f, source, label_prefix, context)
                    if section:
                        sections.append(section)
        elif rules_dir.is_file():
            section = self._load_rule_file(rules_dir, source, label_prefix, context)
            if section:
                sections.append(section)

        return sections

    def _load_rule_file(
        self,
        filepath: Path,
        source: str,
        label_prefix: str,
        context: Optional[Dict] = None,
    ) -> Optional[ContextSection]:
        """加载单个规则文件（支持 YAML frontmatter 条件判断）"""
        try:
            raw = filepath.read_text(encoding="utf-8").strip()
            if not raw:
                return None

            # 解析 frontmatter
            fm, body = _parse_yaml_frontmatter(raw)

            # 评估条件
            if not _evaluate_conditionals(fm, context):
                logger.debug(f"规则文件 {filepath.name} 条件不满足，跳过")
                return None

            content = body if body else raw
            return ContextSection(
                source=f"{source}:{filepath.name}",
                label=f"{label_prefix}/{filepath.stem}",
                content=content,
                priority=10,
                layer="rules",
            )
        except Exception as e:
            logger.debug(f"加载规则文件 {filepath} 失败: {e}")
            return None

    def _load_external_rules(
        self,
        workspace_root: str,
        context: Optional[Dict] = None,
    ) -> List[ContextSection]:
        """加载外部兼容规则文件（.cursorrules / .windsurfrules 等）"""
        sections = []
        root = Path(workspace_root)

        # .cursorrules
        cursor_rules = root / ".cursorrules"
        if cursor_rules.exists():
            try:
                content = cursor_rules.read_text(encoding="utf-8").strip()
                if content:
                    sections.append(ContextSection(
                        source="external:cursorrules",
                        label="Cursor 规则",
                        content=content,
                        priority=5,
                        layer="rules",
                    ))
            except Exception:
                pass

        # .cursor/rules/ 目录
        cursor_dir = root / ".cursor" / "rules"
        if cursor_dir.exists() and cursor_dir.is_dir():
            for f in sorted(cursor_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in (".md", ".mdc"):
                    section = self._load_rule_file(f, "external:cursor", "Cursor 规则", context)
                    if section:
                        sections.append(section)

        # .windsurfrules
        windsurf_rules = root / ".windsurfrules"
        if windsurf_rules.exists():
            try:
                content = windsurf_rules.read_text(encoding="utf-8").strip()
                if content:
                    sections.append(ContextSection(
                        source="external:windsurfrules",
                        label="Windsurf 规则",
                        content=content,
                        priority=5,
                        layer="rules",
                    ))
            except Exception:
                pass

        return sections

    # ─── Files 层 ──────────────────────────────────────────

    def collect_files(self) -> List[ContextSection]:
        """收集项目文件上下文"""
        sections = []

        if not self.workspace_root:
            return sections

        root = Path(self.workspace_root)

        # AGENTS.md — 项目导引
        agents_md = root / "AGENTS.md"
        if agents_md.exists():
            try:
                content = agents_md.read_text(encoding="utf-8").strip()
                if content:
                    sections.append(ContextSection(
                        source="file:agents_md",
                        label="项目导引 (AGENTS.md)",
                        content=content,
                        priority=20,
                        layer="files",
                    ))
            except Exception:
                pass

        # TOOLS.md — 工具说明
        tools_md = root / "TOOLS.md"
        if tools_md.exists():
            try:
                content = tools_md.read_text(encoding="utf-8").strip()
                if content:
                    sections.append(ContextSection(
                        source="file:tools_md",
                        label="工具说明 (TOOLS.md)",
                        content=content,
                        priority=15,
                        layer="files",
                    ))
            except Exception:
                pass

        # SOUL.md — 角色设定
        soul_md = root / "SOUL.md"
        if soul_md.exists():
            try:
                content = soul_md.read_text(encoding="utf-8").strip()
                if content:
                    sections.append(ContextSection(
                        source="file:soul_md",
                        label="角色设定 (SOUL.md)",
                        content=content,
                        priority=25,
                        layer="files",
                    ))
            except Exception:
                pass

        # .ts2_project.json — 项目元数据
        project_json = root / ".ts2_project.json"
        if project_json.exists():
            try:
                import json
                data = json.loads(project_json.read_text(encoding="utf-8"))
                if data:
                    # 只提取关键字段，避免注入过多
                    summary_parts = []
                    if data.get("name"):
                        summary_parts.append(f"项目: {data['name']}")
                    if data.get("description"):
                        summary_parts.append(f"描述: {data['description']}")
                    if data.get("domain"):
                        summary_parts.append(f"领域: {data['domain']}")
                    if summary_parts:
                        sections.append(ContextSection(
                            source="file:ts2_project",
                            label="项目元数据",
                            content="\n".join(summary_parts),
                            priority=5,
                            layer="files",
                        ))
            except Exception:
                pass

        # skills/ 目录
        skills_dir = root / "skills"
        if skills_dir.exists() and skills_dir.is_dir():
            for skill_dir in sorted(skills_dir.iterdir()):
                if skill_dir.is_dir():
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        try:
                            content = skill_md.read_text(encoding="utf-8").strip()
                            if content:
                                sections.append(ContextSection(
                                    source=f"file:skill:{skill_dir.name}",
                                    label=f"技能/{skill_dir.name}",
                                    content=content,
                                    priority=10,
                                    layer="files",
                                ))
                        except Exception:
                            pass

        return sections

    # ─── Others 层 ─────────────────────────────────────────

    def collect_others(
        self,
        agent: Any = None,
        user_input: str = "",
    ) -> List[ContextSection]:
        """收集动态上下文（Others 层）"""
        sections = []

        # 环境信息（当前日期等）— 始终注入，让 LLM 感知当前日期
        # （system-reminder 伪消息已在 _sanitize_messages 中被过滤，日期改由此处组织进 system 消息）
        try:
            from datetime import datetime
            today = datetime.now()
            sections.append(ContextSection(
                source="env:datetime",
                label="环境信息",
                content=f"当前日期: {today.strftime('%Y-%m-%d, %A')}",
                priority=100,
                layer="others",
            ))
        except Exception as e:
            logger.debug(f"环境信息注入失败: {e}")

        # 调用注册的动态提供者
        for provider in self._dynamic_providers:
            try:
                section = provider(agent, user_input)
                if section and isinstance(section, ContextSection):
                    sections.append(section)
                elif section and isinstance(section, str):
                    # 简化接口：返回字符串自动包装
                    sections.append(ContextSection(
                        source=f"dynamic:{provider.__name__}",
                        label=provider.__name__.replace("_", " ").title(),
                        content=section,
                        priority=0,
                        layer="others",
                    ))
            except Exception as e:
                logger.debug(f"动态上下文提供者 {provider.__name__} 失败: {e}")

        return sections

    # ─── 聚合 ──────────────────────────────────────────────

    def collect(
        self,
        context: Optional[Dict] = None,
        agent: Any = None,
        user_input: str = "",
        token_budget: int = 0,
    ) -> ContextBundle:
        """收集所有上下文并组装为 ContextBundle

        Args:
            token_budget: token 预算上限（0=无限制）。
                          粗略估算：4字符≈1token。
                          超出预算时按优先级裁剪低优先级段落。
        """
        # 应用用户覆盖的 token 预算
        if self._token_budget_override != 0:
            token_budget = self._token_budget_override if self._token_budget_override > 0 else 0

        # 确定启用的层
        enabled = self._enabled_layers  # None=全部启用

        bundle = ContextBundle()

        # Rules 层
        if enabled is None or "rules" in enabled:
            for section in self.collect_rules(context):
                bundle.add(section)

        # Files 层
        if enabled is None or "files" in enabled:
            for section in self.collect_files():
                bundle.add(section)

        # Others 层
        if enabled is None or "others" in enabled:
            for section in self.collect_others(agent, user_input):
                bundle.add(section)

        # Token 预算裁剪
        if token_budget > 0:
            bundle = self._trim_to_budget(bundle, token_budget)

        logger.debug(
            f"上下文收集完成: {len(bundle.sections)} 个段落 "
            f"(rules={len(bundle.get_by_layer('rules'))}, "
            f"files={len(bundle.get_by_layer('files'))}, "
            f"others={len(bundle.get_by_layer('others'))})"
        )

        return bundle

    def _trim_to_budget(self, bundle: ContextBundle, token_budget: int) -> ContextBundle:
        """按 token 预算裁剪上下文包

        策略：按优先级从低到高裁剪，直到总 token 在预算内。
        Rules 层优先级最高不会被裁剪，Others 层最先被裁剪。
        """
        # 估算当前 token
        total_chars = sum(len(s.content) for s in bundle.sections)
        total_tokens = total_chars // 4

        if total_tokens <= token_budget:
            return bundle

        # 按优先级排序（低优先级在前，先裁剪）
        sorted_sections = sorted(bundle.sections, key=lambda s: s.priority)

        trimmed = list(bundle.sections)
        for section in sorted_sections:
            if total_tokens <= token_budget:
                break
            # Rules 层不裁剪（priority >= 10 的不裁剪）
            if section.layer == "rules" and section.priority >= 10:
                continue
            # 裁剪低优先级段落
            section_tokens = len(section.content) // 4
            trimmed.remove(section)
            total_tokens -= section_tokens
            logger.debug(f"上下文裁剪: 移除 {section.label} ({section_tokens} tokens)")

        bundle.sections = trimmed
        return bundle


# ─── 便捷函数 ────────────────────────────────────────────────

def create_context_provider(workspace_root: Optional[str] = None) -> ContextProvider:
    """创建上下文提供者"""
    return ContextProvider(workspace_root=workspace_root)
