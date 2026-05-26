#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 DataHub MCP 工具集
让 Agent 可以直接调用 DataHub 的所有功能
包括数据项 CRUD、RSS 管理、数据集合、数据管道、统计

所有工具继承 WS2BaseTool，通过 get_data_hub() 访问核心
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .tools import Tool, ToolResult
from .ws2_tools import WS2BaseTool

logger = logging.getLogger(__name__)


def _get_hub():
    from ws2_data_hub import get_data_hub
    return get_data_hub()


def _hub_check():
    try:
        hub = _get_hub()
    except Exception as e:
        return None, f"DataHub 导入失败: {e}"
    if not hub:
        return None, "DataHub 未初始化，请先打开数据枢纽界面或调用 init_data_hub"
    return hub, None


# ============================================================
# 1. 数据项 CRUD 工具
# ============================================================

class HubAddItemTool(WS2BaseTool):
    name = "ws2_hub_add_item"
    description = "向数据枢纽添加新数据项。支持指定来源类型(crawler/rss/agent/bookmark/analysis/manual/local_file)和项目类型(webpage/paper/github_repo/rss_entry/bookmark/note/file/analysis_result)"
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "标题"},
            "url": {"type": "string", "description": "URL（可选）", "default": ""},
            "content": {"type": "string", "description": "内容（可选）", "default": ""},
            "summary": {"type": "string", "description": "摘要（可选）", "default": ""},
            "source_type": {"type": "string", "description": "来源类型: crawler/rss/agent/bookmark/analysis/manual/local_file", "default": "manual"},
            "item_type": {"type": "string", "description": "项目类型: webpage/paper/github_repo/rss_entry/bookmark/note/file/analysis_result", "default": "webpage"},
            "tags": {"type": "string", "description": "标签，逗号分隔（可选）", "default": ""},
            "keywords": {"type": "string", "description": "关键词，逗号分隔（可选）", "default": ""},
        },
        "required": ["title"]
    }

    def execute(self, title: str = "", url: str = "", content: str = "",
                summary: str = "", source_type: str = "manual",
                item_type: str = "webpage", tags: str = "",
                keywords: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        from ws2_data_hub import HubItem
        item = HubItem(
            title=title, url=url, content=content, summary=summary,
            source_type=source_type, item_type=item_type,
            tags=[t.strip() for t in tags.split(",") if t.strip()],
            keywords=[k.strip() for k in keywords.split(",") if k.strip()],
        )
        result = hub.add_item(item)
        data = result.to_dict()
        msg = f"✅ 已添加数据项: {title} (ID: {result.id}, 来源: {source_type})"
        return self._make_result(True, data, msg)


class HubQueryItemsTool(WS2BaseTool):
    name = "ws2_hub_query_items"
    description = "查询数据枢纽中的数据项。支持按来源类型、项目类型、标签、星标、未读、关键词搜索等条件过滤"
    parameters = {
        "type": "object",
        "properties": {
            "source_type": {"type": "string", "description": "按来源过滤: crawler/rss/agent/bookmark/analysis/manual/local_file", "default": ""},
            "item_type": {"type": "string", "description": "按类型过滤: webpage/paper/github_repo/rss_entry/bookmark/note/file/analysis_result", "default": ""},
            "tag": {"type": "string", "description": "按标签过滤", "default": ""},
            "starred_only": {"type": "boolean", "description": "仅星标项", "default": False},
            "unread_only": {"type": "boolean", "description": "仅未读项", "default": False},
            "search": {"type": "string", "description": "搜索关键词（标题/内容/摘要）", "default": ""},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 50},
            "offset": {"type": "integer", "description": "偏移量", "default": 0},
        },
    }

    def execute(self, source_type: str = "", item_type: str = "", tag: str = "",
                starred_only: bool = False, unread_only: bool = False,
                search: str = "", limit: int = 50, offset: int = 0) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        items = hub.query_items(
            source_type=source_type or None,
            item_type=item_type or None,
            tag=tag or None,
            starred_only=starred_only,
            unread_only=unread_only,
            search=search or None,
            limit=limit, offset=offset
        )
        data = {
            "count": len(items),
            "items": [{"id": i.id, "title": i.title, "url": i.url,
                       "source_type": i.source_type, "item_type": i.item_type,
                       "tags": i.tags, "is_starred": i.is_starred, "is_read": i.is_read,
                       "pipeline_stage": getattr(i, 'pipeline_stage', None),
                       "quality_score": getattr(i, 'quality_score', None),
                       "updated_at": i.updated_at} for i in items]
        }
        msg = f"📋 查询结果: {len(items)} 项"
        if source_type:
            msg += f" (来源: {source_type})"
        if search:
            msg += f" (搜索: {search})"
        return self._make_result(True, data, msg)


class HubGetItemTool(WS2BaseTool):
    name = "ws2_hub_get_item"
    description = "获取数据枢纽中单个数据项的完整详情"
    parameters = {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "数据项ID"},
        },
        "required": ["item_id"]
    }

    def execute(self, item_id: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        item = hub.get_item(item_id)
        if not item:
            return self._make_result(False, {}, error=f"未找到数据项: {item_id}")

        data = item.to_dict()
        msg = f"📄 数据项详情: {item.title} (ID: {item.id})"
        return self._make_result(True, data, msg)


class HubUpdateItemTool(WS2BaseTool):
    name = "ws2_hub_update_item"
    description = "更新数据枢纽中的数据项。可更新标题、内容、标签、星标、已读状态、关联项等"
    parameters = {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "数据项ID"},
            "title": {"type": "string", "description": "新标题（可选）", "default": ""},
            "content": {"type": "string", "description": "新内容（可选）", "default": ""},
            "summary": {"type": "string", "description": "新摘要（可选）", "default": ""},
            "tags": {"type": "string", "description": "新标签，逗号分隔（可选）", "default": ""},
            "related_ids": {"type": "string", "description": "关联项ID，逗号分隔（可选，替换式）", "default": ""},
            "is_starred": {"type": "boolean", "description": "星标状态（可选）", "default": None},
            "is_read": {"type": "boolean", "description": "已读状态（可选）", "default": None},
            "is_archived": {"type": "boolean", "description": "归档状态（可选）", "default": None},
        },
        "required": ["item_id"]
    }

    def execute(self, item_id: str = "", title: str = "", content: str = "",
                summary: str = "", tags: str = "", related_ids: str = "",
                is_starred=None, is_read=None, is_archived=None) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        kwargs = {}
        if title:
            kwargs["title"] = title
        if content:
            kwargs["content"] = content
        if summary:
            kwargs["summary"] = summary
        if tags:
            kwargs["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if related_ids:
            kwargs["related_ids"] = [rid.strip() for rid in related_ids.split(",") if rid.strip()]
        if is_starred is not None:
            kwargs["is_starred"] = is_starred
        if is_read is not None:
            kwargs["is_read"] = is_read
        if is_archived is not None:
            kwargs["is_archived"] = is_archived

        if not kwargs:
            return self._make_result(False, {}, error="未提供任何更新字段")

        success = hub.update_item(item_id, **kwargs)
        if not success:
            return self._make_result(False, {}, error=f"更新失败，未找到数据项: {item_id}")

        msg = f"✅ 已更新数据项: {item_id} ({', '.join(kwargs.keys())})"
        return self._make_result(True, {"updated_fields": list(kwargs.keys())}, msg)


class HubDeleteItemTool(WS2BaseTool):
    name = "ws2_hub_delete_item"
    description = "删除数据枢纽中的数据项"
    parameters = {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "数据项ID"},
        },
        "required": ["item_id"]
    }

    def execute(self, item_id: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        success = hub.delete_item(item_id)
        if not success:
            return self._make_result(False, {}, error=f"删除失败，未找到数据项: {item_id}")

        return self._make_result(True, {"deleted_id": item_id}, f"🗑️ 已删除数据项: {item_id}")


# ============================================================
# 2. RSS 管理工具
# ============================================================

class HubAddRSSTool(WS2BaseTool):
    name = "ws2_hub_add_rss"
    description = "添加 RSS 订阅源到数据枢纽"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "RSS 订阅源 URL"},
            "title": {"type": "string", "description": "订阅源标题（可选）", "default": ""},
            "category": {"type": "string", "description": "分类（可选）", "default": ""},
            "poll_interval_minutes": {"type": "integer", "description": "轮询间隔（分钟）", "default": 60},
        },
        "required": ["url"]
    }

    def execute(self, url: str = "", title: str = "", category: str = "",
                poll_interval_minutes: int = 60) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        from ws2_data_hub import RSSSubscription
        sub = RSSSubscription(
            url=url, title=title, category=category,
            poll_interval_minutes=poll_interval_minutes
        )
        result = hub.add_rss_subscription(sub)
        data = {"id": result.id, "url": result.url, "title": result.title}
        msg = f"📡 已添加 RSS 订阅: {title or url} (ID: {result.id})"
        return self._make_result(True, data, msg)


class HubRemoveRSSTool(WS2BaseTool):
    name = "ws2_hub_remove_rss"
    description = "移除数据枢纽中的 RSS 订阅源"
    parameters = {
        "type": "object",
        "properties": {
            "sub_id": {"type": "string", "description": "RSS 订阅源 ID"},
        },
        "required": ["sub_id"]
    }

    def execute(self, sub_id: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        success = hub.remove_rss_subscription(sub_id)
        if not success:
            return self._make_result(False, {}, error=f"移除失败，未找到订阅: {sub_id}")

        return self._make_result(True, {"removed_id": sub_id}, f"🗑️ 已移除 RSS 订阅: {sub_id}")


class HubListRSSTool(WS2BaseTool):
    name = "ws2_hub_list_rss"
    description = "列出数据枢纽中所有 RSS 订阅源"
    parameters = {
        "type": "object",
        "properties": {
            "active_only": {"type": "boolean", "description": "仅显示活跃订阅", "default": False},
        },
    }

    def execute(self, active_only: bool = False) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        subs = hub.get_rss_subscriptions(active_only=active_only)
        data = {
            "count": len(subs),
            "subscriptions": [
                {"id": s.id, "title": s.title, "url": s.url,
                 "category": s.category, "active": s.active,
                 "last_polled": s.last_polled, "poll_interval_minutes": s.poll_interval_minutes}
                for s in subs
            ]
        }
        msg = f"📡 RSS 订阅列表: {len(subs)} 个"
        return self._make_result(True, data, msg)


class HubPollRSSTool(WS2BaseTool):
    name = "ws2_hub_poll_rss"
    description = "轮询 RSS 订阅源获取新条目。可轮询单个订阅或所有活跃订阅"
    parameters = {
        "type": "object",
        "properties": {
            "sub_id": {"type": "string", "description": "RSS 订阅源 ID（为空则轮询所有）", "default": ""},
        },
    }

    def execute(self, sub_id: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        if sub_id:
            new_items = hub.poll_rss_feed(sub_id)
            data = {"sub_id": sub_id, "new_count": len(new_items),
                    "new_items": [{"id": i.id, "title": i.title, "url": i.url} for i in new_items[:20]]}
            msg = f"📡 RSS 轮询完成: {sub_id} → {len(new_items)} 条新内容"
        else:
            results = hub.poll_all_rss_feeds()
            data = {"results": results}
            total_new = sum(v for v in results.values() if v > 0)
            msg = f"📡 RSS 全量轮询完成: {len(results)} 个源, {total_new} 条新内容"
        return self._make_result(True, data, msg)


# ============================================================
# 3. 数据集合工具
# ============================================================

class HubCreateCollectionTool(WS2BaseTool):
    name = "ws2_hub_create_collection"
    description = "创建数据集合（类似文件夹/播放列表），用于组织和分组数据项"
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "集合标题"},
            "description": {"type": "string", "description": "集合描述（可选）", "default": ""},
            "tags": {"type": "string", "description": "标签，逗号分隔（可选）", "default": ""},
        },
        "required": ["title"]
    }

    def execute(self, title: str = "", description: str = "", tags: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        from ws2_data_hub import DataCollection
        coll = DataCollection(
            title=title, description=description,
            tags=[t.strip() for t in tags.split(",") if t.strip()]
        )
        result = hub.create_collection(coll)
        data = {"id": result.id, "title": result.title}
        msg = f"📁 已创建数据集合: {title} (ID: {result.id})"
        return self._make_result(True, data, msg)


class HubAddToCollectionTool(WS2BaseTool):
    name = "ws2_hub_add_to_collection"
    description = "将数据项添加到数据集合中"
    parameters = {
        "type": "object",
        "properties": {
            "collection_id": {"type": "string", "description": "集合 ID"},
            "item_id": {"type": "string", "description": "数据项 ID"},
        },
        "required": ["collection_id", "item_id"]
    }

    def execute(self, collection_id: str = "", item_id: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        success = hub.add_to_collection(collection_id, item_id)
        if not success:
            return self._make_result(False, {}, error="添加失败，集合或数据项不存在")

        return self._make_result(True, {}, f"✅ 已将数据项 {item_id} 添加到集合 {collection_id}")


class HubListCollectionsTool(WS2BaseTool):
    name = "ws2_hub_list_collections"
    description = "列出数据枢纽中所有数据集合"
    parameters = {
        "type": "object",
        "properties": {},
    }

    def execute(self) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        colls = hub.get_collections()
        data = {
            "count": len(colls),
            "collections": [
                {"id": c.id, "title": c.title, "description": c.description,
                 "item_count": len(c.item_ids), "tags": c.tags}
                for c in colls
            ]
        }
        msg = f"📁 数据集合列表: {len(colls)} 个"
        return self._make_result(True, data, msg)


# ============================================================
# 4. 数据管道工具
# ============================================================

class HubPipelineCrawlTool(WS2BaseTool):
    name = "ws2_hub_pipeline_crawl"
    description = "数据管道：将爬虫结果导入数据枢纽"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "爬取的 URL"},
            "title": {"type": "string", "description": "标题（可选）", "default": ""},
            "content": {"type": "string", "description": "内容（可选）", "default": ""},
            "keywords": {"type": "string", "description": "关键词，逗号分隔（可选）", "default": ""},
        },
        "required": ["url"]
    }

    def execute(self, url: str = "", title: str = "", content: str = "",
                keywords: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        item = hub.pipeline_crawl_to_hub(url=url, title=title, content=content, keywords=kw_list)
        data = {"id": item.id, "title": item.title, "url": item.url}
        msg = f"🔄 管道导入(爬虫→枢纽): {title or url} (ID: {item.id})"
        return self._make_result(True, data, msg)


class HubPipelineBookmarkTool(WS2BaseTool):
    name = "ws2_hub_pipeline_bookmark"
    description = "数据管道：将书签导入数据枢纽"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "书签名称"},
            "url": {"type": "string", "description": "书签 URL"},
            "category": {"type": "string", "description": "分类（可选）", "default": ""},
            "description": {"type": "string", "description": "描述（可选）", "default": ""},
        },
        "required": ["name", "url"]
    }

    def execute(self, name: str = "", url: str = "", category: str = "",
                description: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        item = hub.pipeline_bookmark_to_hub(name=name, url=url, category=category, description=description)
        data = {"id": item.id, "title": item.title, "url": item.url}
        msg = f"🔖 管道导入(书签→枢纽): {name} (ID: {item.id})"
        return self._make_result(True, data, msg)


class HubPipelineAnalysisTool(WS2BaseTool):
    name = "ws2_hub_pipeline_analysis"
    description = "数据管道：将分析结果导入数据枢纽"
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "分析结果标题"},
            "content": {"type": "string", "description": "分析内容"},
            "keywords": {"type": "string", "description": "关键词，逗号分隔（可选）", "default": ""},
        },
        "required": ["title", "content"]
    }

    def execute(self, title: str = "", content: str = "", keywords: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        item = hub.pipeline_analysis_to_hub(title=title, content=content, keywords=kw_list)
        data = {"id": item.id, "title": item.title}
        msg = f"🔬 管道导入(分析→枢纽): {title} (ID: {item.id})"
        return self._make_result(True, data, msg)


class HubPipelineLocalTool(WS2BaseTool):
    name = "ws2_hub_pipeline_local"
    description = "数据管道：将本地文件导入数据枢纽"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "本地文件路径"},
            "title": {"type": "string", "description": "标题（可选，默认为文件名）", "default": ""},
        },
        "required": ["file_path"]
    }

    def execute(self, file_path: str = "", title: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        try:
            item = hub.pipeline_local_file_to_hub(file_path=file_path, title=title)
            data = {"id": item.id, "title": item.title, "url": item.url}
            msg = f"📂 管道导入(本地→枢纽): {title or file_path} (ID: {item.id})"
            return self._make_result(True, data, msg)
        except FileNotFoundError as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 5. 书签爬取管道工具
# ============================================================

class HubBookmarkCrawlTool(WS2BaseTool):
    name = "ws2_hub_bookmark_crawl"
    description = "以书签URL为爬虫起始点，抓取网页内容并自动回流到数据枢纽。支持单个书签爬取或批量爬取所有书签"
    parameters = {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "要爬取的书签数据项ID（为空则批量爬取所有书签）", "default": ""},
            "source_type": {"type": "string", "description": "批量爬取时的来源类型过滤", "default": "bookmark"},
            "limit": {"type": "integer", "description": "批量爬取数量限制", "default": 20},
        },
    }

    def execute(self, item_id: str = "", source_type: str = "bookmark",
                limit: int = 20) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        if item_id:
            result = hub.pipeline_bookmark_crawl(item_id)
            if result:
                data = {"id": result.id, "title": result.title,
                        "content_length": len(result.content)}
                msg = f"🕷️ 书签爬取完成: {result.title} ({len(result.content)} 字符)"
                return self._make_result(True, data, msg)
            else:
                return self._make_result(False, {}, error="爬取失败，数据项不存在或URL无效")
        else:
            results = hub.pipeline_crawl_bookmarks_batch(source_type=source_type, limit=limit)
            msg = (f"🕷️ 批量书签爬取完成\n"
                   f"✅ 成功: {results['crawled']}\n"
                   f"❌ 失败: {results['failed']}\n"
                   f"⏭️ 跳过: {results['skipped']}")
            return self._make_result(True, results, msg)


# ============================================================
# 6. RSS 制作法工具
# ============================================================

class HubGenerateRSSTool(WS2BaseTool):
    name = "ws2_hub_generate_rss"
    description = "RSS制作法：从数据枢纽中的数据项生成RSS 2.0 XML feed。可按集合、来源类型或标签筛选"
    parameters = {
        "type": "object",
        "properties": {
            "collection_id": {"type": "string", "description": "按集合ID筛选（可选）", "default": ""},
            "source_type": {"type": "string", "description": "按来源类型筛选（可选）", "default": ""},
            "tag": {"type": "string", "description": "按标签筛选（可选）", "default": ""},
            "limit": {"type": "integer", "description": "最大条目数", "default": 50},
            "feed_title": {"type": "string", "description": "Feed标题", "default": "WS2 DataHub Feed"},
            "feed_description": {"type": "string", "description": "Feed描述（可选）", "default": ""},
            "save_to_file": {"type": "string", "description": "保存到文件路径（可选，不填则仅返回XML）", "default": ""},
        },
    }

    def execute(self, collection_id: str = "", source_type: str = "",
                tag: str = "", limit: int = 50,
                feed_title: str = "WS2 DataHub Feed",
                feed_description: str = "",
                save_to_file: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        kwargs = {
            "collection_id": collection_id or None,
            "source_type": source_type or None,
            "tag": tag or None,
            "limit": limit,
            "feed_title": feed_title,
            "feed_description": feed_description,
        }

        if save_to_file:
            feed_xml = hub.export_rss_feed_to_file(save_to_file, **kwargs)
            data = {"file": save_to_file, "size": len(feed_xml)}
            msg = f"📡 RSS feed已导出: {save_to_file} ({len(feed_xml)} 字符)"
        else:
            feed_xml = hub.generate_rss_feed(**kwargs)
            data = {"xml_length": len(feed_xml), "preview": feed_xml[:2000]}
            msg = f"📡 RSS feed已生成 ({len(feed_xml)} 字符)"

        if not feed_xml:
            return self._make_result(False, {}, error="生成RSS失败，无匹配数据项")

        return self._make_result(True, data, msg)


# ============================================================
# 7. 内容解析工具
# ============================================================

class HubParseContentTool(WS2BaseTool):
    name = "ws2_hub_parse_content"
    description = "解析数据枢纽中数据项的内容。支持auto自动检测、html转文本、json解析、markdown结构提取、url_list提取URL、keywords提取关键词"
    parameters = {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "数据项ID"},
            "parser": {"type": "string", "description": "解析器: auto/html/json/markdown/url_list/keywords", "default": "auto"},
        },
        "required": ["item_id"]
    }

    def execute(self, item_id: str = "", parser: str = "auto") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        result = hub.parse_item_content(item_id, parser=parser)
        if "error" in result:
            return self._make_result(False, {}, error=result["error"])

        msg = f"🔍 内容解析完成: {item_id} (解析器: {result['parser']})"
        return self._make_result(True, result, msg)


class HubFetchUrlTool(WS2BaseTool):
    name = "ws2_hub_fetch_url"
    description = "抓取URL内容并导入数据枢纽。自动获取网页纯文本内容，存入枢纽后可被其他工具解析"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的URL"},
            "title": {"type": "string", "description": "标题（可选，默认为URL）", "default": ""},
            "source_type": {"type": "string", "description": "来源类型", "default": "crawler"},
            "tags": {"type": "string", "description": "标签，逗号分隔（可选）", "default": ""},
        },
        "required": ["url"]
    }

    def execute(self, url: str = "", title: str = "", source_type: str = "crawler",
                tags: str = "") -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        content = hub.fetch_url_content(url)
        if not content:
            return self._make_result(False, {}, error=f"无法获取URL内容: {url}")

        from ws2_data_hub import HubItem, ItemType
        item = HubItem(
            title=title or url, url=url, content=content,
            summary=content[:500], source_type=source_type,
            item_type=ItemType.WEBPAGE.value,
            tags=[t.strip() for t in tags.split(",") if t.strip()],
        )
        result = hub.add_item(item)
        data = {"id": result.id, "title": result.title,
                "content_length": len(content), "url": url}
        msg = f"🌐 URL抓取并导入: {title or url} ({len(content)} 字符, ID: {result.id})"
        return self._make_result(True, data, msg)


# ============================================================
# 5. 统计工具
# ============================================================

class HubGetStatsTool(WS2BaseTool):
    name = "ws2_hub_get_stats"
    description = "获取数据枢纽的统计信息，包括总项目数、来源分布、类型分布、RSS订阅数、集合数等"
    parameters = {
        "type": "object",
        "properties": {},
    }

    def execute(self) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        stats = hub.get_statistics()
        msg = (
            f"📊 数据枢纽统计\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 总项目: {stats['total_items']}\n"
            f"⭐ 星标: {stats['starred']}\n"
            f"📩 未读: {stats['unread']}\n"
            f"📡 RSS源: {stats['rss_subscriptions']}\n"
            f"📁 集合: {stats['collections']}\n"
            f"🔄 管道阶段: {json.dumps(stats.get('pipeline_stages', {}), ensure_ascii=False)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"来源分布: {json.dumps(stats['source_distribution'], ensure_ascii=False)}\n"
            f"类型分布: {json.dumps(stats['type_distribution'], ensure_ascii=False)}"
        )
        return self._make_result(True, stats, msg)


class HubAutoScanTool(WS2BaseTool):
    name = "ws2_hub_auto_scan"
    description = "自动扫描CourseTracker中所有已知数据源并导入数据枢纽。包括网络探研书签(bookmarks.json)、WebAnalyseII已爬取页面(pages_index.json)、课程资源索引(resource_index.json)、工作流数据(workflow.db)。也可作为反馈管道的Scan阶段使用"
    parameters = {
        "type": "object",
        "properties": {},
    }

    def execute(self) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        results = hub.auto_scan_all_sources()
        total = sum(results.values())
        details = " | ".join(f"{k}:{v}" for k, v in results.items() if v > 0)
        msg = f"🔍 自动扫描完成: {total}项新数据 [{details}]"
        return self._make_result(True, results, msg)


# ============================================================
# 8. 反馈管道控制工具
# ============================================================

class HubRunPipelineTool(WS2BaseTool):
    name = "ws2_hub_run_pipeline"
    description = "手动触发数据枢纽的六阶段反馈管道(Scan→Ingest→Enrich→Filter→Update→SyncBack)。管道会自动扫描数据源、爬取空内容项、质量评分、更新过期内容、同步回源系统"
    parameters = {
        "type": "object",
        "properties": {
            "stage": {"type": "string", "description": "指定运行单个阶段(scan/enrich/filter/update/syncback)，为空则运行完整管道", "default": ""},
            "enrich_limit": {"type": "integer", "description": "Enrich阶段最大爬取数量", "default": 20},
            "update_max_age_hours": {"type": "integer", "description": "Update阶段内容过期阈值(小时)", "default": 24},
        },
    }

    def execute(self, stage: str = "", enrich_limit: int = 20,
                update_max_age_hours: int = 24) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        engine = hub.get_pipeline_engine()

        if stage:
            stage_map = {
                "scan": lambda: engine._stage_scan(),
                "enrich": lambda: engine._stage_enrich(limit=enrich_limit),
                "filter": lambda: engine._stage_filter(),
                "update": lambda: engine._stage_update(max_age_hours=update_max_age_hours),
                "syncback": lambda: engine._stage_syncback(),
            }
            if stage not in stage_map:
                return self._make_result(False, {}, error=f"未知阶段: {stage}，可选: scan/enrich/filter/update/syncback")
            result = stage_map[stage]()
            msg = f"🔄 管道阶段 [{stage}] 执行完成"
            return self._make_result(True, result, msg)
        else:
            result = engine.run_full_pipeline()
            msg = (
                f"🔄 完整管道执行完成\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"阶段结果: {json.dumps(result, ensure_ascii=False, default=str)}"
            )
            return self._make_result(True, result, msg)


class HubPipelineStatusTool(WS2BaseTool):
    name = "ws2_hub_pipeline_status"
    description = "查看数据枢纽反馈管道的运行状态，包括管道是否运行中、运行次数、上次运行时间、各阶段统计"
    parameters = {
        "type": "object",
        "properties": {},
    }

    def execute(self) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        status = hub.get_pipeline_status()
        stage_stats = hub.get_pipeline_stage_stats()
        data = {**status, "stage_stats": stage_stats}
        msg = (
            f"🔄 管道状态\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"运行中: {'是' if status.get('running') else '否'}\n"
            f"运行次数: {status.get('run_count', 0)}\n"
            f"上次运行: {status.get('last_run_time', '无')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"阶段统计: {json.dumps(stage_stats, ensure_ascii=False, default=str)}"
        )
        return self._make_result(True, data, msg)


class HubLightweightCrawlTool(WS2BaseTool):
    name = "ws2_hub_lightweight_crawl"
    description = "轻度爬取URL获取元信息(标题/描述/关键词)和RSS/Atom订阅链接，不下载全文。适合快速探测网站并发现订阅源"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要探测的URL地址",
            },
            "discover_feeds": {
                "type": "boolean",
                "description": "是否自动将发现的订阅源导入RSS订阅(默认false)",
                "default": False,
            },
        },
        "required": ["url"],
    }

    def execute(self, url: str = "", discover_feeds: bool = False) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        info = hub.lightweight_crawl(url)
        data = {
            "url": info.get("url", ""),
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "keywords": info.get("keywords", []),
            "author": info.get("author", ""),
            "feeds": info.get("feeds", []),
            "links_count": len(info.get("links", [])),
            "status": info.get("status", 0),
        }

        if discover_feeds and info.get("feeds"):
            count = hub.import_discovered_subscriptions(
                [{"url": f["url"], "type": f.get("type", "rss"), "title": f.get("title", "")} for f in info["feeds"]]
            )
            data["imported_feeds"] = count

        msg = f"探测 {url[:50]}: 标题={data['title'][:30]}, 订阅源={len(data['feeds'])}, 链接={data['links_count']}"
        if discover_feeds and data.get("imported_feeds"):
            msg += f", 已导入{data['imported_feeds']}个订阅"
        return self._make_result(True, data, msg)


class HubDiscoverSubscriptionsTool(WS2BaseTool):
    name = "ws2_hub_discover_subscriptions"
    description = "从数据枢纽中的书签/网页URL批量发现RSS/Atom订阅源。轻度爬取每个URL的<head>区域，提取<link rel=alternate>订阅链接"
    parameters = {
        "type": "object",
        "properties": {
            "source_type": {
                "type": "string",
                "description": "从哪种来源的URL中探测(bookmark/crawler/rss/agent)",
                "default": "bookmark",
            },
            "limit": {
                "type": "integer",
                "description": "最多探测多少个URL",
                "default": 20,
            },
            "auto_import": {
                "type": "boolean",
                "description": "是否自动将发现的订阅源导入RSS订阅(默认false)",
                "default": False,
            },
        },
    }

    def execute(self, source_type: str = "bookmark", limit: int = 20,
                auto_import: bool = False) -> str:
        hub, err = _hub_check()
        if err:
            return self._make_result(False, {}, error=err)

        subs = hub.discover_subscriptions(source_type=source_type, limit=limit)
        data = {
            "discovered": len(subs),
            "subscriptions": subs,
        }

        if auto_import and subs:
            count = hub.import_discovered_subscriptions(subs)
            data["imported"] = count

        msg = f"发现 {len(subs)} 个订阅源(来源={source_type}, 探测={limit}个URL)"
        if auto_import and subs:
            msg += f", 已导入{data['imported']}个"
        return self._make_result(True, data, msg)


def get_hub_tools(base_dir=None) -> List[Tool]:
    """获取所有 DataHub 工具"""
    common_kwargs = {
        "ws2_system": None,
        "project_manager": None,
        "task_board_manager": None,
        "base_dir": base_dir,
    }

    return [
        HubAddItemTool(**common_kwargs),
        HubQueryItemsTool(**common_kwargs),
        HubGetItemTool(**common_kwargs),
        HubUpdateItemTool(**common_kwargs),
        HubDeleteItemTool(**common_kwargs),
        HubAddRSSTool(**common_kwargs),
        HubRemoveRSSTool(**common_kwargs),
        HubListRSSTool(**common_kwargs),
        HubPollRSSTool(**common_kwargs),
        HubCreateCollectionTool(**common_kwargs),
        HubAddToCollectionTool(**common_kwargs),
        HubListCollectionsTool(**common_kwargs),
        HubPipelineCrawlTool(**common_kwargs),
        HubPipelineBookmarkTool(**common_kwargs),
        HubPipelineAnalysisTool(**common_kwargs),
        HubPipelineLocalTool(**common_kwargs),
        HubBookmarkCrawlTool(**common_kwargs),
        HubGenerateRSSTool(**common_kwargs),
        HubParseContentTool(**common_kwargs),
        HubFetchUrlTool(**common_kwargs),
        HubAutoScanTool(**common_kwargs),
        HubLightweightCrawlTool(**common_kwargs),
        HubDiscoverSubscriptionsTool(**common_kwargs),
        HubRunPipelineTool(**common_kwargs),
        HubPipelineStatusTool(**common_kwargs),
        HubGetStatsTool(**common_kwargs),
    ]
