#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 书签管理器 - 自动爬取书签内容和RSS订阅
功能：
- 书签分类管理
- 自动爬取书签网页内容
- RSS订阅解析和推送
- 智能过滤机制
- AI分析和项目创建
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib
import threading
import time
import re
from html import unescape
import urllib.request
import urllib.error
import ssl
import feedparser
from bs4 import BeautifulSoup


@dataclass
class Bookmark:
    """书签数据模型"""
    id: str
    url: str
    title: str
    category: str = "默认"
    sub_category: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    favicon: str = ""
    last_fetched: Optional[str] = None
    content_hash: str = ""
    is_rss: bool = False
    rss_items: List[Dict] = field(default_factory=list)
    fetched_content: str = ""
    created_at: str = ""
    priority: int = 0
    
    @property
    def display_title(self) -> str:
        if self.sub_category:
            return f"{self.title} [{self.sub_category}]"
        return self.title


@dataclass
class RSSItem:
    """RSS条目"""
    title: str
    link: str
    description: str
    pub_date: Optional[str] = None
    author: str = ""
    content: str = ""


class ContentFilter:
    """内容过滤器 - 防止内存爆炸"""
    
    def __init__(self):
        self.max_content_length = 50000
        self.max_items_per_source = 20
        self.blocked_domains: Set[str] = set()
        self.blocked_patterns: List[str] = []
        self.min_content_length = 100
        self.max_age_days = 7
        
    def should_store_content(self, content: str) -> bool:
        """判断内容是否应该存储"""
        if len(content) < self.min_content_length:
            return False
        if len(content) > self.max_content_length:
            content = content[:self.max_content_length]
        return True
    
    def is_domain_blocked(self, url: str) -> bool:
        """检查域名是否被屏蔽"""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            return domain in self.blocked_domains
        except:
            return False
    
    def extract_keywords(self, text: str, max_keywords: int = 20) -> List[str]:
        """提取关键词"""
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        english_words = re.findall(r'[a-zA-Z]{3,}', text)
        
        keywords = []
        chinese_word_freq = {}
        for chars in chinese_chars:
            for word in chars:
                chinese_word_freq[word] = chinese_word_freq.get(word, 0) + 1
        
        keywords.extend([w for w, c in sorted(chinese_word_freq.items(), key=lambda x: -x[1])[:max_keywords//2]])
        
        english_freq = {}
        for word in english_words:
            w = word.lower()
            english_freq[w] = english_freq.get(w, 0) + 1
        
        keywords.extend([w for w, c in sorted(english_freq.items(), key=lambda x: -x[1])[:max_keywords//2]])
        
        return keywords[:max_keywords]
    
    def clean_html(self, html: str) -> str:
        """清理HTML，提取纯文本"""
        soup = BeautifulSoup(html, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator=' ', strip=True)
        return unescape(text)
    
    def generate_hash(self, content: str) -> str:
        """生成内容哈希"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()


class BookmarkManager:
    """书签管理器核心类"""
    
    def __init__(self, base_path: str, project_mgr=None):
        self.base_path = Path(base_path)
        self.data_dir = self.base_path / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        self.bookmarks_file = self.data_dir / "bookmarks.json"
        self.settings_file = self.data_dir / "bookmark_settings.json"
        
        self.bookmarks: Dict[str, Bookmark] = {}
        self.categories: Dict[str, List[str]] = {}
        self.filter = ContentFilter()
        self.project_mgr = project_mgr
        
        self.load_bookmarks()
        self.load_settings()
        
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
    
    def load_bookmarks(self):
        """加载书签"""
        if self.bookmarks_file.exists():
            try:
                with open(self.bookmarks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for bm_data in data.get('bookmarks', []):
                        bm = Bookmark(**bm_data)
                        self.bookmarks[bm.id] = bm
                    self.categories = data.get('categories', {})
            except Exception as e:
                print(f"加载书签失败: {e}")
    
    def save_bookmarks(self):
        """保存书签"""
        data = {
            'bookmarks': [vars(bm) for bm in self.bookmarks.values()],
            'categories': self.categories
        }
        try:
            with open(self.bookmarks_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存书签失败: {e}")
    
    def load_settings(self):
        """加载设置"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.filter.max_content_length = settings.get('max_content_length', 50000)
                    self.filter.max_items_per_source = settings.get('max_items_per_source', 20)
                    self.filter.blocked_domains = set(settings.get('blocked_domains', []))
                    self.filter.blocked_patterns = settings.get('blocked_patterns', [])
                    self.filter.max_age_days = settings.get('max_age_days', 7)
            except Exception as e:
                print(f"加载设置失败: {e}")
    
    def save_settings(self):
        """保存设置"""
        settings = {
            'max_content_length': self.filter.max_content_length,
            'max_items_per_source': self.filter.max_items_per_source,
            'blocked_domains': list(self.filter.blocked_domains),
            'blocked_patterns': self.filter.blocked_patterns,
            'max_age_days': self.filter.max_age_days
        }
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存设置失败: {e}")
    
    def add_bookmark(self, url: str, title: str, category: str = "默认", 
                    sub_category: str = "", description: str = "", is_rss: bool = False) -> Bookmark:
        """添加书签"""
        bm_id = hashlib.md5(url.encode()).hexdigest()[:12]
        
        if bm_id in self.bookmarks:
            return self.bookmarks[bm_id]
        
        bookmark = Bookmark(
            id=bm_id,
            url=url,
            title=title,
            category=category,
            sub_category=sub_category,
            description=description,
            is_rss=is_rss,
            created_at=datetime.now().isoformat()
        )
        
        self.bookmarks[bm_id] = bookmark
        self._update_categories(bookmark)
        self.save_bookmarks()
        
        return bookmark
    
    def _update_categories(self, bookmark: Bookmark):
        """更新分类"""
        if bookmark.category not in self.categories:
            self.categories[bookmark.category] = []
        if bookmark.sub_category and bookmark.sub_category not in self.categories[bookmark.category]:
            self.categories[bookmark.category].append(bookmark.sub_category)
    
    def fetch_bookmark_content(self, bookmark: Bookmark) -> Optional[str]:
        """爬取书签内容"""
        if self.filter.is_domain_blocked(bookmark.url):
            return None
        
        try:
            req = urllib.request.Request(
                bookmark.url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            with urllib.request.urlopen(req, timeout=10, context=self.ctx) as response:
                html = response.read().decode('utf-8', errors='ignore')
                content = self.filter.clean_html(html)
                
                if self.filter.should_store_content(content):
                    bookmark.fetched_content = content
                    bookmark.content_hash = self.filter.generate_hash(content)
                    bookmark.last_fetched = datetime.now().isoformat()
                    return content
                else:
                    return None
                    
        except Exception as e:
            print(f"抓取失败 {bookmark.url}: {e}")
            return None
    
    def fetch_rss_feed(self, bookmark: Bookmark) -> List[RSSItem]:
        """解析RSS订阅"""
        if not bookmark.is_rss:
            return []
        
        try:
            feed = feedparser.parse(bookmark.url)
            items = []
            
            for entry in feed.entries[:self.filter.max_items_per_source]:
                item = RSSItem(
                    title=entry.get('title', ''),
                    link=entry.get('link', ''),
                    description=self.filter.clean_html(entry.get('summary', '')),
                    pub_date=entry.get('published', ''),
                    author=entry.get('author', ''),
                    content=self.filter.clean_html(entry.get('content', [{}])[0].get('value', ''))
                )
                items.append(item)
            
            bookmark.rss_items = [
                {
                    'title': item.title,
                    'link': item.link,
                    'description': item.description[:500],
                    'pub_date': item.pub_date
                }
                for item in items
            ]
            bookmark.last_fetched = datetime.now().isoformat()
            
            return items
            
        except Exception as e:
            print(f"RSS解析失败 {bookmark.url}: {e}")
            return []
    
    def fetch_all(self, progress_callback=None) -> Dict[str, int]:
        """批量抓取所有书签"""
        results = {'success': 0, 'failed': 0, 'skipped': 0}
        total = len(self.bookmarks)
        
        for i, bookmark in enumerate(self.bookmarks.values()):
            if progress_callback:
                progress_callback(i + 1, total)
            
            if bookmark.is_rss:
                items = self.fetch_rss_feed(bookmark)
                if items:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            else:
                content = self.fetch_bookmark_content(bookmark)
                if content:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            
            time.sleep(0.5)
        
        self.save_bookmarks()
        return results
    
    def summarize_all(self) -> str:
        """一键汇总所有书签信息"""
        summary_lines = [
            f"# 📚 书签汇总报告",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"总计书签: {len(self.bookmarks)} 个",
            f"RSS订阅: {sum(1 for bm in self.bookmarks.values() if bm.is_rss)} 个",
            "",
        ]
        
        for category, subs in sorted(self.categories.items()):
            category_bookmarks = [bm for bm in self.bookmarks.values() if bm.category == category]
            
            summary_lines.append(f"## 📁 {category} ({len(category_bookmarks)})")
            
            for sub in sorted(subs):
                sub_bookmarks = [bm for bm in category_bookmarks if bm.sub_category == sub]
                summary_lines.append(f"### 📂 {sub} ({len(sub_bookmarks)})")
                for bm in sub_bookmarks:
                    summary_lines.append(f"- [{bm.title}]({bm.url})")
                summary_lines.append("")
            
            no_sub = [bm for bm in category_bookmarks if not bm.sub_category]
            if no_sub:
                summary_lines.append(f"### 📄 未分类 ({len(no_sub)})")
                for bm in no_sub:
                    summary_lines.append(f"- [{bm.title}]({bm.url})")
                summary_lines.append("")
        
        summary_lines.extend([
            "## 🔥 热门内容",
            ""
        ])
        
        rss_bookmarks = [bm for bm in self.bookmarks.values() if bm.is_rss and bm.rss_items]
        for bm in rss_bookmarks[:5]:
            summary_lines.append(f"### 📰 {bm.title}")
            for item in bm.rss_items[:3]:
                summary_lines.append(f"- [{item['title']}]({item['link']})")
            summary_lines.append("")
        
        return "\n".join(summary_lines)
    
    def get_all_content_for_analysis(self) -> str:
        """获取所有内容用于AI分析"""
        contents = []
        
        for bookmark in self.bookmarks.values():
            content = []
            content.append(f"## {bookmark.title}")
            content.append(f"URL: {bookmark.url}")
            content.append(f"分类: {bookmark.category} / {bookmark.sub_category}")
            
            if bookmark.description:
                content.append(f"描述: {bookmark.description}")
            
            if bookmark.is_rss and bookmark.rss_items:
                content.append("RSS最新内容:")
                for item in bookmark.rss_items[:5]:
                    content.append(f"- {item['title']}: {item['description'][:200]}")
            elif bookmark.fetched_content:
                content.append(f"内容摘要: {bookmark.fetched_content[:1000]}")
            
            contents.append("\n".join(content))
        
        return "\n\n".join(contents)


class BookmarkManagerWindow:
    """书签管理器窗口"""
    
    def __init__(self, parent, base_path: str, project_mgr=None, embedded: bool = False):
        self.parent = parent
        self.embedded = embedded
        self.manager = BookmarkManager(base_path, project_mgr)
        
        if embedded:
            self.window = parent  # 嵌入式模式下，window 指向 parent
            self._create_ui()
        else:
            self.window = tk.Toplevel(parent)
            self.window.title("📚 书签管理器")
            self.window.geometry("1000x700")
            self._create_ui()
        
        self._refresh_tree()
    
    def _create_ui(self):
        """创建UI"""
        if self.embedded:
            main_frame = ttk.Frame(self.parent, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
        else:
            main_frame = ttk.Frame(self.window, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 顶部工具栏
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(toolbar_frame, text="➕ 添加书签", 
                  command=self._add_bookmark).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_frame, text="📰 添加RSS", 
                  command=self._add_rss).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_frame, text="🔄 抓取全部", 
                  command=self._fetch_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_frame, text="📊 汇总报告", 
                  command=self._generate_summary).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_frame, text="🧹 清理过期", 
                  command=self._cleanup_old).pack(side=tk.LEFT, padx=2)
        
        # 搜索框
        search_frame = ttk.Frame(toolbar_frame)
        search_frame.pack(side=tk.RIGHT, padx=2)
        ttk.Label(search_frame, text="🔍").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self._filter_tree())
        ttk.Entry(search_frame, textvariable=self.search_var, width=20).pack(side=tk.LEFT)
        
        # 分割面板
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # 左侧：书签树
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(tree_frame, columns=("category", "type"), show="tree")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        
        # 右侧：详情面板
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        
        self.detail_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD)
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        self.detail_text.config(state=tk.DISABLED)
        
        # 底部按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="✏️ 编辑", command=self._edit_bookmark).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑️ 删除", command=self._delete_bookmark).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🔗 打开链接", command=self._open_url).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🤖 AI分析", command=self._analyze_with_ai).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📁 创建项目", command=self._create_project).pack(side=tk.LEFT, padx=2)
        
        self.status_label = ttk.Label(btn_frame, text=f"共 {len(self.manager.bookmarks)} 个书签", 
                                     relief=tk.SUNKEN)
        self.status_label.pack(side=tk.RIGHT)
    
    def _refresh_tree(self):
        """刷新树视图"""
        self.tree.delete(*self.tree.get_children())
        
        for category in sorted(self.manager.categories.keys()):
            cat_id = self.tree.insert("", "end", text=f"📁 {category}", values=(category, "category"))
            
            subs = sorted(self.manager.categories[category])
            for sub in subs:
                sub_id = self.tree.insert(cat_id, "end", text=f"📂 {sub}", 
                                        values=(sub, "sub_category"))
                bookmarks = [bm for bm in self.manager.bookmarks.values() 
                           if bm.category == category and bm.sub_category == sub]
                for bm in bookmarks:
                    icon = "📰" if bm.is_rss else "🔗"
                    self.tree.insert(sub_id, "end", text=f"{icon} {bm.title}", 
                                   values=(bm.id, "bookmark"))
            
            no_sub = [bm for bm in self.manager.bookmarks.values() 
                     if bm.category == category and not bm.sub_category]
            if no_sub:
                for bm in no_sub:
                    icon = "📰" if bm.is_rss else "🔗"
                    self.tree.insert(cat_id, "end", text=f"{icon} {bm.title}", 
                                   values=(bm.id, "bookmark"))
        
        self.status_label.config(text=f"共 {len(self.manager.bookmarks)} 个书签")
    
    def _filter_tree(self):
        """过滤树视图"""
        search_text = self.search_var.get().lower()
        if not search_text:
            self._refresh_tree()
            return
        
        self.tree.delete(*self.tree.get_children())
        
        for bookmark in self.manager.bookmarks.values():
            if (search_text in bookmark.title.lower() or 
                search_text in bookmark.url.lower() or
                search_text in bookmark.description.lower()):
                icon = "📰" if bookmark.is_rss else "🔗"
                self.tree.insert("", "end", text=f"{icon} {bookmark.title}", 
                               values=(bookmark.id, "bookmark"))
    
    def _on_tree_double_click(self, event):
        """双击树节点"""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_type = self.tree.item(item, "values")[1]
        
        if item_type == "bookmark":
            bookmark_id = self.tree.item(item, "values")[0]
            self._show_bookmark_detail(bookmark_id)
    
    def _show_bookmark_detail(self, bookmark_id: str):
        """显示书签详情"""
        if bookmark_id not in self.manager.bookmarks:
            return
        
        bookmark = self.manager.bookmarks[bookmark_id]
        
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete(1.0, tk.END)
        
        content = [
            f"# {bookmark.title}",
            f"",
            f"## 基本信息",
            f"- **分类**: {bookmark.category} / {bookmark.sub_category or '未分类'}",
            f"- **URL**: {bookmark.url}",
            f"- **类型**: {'📰 RSS订阅' if bookmark.is_rss else '🔗 网页书签'}",
            f"- **创建时间**: {bookmark.created_at}",
            f"- **最后抓取**: {bookmark.last_fetched or '从未抓取'}",
            f"",
        ]
        
        if bookmark.description:
            content.append(f"## 描述")
            content.append(bookmark.description)
            content.append("")
        
        if bookmark.is_rss and bookmark.rss_items:
            content.append("## 📰 最新内容")
            for item in bookmark.rss_items[:10]:
                content.append(f"### {item['title']}")
                content.append(f"链接: {item['link']}")
                if item['pub_date']:
                    content.append(f"发布时间: {item['pub_date']}")
                if item['description']:
                    content.append(f"摘要: {item['description'][:300]}")
                content.append("")
        elif bookmark.fetched_content:
            content.append("## 📄 内容摘要")
            content.append(bookmark.fetched_content[:2000])
        
        self.detail_text.insert(tk.END, "\n".join(content))
        self.detail_text.config(state=tk.DISABLED)
    
    def _add_bookmark(self):
        """添加书签"""
        dialog = BookmarkEditDialog(self.window, "添加书签")
        if dialog.result:
            self.manager.add_bookmark(**dialog.result)
            self._refresh_tree()
    
    def _add_rss(self):
        """添加RSS订阅"""
        dialog = BookmarkEditDialog(self.window, "添加RSS订阅", is_rss=True)
        if dialog.result:
            self.manager.add_bookmark(is_rss=True, **dialog.result)
            self._refresh_tree()
    
    def _edit_bookmark(self):
        """编辑书签"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要编辑的书签")
            return
        
        item = selection[0]
        item_type = self.tree.item(item, "values")[1]
        
        if item_type != "bookmark":
            return
        
        bookmark_id = self.tree.item(item, "values")[0]
        bookmark = self.manager.bookmarks.get(bookmark_id)
        
        if bookmark:
            dialog = BookmarkEditDialog(self.window, "编辑书签", bookmark=bookmark)
            if dialog.result:
                for key, value in dialog.result.items():
                    setattr(bookmark, key, value)
                self.manager.save_bookmarks()
                self._refresh_tree()
    
    def _delete_bookmark(self):
        """删除书签"""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_type = self.tree.item(item, "values")[1]
        
        if item_type != "bookmark":
            return
        
        bookmark_id = self.tree.item(item, "values")[0]
        
        if messagebox.askyesno("确认", "确定要删除这个书签吗？"):
            del self.manager.bookmarks[bookmark_id]
            self.manager.save_bookmarks()
            self._refresh_tree()
    
    def _open_url(self):
        """打开链接"""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_type = self.tree.item(item, "values")[1]
        
        if item_type == "bookmark":
            bookmark_id = self.tree.item(item, "values")[0]
            bookmark = self.manager.bookmarks.get(bookmark_id)
            if bookmark:
                import webbrowser
                webbrowser.open(bookmark.url)
    
    def _fetch_all(self):
        """批量抓取"""
        def fetch_thread():
            def progress(current, total):
                self.status_label.config(text=f"正在抓取: {current}/{total}")
            
            results = self.manager.fetch_all(progress)
            self.window.after(0, lambda: (
                self.status_label.config(text=f"完成: 成功{results['success']}个, 失败{results['failed']}个"),
                self._refresh_tree()
            ))
        
        threading.Thread(target=fetch_thread, daemon=True).start()
    
    def _generate_summary(self):
        """生成汇总报告"""
        summary = self.manager.summarize_all()
        
        save_path = filedialog.asksaveasfilename(
            title="保存汇总报告",
            defaultextension=".md",
            filetypes=[("Markdown文件", "*.md"), ("文本文件", "*.txt")]
        )
        
        if save_path:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            messagebox.showinfo("成功", f"报告已保存到: {save_path}")
    
    def _cleanup_old(self):
        """清理过期内容"""
        count = 0
        cutoff = datetime.now() - timedelta(days=self.manager.filter.max_age_days)
        
        for bookmark in list(self.manager.bookmarks.values()):
            if bookmark.last_fetched:
                fetch_time = datetime.fromisoformat(bookmark.last_fetched)
                if fetch_time < cutoff:
                    bookmark.fetched_content = ""
                    bookmark.rss_items = []
                    count += 1
        
        self.manager.save_bookmarks()
        messagebox.showinfo("清理完成", f"已清理 {count} 个过期的书签内容")
    
    def _analyze_with_ai(self):
        """使用AI分析"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要分析的书签")
            return
        
        item = selection[0]
        item_type = self.tree.item(item, "values")[1]
        
        if item_type != "bookmark":
            return
        
        bookmark_id = self.tree.item(item, "values")[0]
        bookmark = self.manager.bookmarks.get(bookmark_id)
        
        if bookmark:
            content = self.manager.get_all_content_for_analysis()
            messagebox.showinfo("AI分析", 
                f"已准备分析内容 ({len(content)} 字符)\n"
                "请在AI助手中查看分析结果。")
    
    def _create_project(self):
        """创建项目"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要创建项目的书签")
            return
        
        item = selection[0]
        item_type = self.tree.item(item, "values")[1]
        
        if item_type != "bookmark":
            return
        
        bookmark_id = self.tree.item(item, "values")[0]
        bookmark = self.manager.bookmarks.get(bookmark_id)
        
        if bookmark and self.manager.project_mgr:
            project_name = f"项目-{bookmark.title[:20]}"
            self.manager.project_mgr.create_project(project_name, bookmark.url)
            messagebox.showinfo("成功", f"已创建项目: {project_name}")


class BookmarkEditDialog:
    """书签编辑对话框"""
    
    def __init__(self, parent, title: str, bookmark: Optional[Bookmark] = None, is_rss: bool = False):
        self.result = None
        self.bookmark = bookmark
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("500x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self._create_widgets(is_rss)
        
        if bookmark:
            self._load_data()
    
    def _create_widgets(self, is_rss: bool):
        frame = ttk.Frame(self.dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="标题:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.title_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.title_var, width=40).grid(row=0, column=1, sticky=tk.EW, pady=5)
        
        ttk.Label(frame, text="URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.url_var, width=40).grid(row=1, column=1, sticky=tk.EW, pady=5)
        
        ttk.Label(frame, text="分类:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.category_var = tk.StringVar(value="默认")
        ttk.Entry(frame, textvariable=self.category_var, width=40).grid(row=2, column=1, sticky=tk.EW, pady=5)
        
        ttk.Label(frame, text="子分类:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.sub_category_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.sub_category_var, width=40).grid(row=3, column=1, sticky=tk.EW, pady=5)
        
        ttk.Label(frame, text="描述:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.desc_text = tk.Text(frame, width=40, height=6)
        self.desc_text.grid(row=4, column=1, sticky=tk.EW, pady=5)
        
        frame.columnconfigure(1, weight=1)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(20, 0))
        
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(btn_frame, text="取消", command=self.dialog.destroy).pack(side=tk.RIGHT)
    
    def _load_data(self):
        if self.bookmark:
            self.title_var.set(self.bookmark.title)
            self.url_var.set(self.bookmark.url)
            self.category_var.set(self.bookmark.category)
            self.sub_category_var.set(self.bookmark.sub_category)
            self.desc_text.insert(1.0, self.bookmark.description)
    
    def _save(self):
        self.result = {
            'title': self.title_var.get().strip(),
            'url': self.url_var.get().strip(),
            'category': self.category_var.get().strip() or "默认",
            'sub_category': self.sub_category_var.get().strip(),
            'description': self.desc_text.get(1.0, tk.END).strip()
        }
        self.dialog.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    BookmarkManagerWindow(root, ".")
