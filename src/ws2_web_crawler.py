#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2网络爬虫集成模块
WebAnalyze II爬虫功能无缝集成到WS2系统

支持功能：
- 广谱网页爬虫（深度、关键词过滤、并发控制）
- GitHub项目搜索和爬取
- 网页内容分析
- 资源收集和管理
- 导出功能（JSON、CSV等）
"""

import sys
import asyncio
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
from datetime import datetime

# 导入路径调整
WEBANALYZE_PATH = Path(__file__).parent / "WebAnalyze II"
if WEBANALYZE_PATH.exists():
    sys.path.insert(0, str(WEBANALYZE_PATH))

# 检查依赖可用性
try:
    from core.search_engine import SearchEngine
    from core.github_crawler import GitHubCrawler, GitHubRepo
    from core.page_analyzer import PageAnalyzer
    from core.resource_aggregator import ResourceAggregator
    HAS_WEBANALYZE = True
except ImportError as e:
    print(f"警告：WebAnalyze II模块导入失败: {e}")
    HAS_WEBANALYZE = False

try:
    import aiohttp
    import aiofiles
    HAS_AIO = True
except ImportError:
    HAS_AIO = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


class WS2WebCrawler:
    """WS2网络爬虫 - 集成式爬虫管理器"""
    
    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path(__file__).parent
        self.data_dir = self.base_dir / "web_crawler_data"
        self.data_dir.mkdir(exist_ok=True)
        
        self.results_dir = self.data_dir / "results"
        self.results_dir.mkdir(exist_ok=True)
        
        self.html_dir = self.data_dir / "html_pages"
        self.html_dir.mkdir(exist_ok=True)
        
        self.crawl_history = []
        self.current_task = None
        self._task_running = False
        self._task_lock = threading.Lock()
        self._cancel_event = None
        
        self.search_engine = None
        self.github_crawler = None
        self._current_config = None
        
        # 自动加载历史记录
        self.load_history_from_files()
        
    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            'has_web_analyze': HAS_WEBANALYZE,
            'has_aio': HAS_AIO,
            'has_bs4': HAS_BS4,
            'is_running': self._task_running,
            'history_count': len(self.crawl_history)
        }
    
    def start_web_crawl(self, url: str, config: Dict[str, Any], callback=None):
        """启动网页爬虫（后台线程）"""
        if self._task_running:
            messagebox.warning("警告", "已有任务正在运行！")
            return False
        
        if not HAS_WEBANALYZE:
            messagebox.showerror("错误", "WebAnalyze II模块不可用，请检查依赖！")
            return False
        
        # 创建取消事件
        self._cancel_event = threading.Event()
        # 保存当前配置
        self._current_config = config
        # 每次都重新创建搜索引擎，确保使用最新配置
        self.search_engine = None
        
        def crawl_thread():
            self._task_running = True
            try:
                results = asyncio.run(self._async_web_crawl(url, self._current_config, callback))
                
                # 检查是否已取消
                if self._cancel_event and self._cancel_event.is_set():
                    if results:
                        self._save_crawl_results(results, 'web')
                        if callback:
                            callback('stopped', results)
                    return
                
                if results:
                    self._save_crawl_results(results, 'web')
                    if callback:
                        callback('complete', results)
            except Exception as e:
                if callback and (not self._cancel_event or not self._cancel_event.is_set()):
                    callback('error', str(e))
            finally:
                self._task_running = False
                self._cancel_event = None
        
        thread = threading.Thread(target=crawl_thread, daemon=True)
        thread.start()
        return True
    
    def stop_crawl(self):
        """停止当前爬取任务"""
        if self._cancel_event:
            self._cancel_event.set()
            return True
        return False
    
    async def _async_web_crawl(self, url: str, config: Dict[str, Any], callback=None):
        """异步执行网页爬取"""
        # 将取消事件传递给搜索引擎
        if not self.search_engine:
            self.search_engine = SearchEngine(config)
        
        # 设置搜索引擎的取消事件
        if hasattr(self.search_engine, 'set_cancel_event'):
            self.search_engine.set_cancel_event(self._cancel_event)
        
        results = await self.search_engine.crawl_website(
            url,
            max_depth=config.get('max_depth', 3),
            max_pages=config.get('max_pages', 50),
            max_concurrent=config.get('max_concurrent', 5),
            keywords=config.get('keywords', []),
            keyword_match_mode=config.get('keyword_match_mode', 'AND'),
            save_pages=config.get('save_html', True),
            cancel_event=self._cancel_event
        )
        
        # 检查是否被取消
        if self._cancel_event and self._cancel_event.is_set():
            if callback:
                callback('stopped', results)
            return results
        
        return results
    
    def start_github_search(self, query: str, config: Dict[str, Any], callback=None):
        """启动GitHub搜索（后台线程）"""
        if self._task_running:
            messagebox.warning("警告", "已有任务正在运行！")
            return False
        
        if not HAS_WEBANALYZE:
            messagebox.showerror("错误", "WebAnalyze II模块不可用，请检查依赖！")
            return False
        
        def search_thread():
            self._task_running = True
            try:
                results = asyncio.run(self._async_github_search(query, config, callback))
                if results:
                    self._save_crawl_results(results, 'github')
                    if callback:
                        callback('complete', results)
            except Exception as e:
                if callback:
                    callback('error', str(e))
            finally:
                self._task_running = False
        
        thread = threading.Thread(target=search_thread, daemon=True)
        thread.start()
        return True
    
    async def _async_github_search(self, query: str, config: Dict[str, Any], callback=None):
        """异步执行GitHub搜索"""
        if not self.github_crawler:
            self.github_crawler = GitHubCrawler(
                token=config.get('github_token'),
                output_dir=str(self.results_dir)
            )
        
        repos = await self.github_crawler.search_repositories(
            query,
            sort=config.get('sort', 'stars'),
            order=config.get('order', 'desc'),
            max_pages=config.get('max_pages', 5),
            language=config.get('language'),
            min_stars=config.get('min_stars'),
            topic=config.get('topic')
        )
        
        if config.get('get_details', True):
            repos = await self.github_crawler.get_repo_details(repos)
        
        return repos
    
    def _save_crawl_results(self, results, source_type):
        """保存爬取结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"crawl_{source_type}_{timestamp}.json"
        filepath = self.results_dir / filename
        
        try:
            if isinstance(results, list) and results:
                if isinstance(results[0], GitHubRepo):
                    data = {
                        'type': 'github',
                        'timestamp': datetime.now().isoformat(),
                        'count': len(results),
                        'results': [r.to_dict() for r in results]
                    }
                else:
                    data = {
                        'type': 'web',
                        'timestamp': datetime.now().isoformat(),
                        'count': len(results),
                        'results': results
                    }
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                self.crawl_history.append({
                    'time': datetime.now().isoformat(),
                    'type': source_type,
                    'count': len(results),
                    'file': str(filepath)
                })
                
                return str(filepath)
        except Exception as e:
            print(f"保存结果失败: {e}")
        
        return None
    
    def get_history(self) -> List[Dict]:
        """获取爬取历史"""
        return self.crawl_history
    
    def load_history_from_files(self):
        """从结果目录加载历史记录"""
        self.crawl_history = []
        try:
            if not self.results_dir.exists():
                return
            
            for json_file in self.results_dir.glob("crawl_*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 提取时间戳
                    timestamp = data.get('timestamp', data.get('time', ''))
                    source_type = data.get('type', 'unknown')
                    count = data.get('count', 0)
                    
                    self.crawl_history.append({
                        'time': timestamp,
                        'type': source_type,
                        'count': count,
                        'file': str(json_file)
                    })
                except Exception as e:
                    print(f"加载历史文件失败 {json_file}: {e}")
            
            # 按时间倒序排序
            self.crawl_history.sort(key=lambda x: x.get('time', ''), reverse=True)
            print(f"已加载 {len(self.crawl_history)} 条历史记录")
        except Exception as e:
            print(f"扫描历史记录失败: {e}")
    
    def load_history_file(self, filepath: str) -> Dict:
        """加载历史文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载文件失败: {e}")
            return {}


class WebCrawlerTab:
    """网页爬虫选项卡"""
    
    def __init__(self, parent, crawler: WS2WebCrawler):
        self.parent = parent
        self.crawler = crawler
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """创建界面组件"""
        # 顶部控制区
        control_frame = ttk.LabelFrame(self.frame, text="📡 网页爬虫控制", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # URL输入
        ttk.Label(control_frame, text="起始URL:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.url_var = tk.StringVar(value="https://")
        ttk.Entry(control_frame, textvariable=self.url_var, width=60).grid(row=0, column=1, columnspan=3, sticky=tk.EW, padx=5)
        
        # 关键词
        ttk.Label(control_frame, text="关键词:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.keywords_var = tk.StringVar()
        ttk.Entry(control_frame, textvariable=self.keywords_var, width=60).grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=5)
        ttk.Label(control_frame, text="(逗号分隔，如: python, machine learning)").grid(row=2, column=1, columnspan=3, sticky=tk.W, padx=5)
        
        # 配置选项
        config_frame = ttk.Frame(control_frame)
        config_frame.grid(row=3, column=0, columnspan=4, sticky=tk.EW, pady=10)
        
        self.depth_var = tk.IntVar(value=3)
        self.pages_var = tk.IntVar(value=50)
        self.concurrent_var = tk.IntVar(value=5)
        self.save_html_var = tk.BooleanVar(value=True)
        
        ttk.Label(config_frame, text="最大深度:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Spinbox(config_frame, from_=1, to=10, textvariable=self.depth_var, width=8).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(config_frame, text="最大页数:").grid(row=0, column=2, sticky=tk.W, padx=5)
        ttk.Spinbox(config_frame, from_=10, to=500, textvariable=self.pages_var, width=8).grid(row=0, column=3, sticky=tk.W)
        
        ttk.Label(config_frame, text="并发数:").grid(row=0, column=4, sticky=tk.W, padx=5)
        ttk.Spinbox(config_frame, from_=1, to=20, textvariable=self.concurrent_var, width=8).grid(row=0, column=5, sticky=tk.W)
        
        ttk.Checkbutton(config_frame, text="保存HTML", variable=self.save_html_var).grid(row=0, column=6, sticky=tk.W, padx=10)
        
        row2_frame = ttk.Frame(config_frame)
        row2_frame.grid(row=1, column=0, columnspan=7, sticky=tk.W, pady=(5, 0))
        
        ttk.Label(row2_frame, text="关键词匹配:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.keyword_match_var = tk.StringVar(value="AND")
        ttk.Combobox(row2_frame, textvariable=self.keyword_match_var, width=8,
                    values=["AND", "OR"], state="readonly").grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(row2_frame, text="(AND=全匹配 OR=任一匹配)").grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # 按钮
        btn_frame = ttk.Frame(control_frame)
        btn_frame.grid(row=4, column=0, columnspan=4, pady=10)
        
        self.start_web_btn = ttk.Button(btn_frame, text="🚀 开始爬取", command=self._start_crawl)
        self.start_web_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_web_btn = ttk.Button(btn_frame, text="🛑 停止爬取", command=self._stop_crawl, state=tk.DISABLED)
        self.stop_web_btn.pack(side=tk.LEFT, padx=5)
        
        self.import_hub_btn = ttk.Button(btn_frame, text="📥 导入到枢纽", command=self._import_to_hub, state=tk.DISABLED)
        self.import_hub_btn.pack(side=tk.LEFT, padx=5)
        
        # 进度显示
        self.web_progress_var = tk.StringVar(value="等待开始...")
        ttk.Label(control_frame, textvariable=self.web_progress_var).grid(row=5, column=0, columnspan=4, sticky=tk.W)
        
        # 结果显示区
        result_frame = ttk.LabelFrame(self.frame, text="📊 爬取结果", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 树状显示
        columns = ('title', 'url', 'depth', 'word_count')
        self.web_tree = ttk.Treeview(result_frame, columns=columns, show='headings')
        self.web_tree.heading('title', text='标题')
        self.web_tree.heading('url', text='URL')
        self.web_tree.heading('depth', text='深度')
        self.web_tree.heading('word_count', text='字数')
        
        scroll = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.web_tree.yview)
        self.web_tree.configure(yscrollcommand=scroll.set)
        
        self.web_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        control_frame.columnconfigure(1, weight=1)
    
    def _start_crawl(self):
        """启动爬取"""
        url = self.url_var.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("警告", "请输入有效的URL！")
            return
        
        keywords = [kw.strip() for kw in self.keywords_var.get().split(',') if kw.strip()]
        
        config = {
            'max_depth': self.depth_var.get(),
            'max_pages': self.pages_var.get(),
            'max_concurrent': self.concurrent_var.get(),
            'save_html': self.save_html_var.get(),
            'keywords': keywords,
            'keyword_match_mode': self.keyword_match_var.get(),
        }
        
        def callback(status, data):
            if status == 'complete':
                self.web_progress_var.set(f"完成！共爬取 {len(data)} 页")
                self._display_results(data)
                self.import_hub_btn.config(state=tk.NORMAL)
            elif status == 'error':
                self.web_progress_var.set(f"错误: {data}")
            elif status == 'stopped':
                self.web_progress_var.set("爬取已停止")
                if data:
                    self._display_results(data)
                    self.import_hub_btn.config(state=tk.NORMAL)
            # 恢复按钮状态
            self.start_web_btn.config(state=tk.NORMAL)
            self.stop_web_btn.config(state=tk.DISABLED)
        
        # 更新按钮状态
        self.start_web_btn.config(state=tk.DISABLED)
        self.stop_web_btn.config(state=tk.NORMAL)
        
        self.web_progress_var.set("正在爬取...")
        self.crawler.start_web_crawl(url, config, callback)
    
    def _stop_crawl(self):
        """停止爬取"""
        if self.crawler.stop_crawl():
            self.web_progress_var.set("正在停止...")
            self.stop_web_btn.config(state=tk.DISABLED)
    
    def _display_results(self, results):
        """显示结果"""
        # 清空旧结果
        for item in self.web_tree.get_children():
            self.web_tree.delete(item)
        
        # 保存当前结果供导入使用
        self._last_results = results
        
        for page in results:
            title = page.get('title', '无标题')
            url = page.get('url', '')
            depth = page.get('depth', 0)
            word_count = page.get('word_count', 0)
            
            self.web_tree.insert('', tk.END, values=(title[:60], url[:80], depth, word_count))
        
        # 自动导入到枢纽
        if results:
            imported = self._auto_import_to_hub(results)
            if imported > 0:
                self.web_progress_var.set(f"完成！共爬取 {len(results)} 页，已导入 {imported} 条到枢纽")
    
    def _auto_import_to_hub(self, results):
        """自动将爬取结果导入到 DataHub"""
        try:
            from ws2_data_hub import get_data_hub, HubItem, SourceType, ItemType
            from pathlib import Path
            
            hub = get_data_hub()
            if hub is None:
                # 尝试初始化 DataHub
                try:
                    from ws2_data_hub import init_data_hub
                    base_dir = self.crawler.base_dir if hasattr(self.crawler, 'base_dir') else Path(__file__).parent
                    hub_dir = base_dir / "data_hub"
                    hub = init_data_hub(hub_dir)
                    print(f"DataHub 已初始化: {hub_dir}")
                except Exception as init_err:
                    print(f"DataHub 初始化失败: {init_err}")
                    return 0
            
            if hub is None:
                print("DataHub 未初始化，无法导入")
                return 0
            
            imported = 0
            
            for item in results:
                if isinstance(item, dict):
                    title = item.get('title', item.get('name', '未知'))
                    content = item.get('content', item.get('text', ''))[:5000] if item.get('content') else ''
                    url = item.get('url', '')
                    
                    hub_item = HubItem(
                        title=title,
                        content=content,
                        summary=item.get('meta_description', '')[:500] if item.get('meta_description') else '',
                        url=url,
                        source_type=SourceType.CRAWLER.value,
                        item_type=ItemType.WEBPAGE.value,
                        tags=['web_crawl', '爬虫', 'web'],
                        metadata={
                            'depth': item.get('depth', 0),
                            'word_count': item.get('word_count', 0),
                            'links_count': item.get('links_count', 0),
                            'images_count': item.get('images_count', 0),
                            'imported_at': datetime.now().isoformat(),
                        }
                    )
                    hub.add_item(hub_item)
                    imported += 1
            
            return imported
        except Exception as e:
            import traceback
            print(f"导入到枢纽失败: {e}")
            traceback.print_exc()
            return 0
    
    def _import_to_hub(self):
        """手动导入到枢纽"""
        if not hasattr(self, '_last_results') or not self._last_results:
            messagebox.showinfo("提示", "没有可导入的结果")
            return
        
        imported = self._auto_import_to_hub(self._last_results)
        messagebox.showinfo("导入完成", f"已导入 {imported} 条到数据中心")
    
    def _refresh_history(self):
        """刷新历史记录"""
        self.crawler.load_history_from_files()
        for item in self.web_tree.get_children():
            self.web_tree.delete(item)
        
        for entry in self.crawler.get_history():
            self.web_tree.insert('', tk.END, values=(
                entry['time'],
                entry['type'],
                entry['count'],
                entry['file']
            ))


class GitHubSearchTab:
    """GitHub搜索选项卡"""
    
    def __init__(self, parent, crawler: WS2WebCrawler):
        self.parent = parent
        self.crawler = crawler
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """创建界面组件"""
        # 搜索控制区
        control_frame = ttk.LabelFrame(self.frame, text="🔍 GitHub搜索配置", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 搜索关键词
        ttk.Label(control_frame, text="搜索查询:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.query_var = tk.StringVar(value="python")
        ttk.Entry(control_frame, textvariable=self.query_var, width=50).grid(row=0, column=1, columnspan=3, sticky=tk.EW, padx=5)
        
        # 高级搜索
        search_options = ttk.Frame(control_frame)
        search_options.grid(row=1, column=0, columnspan=4, sticky=tk.EW, pady=10)
        
        self.language_var = tk.StringVar()
        self.min_stars_var = tk.IntVar(value=100)
        self.topic_var = tk.StringVar()
        
        ttk.Label(search_options, text="语言:").grid(row=0, column=0, sticky=tk.W, padx=5)
        langs = ['', 'Python', 'JavaScript', 'Java', 'Go', 'Rust', 'C++', 'TypeScript', 'Ruby']
        ttk.Combobox(search_options, textvariable=self.language_var, values=langs, width=15).grid(row=0, column=1)
        
        ttk.Label(search_options, text="最小Stars:").grid(row=0, column=2, sticky=tk.W, padx=5)
        ttk.Spinbox(search_options, from_=0, to=100000, textvariable=self.min_stars_var, width=10).grid(row=0, column=3)
        
        ttk.Label(search_options, text="主题:").grid(row=0, column=4, sticky=tk.W, padx=5)
        ttk.Entry(search_options, textvariable=self.topic_var, width=15).grid(row=0, column=5)
        
        # 分页设置
        page_frame = ttk.Frame(control_frame)
        page_frame.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=10)
        
        self.pages_var = tk.IntVar(value=3)
        self.per_page_var = tk.IntVar(value=30)
        self.get_details_var = tk.BooleanVar(value=True)
        
        ttk.Label(page_frame, text="最大页数:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Spinbox(page_frame, from_=1, to=20, textvariable=self.pages_var, width=8).grid(row=0, column=1)
        
        ttk.Label(page_frame, text="每页:").grid(row=0, column=2, sticky=tk.W, padx=5)
        ttk.Spinbox(page_frame, from_=10, to=100, textvariable=self.per_page_var, width=8).grid(row=0, column=3)
        
        ttk.Checkbutton(page_frame, text="获取详细信息", variable=self.get_details_var).grid(row=0, column=4, sticky=tk.W, padx=10)
        
        # 按钮
        btn_frame = ttk.Frame(control_frame)
        btn_frame.grid(row=3, column=0, columnspan=4, pady=10)
        
        self.start_github_btn = ttk.Button(btn_frame, text="🔍 开始搜索", command=self._start_search)
        self.start_github_btn.pack(side=tk.LEFT, padx=5)
        
        # 进度显示
        self.github_progress_var = tk.StringVar(value="等待搜索...")
        ttk.Label(control_frame, textvariable=self.github_progress_var).grid(row=4, column=0, columnspan=4, sticky=tk.W)
        
        # 结果显示区
        result_frame = ttk.LabelFrame(self.frame, text="📚 GitHub项目结果", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 树状显示
        columns = ('name', 'owner', 'stars', 'forks', 'language', 'description')
        self.github_tree = ttk.Treeview(result_frame, columns=columns, show='headings')
        self.github_tree.heading('name', text='项目名称')
        self.github_tree.heading('owner', text='作者')
        self.github_tree.heading('stars', text='Stars')
        self.github_tree.heading('forks', text='Forks')
        self.github_tree.heading('language', text='语言')
        self.github_tree.heading('description', text='描述')
        
        self.github_tree.column('name', width=150)
        self.github_tree.column('owner', width=100)
        self.github_tree.column('stars', width=80)
        self.github_tree.column('forks', width=80)
        self.github_tree.column('language', width=100)
        self.github_tree.column('description', width=300)
        
        scroll = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.github_tree.yview)
        self.github_tree.configure(yscrollcommand=scroll.set)
        
        self.github_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        control_frame.columnconfigure(1, weight=1)
    
    def _start_search(self):
        """启动搜索"""
        query = self.query_var.get().strip()
        if not query:
            messagebox.showwarning("警告", "请输入搜索查询！")
            return
        
        config = {
            'language': self.language_var.get() or None,
            'min_stars': self.min_stars_var.get() or None,
            'topic': self.topic_var.get() or None,
            'max_pages': self.pages_var.get(),
            'per_page': self.per_page_var.get(),
            'get_details': self.get_details_var.get()
        }
        
        def callback(status, data):
            if status == 'complete':
                self.github_progress_var.set(f"完成！找到 {len(data)} 个项目")
                self._display_repos(data)
            elif status == 'error':
                self.github_progress_var.set(f"错误: {data}")
        
        self.github_progress_var.set("正在搜索...")
        self.crawler.start_github_search(query, config, callback)
    
    def _display_repos(self, repos):
        """显示GitHub项目"""
        for item in self.github_tree.get_children():
            self.github_tree.delete(item)
        
        for repo in repos:
            if isinstance(repo, dict):
                name = repo.get('name', '')
                owner = repo.get('owner', '')
                stars = repo.get('stargazers_count', 0)
                forks = repo.get('forks_count', 0)
                language = repo.get('language', '')
                description = repo.get('description', '')
            else:
                name = repo.name
                owner = repo.owner
                stars = repo.stargazers_count
                forks = repo.forks_count
                language = repo.language or ''
                description = repo.description or ''
            
            desc = description[:80] if description else ''
            self.github_tree.insert('', tk.END, values=(name, owner, stars, forks, language, desc))


class HistoryTab:
    """历史记录选项卡"""
    
    def __init__(self, parent, crawler: WS2WebCrawler):
        self.parent = parent
        self.crawler = crawler
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """创建界面组件"""
        # 历史列表
        list_frame = ttk.LabelFrame(self.frame, text="📋 爬取历史", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        columns = ('time', 'type', 'count', 'file')
        self.history_tree = ttk.Treeview(list_frame, columns=columns, show='headings')
        self.history_tree.heading('time', text='时间')
        self.history_tree.heading('type', text='类型')
        self.history_tree.heading('count', text='数量')
        self.history_tree.heading('file', text='文件路径')
        
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scroll.set)
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 刷新按钮
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(btn_frame, text="🔄 刷新历史", command=self._refresh).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="📁 加载文件", command=self._load_file).pack(side=tk.LEFT, padx=5)
        
        self._refresh()
    
    def _refresh(self):
        """刷新历史"""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        # 重新从文件加载历史记录
        self.crawler.load_history_from_files()
        
        for entry in self.crawler.get_history():
            self.history_tree.insert('', tk.END, values=(
                entry['time'],
                entry['type'],
                entry['count'],
                entry['file']
            ))
    
    def _load_file(self):
        """加载历史文件"""
        filepath = filedialog.askopenfilename(
            title="选择历史文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if filepath:
            data = self.crawler.load_history_file(filepath)
            messagebox.showinfo("加载成功", f"已加载 {data.get('count', 0)} 条记录！")


class WebCrawlerUI:
    """WS2网络爬虫主界面"""
    
    def __init__(self, parent, base_dir: Path = None):
        self.parent = parent
        self.crawler = WS2WebCrawler(base_dir)
        
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """创建主界面"""
        # 标题
        header = ttk.Frame(self.frame)
        header.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(header, text="🌐 WS2 网络爬虫系统", font=('', 14, 'bold')).pack(side=tk.LEFT)
        
        status = self.crawler.get_status()
        status_text = []
        if status['has_web_analyze']:
            status_text.append("✅ WebAnalyze就绪")
        else:
            status_text.append("❌ WebAnalyze不可用")
        
        ttk.Label(header, text=" | ".join(status_text)).pack(side=tk.RIGHT)
        
        # 选项卡
        notebook = ttk.Notebook(self.frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 网页爬虫
        self.web_tab = WebCrawlerTab(notebook, self.crawler)
        notebook.add(self.web_tab.frame, text="📡 网页爬虫")
        
        # GitHub搜索
        self.github_tab = GitHubSearchTab(notebook, self.crawler)
        notebook.add(self.github_tab.frame, text="🔍 GitHub搜索")
        
        # 历史记录
        self.history_tab = HistoryTab(notebook, self.crawler)
        notebook.add(self.history_tab.frame, text="📋 历史记录")

        # 学术搜索
        self.scholar_tab = ScholarSearchTab(notebook, base_dir=self.crawler.base_dir if hasattr(self.crawler, 'base_dir') else None)
        notebook.add(self.scholar_tab.frame, text="📚 学术搜索")


class ScholarSearchTab:
    """学术搜索选项卡 - 集成ScholarMCP 15个学术API"""

    TOOL_CATEGORIES = {
        "论文检索": [
            ("search_papers", "跨库论文检索", "query, max_results=10"),
            ("get_paper_by_doi", "DOI查论文", "doi"),
            ("get_oa_fulltext", "开放获取全文", "doi"),
            ("get_citations", "引用关系", "doi, direction=forward"),
            ("fetch_arxiv", "arXiv预印本", "query, max_results=10"),
            ("search_biorxiv", "bioRxiv预印本", "query, max_results=10"),
        ],
        "生物/基因": [
            ("get_gene_info", "基因信息", "gene_id, species=human"),
            ("get_variant_annotation", "变异注释", "variant_id"),
            ("get_protein_structure", "蛋白结构", "pdb_id"),
            ("align_sequences", "序列比对", "sequence, database=nr"),
            ("get_genome_region", "基因组区域", "chromosome, start, end, species=human"),
        ],
        "数据/地球": [
            ("list_chinadoi", "中国DOI", "query, page=1"),
            ("search_ngdc", "国家基因库", "query, database=gsa"),
            ("get_earthquake_events", "地震事件", "min_magnitude=4.0, limit=10"),
            ("resolve_datacite", "DataCite DOI", "doi"),
        ],
    }

    def __init__(self, parent, base_dir=None):
        self.parent = parent
        self.base_dir = base_dir
        self.frame = ttk.Frame(parent)
        self._scholar_server = None
        self._create_widgets()

    def _get_scholar_server(self):
        if self._scholar_server is not None:
            return self._scholar_server
        try:
            from mcp.scholar.server import ScholarMCPServer
            self._scholar_server = ScholarMCPServer()
            return self._scholar_server
        except Exception:
            return None

    def _create_widgets(self):
        top_frame = ttk.LabelFrame(self.frame, text="📚 学术API聚合搜索", padding=10)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        cat_frame = ttk.Frame(top_frame)
        cat_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(cat_frame, text="分类:", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        self._tool_cat_var = tk.StringVar(value="论文检索")
        for cat_name in self.TOOL_CATEGORIES:
            ttk.Radiobutton(
                cat_frame, text=cat_name, value=cat_name,
                variable=self._tool_cat_var, command=self._on_cat_changed
            ).pack(side=tk.LEFT, padx=3)

        tool_frame = ttk.Frame(top_frame)
        tool_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(tool_frame, text="工具:", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        self._tool_var = tk.StringVar()
        self._tool_combo = ttk.Combobox(tool_frame, textvariable=self._tool_var, width=25, state="readonly")
        self._tool_combo.pack(side=tk.LEFT, padx=5)
        self._tool_combo.bind("<<ComboboxSelected>>", self._on_tool_changed)

        self._tool_desc_label = ttk.Label(tool_frame, text="", foreground="#666", font=("", 8))
        self._tool_desc_label.pack(side=tk.LEFT, padx=10)

        params_frame = ttk.LabelFrame(self.frame, text="参数配置", padding=8)
        params_frame.pack(fill=tk.X, padx=10, pady=5)

        self._params_container = ttk.Frame(params_frame)
        self._params_container.pack(fill=tk.X)

        self._param_entries = {}
        self._param_validators = {}

        self._on_cat_changed()

        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self._search_btn = ttk.Button(btn_frame, text="🔍 执行搜索", command=self._execute_search)
        self._search_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🗑️ 清空结果", command=self._clear_results).pack(side=tk.LEFT, padx=5)
        self._import_btn = ttk.Button(btn_frame, text="📥 导入到数据中心", command=self._import_to_hub, state=tk.DISABLED)
        self._import_btn.pack(side=tk.LEFT, padx=5)

        self._search_status = tk.StringVar(value="就绪")
        ttk.Label(btn_frame, textvariable=self._search_status, foreground="#666").pack(side=tk.LEFT, padx=10)

        self._last_results = None

        result_frame = ttk.LabelFrame(self.frame, text="📊 搜索结果", padding=5)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        result_paned = ttk.PanedWindow(result_frame, orient=tk.HORIZONTAL)
        result_paned.pack(fill=tk.BOTH, expand=True)

        list_frame = ttk.Frame(result_paned)
        list_scroll_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        list_scroll_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL)
        self._result_tree = ttk.Treeview(list_frame, 
            columns=("title", "authors", "year", "source"), 
            show="tree headings",
            yscrollcommand=list_scroll_y.set,
            xscrollcommand=list_scroll_x.set,
            height=15)
        list_scroll_y.config(command=self._result_tree.yview)
        list_scroll_x.config(command=self._result_tree.xview)
        
        self._result_tree.heading("#0", text="类型")
        self._result_tree.heading("title", text="标题")
        self._result_tree.heading("authors", text="作者")
        self._result_tree.heading("year", text="年份")
        self._result_tree.heading("source", text="来源")
        
        self._result_tree.column("#0", width=60, anchor="center")
        self._result_tree.column("title", width=300)
        self._result_tree.column("authors", width=150)
        self._result_tree.column("year", width=60, anchor="center")
        self._result_tree.column("source", width=100)
        
        self._result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        list_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self._result_tree.bind("<<TreeviewSelect>>", self._on_result_selected)
        
        detail_frame = ttk.LabelFrame(result_paned, text="详情", padding=5)
        self._detail_text = tk.Text(detail_frame, wrap=tk.WORD, font=("Microsoft YaHei UI", 9),
                                     bg="#fafafa", fg="#1f2937", relief=tk.FLAT)
        detail_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self._detail_text.yview)
        self._detail_text.configure(yscrollcommand=detail_scroll.set)
        self._detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._detail_text.tag_configure("label", foreground="#6b7280", font=("", 8, "bold"))
        self._detail_text.tag_configure("value", foreground="#1f2937", font=("", 9))
        self._detail_text.tag_configure("url", foreground="#3b82f6", font=("", 9))
        self._detail_text.tag_configure("abstract", foreground="#374151", font=("", 9), lmargin1=20, lmargin2=20)
        
        result_paned.add(list_frame, weight=3)
        result_paned.add(detail_frame, weight=2)

    def _on_cat_changed(self, event=None):
        cat = self._tool_cat_var.get()
        tools = self.TOOL_CATEGORIES.get(cat, [])
        self._tool_combo["values"] = [t[1] for t in tools]
        if tools:
            self._tool_combo.current(0)
            self._on_tool_changed()

    def _on_tool_changed(self, event=None):
        cat = self._tool_cat_var.get()
        tools = self.TOOL_CATEGORIES.get(cat, [])
        selected_name = self._tool_var.get()
        for tool_id, tool_name, tool_params in tools:
            if tool_name == selected_name:
                self._tool_desc_label.configure(text=f"参数: {tool_params}")
                self._build_param_fields(tool_params)
                return

    def _build_param_fields(self, params_str):
        for w in self._params_container.winfo_children():
            w.destroy()
        self._param_entries = {}
        self._param_validators = {}

        if not params_str:
            return

        params = [p.strip() for p in params_str.split(",")]
        for i, param in enumerate(params):
            if "=" in param:
                name, default = param.split("=", 1)
                name = name.strip()
                default = default.strip()
            else:
                name = param.strip()
                default = ""

            row = ttk.Frame(self._params_container)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{name}:", width=16, anchor=tk.E).pack(side=tk.LEFT, padx=(0, 5))
            var = tk.StringVar(value=default)
            
            is_int_param = name in ("max_results", "page", "limit", "start", "end", "min_magnitude", "start_year", "end_year")
            is_float_param = name in ("threshold", "score")
            
            if is_int_param:
                entry = ttk.Spinbox(row, from_=0, to=9999, textvariable=var, width=15)
            elif is_float_param:
                entry = ttk.Entry(row, textvariable=var, width=15)
                self._param_validators[name] = ("float", var)
            else:
                entry = ttk.Entry(row, textvariable=var, width=40)
            
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._param_entries[name] = var
            
            if name == "query":
                ttk.Label(row, text="🔍 搜索关键词", foreground="#3b82f6", font=("", 8)).pack(side=tk.LEFT, padx=5)
            elif name == "doi":
                ttk.Label(row, text="📑 如: 10.1234/example", foreground="#6b7280", font=("", 8)).pack(side=tk.LEFT, padx=5)

    def _get_selected_tool_id(self):
        cat = self._tool_cat_var.get()
        tools = self.TOOL_CATEGORIES.get(cat, [])
        selected_name = self._tool_var.get()
        for tool_id, tool_name, _ in tools:
            if tool_name == selected_name:
                return tool_id
        return None

    def _execute_search(self):
        tool_id = self._get_selected_tool_id()
        if not tool_id:
            messagebox.showwarning("警告", "请选择搜索工具")
            return

        server = self._get_scholar_server()
        if not server:
            self._result_text.configure(state=tk.NORMAL)
            self._result_text.delete("1.0", tk.END)
            self._result_text.insert(tk.END, "❌ ScholarMCP 模块未加载\n", "error")
            self._result_text.insert(tk.END, "请检查 mcp/scholar/ 目录是否完整\n")
            self._result_text.configure(state=tk.DISABLED)
            return

        kwargs = {}
        for name, var in self._param_entries.items():
            val = var.get().strip()
            if val:
                try:
                    if name in ("max_results", "page", "limit", "start", "end", "min_magnitude"):
                        val = int(val)
                    kwargs[name] = val
                except ValueError:
                    kwargs[name] = val

        self._search_status.set(f"搜索中: {tool_id}...")
        self._search_btn.configure(state=tk.DISABLED)

        def do_search():
            try:
                tools_list = server.get_scholar_tools()
                tool_obj = None
                for t in tools_list:
                    if t.name == tool_id:
                        tool_obj = t
                        break

                if not tool_obj:
                    self.frame.after(0, lambda: self._show_error(f"工具 {tool_id} 未找到"))
                    return

                result = tool_obj.execute(**kwargs)

                self.frame.after(0, lambda: self._show_result(result))
            except Exception as e:
                error_msg = str(e)
                self.frame.after(0, lambda err=error_msg: self._show_error(err))
            finally:
                self.frame.after(0, lambda: self._search_btn.configure(state=tk.NORMAL))
                self.frame.after(0, lambda: self._search_status.set("就绪"))

        threading.Thread(target=do_search, daemon=True).start()

    def _show_result(self, result):
        for item in self._result_tree.get_children():
            self._result_tree.delete(item)
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        
        self._last_results = None
        imported_count = 0

        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, list):
                    result = parsed
                elif isinstance(parsed, dict):
                    result = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        items = []
        
        if isinstance(result, dict):
            if "error" in result:
                self._detail_text.insert(tk.END, f"❌ 错误: {result['error']}\n", "label")
            elif "results" in result:
                items = result["results"]
            else:
                items = [result]
        elif isinstance(result, list):
            items = result
        
        if items:
            self._last_results = items
            self._import_btn.configure(state=tk.NORMAL)
            
            for item in items[:50]:
                if isinstance(item, dict):
                    title = item.get("title", item.get("name", item.get("display_name", "无标题")))
                    authors = item.get("authors", item.get("author", []))
                    if isinstance(authors, list):
                        authors_str = ", ".join(str(a) for a in authors[:3])
                        if len(authors) > 3:
                            authors_str += "..."
                    else:
                        authors_str = str(authors)
                    year = item.get("year", item.get("publication_year", ""))
                    source = item.get("source", item.get("database", item.get("platform", "")))
                    
                    icon = "📄"
                    if "arxiv" in str(source).lower() or "arxiv" in str(title).lower():
                        icon = "📝"
                    elif "doi" in str(source).lower():
                        icon = "🔗"
                    elif "gene" in str(title).lower() or "protein" in str(title).lower():
                        icon = "🧬"
                    elif "earthquake" in str(title).lower() or "seismic" in str(title).lower():
                        icon = "🌍"
                    
                    self._result_tree.insert("", tk.END, text=icon, values=(title[:50] + ("..." if len(title) > 50 else ""), authors_str[:25], year, source[:15]))
            
            if items:
                imported_count = self._auto_import_to_hub(items)
                self._import_btn.configure(state=tk.NORMAL)
        else:
            self._import_btn.configure(state=tk.DISABLED)
            if isinstance(result, str):
                self._detail_text.insert(tk.END, str(result)[:2000])
        
        if imported_count > 0:
            self._search_status.set(f"已导入 {imported_count} 条到数据中心")
        
        self._detail_text.configure(state=tk.DISABLED)

    def _auto_import_to_hub(self, items):
        try:
            from ws2_data_hub import get_data_hub, HubItem, SourceType, ItemType
            from pathlib import Path
            
            hub = get_data_hub()
            if hub is None:
                try:
                    from ws2_data_hub import init_data_hub
                    base_dir = self.base_dir if hasattr(self, 'base_dir') else Path(__file__).parent
                    hub_dir = base_dir / "data_hub"
                    hub = init_data_hub(hub_dir)
                    print(f"ScholarSearchTab - DataHub 已初始化: {hub_dir}")
                except Exception as init_err:
                    print(f"DataHub 初始化失败: {init_err}")
                    return 0
            
            if hub is None:
                print("DataHub 未初始化，无法导入")
                return 0
            
            imported = 0
            
            for item in items:
                if isinstance(item, dict):
                    title = item.get("title", item.get("name", "未知"))
                    content = item.get("abstract", item.get("description", item.get("summary", "")))
                    doi = item.get("doi", "")
                    url = item.get("url", doi)
                    authors = item.get("authors", item.get("author", []))
                    if isinstance(authors, list):
                        authors = ", ".join(str(a) for a in authors)
                    
                    hub_item = HubItem(
                        title=title,
                        content=content,
                        summary=f"作者: {authors}" if authors else "",
                        url=url,
                        source_type=SourceType.MANUAL.value,
                        item_type=ItemType.PAPER.value,
                        tags=["scholar", "academic", "paper", item.get("source", "unknown"), "auto_import"],
                        metadata={
                            "doi": doi,
                            "year": item.get("year", ""),
                            "authors": item.get("authors", []),
                            "journal": item.get("journal", item.get("venue", "")),
                            "cited_by_count": item.get("cited_by_count", 0),
                            "imported_at": datetime.now().isoformat(),
                            "tool_id": self._get_selected_tool_id() or "unknown",
                        }
                    )
                    hub.add_item(hub_item)
                    imported += 1
            
            return imported
        except Exception as e:
            import traceback
            print(f"学术搜索导入到枢纽失败: {e}")
            traceback.print_exc()
            return 0

    def _on_result_selected(self, event=None):
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        
        selection = self._result_tree.selection()
        if not selection or not self._last_results:
            self._detail_text.configure(state=tk.DISABLED)
            return
        
        idx = 0
        for i, item_id in enumerate(self._result_tree.get_children()):
            if item_id == selection[0]:
                idx = i
                break
        
        if idx < len(self._last_results):
            item = self._last_results[idx]
            if isinstance(item, dict):
                fields = [
                    ("title", "标题"),
                    ("authors", "作者"),
                    ("year", "年份"),
                    ("doi", "DOI"),
                    ("url", "URL"),
                    ("abstract", "摘要"),
                    ("source", "来源"),
                    ("journal", "期刊"),
                    ("institutions", "机构"),
                    ("keywords", "关键词"),
                    ("cited_by_count", "引用数"),
                    ("open_access", "开放获取"),
                ]
                
                for key, label in fields:
                    val = item.get(key, "")
                    if val:
                        if isinstance(val, list):
                            val = ", ".join(str(v) for v in val)
                        self._detail_text.insert(tk.END, f"{label}: ", "label")
                        self._detail_text.insert(tk.END, f"{val}\n", "value")
                
                for key in item:
                    if key not in [f[0] for f in fields] and item[key]:
                        self._detail_text.insert(tk.END, f"{key}: ", "label")
                        self._detail_text.insert(tk.END, f"{item[key]}\n", "value")
        
        self._detail_text.configure(state=tk.DISABLED)

    def _import_to_hub(self):
        if not self._last_results:
            messagebox.showwarning("提示", "没有可导入的结果")
            return
        
        try:
            from ws2_data_hub import get_data_hub, HubItem, SourceType, ItemType
            hub = get_data_hub()
            imported = 0
            
            for item in self._last_results:
                if isinstance(item, dict):
                    title = item.get("title", item.get("name", "未知"))
                    content = item.get("abstract", item.get("description", ""))
                    doi = item.get("doi", "")
                    url = item.get("url", doi)
                    authors = item.get("authors", [])
                    if isinstance(authors, list):
                        authors = ", ".join(str(a) for a in authors)
                    
                    hub_item = HubItem(
                        title=title,
                        content=content,
                        summary=f"作者: {authors}" if authors else "",
                        url=url,
                        source_type=SourceType.MANUAL.value,
                        item_type=ItemType.PAPER.value,
                        tags=["scholar", "academic", "paper", item.get("source", "unknown")],
                        metadata={
                            "doi": doi,
                            "year": item.get("year", ""),
                            "authors": item.get("authors", []),
                            "journal": item.get("journal", ""),
                            "cited_by_count": item.get("cited_by_count", 0),
                            "imported_at": datetime.now().isoformat(),
                        }
                    )
                    hub.add_item(hub_item)
                    imported += 1
            
            messagebox.showinfo("导入完成", f"已导入 {imported} 条学术资源到数据中心")
        except Exception as e:
            messagebox.showerror("导入失败", f"无法导入到数据中心:\n{e}")

    def _show_error(self, error_msg):
        for item in self._result_tree.get_children():
            self._result_tree.delete(item)
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert(tk.END, f"❌ 搜索失败\n", "label")
        self._detail_text.insert(tk.END, f"{error_msg}\n", "value")
        self._detail_text.configure(state=tk.DISABLED)
        self._search_btn.configure(state=tk.NORMAL)
        self._search_status.set("搜索失败")
        self._import_btn.configure(state=tk.DISABLED)

    def _clear_results(self):
        for item in self._result_tree.get_children():
            self._result_tree.delete(item)
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.configure(state=tk.DISABLED)
        self._last_results = None
        self._import_btn.configure(state=tk.DISABLED)


# 独立启动入口
def main():
    """独立运行主函数"""
    root = tk.Tk()
    root.title("WS2 Web Crawler - 网络爬虫系统")
    root.geometry("1000x700")
    
    app = WebCrawlerUI(root)
    app.frame.pack(fill=tk.BOTH, expand=True)
    
    root.mainloop()


if __name__ == "__main__":
    main()
