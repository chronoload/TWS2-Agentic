#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 三模块联动核心管理器
科研分析、网络研探、网络爬虫 三大模块统一管理与联动
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
import urllib.parse
import uuid


class SynergyItem:
    """联动项目数据模型"""
    def __init__(self, data=None):
        self.id = str(uuid.uuid4())[:12]
        self.title = ""
        self.url = ""
        self.content = ""
        self.content_type = "unknown"  # webpage, paper, github_repo
        self.source = ""  # crawler, search, analysis, manual
        self.keywords = []
        self.tags = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        self.analysis = {}
        self.metadata = {}
        self.related = []  # 相关项目ID列表
        
        if data:
            self.load(data)
    
    def load(self, data):
        """从字典加载数据"""
        self.__dict__.update(data)
        if "id" not in data:
            self.id = str(uuid.uuid4())[:12]
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "content_type": self.content_type,
            "source": self.source,
            "keywords": self.keywords,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "analysis": self.analysis,
            "metadata": self.metadata,
            "related": self.related
        }


class SynergyManager:
    """WS2 三模块联动管理器"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.data_dir = base_dir / "synergy_data"
        self.data_dir.mkdir(exist_ok=True)
        
        self.items = {}
        self._load_items()
        
        # 回调函数（由主程序设置）
        self.on_item_added: Optional[Callable] = None
        self.on_item_updated: Optional[Callable] = None
        self.on_item_deleted: Optional[Callable] = None
    
    def _get_items_file(self) -> Path:
        """获取项目数据文件路径"""
        return self.data_dir / "synergy_items.json"
    
    def _load_items(self):
        """从文件加载项目"""
        items_file = self._get_items_file()
        if items_file.exists():
            try:
                data = json.loads(items_file.read_text(encoding="utf-8"))
                for item_data in data:
                    item = SynergyItem(item_data)
                    self.items[item.id] = item
            except Exception as e:
                print(f"加载联动项目失败: {e}")
    
    def _save_items(self):
        """保存项目到文件"""
        items_file = self._get_items_file()
        data = [item.to_dict() for item in self.items.values()]
        items_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def add_item(self, title: str, url: str = "", content: str = "", 
                 content_type: str = "webpage", source: str = "manual",
                 keywords: List[str] = None, tags: List[str] = None) -> SynergyItem:
        """添加新联动项目"""
        item = SynergyItem()
        item.title = title
        item.url = url
        item.content = content
        item.content_type = content_type
        item.source = source
        item.keywords = keywords or []
        item.tags = tags or []
        
        self.items[item.id] = item
        self._save_items()
        
        if self.on_item_added:
            self.on_item_added(item)
        
        return item
    
    def update_item(self, item_id: str, **kwargs) -> bool:
        """更新项目"""
        if item_id not in self.items:
            return False
        
        item = self.items[item_id]
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        item.updated_at = datetime.now().isoformat()
        self._save_items()
        
        if self.on_item_updated:
            self.on_item_updated(item)
        
        return True
    
    def delete_item(self, item_id: str) -> bool:
        """删除项目"""
        if item_id not in self.items:
            return False
        
        item = self.items[item_id]
        del self.items[item_id]
        self._save_items()
        
        if self.on_item_deleted:
            self.on_item_deleted(item)
        
        return True
    
    def get_item(self, item_id: str) -> Optional[SynergyItem]:
        """获取项目"""
        return self.items.get(item_id)
    
    def get_all_items(self, sort_by: str = "updated_at") -> List[SynergyItem]:
        """获取所有项目（可排序）"""
        items = list(self.items.values())
        if sort_by == "updated_at":
            items.sort(key=lambda x: x.updated_at, reverse=True)
        elif sort_by == "created_at":
            items.sort(key=lambda x: x.created_at, reverse=True)
        elif sort_by == "title":
            items.sort(key=lambda x: x.title.lower())
        return items
    
    def search_items(self, query: str) -> List[SynergyItem]:
        """搜索项目"""
        query = query.lower()
        results = []
        for item in self.items.values():
            if (query in item.title.lower() or 
                query in item.content.lower() or
                any(query in kw.lower() for kw in item.keywords) or
                any(query in tag.lower() for tag in item.tags)):
                results.append(item)
        return results
    
    def get_items_by_source(self, source: str) -> List[SynergyItem]:
        """按来源获取项目"""
        return [item for item in self.items.values() if item.source == source]
    
    def get_items_by_type(self, content_type: str) -> List[SynergyItem]:
        """按类型获取项目"""
        return [item for item in self.items.values() if item.content_type == content_type]
    
    def tag_item(self, item_id: str, tag: str) -> bool:
        """为项目添加标签"""
        item = self.get_item(item_id)
        if not item:
            return False
        
        if tag not in item.tags:
            item.tags.append(tag)
            self.update_item(item_id, tags=item.tags)
        
        return True
    
    def untag_item(self, item_id: str, tag: str) -> bool:
        """移除标签"""
        item = self.get_item(item_id)
        if not item:
            return False
        
        if tag in item.tags:
            item.tags.remove(tag)
            self.update_item(item_id, tags=item.tags)
        
        return True
    
    def link_items(self, item_id1: str, item_id2: str) -> bool:
        """关联两个项目"""
        item1 = self.get_item(item_id1)
        item2 = self.get_item(item_id2)
        
        if not item1 or not item2:
            return False
        
        if item_id2 not in item1.related:
            item1.related.append(item_id2)
            self.update_item(item_id1, related=item1.related)
        
        if item_id1 not in item2.related:
            item2.related.append(item_id1)
            self.update_item(item_id2, related=item2.related)
        
        return True
    
    def clear_items(self):
        """清空所有项目"""
        self.items = {}
        self._save_items()
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            "total_items": len(self.items),
            "source_distribution": {
                "crawler": len(self.get_items_by_source("crawler")),
                "search": len(self.get_items_by_source("search")),
                "analysis": len(self.get_items_by_source("analysis")),
                "manual": len(self.get_items_by_source("manual"))
            },
            "type_distribution": {
                "webpage": len(self.get_items_by_type("webpage")),
                "paper": len(self.get_items_by_type("paper")),
                "github_repo": len(self.get_items_by_type("github_repo"))
            },
            "tags_collected": list(set(tag for item in self.items.values() for tag in item.tags))
        }


# ========== 快速方法（便于其他模块导入） ==========

# 全局管理器实例（在主程序中初始化）
_g_synergy_manager: Optional[SynergyManager] = None


def init_synergy_manager(base_dir: Path) -> SynergyManager:
    """初始化联动管理器"""
    global _g_synergy_manager
    _g_synergy_manager = SynergyManager(base_dir)
    return _g_synergy_manager


def get_synergy_manager() -> Optional[SynergyManager]:
    """获取联动管理器"""
    return _g_synergy_manager


def add_from_crawler(title: str, url: str, content: str, **kwargs) -> Optional[SynergyItem]:
    """从爬虫模块添加项目（自动路由到 DataHub）"""
    try:
        from ws2_data_hub import get_data_hub, SourceType
        hub = get_data_hub()
        if hub:
            hub.pipeline_crawl_to_hub(url=url, title=title, content=content,
                                       keywords=kwargs.get("keywords"))
    except ImportError:
        pass
    if not _g_synergy_manager:
        return None
    return _g_synergy_manager.add_item(
        title=title, url=url, content=content, source="crawler", **kwargs
    )


def add_from_search(title: str, url: str, **kwargs) -> Optional[SynergyItem]:
    """从网络研探模块添加项目（自动路由到 DataHub）"""
    try:
        from ws2_data_hub import get_data_hub
        hub = get_data_hub()
        if hub:
            hub.pipeline_bookmark_to_hub(name=title, url=url,
                                          category=kwargs.get("category", ""),
                                          description=kwargs.get("description", ""))
    except ImportError:
        pass
    if not _g_synergy_manager:
        return None
    return _g_synergy_manager.add_item(
        title=title, url=url, source="search", **kwargs
    )


def add_from_analysis(title: str, content: str, **kwargs) -> Optional[SynergyItem]:
    """从科研分析模块添加项目（自动路由到 DataHub）"""
    try:
        from ws2_data_hub import get_data_hub
        hub = get_data_hub()
        if hub:
            hub.pipeline_analysis_to_hub(title=title, content=content,
                                          keywords=kwargs.get("keywords"))
    except ImportError:
        pass
    if not _g_synergy_manager:
        return None
    return _g_synergy_manager.add_item(
        title=title,
        content=content,
        source="analysis",
        content_type="paper",
        **kwargs
    )


def send_to_analysis(item_id: str) -> Optional[Dict]:
    """发送项目到科研分析模块，返回需要的数据"""
    if not _g_synergy_manager:
        return None
    item = _g_synergy_manager.get_item(item_id)
    if not item:
        return None
    return {
        "title": item.title,
        "url": item.url,
        "content": item.content,
        "keywords": item.keywords
    }


def send_to_crawler(item_id: str) -> Optional[str]:
    """发送项目到爬虫模块，返回 URL"""
    if not _g_synergy_manager:
        return None
    item = _g_synergy_manager.get_item(item_id)
    if not item or not item.url:
        return None
    return item.url


def send_to_search(item_id: str) -> Optional[str]:
    """发送项目到网络研探，返回搜索关键词"""
    if not _g_synergy_manager:
        return None
    item = _g_synergy_manager.get_item(item_id)
    if not item:
        return None
    # 组合标题和关键词作为搜索词
    keywords = item.keywords[:3] if item.keywords else []
    search_query = " ".join([item.title] + keywords)
    return search_query
