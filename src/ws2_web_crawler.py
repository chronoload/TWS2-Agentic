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
        
        self.search_engine = None
        self.github_crawler = None
        
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
        
        def crawl_thread():
            self._task_running = True
            try:
                results = asyncio.run(self._async_web_crawl(url, config, callback))
                if results:
                    self._save_crawl_results(results, 'web')
                    if callback:
                        callback('complete', results)
            except Exception as e:
                if callback:
                    callback('error', str(e))
            finally:
                self._task_running = False
        
        thread = threading.Thread(target=crawl_thread, daemon=True)
        thread.start()
        return True
    
    async def _async_web_crawl(self, url: str, config: Dict[str, Any], callback=None):
        """异步执行网页爬取"""
        if not self.search_engine:
            self.search_engine = SearchEngine(config)
        
        results = await self.search_engine.crawl_website(
            url,
            keywords=config.get('keywords', []),
            save_pages=config.get('save_html', True)
        )
        
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
        
        # 按钮
        btn_frame = ttk.Frame(control_frame)
        btn_frame.grid(row=4, column=0, columnspan=4, pady=10)
        
        self.start_web_btn = ttk.Button(btn_frame, text="🚀 开始爬取", command=self._start_crawl)
        self.start_web_btn.pack(side=tk.LEFT, padx=5)
        
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
            'keywords': keywords
        }
        
        def callback(status, data):
            if status == 'complete':
                self.web_progress_var.set(f"完成！共爬取 {len(data)} 页")
                self._display_results(data)
            elif status == 'error':
                self.web_progress_var.set(f"错误: {data}")
        
        self.web_progress_var.set("正在爬取...")
        self.crawler.start_web_crawl(url, config, callback)
    
    def _display_results(self, results):
        """显示结果"""
        # 清空旧结果
        for item in self.web_tree.get_children():
            self.web_tree.delete(item)
        
        for page in results:
            title = page.get('title', '无标题')
            url = page.get('url', '')
            depth = page.get('depth', 0)
            word_count = page.get('word_count', 0)
            
            self.web_tree.insert('', tk.END, values=(title[:60], url[:80], depth, word_count))


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
