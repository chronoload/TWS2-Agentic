"""
广谱搜索引擎 - 基于 webscrapy 思路的智能搜索和过滤
"""
import re
import asyncio
import aiohttp
import random
import ipaddress
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import logging

# 导入资源聚合器
from core.resource_aggregator import ResourceAggregator
from core.page_analyzer import PageAnalyzer
from core.page_saver import PageSaver
from core.debug_manager import debug
from core.extended_data_models import create_extended_page_item_from_analysis

# 配置logger
logger = logging.getLogger(__name__)


# 常见User-Agent列表
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


class SearchEngine:
    """
    广谱搜索引擎
    支持关键词过滤、深度控制、并发爬取等功能
    """

    def __init__(self, config: Dict[str, Any]):
        debug.log_function_call("SearchEngine.__init__", {"config_keys": list(config.keys())})
        
        self.config = config
        logger.debug(f"初始化SearchEngine，配置: {list(config.keys())}")
        
        # 爬取状态（添加并发锁保护）
        self._urls_lock = asyncio.Lock()
        self.visited_urls: Set[str] = set()
        self.to_visit: List[str] = []
        self.results: List[Dict[str, Any]] = []
        
        # 取消事件
        self._cancel_event = None
        
        # 资源管理
        self.resource_aggregator = ResourceAggregator()
        self.page_analyzer = PageAnalyzer()
        self.page_saver = PageSaver()  # 添加页面保存器
        self.save_pages = True  # 是否保存HTML页面
        
        # 关键词匹配模式（AND 或 OR）
        self.keyword_match_mode = config.get('keyword_match_mode', 'AND').upper()
        
        # 并发控制
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # 随机User-Agent
        self.user_agent = random.choice(USER_AGENTS)
        
        debug.log_function_return("SearchEngine.__init__", "初始化完成")
        
    def set_cancel_event(self, cancel_event):
        """设置取消事件"""
        self._cancel_event = cancel_event
        logger.debug(f"设置取消事件: {cancel_event}")


    async def crawl_website(
        self, 
        start_url: str, 
        keywords: List[str] = None, 
        save_pages: bool = True,
        max_depth: int = None,
        max_pages: int = None,
        max_concurrent: int = None,
        keyword_match_mode: str = None,
        cancel_event = None
    ) -> List[Dict[str, Any]]:
        """
        爬取整个网站
        
        Args:
            start_url: 起始URL
            keywords: 关键词列表
            save_pages: 是否保存HTML页面
            max_depth: 最大深度
            max_pages: 最大页数
            max_concurrent: 最大并发数
            keyword_match_mode: 关键词匹配模式（AND/OR）
            cancel_event: 取消事件对象
            
        Returns:
            爬取结果列表
        """
        debug.log_function_call("SearchEngine.crawl_website", {
            "start_url": start_url[:50], 
            "keywords": keywords, 
            "save_pages": save_pages,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "max_concurrent": max_concurrent
        })
        
        logger.info(f"开始爬取网站: {start_url}")
        
        self.visited_urls.clear()
        self.to_visit = [start_url]
        self.results.clear()
        
        # 保存页面设置
        self.save_pages = save_pages
        
        # 使用传入的参数或配置中的默认值
        max_depth = max_depth if max_depth is not None else self.config.get('max_depth', 3)
        max_pages = max_pages if max_pages is not None else self.config.get('max_pages', 100)
        max_concurrent = max_concurrent if max_concurrent is not None else self.config.get('max_concurrent', 10)
        
        # 设置关键词匹配模式
        if keyword_match_mode:
            self.keyword_match_mode = keyword_match_mode.upper()
        
        # 设置取消事件
        if cancel_event is not None:
            self._cancel_event = cancel_event
        
        # 初始化并发控制
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # 构建请求头
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        self.session = aiohttp.ClientSession(headers=headers)
        
        logger.debug(f"爬取配置 - 最大深度: {max_depth}, 最大页数: {max_pages}, 最大并发: {max_concurrent}")
        debug.log_data("爬取配置", f"深度:{max_depth}, 页数:{max_pages}, 并发:{max_concurrent}, 匹配模式:{self.keyword_match_mode}")
        
        try:
            # 开始广度优先搜索
            tasks = []
            depth = 0
            
            while self.to_visit and depth < max_depth and len(self.results) < max_pages:
                # 检查是否已取消
                if self._cancel_event and self._cancel_event.is_set():
                    logger.info("爬取已取消")
                    break
                
                current_depth_urls = self.to_visit.copy()
                self.to_visit.clear()
                
                logger.info(f"处理深度 {depth}: 待爬取 {len(current_depth_urls)} 个URL，已爬取 {len(self.results)} 个")
                
                # 创建当前深度的爬取任务
                for url in current_depth_urls:
                    # 检查是否已取消
                    if self._cancel_event and self._cancel_event.is_set():
                        logger.info("爬取已取消")
                        break
                        
                    # 使用锁保护visited_urls检查
                    should_crawl = False
                    async with self._urls_lock:
                        if url not in self.visited_urls:
                            should_crawl = True
                    
                    if should_crawl:
                        task = self._crawl_page(url, keywords, depth)
                        tasks.append(task)
                
                # 等待当前深度完成
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    tasks.clear()
                
                depth += 1
                
                # 随机延迟，避免被识别为爬虫
                delay = self.config.get('request_delay', 1.0) * random.uniform(0.8, 1.5)
                await asyncio.sleep(delay)
                
        finally:
            if self.session:
                await self.session.close()
        
        logger.info(f"爬取完成 - 总结果: {len(self.results)}, 总访问: {len(self.visited_urls)}")
        logger.info(f"资源统计: {self.resource_aggregator.get_stats()}")
        
        debug.log_function_return("SearchEngine.crawl_website", f"完成: {len(self.results)}个结果")
        
        return self.results
    
    def get_resources_info(self) -> Dict[str, Any]:
        """获取资源聚合信息"""
        return {
            'all_resources': self.resource_aggregator.all_resources,
            'by_category': self.resource_aggregator.get_resources_by_category(),
            'top_domains': self.resource_aggregator.get_top_domains(10),
            'stats': self.resource_aggregator.get_stats(),
            'summary': self.resource_aggregator.get_summary()
        }

    async def _crawl_page(self, url: str, keywords: List[str], depth: int) -> None:
        """爬取单个页面 - 带重试机制"""
        debug.log_function_call("SearchEngine._crawl_page", {"url": url[:50], "depth": depth})
        logger.debug(f"爬取页面: {url} (深度: {depth})")
        
        # 检查是否已取消
        if self._cancel_event and self._cancel_event.is_set():
            logger.debug(f"爬取已取消，跳过: {url}")
            return
        
        async with self.semaphore:
            # 重试配置
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    # 检查URL是否有效
                    if not self._is_valid_url(url):
                        logger.debug(f"URL无效: {url}")
                        return
                    
                    # 发送请求 - 使用更合理的超时配置
                    timeout = aiohttp.ClientTimeout(
                        total=60,              # 总超时时间
                        connect=15,            # 连接超时
                        sock_read=45,          # Socket 读取超时
                        sock_connect=15        # Socket 连接超时
                    )
                    
                    # 添加随机延迟，避免请求过于频繁
                    await asyncio.sleep(random.uniform(0.1, 0.5))
                    
                    async with self.session.get(url, timeout=timeout, allow_redirects=True) as response:
                        if response.status == 200:
                            logger.debug(f"成功获取: {url} (状态: {response.status})")

                            html = await response.text()
                            logger.debug(f"获取HTML长度: {len(html)}")

                            # 保存HTML页面（如果启用）
                            if hasattr(self, 'save_pages') and self.save_pages:
                                try:
                                    saved_path = self.page_saver.save_page(url, html, {'depth': depth})
                                    logger.debug(f"HTML已保存: {saved_path}")
                                except Exception as e:
                                    logger.warning(f"保存HTML失败: {e}")

                            # 检查是否包含关键词
                            if keywords and not self._contains_keywords(html, keywords):
                                logger.debug(f"关键词不匹配: {url}")
                                return

                            logger.debug(f"关键词匹配: {url}")

                            # 使用 PageAnalyzer 进行统一的内容分析
                            try:
                                page_analysis = self.page_analyzer.analyze_page(html, url)
                            except Exception as e:
                                logger.warning(f"页面分析失败: {e}")
                                # 回退到最小数据集，保证数据流不断裂
                                soup = BeautifulSoup(html, 'lxml')
                                fallback = {
                                    'url': url,
                                    'title': self._extract_title(soup),
                                    'content': self._extract_content(soup),
                                    'links': [],
                                    'images': [],
                                    'meta_keywords': [],
                                    'meta_description': None,
                                    'headers': self._extract_headers(soup),
                                    'word_count': len(html.split()),
                                    'readability_score': 0.0,
                                    'entities': {},
                                    'structure': {},
                                }
                                page_analysis = fallback

                            # 基于分析结果构建 ExtendedPageItem（全场景冗余数据模板）
                            page_item = create_extended_page_item_from_analysis(
                                html=html,
                                url=url,
                                analysis_result=page_analysis,
                                depth=depth,
                            )

                            # 转换为 Dict 结构，保持向后兼容（供 GUI / Button 使用）
                            page_data = page_item.to_dict()
                            # 补充 GUI 依赖的字段（旧字段名）
                            page_data['crawl_time'] = page_item.crawl_timestamp.isoformat() if page_item.crawl_timestamp else None

                            logger.debug(f"页面标题: {page_data.get('title', '无标题')}")

                            # 使用资源聚合器收集资源（基于统一分析结果）
                            try:
                                self.resource_aggregator.add_resources_from_analysis(url, page_analysis)
                                logger.debug(f"已收集资源: {self.resource_aggregator.get_stats()['total_resources']}")
                            except Exception as e:
                                logger.warning(f"资源分析失败: {e}")

                            # 提取新链接用于后续爬取
                            soup = BeautifulSoup(html, 'lxml')
                            new_links = self._extract_new_links(soup, url)

                            # 使用锁保护to_visit集合
                            async with self._urls_lock:
                                self.to_visit.extend(new_links)

                            logger.debug(f"发现新链接: {len(new_links)}")

                            # 添加到结果（Dict 形式，供 GUI 使用）
                            self.results.append(page_data)
                            
                            # 使用锁保护visited_urls集合
                            async with self._urls_lock:
                                self.visited_urls.add(url)
                            
                            logger.info(f"成功爬取: {url} (深度: {depth}, 已爬取: {len(self.results)})")
                            debug.log_step("页面爬取成功", {"url": url[:50], "depth": depth, "total": len(self.results)})
                            return  # 成功，退出函数
                        
                        elif response.status == 404:
                            logger.warning(f"页面不存在: {url} (状态码: 404)")
                            return
                        
                        elif response.status == 403:
                            logger.warning(f"无权限访问: {url} (状态码: 403)")
                            return
                        
                        elif response.status >= 500:
                            logger.warning(f"服务器错误: {url} (状态码: {response.status})")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay * (attempt + 1))
                                continue
                            return
                        
                        else:
                            logger.warning(f"页面返回: {url} (状态码: {response.status})")
                            return
                
                except asyncio.TimeoutError:
                    logger.warning(f"请求超时: {url} (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # 指数退避
                        logger.debug(f"等待 {wait_time} 秒后重试...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"多次尝试后仍然超时，放弃: {url}")
                
                except aiohttp.ClientConnectorError as e:
                    logger.warning(f"连接错误: {url} - {e} (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                    else:
                        logger.error(f"多次尝试后连接仍失败，放弃: {url}")
                
                except aiohttp.ClientSSLError as e:
                    logger.error(f"SSL 证书错误: {url} - {e}")
                    return  # SSL 错误不重试
                
                except aiohttp.ClientError as e:
                    logger.warning(f"HTTP 客户端错误: {url} - {e} (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                    else:
                        logger.error(f"多次尝试后仍然失败，放弃: {url}")
                
                except Exception as e:
                    logger.error(f"未知错误: {url} - {type(e).__name__}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                    else:
                        logger.error(f"多次尝试失败，最终放弃: {url}")

    def _is_valid_url(self, url: str) -> bool:
        """
        检查URL是否有效（增强版，防止SSRF攻击）
        
        Args:
            url: 待检查的URL
            
        Returns:
            True if URL is valid and safe, False otherwise
        """
        try:
            parsed = urlparse(url)
            
            # 1. 验证URL格式
            if not parsed.netloc:
                logger.warning(f"无效URL: 缺少网络部分 - {url[:50]}")
                return False
            
            # 2. 排除特定文件类型
            excluded_extensions = ['.pdf', '.jpg', '.png', '.gif', '.zip', '.exe', 
                                  '.rpm', '.deb', '.dmg', '.msi', '.iso']
            if any(url.lower().endswith(ext) for ext in excluded_extensions):
                logger.debug(f"跳过文件类型: {url[:50]}")
                return False
            
            # 3. 检查协议（只允许HTTP/HTTPS）
            if parsed.scheme not in ['http', 'https']:
                logger.warning(f"无效协议: {parsed.scheme} - {url[:50]}")
                return False
            
            # 4. 检查是否为内网地址（防止SSRF）
            hostname = parsed.hostname
            if hostname:
                try:
                    ip = ipaddress.ip_address(hostname)
                    # 阻止内网IP地址
                    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                        logger.warning(f"阻止内网IP访问: {hostname} - {url[:50]}")
                        return False
                except ValueError:
                    # 不是IP地址，检查域名
                    hostname_lower = hostname.lower()
                    # 阻止常见的内网域名
                    blocked_domains = ['localhost', '127.0.0.1', '0.0.0.0',
                                     '[::1]', '169.254.', '10.', '192.168.',
                                     '172.16.', '172.17.', '172.18.', '172.19.',
                                     '172.20.', '172.21.', '172.22.', '172.23.',
                                     '172.24.', '172.25.', '172.26.', '172.27.',
                                     '172.28.', '172.29.', '172.30.', '172.31.']
                    
                    if any(hostname_lower.startswith(domain) for domain in blocked_domains):
                        logger.warning(f"阻止内网域名访问: {hostname} - {url[:50]}")
                        return False
            
            # 5. 检查端口（只允许标准端口）
            port = parsed.port
            if port and port not in [80, 443, 8080, 8443]:
                logger.warning(f"阻止非标准端口: {port} - {url[:50]}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"URL验证异常: {url[:50]} - {e}")
            return False

    def _contains_keywords(self, html: str, keywords: List[str]) -> bool:
        """
        检查页面是否包含关键词
        
        Args:
            html: HTML内容
            keywords: 关键词列表
            
        Returns:
            True if page matches keyword criteria, False otherwise
        """
        if not keywords:
            # 没有关键词时，接受所有页面
            return True
        
        soup = BeautifulSoup(html, 'lxml')
        text = soup.get_text().lower()
        
        # 根据匹配模式进行关键词检查
        if self.keyword_match_mode == 'AND':
            # AND 逻辑：必须匹配所有关键词
            for keyword in keywords:
                keyword_lower = keyword.strip().lower()
                if keyword_lower not in text:
                    logger.debug(f"关键词未匹配: {keyword}")
                    return False
            logger.debug(f"所有关键词匹配（AND模式）: {keywords}")
            return True
        else:
            # OR 逻辑：匹配任意一个关键词即可
            for keyword in keywords:
                keyword_lower = keyword.strip().lower()
                if keyword_lower in text:
                    logger.debug(f"关键词匹配（OR模式）: {keyword}")
                    return True
            logger.debug(f"没有任何关键词匹配（OR模式）")
            return False

    def _analyze_page(self, soup: BeautifulSoup, url: str, depth: int) -> Dict[str, Any]:
        """分析页面内容"""
        logger.debug(f"分析页面: {url}")
        
        page_data = {
            'url': url,
            'title': self._extract_title(soup),
            'content': self._extract_content(soup),
            'links_count': len(soup.find_all('a', href=True)),
            'images_count': len(soup.find_all('img', src=True)),
            'depth': depth,
            'meta_description': self._extract_meta_description(soup),
            'meta_keywords': self._extract_meta_keywords(soup),
            'headers': self._extract_headers(soup),
            'crawl_time': self._get_current_time()
        }
        
        logger.debug(f"页面分析 - 标题: {page_data['title'][:50]}, 链接: {page_data['links_count']}, 图片: {page_data['images_count']}")
        
        return page_data

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取标题"""
        if soup.title:
            return soup.title.string.strip() if soup.title.string else ""
        return ""

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取主要内容"""
        # 优先级选择器
        selectors = ['main', 'article', '[class*="content"]', '[class*="main"]']
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                content = max(elements, key=lambda x: len(x.get_text(strip=True)))
                return content.get_text(strip=True)
        
        return soup.body.get_text(strip=True) if soup.body else ""

    def _extract_meta_description(self, soup: BeautifulSoup) -> Optional[str]:
        """提取元描述"""
        meta = soup.find('meta', attrs={'name': 'description'})
        return meta.get('content') if meta else None

    def _extract_meta_keywords(self, soup: BeautifulSoup) -> List[str]:
        """提取元关键词"""
        meta = soup.find('meta', attrs={'name': 'keywords'})
        if meta and meta.get('content'):
            return [kw.strip() for kw in meta['content'].split(',')]
        return []

    def _extract_headers(self, soup: BeautifulSoup) -> Dict[str, List[str]]:
        """提取标题层级"""
        headers = {}
        for level in range(1, 7):
            tags = soup.find_all(f'h{level}')
            headers[f'h{level}'] = [tag.get_text(strip=True) for tag in tags]
        return headers

    def _extract_new_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """提取新链接（线程安全）"""
        new_links = []
        base_domain = urlparse(base_url).netloc
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            absolute_url = urljoin(base_url, href)
            
            # 检查是否同域
            if urlparse(absolute_url).netloc == base_domain:
                # 使用锁保护共享状态
                if absolute_url not in self.visited_urls and absolute_url not in self.to_visit:
                    new_links.append(absolute_url)
        
        return new_links

    def _get_current_time(self) -> str:
        """获取当前时间"""
        from datetime import datetime
        return datetime.now().isoformat()