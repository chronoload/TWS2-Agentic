#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 三模块联动系统
科研分析、网络研探、网络爬虫 三大功能统一管理
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import json

try:
    from ws2_synergy import (
        SynergyManager, SynergyItem,
        init_synergy_manager, get_synergy_manager
    )
    HAS_SYNERGY = True
except ImportError:
    HAS_SYNERGY = False


class SynergyHubUI:
    """WS2 三模块联动中心界面"""
    
    def __init__(self, parent, base_dir: Path, main_app=None):
        self.parent = parent
        self.base_dir = base_dir
        self.main_app = main_app
        
        if HAS_SYNERGY:
            try:
                self.manager = init_synergy_manager(base_dir)
            except Exception as e:
                print(f"Error initializing synergy manager: {e}")
                self.manager = None
        else:
            self.manager = None
        
        self.frame = ttk.Frame(parent)
        self._create_ui()
    
    def _create_ui(self):
        """创建主界面"""
        header_frame = ttk.Frame(self.frame)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        ttk.Label(header_frame, text="WS2 三模块联动中心", 
                 font=("", 16, "bold")).pack(side=tk.LEFT)
        
        self._stats_label = ttk.Label(header_frame, text="", foreground="#666")
        self._stats_label.pack(side=tk.RIGHT)
        
        quick_action_frame = ttk.LabelFrame(self.frame, text="快捷工作流", padding=10)
        quick_action_frame.pack(fill=tk.X, padx=10, pady=5)
        
        quick_cols = ttk.Frame(quick_action_frame)
        quick_cols.pack(fill=tk.X, expand=True)
        
        crawler_col = ttk.Frame(quick_cols)
        crawler_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        ttk.Label(crawler_col, text="从爬虫开始", font=("", 11, "bold")).pack(anchor="w")
        ttk.Button(crawler_col, text="1. 爬取网页", 
                  command=self._workflow_crawl_analyze).pack(fill=tk.X, pady=2)
        ttk.Button(crawler_col, text="2. GitHub搜索", 
                  command=self._workflow_github_search).pack(fill=tk.X, pady=2)
        
        search_col = ttk.Frame(quick_cols)
        search_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        ttk.Label(search_col, text="从研探开始", font=("", 11, "bold")).pack(anchor="w")
        ttk.Button(search_col, text="1. 浏览学术网站", 
                  command=self._workflow_go_search).pack(fill=tk.X, pady=2)
        ttk.Button(search_col, text="2. 导入到分析", 
                  command=self._workflow_import_to_analysis).pack(fill=tk.X, pady=2)
        
        analysis_col = ttk.Frame(quick_cols)
        analysis_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        ttk.Label(analysis_col, text="从分析开始", font=("", 11, "bold")).pack(anchor="w")
        ttk.Button(analysis_col, text="1. 导入论文", 
                  command=self._workflow_go_analysis).pack(fill=tk.X, pady=2)
        ttk.Button(analysis_col, text="2. 生成笔记", 
                  command=self._workflow_generate_note).pack(fill=tk.X, pady=2)
        
        notebook = ttk.Notebook(self.frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self._create_items_tab(notebook)
        self._create_workflow_tab(notebook)
        self._create_stats_tab(notebook)
        
        self._refresh_stats()
    
    def _create_items_tab(self, parent_notebook):
        """创建项目列表选项卡"""
        items_frame = ttk.Frame(parent_notebook)
        parent_notebook.add(items_frame, text="所有项目")
        
        filter_frame = ttk.Frame(items_frame)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(filter_frame, text="搜索:").pack(side=tk.LEFT, padx=5)
        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_frame, textvariable=self._search_var, width=30)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self._refresh_items())
        
        ttk.Button(filter_frame, text="搜索", command=self._refresh_items).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="添加", command=self._add_manual_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="刷新", command=self._refresh_items).pack(side=tk.LEFT, padx=5)
        
        filter_row = ttk.Frame(items_frame)
        filter_row.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(filter_row, text="来源:").pack(side=tk.LEFT, padx=2)
        self._source_filter_var = tk.StringVar(value="all")
        source_combo = ttk.Combobox(filter_row, textvariable=self._source_filter_var, 
                                    values=["all", "crawler", "search", "analysis", "manual"], 
                                    width=10, state="readonly")
        source_combo.pack(side=tk.LEFT, padx=2)
        source_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_items())
        
        ttk.Separator(filter_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Label(filter_row, text="类型:").pack(side=tk.LEFT, padx=2)
        self._type_filter_var = tk.StringVar(value="all")
        type_combo = ttk.Combobox(filter_row, textvariable=self._type_filter_var, 
                                  values=["all", "webpage", "paper", "github_repo"], 
                                  width=12, state="readonly")
        type_combo.pack(side=tk.LEFT, padx=2)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_items())
        
        list_frame = ttk.Frame(items_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = ("title", "source", "type", "updated")
        self._items_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self._items_tree.heading("title", text="标题")
        self._items_tree.heading("source", text="来源")
        self._items_tree.heading("type", text="类型")
        self._items_tree.heading("updated", text="更新时间")
        
        self._items_tree.column("title", width=400)
        self._items_tree.column("source", width=100)
        self._items_tree.column("type", width=100)
        self._items_tree.column("updated", width=180)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._items_tree.yview)
        self._items_tree.configure(yscrollcommand=scrollbar.set)
        
        self._items_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._items_tree.bind("<<TreeviewSelect>>", self._on_item_selected)
        self._items_tree.bind("<Double-1>", self._on_item_double_click)
        
        action_frame = ttk.LabelFrame(items_frame, text="项目操作", padding=5)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(action_frame, text="发送到科研分析", 
                  command=self._send_to_analysis).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="发送到爬虫", 
                  command=self._send_to_crawler).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="发送到研探", 
                  command=self._send_to_search).pack(side=tk.LEFT, padx=5)
        ttk.Separator(action_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(action_frame, text="标签管理", 
                  command=self._manage_tags).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="编辑", 
                  command=self._edit_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="删除", 
                  command=self._delete_item).pack(side=tk.LEFT, padx=5)
        
        detail_frame = ttk.LabelFrame(items_frame, text="项目详情", padding=5)
        detail_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._detail_text = tk.Text(detail_frame, wrap=tk.WORD, font=("Consolas", 10))
        detail_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self._detail_text.yview)
        self._detail_text.configure(yscrollcommand=detail_scroll.set)
        
        self._detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._refresh_items()
    
    def _create_workflow_tab(self, parent_notebook):
        """创建工作流选项卡"""
        workflow_frame = ttk.Frame(parent_notebook)
        parent_notebook.add(workflow_frame, text="工作流")
        
        help_frame = ttk.LabelFrame(workflow_frame, text="推荐工作流", padding=10)
        help_frame.pack(fill=tk.X, padx=10, pady=10)
        
        help_text = """典型科研工作流：

1. 使用爬虫获取网页内容或 GitHub 项目
2. 在网络研探中浏览和筛选
3. 在科研分析中处理和分析
4. 生成文献笔记，记录发现

或从任意起点开始，随时跳转！
"""
        ttk.Label(help_frame, text=help_text, justify=tk.LEFT, font=("Consolas", 11)).pack(anchor="w")
        
        flows_frame = ttk.LabelFrame(workflow_frame, text="预定义工作流", padding=10)
        flows_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        flows = [
            ("文献调研工作流", "1. 搜索论文 -> 2. 批量爬虫 -> 3. 分析整理 -> 4. 生成综述"),
            ("代码收集工作流", "1. GitHub搜索 -> 2. 克隆项目 -> 3. 分析 README -> 4. 建立索引"),
            ("课程学习工作流", "1. 浏览课程网站 -> 2. 爬取课件 -> 3. 整理笔记 -> 4. 复习回顾"),
        ]
        
        for title, desc in flows:
            flow_card = ttk.Frame(flows_frame)
            flow_card.pack(fill=tk.X, pady=5)
            
            ttk.Label(flow_card, text=title, font=("", 11, "bold")).pack(anchor="w")
            ttk.Label(flow_card, text=desc, foreground="#666").pack(anchor="w")
        
        jump_frame = ttk.Frame(workflow_frame)
        jump_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(jump_frame, text="回到首页", 
                  command=self._go_home).pack(side=tk.LEFT, padx=5)
        ttk.Button(jump_frame, text="去爬虫", 
                  command=self._go_crawler).pack(side=tk.LEFT, padx=5)
        ttk.Button(jump_frame, text="去研探", 
                  command=self._go_search).pack(side=tk.LEFT, padx=5)
        ttk.Button(jump_frame, text="去分析", 
                  command=self._go_analysis).pack(side=tk.LEFT, padx=5)
    
    def _create_stats_tab(self, parent_notebook):
        """创建统计选项卡"""
        stats_frame = ttk.Frame(parent_notebook)
        parent_notebook.add(stats_frame, text="统计")
        
        self._stats_text = tk.Text(stats_frame, wrap=tk.WORD, font=("Consolas", 11))
        stats_scroll = ttk.Scrollbar(stats_frame, orient=tk.VERTICAL, command=self._stats_text.yview)
        self._stats_text.configure(yscrollcommand=stats_scroll.set)
        
        self._stats_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        stats_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._refresh_stats_display()
    
    def _refresh_items(self):
        """刷新项目列表"""
        for item in self._items_tree.get_children():
            self._items_tree.delete(item)
        
        if not self.manager:
            return
        
        items = self.manager.get_all_items()
        
        search_query = self._search_var.get().lower()
        source_filter = self._source_filter_var.get()
        type_filter = self._type_filter_var.get()
        
        filtered = []
        for item in items:
            if source_filter != "all" and item.source != source_filter:
                continue
            if type_filter != "all" and item.content_type != type_filter:
                continue
            if search_query:
                if (search_query not in item.title.lower() and 
                    search_query not in item.content.lower()):
                    continue
            filtered.append(item)
        
        for item in filtered:
            self._items_tree.insert("", tk.END, values=(
                item.title[:80] + "..." if len(item.title) > 80 else item.title,
                item.source,
                item.content_type,
                item.updated_at[:19]
            ), tags=(item.id,))
    
    def _on_item_selected(self, event):
        """选中项目时"""
        selection = self._items_tree.selection()
        if not selection or not self.manager:
            return
        
        tag = self._items_tree.item(selection[0], "tags")[0]
        item = self.manager.get_item(tag)
        if item:
            self._display_item_detail(item)
    
    def _on_item_double_click(self, event):
        """双击项目"""
        self._send_to_analysis()
    
    def _display_item_detail(self, item: SynergyItem):
        """显示项目详情"""
        self._detail_text.delete(1.0, tk.END)
        
        content = f"""
{"="*70}
{item.title}
{"="*70}

ID: {item.id}
URL: {item.url or '无'}
来源: {item.source}
类型: {item.content_type}
标签: {', '.join(item.tags) or '无'}
关键词: {', '.join(item.keywords) or '无'}

创建时间: {item.created_at}
更新时间: {item.updated_at}

{"="*70}
内容预览:
{"="*70}
{item.content[:2000] if len(item.content) > 2000 else item.content}

{"="*70}
元数据:
{"="*70}
{json.dumps(item.metadata, indent=2, ensure_ascii=False) if item.metadata else '无'}

{"="*70}
关联项目: {len(item.related)} 个
{"="*70}
{', '.join(item.related) or '无'}
"""
        self._detail_text.insert(1.0, content)
    
    def _refresh_stats(self):
        """刷新统计显示"""
        if not self.manager:
            self._stats_label.config(text="警告: 联动管理器未加载")
            return
        
        stats = self.manager.get_statistics()
        self._stats_label.config(text=f"共 {stats['total_items']} 个项目")
    
    def _refresh_stats_display(self):
        """刷新统计详情"""
        self._stats_text.delete(1.0, tk.END)
        
        if not self.manager:
            self._stats_text.insert(1.0, "警告: 联动管理器未加载")
            return
        
        stats = self.manager.get_statistics()
        
        content = f"""
{"="*70}
WS2 三模块联动统计
{"="*70}

总项目数: {stats['total_items']}

{"="*70}
来源分布
{"="*70}
"""
        for source, count in stats['source_distribution'].items():
            content += f"  {source}: {count} 项\n"
        
        content += f"""
{"="*70}
类型分布
{"="*70}
"""
        for content_type, count in stats['type_distribution'].items():
            content += f"  {content_type}: {count} 项\n"
        
        content += f"""
{"="*70}
标签列表 ({len(stats['tags_collected'])} 个)
{"="*70}
  {', '.join(stats['tags_collected'][:50]) if stats['tags_collected'] else '无标签'}
  {f'... 还有 {len(stats["tags_collected"]) - 50} 个' if len(stats['tags_collected']) > 50 else ''}
"""
        self._stats_text.insert(1.0, content)
    
    def _add_manual_item(self):
        """手动添加项目"""
        dialog = tk.Toplevel(self.frame)
        dialog.title("添加新项目")
        dialog.geometry("500x400")
        dialog.transient(self.frame)
        dialog.grab_set()
        
        ttk.Label(dialog, text="标题:").pack(anchor="w", padx=20, pady=5)
        title_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=title_var, width=60).pack(padx=20)
        
        ttk.Label(dialog, text="URL (可选):").pack(anchor="w", padx=20, pady=5)
        url_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=url_var, width=60).pack(padx=20)
        
        ttk.Label(dialog, text="内容:").pack(anchor="w", padx=20, pady=5)
        content_text = tk.Text(dialog, height=10)
        content_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        ttk.Label(dialog, text="标签 (逗号分隔):").pack(anchor="w", padx=20, pady=5)
        tags_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=tags_var, width=60).pack(padx=20)
        
        def save():
            if not title_var.get():
                messagebox.showwarning("提示", "请输入标题")
                return
            
            tags = [t.strip() for t in tags_var.get().split(",") if t.strip()]
            item = self.manager.add_item(
                title=title_var.get(),
                url=url_var.get(),
                content=content_text.get(1.0, tk.END).strip(),
                tags=tags
            )
            messagebox.showinfo("成功", f"项目已添加！ID: {item.id}")
            self._refresh_items()
            self._refresh_stats()
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="保存", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _send_to_analysis(self):
        """发送到科研分析"""
        selection = self._items_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个项目")
            return
        
        if not self.main_app:
            messagebox.showinfo("提示", "请在主程序中使用此功能")
            return
        
        tag = self._items_tree.item(selection[0], "tags")[0]
        item = self.manager.get_item(tag)
        
        if not item:
            return
        
        if hasattr(self.main_app, '_show_research_analysis'):
            self.main_app._show_research_analysis()
            
            if hasattr(self.main_app, '_research_text'):
                self.main_app._research_text.delete(1.0, tk.END)
                if item.content:
                    self.main_app._research_text.insert(1.0, item.content)
                elif item.url:
                    self.main_app._research_text.insert(1.0, f"URL: {item.url}\n\n请从URL获取内容")
        
        messagebox.showinfo("成功", f"已跳转到科研分析！\n项目: {item.title}")
    
    def _send_to_crawler(self):
        """发送到爬虫"""
        selection = self._items_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个项目")
            return
        
        if not self.main_app:
            messagebox.showinfo("提示", "请在主程序中使用此功能")
            return
        
        tag = self._items_tree.item(selection[0], "tags")[0]
        item = self.manager.get_item(tag)
        
        if not item or not item.url:
            messagebox.showwarning("提示", "该项目没有URL，无法发送到爬虫")
            return
        
        if hasattr(self.main_app, '_show_web_crawler'):
            self.main_app._show_web_crawler()
        
        messagebox.showinfo("成功", f"已跳转到爬虫！\nURL: {item.url}")
    
    def _send_to_search(self):
        """发送到网络研探"""
        selection = self._items_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个项目")
            return
        
        if not self.main_app:
            messagebox.showinfo("提示", "请在主程序中使用此功能")
            return
        
        tag = self._items_tree.item(selection[0], "tags")[0]
        item = self.manager.get_item(tag)
        
        if not item:
            return
        
        if hasattr(self.main_app, '_show_search_page'):
            self.main_app._show_search_page()
        
        search_keywords = " ".join(item.keywords[:3]) if item.keywords else item.title
        messagebox.showinfo("成功", f"已跳转到网络研探！\n搜索关键词: {search_keywords}")
    
    def _manage_tags(self):
        """管理标签"""
        selection = self._items_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个项目")
            return
        
        tag = self._items_tree.item(selection[0], "tags")[0]
        item = self.manager.get_item(tag)
        
        if not item:
            return
        
        dialog = tk.Toplevel(self.frame)
        dialog.title(f"管理标签 - {item.title[:30]}")
        dialog.geometry("400x300")
        dialog.transient(self.frame)
        dialog.grab_set()
        
        ttk.Label(dialog, text="现有标签:").pack(anchor="w", padx=20, pady=5)
        tags_frame = ttk.Frame(dialog)
        tags_frame.pack(fill=tk.X, padx=20)
        
        current_tags = item.tags.copy()
        
        ttk.Label(dialog, text="添加新标签:").pack(anchor="w", padx=20, pady=5)
        new_tag_var = tk.StringVar()
        add_frame = ttk.Frame(dialog)
        add_frame.pack(fill=tk.X, padx=20)
        ttk.Entry(add_frame, textvariable=new_tag_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        def add_tag():
            new_tag = new_tag_var.get().strip()
            if new_tag and new_tag not in current_tags:
                current_tags.append(new_tag)
                self.manager.update_item(tag, tags=current_tags)
                new_tag_var.set("")
                self._refresh_items()
        
        ttk.Button(add_frame, text="添加", command=add_tag).pack(side=tk.LEFT)
        
        ttk.Label(dialog, text="点击标签移除:").pack(anchor="w", padx=20, pady=5)
        tags_list_frame = ttk.Frame(dialog)
        tags_list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        def remove_tag(remove_t):
            if remove_t in current_tags:
                current_tags.remove(remove_t)
                self.manager.update_item(tag, tags=current_tags)
                self._refresh_items()
                for widget in tags_list_frame.winfo_children():
                    widget.destroy()
                for t in current_tags:
                    ttk.Button(tags_list_frame, text=f"移除 {t}", 
                              command=lambda lt=t: remove_tag(lt)).pack(side=tk.LEFT, padx=2, pady=2)
        
        for t in current_tags:
            ttk.Button(tags_list_frame, text=f"移除 {t}", 
                      command=lambda lt=t: remove_tag(lt)).pack(side=tk.LEFT, padx=2, pady=2)
        
        ttk.Button(dialog, text="关闭", command=dialog.destroy).pack(pady=10)
    
    def _edit_item(self):
        """编辑项目"""
        selection = self._items_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个项目")
            return
        
        tag = self._items_tree.item(selection[0], "tags")[0]
        item = self.manager.get_item(tag)
        
        if not item:
            return
        
        dialog = tk.Toplevel(self.frame)
        dialog.title("编辑项目")
        dialog.geometry("500x400")
        dialog.transient(self.frame)
        dialog.grab_set()
        
        ttk.Label(dialog, text="标题:").pack(anchor="w", padx=20, pady=5)
        title_var = tk.StringVar(value=item.title)
        ttk.Entry(dialog, textvariable=title_var, width=60).pack(padx=20)
        
        ttk.Label(dialog, text="内容:").pack(anchor="w", padx=20, pady=5)
        content_text = tk.Text(dialog, height=15)
        content_text.insert(1.0, item.content)
        content_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        def save_edit():
            new_title = title_var.get().strip()
            new_content = content_text.get(1.0, tk.END).strip()
            if new_title:
                self.manager.update_item(tag, title=new_title, content=new_content)
                self._refresh_items()
                messagebox.showinfo("成功", "项目已更新")
                dialog.destroy()
        
        ttk.Button(dialog, text="保存", command=save_edit).pack(pady=10)
    
    def _delete_item(self):
        """删除项目"""
        selection = self._items_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个项目")
            return
        
        if not messagebox.askyesno("确认", "确定要删除此项目吗？"):
            return
        
        tag = self._items_tree.item(selection[0], "tags")[0]
        if self.manager.delete_item(tag):
            self._refresh_items()
            self._refresh_stats()
            messagebox.showinfo("成功", "项目已删除")
    
    def _workflow_crawl_analyze(self):
        self._go_crawler()
    
    def _workflow_github_search(self):
        self._go_crawler()
    
    def _workflow_go_search(self):
        self._go_search()
    
    def _workflow_import_to_analysis(self):
        self._go_analysis()
    
    def _workflow_go_analysis(self):
        self._go_analysis()
    
    def _workflow_generate_note(self):
        messagebox.showinfo("提示", "请先在科研分析中导入内容，然后使用生成笔记功能")
        self._go_analysis()
    
    def _go_home(self):
        if self.main_app and hasattr(self.main_app, '_show_overview'):
            self.main_app._show_overview()
    
    def _go_crawler(self):
        if self.main_app and hasattr(self.main_app, '_show_web_crawler'):
            self.main_app._show_web_crawler()
    
    def _go_search(self):
        if self.main_app and hasattr(self.main_app, '_show_search_page'):
            self.main_app._show_search_page()
    
    def _go_analysis(self):
        if self.main_app and hasattr(self.main_app, '_show_research_analysis'):
            self.main_app._show_research_analysis()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("WS2 三模块联动测试")
    root.geometry("1000x700")
    
    base = Path(__file__).parent
    app = SynergyHubUI(root, base)
    app.frame.pack(fill=tk.BOTH, expand=True)
    
    root.mainloop()
