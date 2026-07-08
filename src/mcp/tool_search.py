#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具分组管理器 — 基于意图的动态工具过滤
核心组 + WS2基本组 始终发送，专业组按意图激活

所有工具名 → 分组的映射由前缀规则自动完成，无需手动维护工具列表。
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set

from .tools import Tool

logger = logging.getLogger(__name__)


# ── 前缀 → 分组规则 ────────────────────────────────────
# 工具名前缀匹配，自动将工具归入对应组
PREFIX_GROUP_RULES: List[Dict[str, Any]] = [
    # WS2 基本工具
    {
        "prefix": "ws2_",
        "group": "ws2",
        "label": "WS2 基本组",
        "always_active": True,
        "keywords": [],
    },
    # DataHub 工具
    {
        "prefix": "ws2_hub_",
        "group": "datahub",
        "label": "数据枢纽",
        "always_active": False,
        "keywords": ["hub", "rss", "爬取", "爬虫", "数据枢纽", "数据收集",
                      "crawl", "scrape", "订阅", "collection", "管道", "pipeline"],
    },
    # Scholar 工具
    {
        "prefix": "search_papers",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": ["论文", "paper", "doi", "scholar", "学术", "文献",
                      "biorxiv", "基因", "gene", "蛋白质", "protein", "预印本"],
    },
    {
        "prefix": "get_paper_",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "get_oa_",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "search_biorxiv",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "get_gene_",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "get_variant_",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "get_protein_",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "align_",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "get_citations",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "list_chinadoi",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "get_genome_",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "search_ngdc",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "get_earthquake_",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "fetch_arxiv",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    {
        "prefix": "resolve_datacite",
        "group": "scholar",
        "label": "学术搜索",
        "always_active": False,
        "keywords": [],
    },
    # Wolfram 工具
    {
        "prefix": "wolfram_",
        "group": "wolfram",
        "label": "Wolfram 数学",
        "always_active": False,
        "keywords": ["wolfram", "积分", "求导", "微分", "线性代数", "行列式",
                      "特征值", "统计", "分布", "绘图", "符号计算", "mathematica",
                      "integral", "derivative", "calculus", "algebra", "equation"],
    },
    # Lean4 工具
    {
        "prefix": "lean4_",
        "group": "lean4",
        "label": "Lean4 定理证明",
        "always_active": False,
        "keywords": ["lean4", "lean", "证明", "定理", "形式化", "形式验证",
                      "proof", "theorem", "tactic", "类型论"],
    },
    # Manim 工具
    {
        "prefix": "manim_",
        "group": "manim",
        "label": "Manim 动画",
        "always_active": False,
        "keywords": ["manim", "动画", "渲染", "数学动画", "3blue1brown",
                      "animation", "render", "scene"],
    },
    # MathLens 工具
    {
        "prefix": "mathlens_",
        "group": "mathlens",
        "label": "MathLens",
        "always_active": False,
        "keywords": ["mathlens", "数学分析", "可视化数学", "数学探索"],
    },
    # AutoResearch 工具
    {
        "prefix": "autoresearch_",
        "group": "autoresearch",
        "label": "AutoResearch",
        "always_active": False,
        "keywords": ["autoresearch", "自动研究", "文献综述", "研究综述",
                      "系统综述", "research"],
    },
    # 飞书工具
    {
        "prefix": "feishu_",
        "group": "feishu",
        "label": "飞书",
        "always_active": False,
        "keywords": ["飞书", "feishu", "lark", "多维表格", "飞书文档",
                      "飞书日历", "飞书消息"],
    },
    # GT 课程追踪
    {
        "prefix": "gt_",
        "group": "gt",
        "label": "GT 课程追踪",
        "always_active": False,
        "keywords": ["课程追踪", "gt agent", "学习追踪", "计时学习",
                      "番茄钟", "pomodoro"],
    },
    # MCP 远程服务工具（百度搜索等）
    {
        "prefix": "baidu_",
        "group": "mcp_service",
        "label": "MCP 远程服务",
        "always_active": True,
        "keywords": ["搜索", "百度", "baidu", "search", "联网", "网页",
                      "网络搜索", "最新", "新闻"],
    },
    # MCP 远程服务工具（博查搜索等）
    {
        "prefix": "bocha_",
        "group": "mcp_service",
        "label": "MCP 远程服务",
        "always_active": True,
        "keywords": ["搜索", "博查", "bocha", "search", "联网", "网页",
                      "网络搜索", "最新", "新闻"],
    },
]

# 核心工具名（始终发送）— 不依赖前缀，显式列出
CORE_TOOL_NAMES = {
    # 文件操作
    "read_file", "write_file", "edit_file", "search_files",
    "grep", "glob", "list_directory",
    "file_info", "diff_files", "move_file", "copy_file",
    "open_file",
    # 搜索
    "web_search", "fetch_url",
    # 计算
    "calculate", "analyze_paper",
    # 系统
    "cli_execute", "terminal_open",
    "config_manage",
    # 搜索型工具
    "search_configs", "search_skills", "search_documents", "search_mcp_tools",
    # RAG / Skill / MCP（单工具多 action）
    "rag_retrieval", "skill_manager", "mcp_client",
    # 沙箱
    "sandbox_execute",
    # 会话
    "session_manage",
    # 子Agent
    "sub_agent",
    # 工具组激活（LLM 主动激活专业工具组）
    "activate_tool_group",
    # 服务端工具（操作 Web 前端，全端可用）
    "ensure_server", "open_in_editor", "list_server_files", "read_server_file",
    "write_server_file", "switch_panel", "navigate_source",
}

# DataHub 高频工具（始终发送）
DATAHUB_CORE_PREFIX = "ws2_hub_"
DATAHUB_CORE_NAMES = {
    "ws2_hub_add_item", "ws2_hub_query_items", "ws2_hub_get_item",
    "ws2_hub_update_item", "ws2_hub_delete_item",
    "ws2_hub_list_rss", "ws2_hub_list_collections",
    "ws2_hub_fetch_url", "ws2_hub_parse_content",
    "ws2_hub_get_stats",
}


def _classify_tool(tool_name: str) -> str:
    """根据工具名前缀自动分类到组

    Returns:
        组名: "core" | "ws2" | "datahub_core" | "datahub_pro" |
              "scholar" | "wolfram" | "lean4" | "manim" | "mathlens" |
              "autoresearch" | "feishu" | "gt" | "other"
    """
    # 1. 核心工具
    if tool_name in CORE_TOOL_NAMES:
        return "core"

    # 2. DataHub 高频
    if tool_name in DATAHUB_CORE_NAMES:
        return "datahub_core"

    # 3. 按前缀匹配
    for rule in PREFIX_GROUP_RULES:
        if tool_name.startswith(rule["prefix"]):
            group = rule["group"]
            if group == "datahub":
                return "datahub_pro"
            if group == "ws2":
                return "ws2"
            return group

    return "other"


def _get_group_keywords(group_name: str) -> List[str]:
    """获取组的激活关键词"""
    for rule in PREFIX_GROUP_RULES:
        if rule["group"] == group_name:
            return rule.get("keywords", [])
    return []


def _get_group_label(group_name: str) -> str:
    """获取组的显示标签"""
    for rule in PREFIX_GROUP_RULES:
        if rule["group"] == group_name:
            return rule.get("label", group_name)
    labels = {
        "core": "核心工具",
        "ws2": "WS2 基本组",
        "datahub_core": "DataHub 高频",
        "datahub_pro": "DataHub 专业",
        "other": "其他",
    }
    return labels.get(group_name, group_name)


def _generate_summary(tool: Tool) -> str:
    """从工具的 description 自动生成一句话摘要"""
    desc = tool.description or ""
    # 取第一行或前 30 字符
    first_line = desc.split("\n")[0].strip()
    if len(first_line) > 40:
        return first_line[:37] + "..."
    return first_line or tool.name


class ToolGroupManager:
    """基于意图的工具分组管理器

    核心组 + WS2基本组 + DataHub高频组始终发送，专业组按用户意图激活。
    已激活的组在会话内保留（避免"用了又消失"）。

    工具分类完全自动：根据工具名前缀规则，无需手动维护列表。
    """

    def __init__(self, tools: List[Tool]):
        self._all_tools: Dict[str, Tool] = {t.name: t for t in tools} if tools else {}
        # 会话内已激活的组名
        self._activated_groups: Set[str] = set()
        # 会话内已使用过的工具名（确保不消失）
        self._used_tools: Set[str] = set()
        # 自动分类缓存
        self._tool_groups: Dict[str, str] = {}  # tool_name → group_name
        self._group_tools: Dict[str, Set[str]] = {}  # group_name → {tool_names}
        # 自动生成的摘要
        self._tool_summaries: Dict[str, str] = {}

        self._auto_classify()

    def _auto_classify(self):
        """自动将所有工具分类到组"""
        self._tool_groups.clear()
        self._group_tools.clear()
        self._tool_summaries.clear()

        for name, tool in self._all_tools.items():
            group = _classify_tool(name)
            self._tool_groups[name] = group
            if group not in self._group_tools:
                self._group_tools[group] = set()
            self._group_tools[group].add(name)
            self._tool_summaries[name] = _generate_summary(tool)

        # 日志输出分类结果
        for group, names in sorted(self._group_tools.items()):
            label = _get_group_label(group)
            logger.debug(f"工具组 [{group}] ({label}): {len(names)} 个工具")

    def activate_for_query(self, user_input: str) -> Set[str]:
        """根据用户输入激活意图组，返回本轮激活的组名集合"""
        input_lower = user_input.lower()
        newly_activated = set()

        for group_name in self._group_tools:
            if group_name in self._activated_groups:
                continue
            if group_name in ("core", "ws2", "datahub_core", "other"):
                continue  # 始终活跃的组无需激活

            keywords = _get_group_keywords(group_name)
            for kw in keywords:
                if kw in input_lower:
                    self._activated_groups.add(group_name)
                    newly_activated.add(group_name)
                    logger.info(f"意图激活工具组: {group_name} ({_get_group_label(group_name)}) — 关键词: {kw}")
                    break

        return newly_activated

    def activate_group(self, group_name: str) -> Dict[str, Any]:
        """主动激活指定工具组（供 LLM 调用）

        Args:
            group_name: 组名（如 'wolfram', 'lean4', 'manim' 等）

        Returns:
            激活结果，包含组信息和可用工具列表
        """
        # 检查组是否存在
        if group_name not in self._group_tools:
            # 尝试模糊匹配
            matched = None
            for existing_group in self._group_tools:
                label = _get_group_label(existing_group)
                if group_name in existing_group or group_name in label:
                    matched = existing_group
                    break
            if matched is None:
                available = ", ".join(
                    f"{g}({_get_group_label(g)})" for g in sorted(self._group_tools)
                )
                return {
                    "success": False,
                    "error": f"未知工具组: {group_name}",
                    "available_groups": available,
                }
            group_name = matched

        was_activated = group_name in self._activated_groups

        if not was_activated:
            self._activated_groups.add(group_name)
            logger.info(f"主动激活工具组: {group_name} ({_get_group_label(group_name)})")

        # 列出该组中实际存在的工具
        available_tools = [
            name for name in self._group_tools.get(group_name, set())
            if name in self._all_tools
        ]

        return {
            "success": True,
            "group": group_name,
            "label": _get_group_label(group_name),
            "was_already_active": was_activated,
            "tools_count": len(available_tools),
            "tools": available_tools,
        }

    def mark_tool_used(self, tool_name: str):
        """标记工具已使用，确保后续轮次保留"""
        self._used_tools.add(tool_name)
        # 如果工具属于某个专业组，自动激活该组
        group = self._tool_groups.get(tool_name)
        if group and group not in ("core", "ws2", "datahub_core", "other"):
            self._activated_groups.add(group)

    def get_active_tools(self) -> List[Tool]:
        """获取当前应发送的工具列表（核心+WS2+DataHub高频+始终活跃组+已激活组+已使用工具）"""
        active_names = set()

        # 1. 核心组
        active_names.update(self._group_tools.get("core", set()))

        # 2. WS2 基本组
        active_names.update(self._group_tools.get("ws2", set()))

        # 3. DataHub 高频组（始终发送）
        active_names.update(self._group_tools.get("datahub_core", set()))

        # 3.5 始终活跃的组（always_active=True 的前缀规则）
        for rule in PREFIX_GROUP_RULES:
            if rule.get("always_active"):
                group = rule["group"]
                active_names.update(self._group_tools.get(group, set()))

        # 4. 已激活的意图组
        for group_name in self._activated_groups:
            active_names.update(self._group_tools.get(group_name, set()))

        # 5. 已使用过的工具
        active_names.update(self._used_tools)

        # 过滤出实际存在的工具
        tools = []
        for name in active_names:
            if name in self._all_tools:
                tools.append(self._all_tools[name])

        return tools

    def get_active_tool_names(self) -> Set[str]:
        """获取当前活跃的工具名集合"""
        active_names = set()
        active_names.update(self._group_tools.get("core", set()))
        active_names.update(self._group_tools.get("ws2", set()))
        active_names.update(self._group_tools.get("datahub_core", set()))
        # 始终活跃的组
        for rule in PREFIX_GROUP_RULES:
            if rule.get("always_active"):
                active_names.update(self._group_tools.get(rule["group"], set()))
        for group_name in self._activated_groups:
            active_names.update(self._group_tools.get(group_name, set()))
        active_names.update(self._used_tools)
        return active_names

    def get_inactive_tool_summaries(self) -> Dict[str, str]:
        """获取未激活工具的摘要（用于 system prompt 中的能力概览）"""
        active = self.get_active_tool_names()
        summaries = {}
        for name, summary in self._tool_summaries.items():
            if name not in active and name in self._all_tools:
                summaries[name] = summary
        return summaries

    def get_group_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有组的状态信息（调试用）"""
        status = {}
        active_names = self.get_active_tool_names()

        for group_name, tool_names in self._group_tools.items():
            existing = [n for n in tool_names if n in self._all_tools]
            status[group_name] = {
                "label": _get_group_label(group_name),
                "activated": group_name in self._activated_groups or group_name in ("core", "ws2", "datahub_core", "other"),
                "total": len(existing),
                "tools": existing,
            }

        # 统计
        status["_summary"] = {
            "all_tools": len(self._all_tools),
            "active_tools": len([n for n in active_names if n in self._all_tools]),
            "activated_groups": list(self._activated_groups),
            "used_tools": list(self._used_tools),
        }

        return status

    def reset_session(self):
        """重置会话状态（新对话时调用）"""
        self._activated_groups.clear()
        self._used_tools.clear()

    def refresh(self, tools: List[Tool]):
        """刷新工具列表"""
        self._all_tools = {t.name: t for t in tools}
        self._auto_classify()


# ── 向后兼容 ──────────────────────────────────────────

class ToolSearchEngine:
    """向后兼容的包装器，委托给 ToolGroupManager"""

    def __init__(self, tools: List[Tool], max_tools: int = 15):
        self._manager = ToolGroupManager(tools)
        self._all_tools: Dict[str, Tool] = {t.name: t for t in tools} if tools else {}

    def search(self, query: str, top_k: int = None) -> List[Tool]:
        self._manager.activate_for_query(query)
        return self._manager.get_active_tools()

    def get_schemas_for_query(self, query: str) -> List[Dict]:
        self._manager.activate_for_query(query)
        tools = self._manager.get_active_tools()
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def refresh(self, tools: List[Tool]):
        self._manager.refresh(tools)
        self._all_tools = {t.name: t for t in tools}

    # 暴露内部 manager 供 Agent 使用
    @property
    def group_manager(self) -> ToolGroupManager:
        return self._manager
