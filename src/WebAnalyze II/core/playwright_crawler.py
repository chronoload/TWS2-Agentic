"""
基于Playwright的Chrome爬虫 - 支持JavaScript渲染和实时调试
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Callable
from urllib.parse import urljoin

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
except ImportError:
    async_playwright = None
    Browser = None
    Page = None
    BrowserContext = None


class PlaywrightCrawler:
    """基于Playwright的Chrome爬虫"""

    def __init__(self, debug_mode=False, headless=True, timeout=30000):
        """
        初始化爬虫
        
        Args:
            debug_mode: 是否启用调试模式
            headless: 是否无头模式运行
            timeout: 页面加载超时 (毫秒)
        """
        if not async_playwright:
            raise ImportError("Playwright未安装，请运行: pip install playwright && playwright install")
        
        self.debug_mode = debug_mode
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # 调试日志
        self.debug_logs: List[Dict] = []
        self.network_logs: List[Dict] = []
        self.performance_metrics: Dict = {}
        
        # 回调函数
        self.on_page_loaded: Optional[Callable] = None
        self.on_network_request: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

    async def launch(self):
        """启动浏览器"""
        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled'] if self.debug_mode else []
            )
            self._log('browser', f'浏览器已启动 (调试模式: {self.debug_mode})')
            return True
        except Exception as e:
            self._log('error', f'浏览器启动失败: {e}')
            if self.on_error:
                await self.on_error(f'浏览器启动失败: {e}')
            return False

    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            self._log('browser', '浏览器已关闭')

    async def create_context(self):
        """创建浏览器上下文"""
        if not self.browser:
            return False
        
        try:
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            self.context = await self.browser.new_context(**context_options)
            
            if self.debug_mode:
                await self.context.add_init_script("""
                    window._crawlerDebug = {
                        logs: [],
                        errors: [],
                        performance: performance.getEntriesByType('navigation')[0]
                    };
                    console.log('爬虫调试环境已初始化');
                """)
            
            self._log('context', '浏览器上下文已创建')
            return True
        except Exception as e:
            self._log('error', f'创建上下文失败: {e}')
            return False

    async def fetch_page(self, url: str, wait_for: Optional[str] = None) -> Optional[Dict]:
        """
        获取页面内容
        
        Args:
            url: 页面URL
            wait_for: 等待的选择器或路径
            
        Returns:
            页面数据字典或None
        """
        try:
            if not self.context:
                await self.create_context()
            
            self.page = await self.context.new_page()
            
            # 设置网络监听
            await self.page.on('request', self._on_request)
            await self.page.on('response', self._on_response)
            
            self._log('request', f'正在加载: {url}')
            
            # 导航到URL
            response = await self.page.goto(url, wait_until='networkidle', timeout=self.timeout)
            
            if not response:
                self._log('error', f'页面加载失败: {url}')
                if self.on_error:
                    await self.on_error(f'页面加载失败: {url}')
                return None
            
            # 等待特定元素加载
            if wait_for:
                try:
                    await self.page.wait_for_selector(wait_for, timeout=5000)
                    self._log('debug', f'已等待元素加载: {wait_for}')
                except:
                    self._log('warning', f'元素加载超时: {wait_for}')
            
            # 获取页面内容
            html = await self.page.content()
            
            # 获取页面标题
            title = await self.page.title()
            
            # 收集性能指标
            metrics = await self.page.evaluate("""() => {
                const perf = performance.timing;
                return {
                    dns: perf.domainLookupEnd - perf.domainLookupStart,
                    tcp: perf.connectEnd - perf.connectStart,
                    request: perf.responseStart - perf.requestStart,
                    response: perf.responseEnd - perf.responseStart,
                    dom: perf.domComplete - perf.domLoading,
                    total: perf.loadEventEnd - perf.navigationStart
                };
            }""")
            
            page_data = {
                'url': url,
                'title': title,
                'html': html,
                'status': response.status,
                'headers': dict(response.headers),
                'metrics': metrics,
                'timestamp': datetime.now().isoformat(),
                'network_logs': self.network_logs[-10:]  # 最近10条网络请求
            }
            
            self._log('success', f'页面已加载: {title} (状态码: {response.status})')
            
            if self.on_page_loaded:
                await self.on_page_loaded(page_data)
            
            return page_data
            
        except asyncio.TimeoutError:
            self._log('error', f'页面加载超时: {url}')
            if self.on_error:
                await self.on_error(f'页面加载超时: {url}')
            return None
        except Exception as e:
            self._log('error', f'获取页面失败: {e}')
            if self.on_error:
                await self.on_error(f'获取页面失败: {e}')
            return None
        finally:
            if self.page:
                await self.page.close()

    async def take_screenshot(self, url: str, output_path: Optional[str] = None) -> Optional[bytes]:
        """
        截图页面
        
        Args:
            url: 页面URL
            output_path: 输出路径（可选）
            
        Returns:
            截图字节数据或None
        """
        try:
            if not self.context:
                await self.create_context()
            
            page = await self.context.new_page()
            await page.goto(url, wait_until='networkidle', timeout=self.timeout)
            
            screenshot = await page.screenshot(full_page=True)
            
            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(screenshot)
                self._log('debug', f'截图已保存: {output_path}')
            
            await page.close()
            return screenshot
            
        except Exception as e:
            self._log('error', f'截图失败: {e}')
            return None

    async def extract_links(self, url: str) -> List[str]:
        """提取页面中的所有链接"""
        try:
            page_data = await self.fetch_page(url)
            if not page_data:
                return []
            
            if not self.page:
                return []
            
            links = await self.page.eval_on_selector_all('a[href]', 'elements => elements.map(el => el.href)')
            return [urljoin(url, link) for link in links if link]
            
        except Exception as e:
            self._log('error', f'提取链接失败: {e}')
            return []

    async def _on_request(self, request):
        """网络请求事件"""
        request_data = {
            'url': request.url,
            'method': request.method,
            'headers': dict(request.headers),
            'timestamp': datetime.now().isoformat()
        }
        self.network_logs.append(request_data)
        
        if self.on_network_request:
            await self.on_network_request(request_data)

    async def _on_response(self, response):
        """网络响应事件"""
        try:
            self._log('network', f'{response.status} {response.url.split("/")[-1]}')
        except:
            pass

    def _log(self, level: str, message: str):
        """记录调试日志"""
        log_entry = {
            'level': level,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        self.debug_logs.append(log_entry)
        
        if self.debug_mode:
            print(f'[{level.upper()}] {message}')

    def get_debug_logs(self) -> List[Dict]:
        """获取调试日志"""
        return self.debug_logs

    def get_network_logs(self) -> List[Dict]:
        """获取网络日志"""
        return self.network_logs

    def clear_logs(self):
        """清空日志"""
        self.debug_logs = []
        self.network_logs = []


class AsyncCrawlerManager:
    """异步爬虫管理器"""
    
    def __init__(self, max_concurrent=3, debug_mode=False):
        """
        初始化管理器
        
        Args:
            max_concurrent: 最大并发数
            debug_mode: 是否启用调试模式
        """
        self.max_concurrent = max_concurrent
        self.debug_mode = debug_mode
        self.crawlers: List[PlaywrightCrawler] = []
        self.results = []
        self.errors = []

    async def fetch_multiple_pages(self, urls: List[str]) -> List[Dict]:
        """并发获取多个页面"""
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def fetch_with_limit(url):
            async with semaphore:
                crawler = PlaywrightCrawler(
                    debug_mode=self.debug_mode,
                    headless=True
                )
                try:
                    await crawler.launch()
                    result = await crawler.fetch_page(url)
                    if result:
                        self.results.append(result)
                    return result
                except Exception as e:
                    error = {'url': url, 'error': str(e)}
                    self.errors.append(error)
                    return None
                finally:
                    await crawler.close()
        
        await asyncio.gather(*[fetch_with_limit(url) for url in urls])
        return self.results
