#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 数据枢纽 UI v3
设计理念：管理优先、懒加载、弹窗监控、书签订阅、跨空间流动

架构:
- 主视图: 3标签管理界面（动态流 / 资源库 / 自动化）
  - 懒加载：首次只加载50条，滚动到底部自动加载更多
  - 书签栏：快速添加/访问书签，自动导入DataHub
  - 数据流动：右键"发送到..."实现跨空间移动
- 管道监控弹窗：按需打开，显示管道状态和活动日志
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
import json
import threading
import re

try:
    from ws2_data_hub import (
        DataHub, HubItem, RSSSubscription, DataCollection,
        SourceType, ItemType, EventBus,
        QualityScorer, PipelineEngine, PIPELINE_STAGES,
        init_data_hub, get_data_hub
    )
    HAS_DATA_HUB = True
except ImportError:
    HAS_DATA_HUB = False
    PIPELINE_STAGES = ["scanned", "ingested", "enriched", "filtered", "updated"]

SOURCE_ICONS = {
    "crawler": "🕷️", "rss": "📡", "agent": "🤖",
    "bookmark": "🔖", "analysis": "🔬", "manual": "✏️",
    "local_file": "📂",
}
SOURCE_LABELS = {
    "crawler": "爬虫", "rss": "RSS", "agent": "Agent",
    "bookmark": "书签", "analysis": "分析", "manual": "手动",
    "local_file": "本地文件",
}
STAGE_LABELS = {
    "scanned": "已扫描", "ingested": "已入库", "enriched": "已充实",
    "filtered": "已筛选", "updated": "已更新",
}

PAGE_SIZE = 50


class DataHubUI:
    """WS2 数据枢纽主界面 v3 — 管理优先 + 懒加载 + 弹窗监控"""

    def __init__(self, parent, base_dir: Path, main_app=None):
        self.parent = parent
        self.base_dir = base_dir
        self.main_app = main_app

        if HAS_DATA_HUB:
            try:
                existing_hub = get_data_hub()
                if existing_hub:
                    self.hub = existing_hub
                else:
                    self.hub = init_data_hub(base_dir)
                self._migrate_if_needed()
            except Exception as e:
                print(f"Error initializing DataHub: {e}")
                import traceback
                traceback.print_exc()
                self.hub = None
        else:
            self.hub = None

        self._selected_item_id = None
        self._current_page = 0
        self._has_more_items = True
        self._loading_more = False
        self._monitor_window = None
        self._pipeline_auto_running = False
        self._pipeline_running_now = False
        self._rss_poller_running = False

        self.frame = ttk.Frame(parent)
        self._create_ui()

        if self.hub:
            self.hub.event_bus.subscribe("*", self._on_any_event)
            self._subscribe_pipeline_events()

    def _migrate_if_needed(self):
        try:
            from ws2_synergy import get_synergy_manager
            synergy = get_synergy_manager()
            if synergy and synergy.items:
                count = self.hub.migrate_from_synergy(synergy)
                if count > 0:
                    print(f"DataHub: migrated {count} items from SynergyManager")
        except Exception:
            pass

    def _subscribe_pipeline_events(self):
        if not self.hub:
            return
        for ev in ["pipeline.start", "pipeline.scan_complete",
                    "pipeline.enrich_complete", "pipeline.filter_complete",
                    "pipeline.update_complete", "pipeline.syncback_complete",
                    "pipeline.complete", "pipeline.error"]:
            self.hub.event_bus.subscribe(ev, self._on_pipeline_event)

    def _start_auto_pipeline(self):
        if not self.hub:
            return
        try:
            engine = self.hub.get_pipeline_engine()
            engine.start_periodic_pipeline(interval_minutes=30)
            self._pipeline_auto_running = True
        except Exception as e:
            print(f"Pipeline auto-start failed: {e}")

        def first_run():
            try:
                engine = self.hub.get_pipeline_engine()
                engine.run_full_pipeline()
            except Exception:
                pass

        threading.Thread(target=first_run, daemon=True).start()

    # ================================================================
    # UI 构建
    # ================================================================

    def _create_ui(self):
        self._create_toolbar()
        self._create_bookmark_bar()
        self._create_notebook()
        self._refresh_all()

    def _create_toolbar(self):
        bar = ttk.Frame(self.frame)
        bar.pack(fill=tk.X, padx=10, pady=(8, 2))

        ttk.Label(bar, text="🔗 数据枢纽", font=("", 13, "bold")).pack(side=tk.LEFT)

        self._stats_label = ttk.Label(bar, text="", foreground="#666", font=("", 9))
        self._stats_label.pack(side=tk.LEFT, padx=15)

        self._smart_var = tk.StringVar()
        smart_entry = ttk.Entry(bar, textvariable=self._smart_var, width=40)
        smart_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        smart_entry.bind("<Return>", self._on_smart_input)

        ttk.Label(bar, text="💡 URL/RSS/搜索", foreground="#999", font=("", 8)).pack(side=tk.LEFT, padx=3)

        ttk.Button(bar, text="📊 管道监控", command=self._open_monitor, width=10).pack(side=tk.RIGHT, padx=3)
        ttk.Button(bar, text="➕ 添加", command=self._add_item_dialog, width=8).pack(side=tk.RIGHT, padx=3)

    def _create_bookmark_bar(self):
        bm_frame = ttk.Frame(self.frame)
        bm_frame.pack(fill=tk.X, padx=10, pady=(0, 4))

        ttk.Label(bm_frame, text="🔖", font=("", 11)).pack(side=tk.LEFT)

        self._bm_url_var = tk.StringVar()
        bm_entry = ttk.Entry(bm_frame, textvariable=self._bm_url_var, width=35)
        bm_entry.pack(side=tk.LEFT, padx=3)
        bm_entry.bind("<Return>", self._quick_add_bookmark)

        self._bm_title_var = tk.StringVar()
        ttk.Entry(bm_frame, textvariable=self._bm_title_var, width=20).pack(side=tk.LEFT, padx=2)

        self._bm_tag_var = tk.StringVar()
        tag_entry = ttk.Entry(bm_frame, textvariable=self._bm_tag_var, width=12)
        tag_entry.pack(side=tk.LEFT, padx=2)
        tag_entry.bind("<Return>", self._quick_add_bookmark)

        ttk.Button(bm_frame, text="📌 添加书签", command=self._quick_add_bookmark, width=10).pack(side=tk.LEFT, padx=3)
        ttk.Button(bm_frame, text="🔍 探测", command=self._lightweight_crawl_input, width=7).pack(side=tk.LEFT, padx=3)

        scroll_canvas = tk.Canvas(bm_frame, height=28, highlightthickness=0)
        scroll_sb = ttk.Scrollbar(bm_frame, orient=tk.HORIZONTAL, command=scroll_canvas.xview)
        self._bm_quick_inner = ttk.Frame(scroll_canvas)
        self._bm_quick_inner.bind("<Configure>",
            lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        self._bm_quick_win_id = scroll_canvas.create_window((0, 0), window=self._bm_quick_inner, anchor="nw")
        scroll_canvas.configure(xscrollcommand=scroll_sb.set)
        scroll_canvas.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        scroll_sb.pack(side=tk.LEFT, fill=tk.X)

        def _on_canvas_configure(event):
            scroll_canvas.itemconfig(self._bm_quick_win_id, width=event.width)
        scroll_canvas.bind("<Configure>", _on_canvas_configure)

        self._bm_scroll_canvas = scroll_canvas
        self._refresh_quick_bookmarks()

    def _create_notebook(self):
        self._notebook = ttk.Notebook(self.frame)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self._create_feed_tab(self._notebook)
        self._create_library_tab(self._notebook)
        self._create_automation_tab(self._notebook)

    # ========== 标签页1: 动态流 ==========

    def _create_feed_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=5)
        notebook.add(tab, text="🏠 动态流")

        filter_bar = ttk.Frame(tab)
        filter_bar.pack(fill=tk.X, pady=(0, 4))

        self._source_filter_var = tk.StringVar(value="全部")
        for text, val in [("全部", "全部"), ("🕷️爬虫", "crawler"), ("📡RSS", "rss"),
                          ("🔖书签", "bookmark"), ("🤖Agent", "agent"), ("🔬分析", "analysis"),
                          ("📂本地", "local_file")]:
            ttk.Radiobutton(filter_bar, text=text, value=val,
                            variable=self._source_filter_var,
                            command=self._refresh_items).pack(side=tk.LEFT, padx=2)

        self._starred_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_bar, text="⭐", variable=self._starred_only_var,
                        command=self._refresh_items).pack(side=tk.LEFT, padx=6)
        self._unread_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_bar, text="📩", variable=self._unread_only_var,
                        command=self._refresh_items).pack(side=tk.LEFT, padx=3)

        ttk.Separator(filter_bar, orient="vertical").pack(side=tk.LEFT, fill="y", padx=6)

        ttk.Label(filter_bar, text="搜索:").pack(side=tk.LEFT, padx=(0, 3))
        self._search_filter_var = tk.StringVar()
        search_entry = ttk.Entry(filter_bar, textvariable=self._search_filter_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=3)
        search_entry.bind("<KeyRelease>", self._on_search_filter_change)
        search_entry.bind("<Return>", self._on_search_filter_change)
        
        self._search_column_var = tk.StringVar(value="title")
        ttk.Combobox(filter_bar, textvariable=self._search_column_var, width=8,
                    values=["title", "content", "tags", "url"], state="readonly").pack(side=tk.LEFT, padx=3)

        main_pane = ttk.PanedWindow(tab, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=2)

        list_frame = ttk.Frame(main_pane)
        main_pane.add(list_frame, weight=3)

        cols = ("icon", "title", "tags", "quality", "updated")
        self._items_tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                         selectmode="extended")
        self._items_tree.heading("icon", text="")
        self._items_tree.heading("title", text="标题")
        self._items_tree.heading("tags", text="标签")
        self._items_tree.heading("quality", text="质量")
        self._items_tree.heading("updated", text="时间")
        self._items_tree.column("icon", width=30, minwidth=30, stretch=False)
        self._items_tree.column("title", width=350)
        self._items_tree.column("tags", width=120)
        self._items_tree.column("quality", width=45, stretch=False)
        self._items_tree.column("updated", width=120, stretch=False)

        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._items_tree.yview)
        self._items_tree.configure(yscrollcommand=vsb.set)
        self._items_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._items_tree.bind("<<TreeviewSelect>>", self._on_item_selected)
        self._items_tree.bind("<Double-1>", self._on_item_double_click)
        self._items_tree.bind("<Button-3>", self._on_item_right_click)
        self._items_tree.bind("<MouseWheel>", self._on_items_scroll)
        self._items_tree.bind("<Button-4>", self._on_items_scroll)
        self._items_tree.bind("<Button-5>", self._on_items_scroll)

        bottom_pane = ttk.PanedWindow(main_pane, orient=tk.HORIZONTAL)
        main_pane.add(bottom_pane, weight=2)

        detail_frame = ttk.LabelFrame(bottom_pane, text="详情", padding=3)
        bottom_pane.add(detail_frame, weight=3)

        self._detail_text = tk.Text(detail_frame, wrap=tk.WORD, font=("Consolas", 10),
                                     state=tk.DISABLED)
        dsb = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self._detail_text.yview)
        self._detail_text.configure(yscrollcommand=dsb.set)
        self._detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dsb.pack(side=tk.RIGHT, fill=tk.Y)

        activity_frame = ttk.LabelFrame(bottom_pane, text="活动流", padding=3)
        bottom_pane.add(activity_frame, weight=1)

        self._activity_text = tk.Text(activity_frame, wrap=tk.WORD, font=("Consolas", 9),
                                       state=tk.DISABLED, foreground="#555")
        asb = ttk.Scrollbar(activity_frame, orient=tk.VERTICAL, command=self._activity_text.yview)
        self._activity_text.configure(yscrollcommand=asb.set)
        self._activity_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        asb.pack(side=tk.RIGHT, fill=tk.Y)

    # ========== 标签页2: 资源库 ==========

    def _create_library_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=5)
        notebook.add(tab, text="📚 资源库")

        lib_pane = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        lib_pane.pack(fill=tk.BOTH, expand=True)

        rss_frame = ttk.LabelFrame(lib_pane, text="📡 RSS 订阅", padding=5)
        lib_pane.add(rss_frame, weight=1)

        add_row = ttk.Frame(rss_frame)
        add_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(add_row, text="URL:").pack(side=tk.LEFT)
        self._rss_url_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self._rss_url_var, width=30).pack(side=tk.LEFT, padx=3, fill=tk.X, expand=True)
        ttk.Label(add_row, text="标题:").pack(side=tk.LEFT)
        self._rss_title_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self._rss_title_var, width=10).pack(side=tk.LEFT, padx=3)
        ttk.Button(add_row, text="➕", command=self._add_rss_subscription, width=3).pack(side=tk.LEFT)

        rss_ctrl_row = ttk.Frame(rss_frame)
        rss_ctrl_row.pack(fill=tk.X, pady=(0, 3))
        self._rss_poller_btn = ttk.Button(rss_ctrl_row, text="▶ 启动RSS推送", command=self._toggle_rss_poller, width=14)
        self._rss_poller_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(rss_ctrl_row, text="🔄 立即轮询", command=self._poll_all_rss, width=10).pack(side=tk.LEFT, padx=2)
        self._rss_poller_status = ttk.Label(rss_ctrl_row, text="⏹ 未启动", foreground="#999", font=("", 8))
        self._rss_poller_status.pack(side=tk.LEFT, padx=5)

        rss_cols = ("title", "url", "interval", "polled", "status")
        self._rss_tree = ttk.Treeview(rss_frame, columns=rss_cols, show="headings", height=8)
        self._rss_tree.heading("title", text="标题")
        self._rss_tree.heading("url", text="URL")
        self._rss_tree.heading("interval", text="间隔")
        self._rss_tree.heading("polled", text="上次轮询")
        self._rss_tree.heading("status", text="状态")
        self._rss_tree.column("title", width=100)
        self._rss_tree.column("url", width=180)
        self._rss_tree.column("interval", width=45)
        self._rss_tree.column("polled", width=110)
        self._rss_tree.column("status", width=40)
        rsb = ttk.Scrollbar(rss_frame, orient=tk.VERTICAL, command=self._rss_tree.yview)
        self._rss_tree.configure(yscrollcommand=rsb.set)
        self._rss_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._rss_tree.bind("<Button-3>", self._on_rss_right_click)

        coll_frame = ttk.LabelFrame(lib_pane, text="📁 数据集合", padding=5)
        lib_pane.add(coll_frame, weight=1)

        add_coll_row = ttk.Frame(coll_frame)
        add_coll_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(add_coll_row, text="名称:").pack(side=tk.LEFT)
        self._coll_name_var = tk.StringVar()
        ttk.Entry(add_coll_row, textvariable=self._coll_name_var, width=18).pack(side=tk.LEFT, padx=3)
        ttk.Button(add_coll_row, text="➕ 创建", command=self._create_collection, width=8).pack(side=tk.LEFT, padx=3)

        coll_cols = ("title", "count", "updated")
        self._coll_tree = ttk.Treeview(coll_frame, columns=coll_cols, show="headings", height=8)
        self._coll_tree.heading("title", text="名称")
        self._coll_tree.heading("count", text="项目数")
        self._coll_tree.heading("updated", text="更新时间")
        self._coll_tree.column("title", width=180)
        self._coll_tree.column("count", width=55)
        self._coll_tree.column("updated", width=110)
        csb = ttk.Scrollbar(coll_frame, orient=tk.VERTICAL, command=self._coll_tree.yview)
        self._coll_tree.configure(yscrollcommand=csb.set)
        self._coll_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        csb.pack(side=tk.RIGHT, fill=tk.Y)
        self._coll_tree.bind("<<TreeviewSelect>>", self._on_collection_selected)
        self._coll_tree.bind("<Button-3>", self._on_coll_right_click)

        self._coll_detail_text = tk.Text(coll_frame, wrap=tk.WORD, font=("Consolas", 9),
                                           height=5, state=tk.DISABLED)
        self._coll_detail_text.pack(fill=tk.X, pady=(5, 0))

    # ========== 标签页3: 自动化 ==========

    def _create_automation_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="⚙️ 自动化")

        auto_frame = ttk.LabelFrame(tab, text="一键操作", padding=10)
        auto_frame.pack(fill=tk.X, pady=5)

        actions = [
            ("📡 轮询所有RSS", self._poll_all_rss, "获取所有RSS订阅源的最新内容"),
            ("🕷️ 爬取书签URL", self._crawl_bookmarks, "以书签URL为起点爬取网页内容"),
            ("🔍 发现订阅源", self._discover_subscriptions, "轻度爬取书签URL，发现RSS/Atom订阅"),
            ("🌐 抓取URL导入", self._fetch_url_dialog, "输入URL抓取网页内容"),
            ("📂 导入本地文件", self._import_local_file, "将本地文件内容导入枢纽"),
            ("📡 制作RSS Feed", self._generate_rss_dialog, "从枢纽数据项生成RSS feed"),
            ("🔍 重新扫描数据源", self._manual_scan, "扫描书签/爬取页面/资源索引/工作流"),
            ("🔄 运行反馈管道", self._run_pipeline_now, "执行完整六阶段管道"),
        ]
        for text, cmd, desc in actions:
            row = ttk.Frame(auto_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Button(row, text=text, command=cmd, width=18).pack(side=tk.LEFT, padx=5)
            ttk.Label(row, text=desc, foreground="#666").pack(side=tk.LEFT, padx=5)

        stats_frame = ttk.LabelFrame(tab, text="统计", padding=10)
        stats_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self._stats_text = tk.Text(stats_frame, wrap=tk.WORD, font=("Consolas", 10),
                                    state=tk.DISABLED)
        ssb = ttk.Scrollbar(stats_frame, orient=tk.VERTICAL, command=self._stats_text.yview)
        self._stats_text.configure(yscrollcommand=ssb.set)
        self._stats_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ssb.pack(side=tk.RIGHT, fill=tk.Y)

    # ================================================================
    # 书签栏
    # ================================================================

    def _quick_add_bookmark(self, event=None):
        if not self.hub:
            return
        url = self._bm_url_var.get().strip()
        if not url:
            return
        title = self._bm_title_var.get().strip() or url
        tag = self._bm_tag_var.get().strip()
        self._bm_url_var.set("")
        self._bm_title_var.set("")
        self._bm_tag_var.set("")

        item = HubItem(
            title=title, url=url,
            source_type=SourceType.BOOKMARK.value,
            item_type=ItemType.BOOKMARK.value,
            tags=[tag] if tag else [],
            pipeline_stage="ingested",
        )
        self.hub.add_item(item)
        self._log_activity(f"🔖 书签已添加: {title[:40]}")
        self._refresh_all()
        self._refresh_quick_bookmarks()

    def _refresh_quick_bookmarks(self):
        if not self.hub:
            return
        for w in self._bm_quick_inner.winfo_children():
            w.destroy()

        items = self.hub.query_items(source_type="bookmark", starred_only=True, limit=30,
                                      sort_by="updated_at", sort_desc=True)
        for item in items:
            btn_text = f"{item.title[:12]}" if len(item.title) <= 12 else f"{item.title[:10]}…"
            btn = ttk.Button(self._bm_quick_inner, text=btn_text, width=14,
                             command=lambda i=item: self._show_bookmark_info(i))
            btn.bind("<Button-3>", lambda e, i=item: self._bookmark_right_click(e, i))
            btn.pack(side=tk.LEFT, padx=1)

    def _show_bookmark_info(self, item):
        dialog = tk.Toplevel(self.frame)
        dialog.title(item.title[:40])
        dialog.geometry("550x380")
        dialog.transient(self.frame)

        header = ttk.Frame(dialog, padding=10)
        header.pack(fill=tk.X)

        icon = SOURCE_ICONS.get(item.source_type, "📦")
        ttk.Label(header, text=f"{icon} {item.title}", font=("", 13, "bold"),
                  wraplength=500).pack(anchor="w")

        info_frame = ttk.Frame(dialog, padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True)

        meta_lines = []
        if item.url:
            meta_lines.append(f"URL: {item.url}")
        if item.tags:
            meta_lines.append(f"标签: {', '.join(item.tags)}")
        if getattr(item, 'keywords', []) and item.keywords:
            meta_lines.append(f"关键词: {', '.join(item.keywords[:8])}")
        stage = getattr(item, 'pipeline_stage', 'ingested')
        score = getattr(item, 'quality_score', 0.0)
        meta_lines.append(f"管道: {STAGE_LABELS.get(stage, stage)}  质量: {score:.2f}")
        meta_lines.append(f"更新: {item.updated_at[:19]}")

        ttk.Label(info_frame, text="\n".join(meta_lines), font=("Consolas", 10),
                  justify=tk.LEFT).pack(anchor="w", pady=(0, 5))

        ttk.Separator(info_frame).pack(fill=tk.X, pady=5)

        content = item.summary or (item.content[:500] if item.content else "暂无内容摘要")
        content_text = tk.Text(info_frame, wrap=tk.WORD, font=("", 10), height=8)
        content_text.insert(1.0, content)
        content_text.config(state=tk.DISABLED)
        content_text.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill=tk.X)

        def open_browser():
            if item.url:
                import webbrowser
                webbrowser.open(item.url)

        def copy_url():
            if item.url:
                self.frame.clipboard_clear()
                self.frame.clipboard_append(item.url)
                self._log_activity(f"📋 已复制URL: {item.url[:50]}")

        def crawl_now():
            dialog.destroy()
            self._crawl_item(item.id)

        ttk.Button(btn_frame, text="🌐 浏览器打开", command=open_browser, width=12).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="📋 复制URL", command=copy_url, width=10).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="🕷️ 爬取内容", command=crawl_now, width=10).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="关闭", command=dialog.destroy, width=8).pack(side=tk.RIGHT, padx=3)

    def _bookmark_right_click(self, event, item):
        menu = tk.Menu(self.frame, tearoff=0)
        menu.add_command(label="🌐 浏览器打开", command=lambda: self._open_url(item.url))
        menu.add_command(label="📋 复制URL", command=lambda: self._copy_url(item.url))
        menu.add_command(label="🕷️ 爬取内容", command=lambda: self._crawl_item(item.id))
        menu.add_separator()
        menu.add_command(label="⭐ 取消星标", command=lambda: self._set_starred(item.id, False))
        menu.add_separator()
        menu.add_command(label="🗑️ 删除", command=lambda: self._delete_item_by_id(item.id))
        menu.tk_popup(event.x_root, event.y_root)

    def _delete_item_by_id(self, item_id):
        if not self.hub:
            return
        if messagebox.askyesno("确认", "确定要删除此书签吗？"):
            self.hub.delete_item(item_id)
            self._refresh_all()
            self._refresh_quick_bookmarks()

    def _open_url(self, url):
        if not url:
            return
        import webbrowser
        webbrowser.open(url)

    # ================================================================
    # 懒加载
    # ================================================================

    def _on_items_scroll(self, event):
        if not self._items_tree:
            return
        try:
            children = self._items_tree.get_children()
            if not children:
                return
            last_visible = self._items_tree.yview()[1]
            if last_visible > 0.95 and self._has_more_items and not self._loading_more:
                self._load_more_items()
        except Exception:
            pass

    def _load_more_items(self):
        if not self.hub or self._loading_more:
            return
        self._loading_more = True
        self._current_page += 1
        offset = self._current_page * PAGE_SIZE

        source = self._source_filter_var.get()
        items = self.hub.query_items(
            source_type=source if source != "全部" else None,
            starred_only=self._starred_only_var.get(),
            unread_only=self._unread_only_var.get(),
            limit=PAGE_SIZE, offset=offset,
            sort_by="updated_at", sort_desc=True,
        )
        if len(items) < PAGE_SIZE:
            self._has_more_items = False
        self._append_items_tree(items)
        self._loading_more = False

    # ================================================================
    # 万能输入栏
    # ================================================================

    def _on_smart_input(self, event=None):
        if not self.hub:
            return
        text = self._smart_var.get().strip()
        if not text:
            return
        self._smart_var.set("")

        if re.match(r'^https?://', text):
            if '/feed' in text or '/rss' in text or text.endswith('.xml') or '/atom' in text:
                self._smart_add_rss(text)
            else:
                self._smart_fetch_url(text)
        else:
            self._smart_search(text)

    def _smart_fetch_url(self, url):
        self._log_activity(f"🌐 抓取URL: {url[:60]}")

        def fetch():
            content = self.hub.fetch_url_content(url)
            if content:
                item = HubItem(title=url, url=url, content=content,
                               summary=content[:500], source_type="crawler",
                               item_type=ItemType.WEBPAGE.value)
                result = self.hub.add_item(item)
                self.frame.after(0, lambda: self._log_activity(f"✅ 已抓取: {result.title[:40]} ({len(content)}字符)"))
                self.frame.after(0, self._refresh_all)
            else:
                self.frame.after(0, lambda: self._log_activity(f"❌ 抓取失败: {url[:60]}"))

        threading.Thread(target=fetch, daemon=True).start()

    def _smart_add_rss(self, url):
        sub = RSSSubscription(url=url, title="")
        self.hub.add_rss_subscription(sub)
        self._log_activity(f"📡 已添加RSS订阅: {url[:60]}")
        self._refresh_rss()
        self._refresh_dashboard()

    def _smart_search(self, query):
        self._source_filter_var.set("全部")
        self._starred_only_var.set(False)
        self._unread_only_var.set(False)
        items = self.hub.query_items(search=query, limit=50)
        self._populate_items_tree(items)
        self._log_activity(f"🔍 搜索 '{query}': 找到 {len(items)} 项")

    # ================================================================
    # 右键菜单
    # ================================================================

    def _on_item_right_click(self, event):
        item_id = self._get_clicked_item_id(event)
        if not item_id:
            return
        self._selected_item_id = item_id
        self._items_tree.selection_set(self._items_tree.identify_row(event.y))

        menu = tk.Menu(self.frame, tearoff=0)
        item = self.hub.get_item(item_id) if self.hub else None
        if not item:
            return

        if item.is_starred:
            menu.add_command(label="⭐ 取消星标", command=lambda: self._set_starred(item_id, False))
        else:
            menu.add_command(label="⭐ 加星标", command=lambda: self._set_starred(item_id, True))

        if not item.is_read:
            menu.add_command(label="✅ 标记已读", command=lambda: self._mark_read(item_id))

        if getattr(item, 'needs_review', False):
            menu.add_command(label="✅ 批准", command=lambda: self._approve_item(item_id))

        menu.add_separator()

        if item.url:
            menu.add_command(label="🕷️ 爬取此URL", command=lambda: self._crawl_item(item_id))
            menu.add_command(label="📋 复制URL", command=lambda: self._copy_url(item.url))
            menu.add_command(label="🌐 浏览器打开", command=lambda: self._open_url(item.url))

        menu.add_command(label="🔍 解析内容", command=lambda: self._parse_item(item_id))
        menu.add_command(label="🔗 关联到...", command=self._link_items)
        menu.add_command(label="📁 加入集合...", command=self._add_to_collection)

        menu.add_separator()
        send_menu = tk.Menu(menu, tearoff=0)
        send_menu.add_command(label="🕷️ → 爬虫空间", command=lambda: self._send_to_space(item_id, "crawler"))
        send_menu.add_command(label="📡 → RSS空间", command=lambda: self._send_to_space(item_id, "rss"))
        send_menu.add_command(label="🤖 → Agent空间", command=lambda: self._send_to_space(item_id, "agent"))
        send_menu.add_command(label="🔬 → 分析空间", command=lambda: self._send_to_space(item_id, "analysis"))
        send_menu.add_command(label="🔖 → 书签空间", command=lambda: self._send_to_space(item_id, "bookmark"))
        menu.add_cascade(label="📤 发送到...", menu=send_menu)

        menu.add_separator()
        menu.add_command(label="📝 编辑", command=self._edit_item)
        menu.add_command(label="🗑️ 删除", command=self._delete_item)

        menu.tk_popup(event.x_root, event.y_root)

    def _on_rss_right_click(self, event):
        sel = self._rss_tree.identify_row(event.y)
        if not sel or not self.hub:
            return
        self._rss_tree.selection_set(sel)
        sub_id = self._rss_tree.item(sel, "tags")[0]
        menu = tk.Menu(self.frame, tearoff=0)
        menu.add_command(label="🔄 轮询此源", command=lambda: self._poll_one_rss(sub_id))
        menu.add_command(label="⏸️ 暂停/恢复", command=lambda: self._toggle_rss(sub_id))
        menu.add_separator()
        menu.add_command(label="🗑️ 移除", command=lambda: self._remove_rss(sub_id))
        menu.tk_popup(event.x_root, event.y_root)

    def _on_coll_right_click(self, event):
        sel = self._coll_tree.identify_row(event.y)
        if not sel or not self.hub:
            return
        self._coll_tree.selection_set(sel)
        coll_id = self._coll_tree.item(sel, "tags")[0]
        menu = tk.Menu(self.frame, tearoff=0)
        menu.add_command(label="📡 生成RSS Feed", command=lambda: self._gen_rss_for_coll(coll_id))
        menu.add_separator()
        menu.add_command(label="🗑️ 删除集合", command=lambda: self._delete_collection(coll_id))
        menu.tk_popup(event.x_root, event.y_root)

    # ================================================================
    # 数据流动
    # ================================================================

    def _send_to_space(self, item_id: str, target_source: str):
        if not self.hub:
            return
        item = self.hub.get_item(item_id)
        if not item:
            return
        self.hub.update_item(item_id, source_type=target_source)
        label = SOURCE_LABELS.get(target_source, target_source)
        self._log_activity(f"📤 已发送到{label}空间: {item.title[:30]}")
        self._refresh_items()

    # ================================================================
    # 刷新（懒加载版）
    # ================================================================

    def _refresh_all(self):
        self._refresh_dashboard()
        self._refresh_items()
        self._refresh_rss()
        self._refresh_collections()
        self._refresh_stats()

    def _refresh_dashboard(self):
        if not self.hub:
            return
        stats = self.hub.get_statistics()
        self._stats_label.config(
            text=f"📦{stats['total_items']} ⭐{stats['starred']} 📩{stats['unread']} 📡{stats['rss_subscriptions']} 📁{stats['collections']}"
        )

    def _refresh_items(self):
        if not self.hub:
            return
        self._current_page = 0
        self._has_more_items = True
        source = self._source_filter_var.get()
        
        search_query = self._search_filter_var.get().strip()
        search_column = self._search_column_var.get() if search_query else None
        
        items = self.hub.query_items(
            source_type=source if source != "全部" else None,
            starred_only=self._starred_only_var.get(),
            unread_only=self._unread_only_var.get(),
            limit=PAGE_SIZE * 5,
            offset=0,
            sort_by="updated_at", sort_desc=True,
        )
        
        if search_query and search_column:
            search_query_lower = search_query.lower()
            filtered_items = []
            for item in items:
                if search_column == "title":
                    if search_query_lower in item.title.lower():
                        filtered_items.append(item)
                elif search_column == "content":
                    if search_query_lower in item.content.lower():
                        filtered_items.append(item)
                elif search_column == "tags":
                    tags_str = ",".join(item.tags).lower()
                    if search_query_lower in tags_str:
                        filtered_items.append(item)
                elif search_column == "url":
                    if search_query_lower in item.url.lower():
                        filtered_items.append(item)
            items = filtered_items[:PAGE_SIZE]
        elif len(items) < PAGE_SIZE:
            self._has_more_items = False
        else:
            items = items[:PAGE_SIZE]
        
        self._populate_items_tree(items)

    def _on_search_filter_change(self, event=None):
        self._refresh_items()

    def _populate_items_tree(self, items):
        for row in self._items_tree.get_children():
            self._items_tree.delete(row)
        self._append_items_tree(items)

    def _append_items_tree(self, items):
        for item in items:
            icon = SOURCE_ICONS.get(item.source_type, "📦")
            star = "⭐" if item.is_starred else ""
            read = "" if item.is_read else "📩"
            tags_str = ", ".join(item.tags[:3])
            score = getattr(item, 'quality_score', 0.0)
            score_str = f"{score:.1f}"
            self._items_tree.insert("", tk.END, values=(
                f"{read}{icon}", f"{star}{item.title[:70]}", tags_str,
                score_str, item.updated_at[:16]
            ), tags=(item.id,))

    def _refresh_rss(self):
        if not self.hub:
            return
        for row in self._rss_tree.get_children():
            self._rss_tree.delete(row)
        for sub in self.hub.get_rss_subscriptions():
            self._rss_tree.insert("", tk.END, values=(
                sub.title or "未命名", sub.url[:50],
                f"{sub.poll_interval_minutes}分",
                sub.last_polled[:16] if sub.last_polled else "从未",
                "✅" if sub.active else "⏸️"
            ), tags=(sub.id,))

    def _refresh_collections(self):
        if not self.hub:
            return
        for row in self._coll_tree.get_children():
            self._coll_tree.delete(row)
        for coll in self.hub.get_collections():
            self._coll_tree.insert("", tk.END, values=(
                coll.title, len(coll.item_ids), coll.updated_at[:16]
            ), tags=(coll.id,))

    def _refresh_stats(self):
        if not self.hub:
            return
        stats = self.hub.get_statistics()
        lines = [
            f"📦 总项目: {stats['total_items']}    ⭐ 星标: {stats['starred']}    📩 未读: {stats['unread']}",
            f"📡 RSS源: {stats['rss_subscriptions']}    📁 集合: {stats['collections']}",
            "",
            "来源分布:",
        ]
        for src, cnt in stats["source_distribution"].items():
            icon = SOURCE_ICONS.get(src, "📦")
            label = SOURCE_LABELS.get(src, src)
            bar = "█" * min(cnt, 25)
            lines.append(f"  {icon} {label}: {cnt}  {bar}")
        lines.append("")
        lines.append("类型分布:")
        for t, cnt in stats["type_distribution"].items():
            lines.append(f"  📄 {t}: {cnt}")

        ps = stats.get("pipeline_stages", {})
        if ps:
            lines.append("")
            lines.append("管道阶段:")
            for stage in PIPELINE_STAGES:
                cnt = ps.get(stage, 0)
                label = STAGE_LABELS.get(stage, stage)
                lines.append(f"  {label}: {cnt}")
            nr = ps.get("needs_review", 0)
            if nr:
                lines.append(f"  ⚠️ 待审: {nr}")

        self._stats_text.config(state=tk.NORMAL)
        self._stats_text.delete(1.0, tk.END)
        self._stats_text.insert(1.0, "\n".join(lines))
        self._stats_text.config(state=tk.DISABLED)

    # ================================================================
    # 活动流
    # ================================================================

    def _log_activity(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        try:
            if hasattr(self, '_activity_text') and self._activity_text.winfo_exists():
                self._activity_text.config(state=tk.NORMAL)
                self._activity_text.insert(tk.END, line)
                self._activity_text.see(tk.END)
                line_count = int(self._activity_text.index('end-1c').split('.')[0])
                if line_count > 300:
                    self._activity_text.delete(1.0, f"{line_count - 200}.0")
                self._activity_text.config(state=tk.DISABLED)
        except (tk.TclError, RuntimeError, AttributeError):
            pass

    # ================================================================
    # 事件处理
    # ================================================================

    def _on_any_event(self, event_type, data):
        try:
            if not self.frame.winfo_exists():
                return
            if event_type == "item.added" and isinstance(data, HubItem):
                icon = SOURCE_ICONS.get(data.source_type, "📦")
                self.frame.after(0, lambda: self._log_activity(f"{icon} 新增: {data.title[:40]}"))
                self.frame.after(0, self._refresh_items)
                self.frame.after(0, self._refresh_dashboard)
            elif event_type == "item.updated":
                self.frame.after(0, self._refresh_items)
                self.frame.after(0, self._refresh_dashboard)
            elif event_type == "item.deleted":
                self.frame.after(0, self._refresh_items)
                self.frame.after(0, self._refresh_dashboard)
            elif event_type == "rss.new_entries" and isinstance(data, dict):
                count = data.get("count", 0)
                sub_id = data.get("sub_id", "")
                sub_title = ""
                if sub_id and self.hub:
                    subs = self.hub.get_rss_subscriptions()
                    sub = next((s for s in subs if s.id == sub_id), None)
                    if sub:
                        sub_title = sub.title or sub.url[:30]
                self.frame.after(0, lambda c=count, t=sub_title: self._log_activity(
                    f"📡 RSS推送: {c}条新内容" + (f" 来自 {t}" if t else "")))
                self.frame.after(0, self._refresh_items)
                self.frame.after(0, self._refresh_rss)
                self.frame.after(0, self._refresh_dashboard)
            elif event_type == "rss.poll_complete":
                self.frame.after(0, self._refresh_rss)
            elif event_type == "pipeline.bookmark_crawl_batch" and isinstance(data, dict):
                c = data.get("crawled", 0)
                f = data.get("failed", 0)
                self.frame.after(0, lambda: self._log_activity(f"🕷️ 书签爬取: ✅{c} ❌{f}"))
                self.frame.after(0, self._refresh_items)
        except (tk.TclError, RuntimeError):
            pass

    def _on_pipeline_event(self, event_type, data):
        try:
            if not self.frame.winfo_exists():
                return
            if event_type == "pipeline.start":
                self._pipeline_running_now = True
                run_id = data.get("run_id", "?") if isinstance(data, dict) else "?"
                self.frame.after(0, lambda: self._log_activity(f"🔄 管道启动 (#{run_id})"))
            elif event_type == "pipeline.complete":
                self._pipeline_running_now = False
                if isinstance(data, dict):
                    success = data.get("success", False)
                    run_id = data.get("run_id", "?")
                    if success:
                        self.frame.after(0, lambda: self._log_activity(f"✅ 管道完成 (#{run_id})"))
                    else:
                        errors = data.get("errors", [])
                        self.frame.after(0, lambda: self._log_activity(f"⚠️ 管道完成但有错误 (#{run_id})"))
                self.frame.after(0, self._refresh_all)
            elif event_type == "pipeline.error":
                self._pipeline_running_now = False
                err_msg = str(data) if data else "未知错误"
                self.frame.after(0, lambda: self._log_activity(f"❌ 管道错误: {err_msg}"))
            elif event_type in ("pipeline.scan_complete", "pipeline.enrich_complete",
                                "pipeline.filter_complete", "pipeline.update_complete",
                                "pipeline.syncback_complete"):
                stage_name = event_type.replace("pipeline.", "").replace("_complete", "")
                self.frame.after(0, lambda s=stage_name: self._log_activity(f"  ✅ {s} 阶段完成"))
            if self._monitor_window and self._monitor_window.winfo_exists():
                self._update_monitor()
        except (tk.TclError, RuntimeError):
            pass

    # ================================================================
    # 管道监控弹窗
    # ================================================================

    def _open_monitor(self):
        if self._monitor_window and self._monitor_window.winfo_exists():
            self._monitor_window.lift()
            return

        self._monitor_window = tk.Toplevel(self.frame)
        self._monitor_window.title("📊 管道监控")
        self._monitor_window.geometry("700x500")

        top = ttk.Frame(self._monitor_window, padding=8)
        top.pack(fill=tk.X)

        self._mon_indicator = ttk.Label(top, text="🟡 空闲", font=("", 12, "bold"))
        self._mon_indicator.pack(side=tk.LEFT, padx=5)

        self._mon_stats = ttk.Label(top, text="", font=("", 10))
        self._mon_stats.pack(side=tk.LEFT, padx=15)

        btn_frame = ttk.Frame(top)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="▶ 运行", command=self._run_pipeline_now, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="▶ 自动", command=self._start_auto, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="⏹ 停止", command=self._stop_auto, width=8).pack(side=tk.LEFT, padx=3)

        stage_frame = ttk.LabelFrame(self._monitor_window, text="管道阶段", padding=5)
        stage_frame.pack(fill=tk.X, padx=8, pady=4)

        self._mon_stage_labels = {}
        for stage in PIPELINE_STAGES:
            lbl = ttk.Label(stage_frame, text=f"{STAGE_LABELS.get(stage, stage)}: 0", font=("", 10))
            lbl.pack(side=tk.LEFT, padx=8)
            self._mon_stage_labels[stage] = lbl

        log_frame = ttk.LabelFrame(self._monitor_window, text="管道日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._mon_log = tk.Text(log_frame, wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED)
        msb = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self._mon_log.yview)
        self._mon_log.configure(yscrollcommand=msb.set)
        self._mon_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        msb.pack(side=tk.RIGHT, fill=tk.Y)

        self._update_monitor()

    def _update_monitor(self):
        if not self.hub or not self._monitor_window or not self._monitor_window.winfo_exists():
            return
        try:
            if self._pipeline_running_now:
                self._mon_indicator.config(text="🟢 运行中")
            elif self._pipeline_auto_running:
                self._mon_indicator.config(text="🟡 自动待机")
            else:
                self._mon_indicator.config(text="🔴 已停止")

            ps = self.hub.get_pipeline_status()
            self._mon_stats.config(text=f"运行次数: {ps.get('run_count', 0)}  上次: {ps.get('last_run', '无')[:16]}")

            stage_stats = self.hub.get_pipeline_stage_stats()
            for stage in PIPELINE_STAGES:
                cnt = stage_stats.get(stage, 0)
                self._mon_stage_labels[stage].config(text=f"{STAGE_LABELS.get(stage, stage)}: {cnt}")

            logs = self.hub.get_pipeline_logs(limit=50)
            self._mon_log.config(state=tk.NORMAL)
            self._mon_log.delete(1.0, tk.END)
            for log in reversed(logs):
                ts = log.get("timestamp", "")[:16]
                action = log.get("action", "")
                status = log.get("status", "")
                msg = log.get("message", "")[:80]
                self._mon_log.insert(tk.END, f"[{ts}] {action} {status} {msg}\n")
            self._mon_log.see(tk.END)
            self._mon_log.config(state=tk.DISABLED)
        except (tk.TclError, RuntimeError):
            pass

    # ================================================================
    # 管道控制
    # ================================================================

    def _run_pipeline_now(self):
        if not self.hub:
            return
        self._log_activity("▶ 手动触发管道...")

        def run():
            try:
                engine = self.hub.get_pipeline_engine()
                engine.run_full_pipeline()
            except Exception as e:
                self.frame.after(0, lambda: self._log_activity(f"❌ 管道失败: {e}"))

        threading.Thread(target=run, daemon=True).start()

    def _start_auto(self):
        if not self.hub:
            return
        try:
            engine = self.hub.get_pipeline_engine()
            engine.start_periodic_pipeline(interval_minutes=30)
            self._pipeline_auto_running = True
            self._log_activity("🟢 管道自动运行已启动")
            if self._monitor_window and self._monitor_window.winfo_exists():
                self._update_monitor()
        except Exception as e:
            self._log_activity(f"⚠️ 启动失败: {e}")

    def _stop_auto(self):
        if not self.hub:
            return
        try:
            engine = self.hub.get_pipeline_engine()
            engine.stop_periodic_pipeline()
            self._pipeline_auto_running = False
            self._log_activity("🔴 管道自动运行已停止")
            if self._monitor_window and self._monitor_window.winfo_exists():
                self._update_monitor()
        except Exception as e:
            self._log_activity(f"⚠️ 停止失败: {e}")

    # ================================================================
    # 数据项操作
    # ================================================================

    def _get_clicked_item_id(self, event):
        row = self._items_tree.identify_row(event.y)
        if not row:
            return None
        tags = self._items_tree.item(row, "tags")
        return tags[0] if tags else None

    def _on_item_selected(self, event):
        sel = self._items_tree.selection()
        if not sel or not self.hub:
            return
        item_id = self._items_tree.item(sel[0], "tags")[0]
        self._selected_item_id = item_id
        item = self.hub.get_item(item_id)
        if item:
            self._display_item_detail(item)

    def _on_item_double_click(self, event):
        if self._selected_item_id and self.hub:
            self.hub.update_item(self._selected_item_id, is_read=True)
            item = self.hub.get_item(self._selected_item_id)
            if item and item.url:
                import webbrowser
                webbrowser.open(item.url)
            self._refresh_items()

    def _display_item_detail(self, item):
        icon = SOURCE_ICONS.get(item.source_type, "📦")
        star = "⭐" if item.is_starred else ""
        read = "✅已读" if item.is_read else "📩未读"
        stage = getattr(item, 'pipeline_stage', 'ingested')
        score = getattr(item, 'quality_score', 0.0)
        review = " ⚠️待审" if getattr(item, 'needs_review', False) else ""

        content = (
            f"{star}{icon} {item.title}\n"
            f"{'─' * 50}\n"
            f"URL: {item.url or '无'}\n"
            f"来源: {SOURCE_LABELS.get(item.source_type, item.source_type or '?')}  "
            f"类型: {item.item_type}  状态: {read}{review}\n"
            f"管道: {STAGE_LABELS.get(stage, stage)}  质量: {score:.2f}\n"
            f"标签: {', '.join(item.tags) or '无'}\n"
            f"关键词: {', '.join(item.keywords) or '无'}\n"
            f"更新: {item.updated_at[:19]}\n"
            f"{'─' * 50}\n"
            f"{item.summary or (item.content[:500] if item.content else '无内容')}\n"
        )
        if item.content and len(item.content) > 500:
            content += f"\n[内容共 {len(item.content)} 字符]"

        self._detail_text.config(state=tk.NORMAL)
        self._detail_text.delete(1.0, tk.END)
        self._detail_text.insert(1.0, content)
        self._detail_text.config(state=tk.DISABLED)

    def _set_starred(self, item_id, starred):
        if self.hub:
            self.hub.update_item(item_id, is_starred=starred)
            self._refresh_items()
            self._refresh_quick_bookmarks()

    def _mark_read(self, item_id):
        if self.hub:
            self.hub.update_item(item_id, is_read=True)
            self._refresh_items()

    def _approve_item(self, item_id):
        if self.hub:
            self.hub.update_item(item_id, needs_review=False)
            self._log_activity(f"✅ 已批准: {item_id[:8]}")
            self._refresh_all()

    def _copy_url(self, url):
        self.frame.clipboard_clear()
        self.frame.clipboard_append(url)
        self._log_activity(f"📋 已复制URL: {url[:60]}")

    def _crawl_item(self, item_id):
        if not self.hub:
            return
        self._log_activity("🕷️ 爬取中...")

        def crawl():
            result = self.hub.pipeline_bookmark_crawl(item_id)
            if result:
                self.frame.after(0, lambda: self._log_activity(f"✅ 爬取完成: {result.title[:40]} ({len(result.content)}字符)"))
                self.frame.after(0, self._refresh_items)
            else:
                self.frame.after(0, lambda: self._log_activity("❌ 爬取失败"))

        threading.Thread(target=crawl, daemon=True).start()

    def _parse_item(self, item_id):
        if not self.hub:
            return
        result = self.hub.parse_item_content(item_id)
        if "error" in result:
            self._log_activity(f"❌ 解析失败: {result['error']}")
            return
        detail = json.dumps(result.get("parsed", {}), indent=2, ensure_ascii=False)
        self._detail_text.config(state=tk.NORMAL)
        self._detail_text.delete(1.0, tk.END)
        self._detail_text.insert(1.0, f"🔍 解析结果 ({result['parser']})\n{'─' * 40}\n\n{detail}")
        self._detail_text.config(state=tk.DISABLED)

    def _add_item_dialog(self):
        dialog = tk.Toplevel(self.frame)
        dialog.title("添加数据项")
        dialog.geometry("500x400")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(dialog, text="标题:").pack(anchor="w", padx=20, pady=3)
        title_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=title_var, width=55).pack(padx=20)

        row_url = ttk.Frame(dialog)
        row_url.pack(fill=tk.X, padx=20, pady=3)
        ttk.Label(row_url, text="URL:").pack(side=tk.LEFT)
        url_var = tk.StringVar()
        ttk.Entry(row_url, textvariable=url_var, width=50).pack(side=tk.LEFT, padx=5)

        row_type = ttk.Frame(dialog)
        row_type.pack(fill=tk.X, padx=20, pady=3)
        ttk.Label(row_type, text="来源:").pack(side=tk.LEFT)
        source_var = tk.StringVar(value="manual")
        if HAS_DATA_HUB:
            ttk.Combobox(row_type, textvariable=source_var,
                         values=[s.value for s in SourceType], width=12,
                         state="readonly").pack(side=tk.LEFT, padx=5)
        ttk.Label(row_type, text="类型:").pack(side=tk.LEFT, padx=(10, 0))
        type_var = tk.StringVar(value="webpage")
        if HAS_DATA_HUB:
            ttk.Combobox(row_type, textvariable=type_var,
                         values=[t.value for t in ItemType], width=12,
                         state="readonly").pack(side=tk.LEFT, padx=5)

        ttk.Label(dialog, text="内容:").pack(anchor="w", padx=20, pady=3)
        content_text = tk.Text(dialog, height=8)
        content_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=3)

        row_tags = ttk.Frame(dialog)
        row_tags.pack(fill=tk.X, padx=20, pady=3)
        ttk.Label(row_tags, text="标签(逗号分隔):").pack(side=tk.LEFT)
        tags_var = tk.StringVar()
        ttk.Entry(row_tags, textvariable=tags_var, width=35).pack(side=tk.LEFT, padx=5)

        def save():
            if not title_var.get():
                messagebox.showwarning("提示", "请输入标题")
                return
            item = HubItem(
                title=title_var.get(), url=url_var.get(),
                content=content_text.get(1.0, tk.END).strip(),
                source_type=source_var.get(), item_type=type_var.get(),
                tags=[t.strip() for t in tags_var.get().split(",") if t.strip()],
            )
            self.hub.add_item(item)
            self._refresh_all()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="保存", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _edit_item(self):
        if not self._selected_item_id or not self.hub:
            return
        item = self.hub.get_item(self._selected_item_id)
        if not item:
            return

        dialog = tk.Toplevel(self.frame)
        dialog.title("编辑数据项")
        dialog.geometry("500x350")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(dialog, text="标题:").pack(anchor="w", padx=20, pady=3)
        title_var = tk.StringVar(value=item.title)
        ttk.Entry(dialog, textvariable=title_var, width=55).pack(padx=20)

        ttk.Label(dialog, text="内容:").pack(anchor="w", padx=20, pady=3)
        content_text = tk.Text(dialog, height=10)
        content_text.insert(1.0, item.content or "")
        content_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=3)

        row_tags = ttk.Frame(dialog)
        row_tags.pack(fill=tk.X, padx=20, pady=3)
        ttk.Label(row_tags, text="标签(逗号分隔):").pack(side=tk.LEFT)
        tags_var = tk.StringVar(value=", ".join(item.tags))
        ttk.Entry(row_tags, textvariable=tags_var, width=35).pack(side=tk.LEFT, padx=5)

        def save_edit():
            new_title = title_var.get().strip()
            new_content = content_text.get(1.0, tk.END).strip()
            new_tags = [t.strip() for t in tags_var.get().split(",") if t.strip()]
            if new_title:
                self.hub.update_item(self._selected_item_id,
                                     title=new_title, content=new_content, tags=new_tags)
                self._refresh_all()
                dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="保存", command=save_edit).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _delete_item(self):
        if not self._selected_item_id or not self.hub:
            return
        if not messagebox.askyesno("确认", "确定要删除此数据项吗？"):
            return
        self.hub.delete_item(self._selected_item_id)
        self._selected_item_id = None
        self._refresh_all()

    def _link_items(self):
        if not self._selected_item_id or not self.hub:
            return
        item = self.hub.get_item(self._selected_item_id)
        if not item:
            return

        dialog = tk.Toplevel(self.frame)
        dialog.title("关联数据项")
        dialog.geometry("400x280")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(dialog, text=f"当前项: {item.title[:40]}").pack(anchor="w", padx=20, pady=5)
        ttk.Label(dialog, text="搜索要关联的项:").pack(anchor="w", padx=20, pady=3)

        search_var = tk.StringVar()
        search_entry = ttk.Entry(dialog, textvariable=search_var, width=40)
        search_entry.pack(padx=20)

        result_tree = ttk.Treeview(dialog, columns=("title", "source"), show="headings", height=8)
        result_tree.heading("title", text="标题")
        result_tree.heading("source", text="来源")
        result_tree.column("title", width=250)
        result_tree.column("source", width=80)
        result_tree.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        def do_search(*_):
            for r in result_tree.get_children():
                result_tree.delete(r)
            q = search_var.get().strip()
            if not q:
                return
            for fi in self.hub.query_items(search=q, limit=20):
                if fi.id != self._selected_item_id:
                    result_tree.insert("", tk.END, values=(fi.title[:50], fi.source_type), tags=(fi.id,))

        search_entry.bind("<KeyRelease>", do_search)

        def do_link():
            sel = result_tree.selection()
            if not sel:
                return
            target_id = result_tree.item(sel[0], "tags")[0]
            target_item = self.hub.get_item(target_id)
            if not target_item:
                return
            if target_id not in item.related_ids:
                item.related_ids.append(target_id)
                self.hub.update_item(self._selected_item_id, related_ids=item.related_ids)
            if self._selected_item_id not in target_item.related_ids:
                target_item.related_ids.append(self._selected_item_id)
                self.hub.update_item(target_id, related_ids=target_item.related_ids)
            self._refresh_items()
            dialog.destroy()
            self._log_activity(f"🔗 已关联: {item.title[:20]} ↔ {target_item.title[:20]}")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="关联", command=do_link).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _add_to_collection(self):
        if not self._selected_item_id or not self.hub:
            return
        colls = self.hub.get_collections()
        if not colls:
            messagebox.showinfo("提示", "请先在资源库中创建集合")
            return

        dialog = tk.Toplevel(self.frame)
        dialog.title("添加到集合")
        dialog.geometry("300x150")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(dialog, text="选择集合:").pack(anchor="w", padx=20, pady=10)
        coll_var = tk.StringVar()
        coll_combo = ttk.Combobox(dialog, textvariable=coll_var,
                                   values=[c.title for c in colls],
                                   state="readonly", width=30)
        coll_combo.pack(padx=20)

        def add():
            idx = coll_combo.current()
            if idx < 0:
                return
            self.hub.add_to_collection(colls[idx].id, self._selected_item_id)
            self._refresh_collections()
            self._log_activity(f"📁 已加入集合: {colls[idx].title}")
            dialog.destroy()

        ttk.Button(dialog, text="添加", command=add).pack(pady=15)

    # ================================================================
    # RSS 操作
    # ================================================================

    def _add_rss_subscription(self):
        if not self.hub:
            return
        url = self._rss_url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入RSS URL")
            return
        sub = RSSSubscription(url=url, title=self._rss_title_var.get().strip())
        self.hub.add_rss_subscription(sub)
        self._rss_url_var.set("")
        self._rss_title_var.set("")
        self._log_activity(f"📡 已添加RSS: {url[:50]}")
        self._refresh_rss()
        self._refresh_dashboard()

    def _toggle_rss_poller(self):
        if not self.hub:
            return
        if self._rss_poller_running:
            self.hub.stop_rss_poller()
            self._rss_poller_running = False
            self._rss_poller_btn.config(text="▶ 启动RSS推送")
            self._rss_poller_status.config(text="⏹ 已停止", foreground="#999")
            self._log_activity("📡 RSS推送已停止")
        else:
            self.hub.start_rss_poller(interval_seconds=300)
            self._rss_poller_running = True
            self._rss_poller_btn.config(text="⏹ 停止RSS推送")
            self._rss_poller_status.config(text="🟢 运行中(5分钟)", foreground="#27ae60")
            self._log_activity("📡 RSS推送已启动(每5分钟轮询)")

    def _poll_all_rss(self):
        if not self.hub:
            return
        self._log_activity("📡 正在轮询所有RSS源...")

        def poll():
            results = self.hub.poll_all_rss_feeds()
            total = sum(v for v in results.values() if v > 0)
            self.frame.after(0, lambda: self._log_activity(f"📡 RSS轮询完成: {total}条新内容"))
            self.frame.after(0, self._refresh_all)

        threading.Thread(target=poll, daemon=True).start()

    def _poll_one_rss(self, sub_id):
        if not self.hub:
            return

        def poll():
            new_items = self.hub.poll_rss_feed(sub_id)
            self.frame.after(0, lambda: self._log_activity(f"📡 轮询完成: {len(new_items)}条新内容"))
            self.frame.after(0, self._refresh_all)

        threading.Thread(target=poll, daemon=True).start()

    def _toggle_rss(self, sub_id):
        if not self.hub:
            return
        subs = self.hub.get_rss_subscriptions()
        sub = next((s for s in subs if s.id == sub_id), None)
        if sub:
            self.hub.update_rss_subscription(sub_id, active=not sub.active)
            self._refresh_rss()

    def _remove_rss(self, sub_id):
        if not self.hub:
            return
        if messagebox.askyesno("确认", "确定要移除此RSS订阅吗？"):
            self.hub.remove_rss_subscription(sub_id)
            self._refresh_rss()
            self._refresh_dashboard()

    # ================================================================
    # 集合操作
    # ================================================================

    def _create_collection(self):
        if not self.hub:
            return
        name = self._coll_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入集合名称")
            return
        coll = DataCollection(title=name)
        self.hub.create_collection(coll)
        self._coll_name_var.set("")
        self._log_activity(f"📁 已创建集合: {name}")
        self._refresh_collections()
        self._refresh_dashboard()

    def _on_collection_selected(self, event):
        sel = self._coll_tree.selection()
        if not sel or not self.hub:
            return
        coll_id = self._coll_tree.item(sel[0], "tags")[0]
        coll = self.hub.get_collection(coll_id)
        if not coll:
            return

        lines = [f"{coll.title} ({len(coll.item_ids)}项)"]
        for iid in coll.item_ids[:20]:
            item = self.hub.get_item(iid)
            if item:
                icon = SOURCE_ICONS.get(item.source_type, "📦")
                lines.append(f"  {icon} {item.title[:50]}")
            else:
                lines.append(f"  ❓ [已删除]")

        self._coll_detail_text.config(state=tk.NORMAL)
        self._coll_detail_text.delete(1.0, tk.END)
        self._coll_detail_text.insert(1.0, "\n".join(lines))
        self._coll_detail_text.config(state=tk.DISABLED)

    def _delete_collection(self, coll_id):
        if not self.hub:
            return
        if messagebox.askyesno("确认", "确定要删除此集合吗？"):
            self.hub.delete_collection(coll_id)
            self._refresh_collections()
            self._refresh_dashboard()

    def _gen_rss_for_coll(self, coll_id):
        if not self.hub:
            return
        coll = self.hub.get_collection(coll_id)
        if not coll:
            return
        feed = self.hub.generate_rss_feed(collection_id=coll_id, feed_title=coll.title)
        if feed:
            self._log_activity(f"📡 已生成RSS Feed: {coll.title}")
            preview = tk.Toplevel(self.frame)
            preview.title(f"RSS Feed: {coll.title}")
            preview.geometry("600x400")
            text = tk.Text(preview, wrap=tk.WORD, font=("Consolas", 10))
            text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text.insert(1.0, feed[:3000])

    # ================================================================
    # 轻度爬取 & 订阅发现
    # ================================================================

    def _lightweight_crawl_input(self, event=None):
        if not self.hub:
            return
        url = self._bm_url_var.get().strip()
        if not url:
            messagebox.showinfo("提示", "请在书签栏URL框中输入要探测的网址")
            return

        self._log_activity(f"🔍 探测中: {url[:50]}")

        def crawl():
            info = self.hub.lightweight_crawl(url)
            self.frame.after(0, lambda: self._show_crawl_result(info))

        threading.Thread(target=crawl, daemon=True).start()

    def _show_crawl_result(self, info):
        if not info.get("title") and not info.get("feeds"):
            self._log_activity(f"❌ 探测失败: {info['url'][:50]}")
            return

        self._log_activity(f"🔍 探测完成: {info.get('title', '?')[:30]} | 发现 {len(info.get('feeds', []))} 个订阅源")

        dialog = tk.Toplevel(self.frame)
        dialog.title(f"🔍 探测结果: {info.get('title', info['url'][:30])}")
        dialog.geometry("650x500")
        dialog.transient(self.frame)
        dialog.grab_set()

        meta_frame = ttk.LabelFrame(dialog, text="元信息", padding=5)
        meta_frame.pack(fill=tk.X, padx=10, pady=5)

        meta_lines = [
            f"标题: {info.get('title', '未知')}",
            f"描述: {info.get('description', '无')[:200]}",
            f"关键词: {', '.join(info.get('keywords', [])) or '无'}",
            f"作者: {info.get('author', '未知')}",
            f"状态: {info.get('status', '?')}",
        ]
        ttk.Label(meta_frame, text="\n".join(meta_lines), font=("Consolas", 10), justify=tk.LEFT).pack(anchor="w")

        feeds = info.get("feeds", [])
        if feeds:
            feeds_frame = ttk.LabelFrame(dialog, text=f"📡 发现 {len(feeds)} 个订阅源", padding=5)
            feeds_frame.pack(fill=tk.X, padx=10, pady=5)

            for i, feed in enumerate(feeds):
                row = ttk.Frame(feeds_frame)
                row.pack(fill=tk.X, pady=1)
                feed_type = feed.get("type", "rss").upper()
                ttk.Label(row, text=f"  {feed_type}:", font=("", 9, "bold"), width=5).pack(side=tk.LEFT)
                ttk.Label(row, text=feed.get("title", "")[:30], font=("", 9), width=30).pack(side=tk.LEFT, padx=3)
                ttk.Label(row, text=feed["url"][:60], foreground="#666", font=("", 8)).pack(side=tk.LEFT, padx=3)

            def import_feeds():
                count = self.hub.import_discovered_subscriptions(
                    [{"url": f["url"], "type": f.get("type", "rss"), "title": f.get("title", "")} for f in feeds]
                )
                self._log_activity(f"📡 已导入 {count} 个订阅源")
                self._refresh_rss()
                self._refresh_dashboard()
                dialog.destroy()

            ttk.Button(feeds_frame, text=f"📥 全部导入为RSS订阅 ({len(feeds)})", command=import_feeds).pack(pady=5)

        links = info.get("links", [])
        if links:
            links_frame = ttk.LabelFrame(dialog, text=f"🔗 页面链接 ({len(links)})", padding=5)
            links_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

            link_text = tk.Text(links_frame, wrap=tk.WORD, font=("Consolas", 9), height=8)
            link_text.pack(fill=tk.BOTH, expand=True)
            for link in links:
                link_text.insert(tk.END, f"{link}\n")
            link_text.config(state=tk.DISABLED)

            def add_links_to_hub():
                added = 0
                for link in links:
                    item = HubItem(
                        title=link.split("/")[-1] or link,
                        url=link,
                        source_type=SourceType.BOOKMARK.value,
                        item_type=ItemType.BOOKMARK.value,
                        pipeline_stage="ingested",
                    )
                    try:
                        self.hub.add_item(item)
                        added += 1
                    except Exception:
                        pass
                self._log_activity(f"🔖 已导入 {added} 个链接到数据枢纽")
                self._refresh_all()
                dialog.destroy()

            ttk.Button(links_frame, text=f"📥 导入全部链接到枢纽 ({len(links)})", command=add_links_to_hub).pack(pady=3)

    def _discover_subscriptions(self):
        if not self.hub:
            return
        self._log_activity("🔍 正在发现订阅源...")

        def discover():
            subs = self.hub.discover_subscriptions(source_type="bookmark", limit=30)
            self.frame.after(0, lambda: self._show_discovered_subscriptions(subs))

        threading.Thread(target=discover, daemon=True).start()

    def _show_discovered_subscriptions(self, subscriptions):
        if not subscriptions:
            self._log_activity("🔍 未发现新的订阅源")
            return

        self._log_activity(f"🔍 发现 {len(subscriptions)} 个新订阅源")

        dialog = tk.Toplevel(self.frame)
        dialog.title(f"🔍 发现 {len(subscriptions)} 个订阅源")
        dialog.geometry("700x450")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(dialog, text=f"从书签URL中发现了 {len(subscriptions)} 个RSS/Atom订阅源:",
                  font=("", 11)).pack(anchor="w", padx=15, pady=10)

        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15)

        cols = ("type", "title", "url", "source")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=15)
        tree.heading("type", text="类型")
        tree.heading("title", text="标题")
        tree.heading("url", text="订阅URL")
        tree.heading("source", text="来源网站")
        tree.column("type", width=45, stretch=False)
        tree.column("title", width=150)
        tree.column("url", width=250)
        tree.column("source", width=150)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for sub in subscriptions:
            tree.insert("", tk.END, values=(
                sub.get("type", "rss").upper(),
                sub.get("title", "")[:30],
                sub["url"][:50],
                sub.get("source_title", "")[:30],
            ))

        def import_all():
            count = self.hub.import_discovered_subscriptions(subscriptions)
            self._log_activity(f"📡 已导入 {count} 个订阅源")
            self._refresh_rss()
            self._refresh_dashboard()
            dialog.destroy()

        def import_selected():
            sel = tree.selection()
            if not sel:
                return
            selected = []
            for s in sel:
                idx = tree.index(s)
                if idx < len(subscriptions):
                    selected.append(subscriptions[idx])
            count = self.hub.import_discovered_subscriptions(selected)
            self._log_activity(f"📡 已导入 {count} 个订阅源")
            self._refresh_rss()
            self._refresh_dashboard()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=f"📥 全部导入 ({len(subscriptions)})", command=import_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📥 导入选中", command=import_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    # ================================================================
    # 管道操作
    # ================================================================

    def _crawl_bookmarks(self):
        if not self.hub:
            return
        self._log_activity("🕷️ 正在爬取书签URL...")

        def crawl():
            self.hub.pipeline_crawl_bookmarks_batch(limit=20)
            self.frame.after(0, self._refresh_all)

        threading.Thread(target=crawl, daemon=True).start()

    def _manual_scan(self):
        if not self.hub:
            return
        self._log_activity("🔍 正在扫描数据源...")

        def scan():
            try:
                results = self.hub.auto_scan_all_sources()
                total = sum(results.values())
                if total > 0:
                    details = " | ".join(f"{k}:{v}" for k, v in results.items() if v > 0)
                    self.frame.after(0, lambda: self._log_activity(f"🔍 扫描完成: {total}项 [{details}]"))
                else:
                    self.frame.after(0, lambda: self._log_activity("🔍 扫描完成: 无新数据"))
                self.frame.after(0, self._refresh_all)
            except Exception as e:
                self.frame.after(0, lambda: self._log_activity(f"❌ 扫描失败: {e}"))

        threading.Thread(target=scan, daemon=True).start()

    def _fetch_url_dialog(self):
        if not self.hub:
            return
        dialog = tk.Toplevel(self.frame)
        dialog.title("抓取URL")
        dialog.geometry("450x200")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(dialog, text="URL:").pack(anchor="w", padx=20, pady=3)
        url_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=url_var, width=55).pack(padx=20)

        ttk.Label(dialog, text="标题(可选):").pack(anchor="w", padx=20, pady=3)
        title_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=title_var, width=55).pack(padx=20)

        def do_fetch():
            url = url_var.get().strip()
            if not url:
                return
            dialog.destroy()
            self._log_activity(f"🌐 抓取中: {url[:50]}")

            def fetch():
                content = self.hub.fetch_url_content(url)
                if content:
                    item = HubItem(
                        title=title_var.get().strip() or url, url=url,
                        content=content, summary=content[:500],
                        source_type="crawler", item_type=ItemType.WEBPAGE.value,
                    )
                    result = self.hub.add_item(item)
                    self.frame.after(0, lambda: self._log_activity(f"✅ 已导入: {result.title[:40]}"))
                    self.frame.after(0, self._refresh_all)
                else:
                    self.frame.after(0, lambda: self._log_activity(f"❌ 抓取失败: {url[:50]}"))

            threading.Thread(target=fetch, daemon=True).start()

        ttk.Button(dialog, text="抓取并导入", command=do_fetch).pack(pady=10)

    def _import_local_file(self):
        filepath = filedialog.askopenfilename(
            title="选择文件导入",
            filetypes=[("所有文件", "*.*"), ("文本", "*.txt"), ("Markdown", "*.md"),
                       ("Python", "*.py"), ("JSON", "*.json"), ("CSV", "*.csv")]
        )
        if filepath and self.hub:
            try:
                item = self.hub.pipeline_local_file_to_hub(filepath)
                self._log_activity(f"📂 已导入: {item.title}")
                self._refresh_all()
            except Exception as e:
                self._log_activity(f"❌ 导入失败: {e}")

    def _generate_rss_dialog(self):
        if not self.hub:
            return
        dialog = tk.Toplevel(self.frame)
        dialog.title("制作RSS Feed")
        dialog.geometry("450x250")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(dialog, text="Feed标题:").pack(anchor="w", padx=20, pady=3)
        title_var = tk.StringVar(value="WS2 DataHub Feed")
        ttk.Entry(dialog, textvariable=title_var, width=50).pack(padx=20)

        row = ttk.Frame(dialog)
        row.pack(fill=tk.X, padx=20, pady=3)
        ttk.Label(row, text="来源类型:").pack(side=tk.LEFT)
        source_var = tk.StringVar()
        ttk.Combobox(row, textvariable=source_var,
                     values=["", "crawler", "rss", "agent", "bookmark", "analysis"],
                     width=12, state="readonly").pack(side=tk.LEFT, padx=5)
        ttk.Label(row, text="标签:").pack(side=tk.LEFT, padx=(10, 0))
        tag_var = tk.StringVar()
        ttk.Entry(row, textvariable=tag_var, width=15).pack(side=tk.LEFT, padx=5)

        ttk.Label(dialog, text="保存路径(可选):").pack(anchor="w", padx=20, pady=3)
        path_var = tk.StringVar()
        path_row = ttk.Frame(dialog)
        path_row.pack(fill=tk.X, padx=20)
        ttk.Entry(path_row, textvariable=path_var, width=40).pack(side=tk.LEFT, padx=5)

        def browse():
            fp = filedialog.asksaveasfilename(defaultextension=".xml",
                                               filetypes=[("XML", "*.xml")])
            if fp:
                path_var.set(fp)

        ttk.Button(path_row, text="浏览", command=browse).pack(side=tk.LEFT)

        def generate():
            kwargs = {
                "source_type": source_var.get() or None,
                "tag": tag_var.get() or None,
                "feed_title": title_var.get(),
            }
            save_path = path_var.get().strip()
            if save_path:
                feed = self.hub.export_rss_feed_to_file(save_path, **kwargs)
                self._log_activity(f"📡 RSS已保存: {save_path}")
            else:
                feed = self.hub.generate_rss_feed(**kwargs)
                if feed:
                    preview = tk.Toplevel(self.frame)
                    preview.title("RSS Feed 预览")
                    preview.geometry("600x400")
                    text = tk.Text(preview, wrap=tk.WORD, font=("Consolas", 10))
                    text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                    text.insert(1.0, feed[:3000])
            dialog.destroy()

        ttk.Button(dialog, text="生成", command=generate).pack(pady=10)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("WS2 数据枢纽")
    root.geometry("1100x750")

    base = Path(__file__).parent
    app = DataHubUI(root, base)
    app.frame.pack(fill=tk.BOTH, expand=True)

    root.mainloop()
