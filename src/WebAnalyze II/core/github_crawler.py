"""
GitHub特制爬虫 - 专用于GitHub项目搜索和爬取
支持关键词、主题、语言、Star数等多维度搜索
"""
import asyncio
import aiohttp
import time
import json
import random
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


@dataclass
class GitHubRepo:
    """GitHub项目数据结构"""
    id: int
    full_name: str  # owner/repo
    name: str
    owner: str
    description: Optional[str]
    html_url: str
    api_url: str
    language: Optional[str]
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    watchers_count: int
    created_at: str
    updated_at: str
    pushed_at: str
    size: int  # KB
    license: Optional[str]
    topics: List[str]
    has_wiki: bool
    has_issues: bool
    has_projects: bool
    archived: bool
    fork: bool
    default_branch: str
    # 扩展字段
    readme_content: Optional[str] = None
    contributors_count: Optional[int] = None
    commit_count: Optional[int] = None
    crawl_time: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class GitHubCrawler:
    """GitHub爬虫 - 使用API搜索和爬取项目"""
    
    # API端点
    SEARCH_API = "https://api.github.com/search/repositories"
    REPO_API = "https://api.github.com/repos"
    
    # 速率限制（认证后）
    RATE_LIMIT_AUTH = 30  # 每分钟30次
    RATE_LIMIT_UNAUTH = 10  # 每分钟10次
    
    def __init__(self, token: Optional[str] = None, 
                 output_dir: str = "./data/github_projects"):
        """
        初始化GitHub爬虫
        
        Args:
            token: GitHub Personal Access Token（提高速率限制）
            output_dir: 输出目录
        """
        self.token = token
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 请求头
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "WebAnalyze-GitHubCrawler/2.0"
        }
        if token:
            self.headers["Authorization"] = f"token {token}"
        
        # 统计
        self.stats = {
            'total_searches': 0,
            'total_repos_found': 0,
            'total_repos_crawled': 0,
            'rate_limit_hits': 0,
            'errors': []
        }
        
        logger.info(f"GitHub爬虫初始化完成 - Token: {'已配置' if token else '未配置'}")
    
    async def search_repositories(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        max_pages: int = 10,
        per_page: int = 100,
        language: Optional[str] = None,
        min_stars: Optional[int] = None,
        max_stars: Optional[int] = None,
        topic: Optional[str] = None,
        created_after: Optional[str] = None,
        pushed_after: Optional[str] = None,
        progress_callback: Optional[Callable] = None
    ) -> List[GitHubRepo]:
        """
        搜索GitHub项目
        
        Args:
            query: 搜索关键词
            sort: 排序方式 (stars, forks, updated)
            order: 排序顺序 (asc, desc)
            max_pages: 最大页数
            per_page: 每页结果数（最大100）
            language: 编程语言过滤
            min_stars: 最小Star数
            max_stars: 最大Star数
            topic: 主题过滤
            created_after: 创建时间过滤（YYYY-MM-DD）
            pushed_after: 最后更新时间过滤（YYYY-MM-DD）
            progress_callback: 进度回调函数
            
        Returns:
            GitHubRepo列表
        """
        logger.info(f"开始搜索GitHub项目: {query}")
        
        # 构造查询字符串
        query_parts = [query]
        
        if language:
            query_parts.append(f"language:{language}")
        if min_stars is not None:
            query_parts.append(f"stars:>={min_stars}")
        if max_stars is not None:
            query_parts.append(f"stars:<={max_stars}")
        if topic:
            query_parts.append(f"topic:{topic}")
        if created_after:
            query_parts.append(f"created:>={created_after}")
        if pushed_after:
            query_parts.append(f"pushed:>={pushed_after}")
        
        full_query = " ".join(query_parts)
        
        all_repos = []
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            for page in range(1, max_pages + 1):
                params = {
                    "q": full_query,
                    "sort": sort,
                    "order": order,
                    "page": page,
                    "per_page": per_page
                }
                
                url = f"{self.SEARCH_API}?{urlencode(params)}"
                
                try:
                    # 检查速率限制
                    await self._check_rate_limit(session)
                    
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            items = data.get('items', [])
                            
                            if not items:
                                logger.info(f"第{page}页无结果，搜索结束")
                                break
                            
                            # 转换为GitHubRepo对象
                            for item in items:
                                repo = self._parse_repo(item)
                                all_repos.append(repo)
                            
                            total_count = data.get('total_count', 0)
                            logger.info(f"第{page}页: 获取{len(items)}个项目，总计{total_count}个")
                            
                            # 进度回调
                            if progress_callback:
                                progress_callback(page, len(all_repos), total_count)
                            
                            self.stats['total_searches'] += 1
                            
                            # 如果已经获取了所有结果
                            if len(items) < per_page:
                                break
                            
                        elif response.status == 403:
                            # 速率限制
                            await self._handle_rate_limit(response)
                            continue
                        else:
                            logger.error(f"搜索失败: {response.status}")
                            break
                    
                    # 智能延迟：基于速率限制动态调整
                    await self._smart_delay(session)
                    
                except Exception as e:
                    logger.error(f"搜索异常: {e}")
                    self.stats['errors'].append(f"搜索失败: {e}")
                    break
        
        self.stats['total_repos_found'] += len(all_repos)
        logger.info(f"搜索完成，共找到{len(all_repos)}个项目")
        
        return all_repos
    
    async def get_repo_details(
        self,
        repos: List[GitHubRepo],
        include_readme: bool = True,
        max_concurrent: int = 10,
        progress_callback: Optional[Callable] = None
    ) -> List[GitHubRepo]:
        """
        获取项目详细信息
        
        Args:
            repos: 项目列表
            include_readme: 是否获取README内容
            max_concurrent: 最大并发数
            progress_callback: 进度回调
            
        Returns:
            详细信息的项目列表
        """
        logger.info(f"开始获取{len(repos)}个项目的详细信息")
        
        semaphore = asyncio.Semaphore(max_concurrent)
        detailed_repos = []
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = []
            for idx, repo in enumerate(repos):
                task = self._fetch_repo_details(
                    session, semaphore, repo, include_readme, idx, progress_callback
                )
                tasks.append(task)
            
            detailed_repos = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 过滤异常结果
            valid_repos = []
            for result in detailed_repos:
                if isinstance(result, GitHubRepo):
                    valid_repos.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"获取详情失败: {result}")
                    self.stats['errors'].append(f"详情获取失败: {result}")
        
        self.stats['total_repos_crawled'] += len(valid_repos)
        logger.info(f"详情获取完成，成功{len(valid_repos)}/{len(repos)}")
        
        return valid_repos
    
    async def _fetch_repo_details(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        repo: GitHubRepo,
        include_readme: bool,
        index: int,
        progress_callback: Optional[Callable]
    ) -> GitHubRepo:
        """获取单个项目的详细信息"""
        async with semaphore:
            try:
                # 检查速率限制
                await self._check_rate_limit(session)
                
                # 获取详情
                url = f"{self.REPO_API}/{repo.full_name}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        repo = self._parse_repo(data)
                    elif response.status == 403:
                        await self._handle_rate_limit(response)
                    else:
                        logger.warning(f"获取{repo.full_name}失败: {response.status}")
                
                # 获取README
                if include_readme:
                    readme = await self._fetch_readme(session, repo.full_name)
                    if readme:
                        repo.readme_content = readme
                
                # 获取统计信息
                contributors = await self._fetch_contributors(session, repo.full_name)
                if contributors is not None:
                    repo.contributors_count = contributors
                
                # 设置爬取时间
                repo.crawl_time = datetime.now().isoformat()
                
                # 进度回调
                if progress_callback:
                    progress_callback(index + 1, repo.full_name)
                
                # 智能延迟
                await self._smart_delay(session)
                
                return repo
                
            except Exception as e:
                logger.error(f"获取{repo.full_name}详情异常: {e}")
                return e
    
    async def _fetch_readme(self, session: aiohttp.ClientSession, full_name: str) -> Optional[str]:
        """获取README内容"""
        try:
            url = f"{self.REPO_API}/{full_name}/readme"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    import base64
                    content = base64.b64decode(data['content']).decode('utf-8', errors='ignore')
                    return content[:5000]  # 限制前5000字符
        except Exception as e:
            logger.debug(f"获取README失败 {full_name}: {e}")
        return None
    
    async def _fetch_contributors(self, session: aiohttp.ClientSession, full_name: str) -> Optional[int]:
        """获取贡献者数量"""
        try:
            url = f"{self.REPO_API}/{full_name}/contributors?per_page=1"
            async with session.get(url) as response:
                if response.status == 200:
                    # GitHub API会在header中返回总数
                    link_header = response.headers.get('Link', '')
                    if 'last' in link_header:
                        # 解析最后一页的页码
                        import re
                        match = re.search(r'page=(\d+)>; rel="last"', link_header)
                        if match:
                            return int(match.group(1))
                    # 如果没有Link header，说明只有一页
                    data = await response.json()
                    return len(data)
        except Exception as e:
            logger.debug(f"获取贡献者失败 {full_name}: {e}")
        return None
    
    def _parse_repo(self, data: Dict[str, Any]) -> GitHubRepo:
        """解析API响应为GitHubRepo对象"""
        license_name = None
        if data.get('license'):
            license_name = data['license'].get('spdx_id') or data['license'].get('name')
        
        return GitHubRepo(
            id=data['id'],
            full_name=data['full_name'],
            name=data['name'],
            owner=data['owner']['login'],
            description=data.get('description'),
            html_url=data['html_url'],
            api_url=data['url'],
            language=data.get('language'),
            stargazers_count=data['stargazers_count'],
            forks_count=data['forks_count'],
            open_issues_count=data['open_issues_count'],
            watchers_count=data['watchers_count'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            pushed_at=data['pushed_at'],
            size=data['size'],
            license=license_name,
            topics=data.get('topics', []),
            has_wiki=data.get('has_wiki', False),
            has_issues=data.get('has_issues', False),
            has_projects=data.get('has_projects', False),
            archived=data.get('archived', False),
            fork=data.get('fork', False),
            default_branch=data.get('default_branch', 'main'),
            crawl_time=datetime.now().isoformat()
        )
    
    async def _smart_delay(self, session: aiohttp.ClientSession):
        """智能延迟策略"""
        try:
            # 获取当前速率限制状态
            url = "https://api.github.com/rate_limit"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    resources = data.get('resources', {})
                    core = resources.get('core', {})
                    search = resources.get('search', {})
                    
                    core_remaining = core.get('remaining', 30)
                    core_limit = core.get('limit', 30 if self.token else 10)
                    
                    # 根据剩余请求比例动态调整延迟
                    ratio = core_remaining / core_limit
                    
                    if ratio < 0.1:  # 剩余少于10%
                        delay = 3.0
                    elif ratio < 0.3:  # 剩余少于30%
                        delay = 2.0
                    elif ratio < 0.5:  # 剩余少于50%
                        delay = 1.0
                    else:  # 剩余充足
                        delay = 0.5
                    
                    # 添加随机抖动避免同步请求
                    delay += random.uniform(0, 0.5)
                    
                    logger.debug(f"智能延迟 {delay:.2f}秒 (剩余: {core_remaining}/{core_limit})")
                    await asyncio.sleep(delay)
                    return
        
        except Exception as e:
            logger.debug(f"智能延迟检查失败: {e}")
        
        # 默认延迟
        await asyncio.sleep(1.0)
    
    async def _check_rate_limit(self, session: aiohttp.ClientSession):
        """智能速率限制检查"""
        try:
            # 检查剩余请求次数
            url = "https://api.github.com/rate_limit"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    resources = data.get('resources', {})
                    search = resources.get('search', {})
                    core = resources.get('core', {})
                    
                    search_remaining = search.get('remaining', 0)
                    core_remaining = core.get('remaining', 0)
                    
                    # 如果剩余请求少于5次，等待重置
                    if search_remaining < 5 or core_remaining < 5:
                        search_reset = search.get('reset', 0)
                        core_reset = core.get('reset', 0)
                        reset_time = max(search_reset, core_reset)
                        sleep_time = max(reset_time - time.time(), 60)
                        
                        logger.warning(f"速率限制即将达到，等待{sleep_time:.0f}秒")
                        logger.info(f"搜索API剩余: {search_remaining}, 核心API剩余: {core_remaining}")
                        await asyncio.sleep(sleep_time)
                    else:
                        logger.debug(f"速率限制正常 - 搜索: {search_remaining}, 核心: {core_remaining}")
        except Exception as e:
            logger.debug(f"速率限制检查失败: {e}")
            # 如果检查失败，使用保守延迟
            await asyncio.sleep(1)
    
    async def _handle_rate_limit(self, response: aiohttp.ClientResponse):
        """处理速率限制"""
        self.stats['rate_limit_hits'] += 1
        reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
        sleep_time = max(reset_time - time.time(), 60)
        logger.warning(f"触发速率限制，等待{sleep_time:.0f}秒")
        await asyncio.sleep(sleep_time)
    
    def save_results(self, repos: List[GitHubRepo], filename: Optional[str] = None) -> str:
        """
        保存结果到JSON文件
        
        Args:
            repos: 项目列表
            filename: 文件名（可选）
            
        Returns:
            保存的文件路径
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"github_repos_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        # 转换为字典列表
        data = {
            'metadata': {
                'crawl_time': datetime.now().isoformat(),
                'total_repos': len(repos),
                'stats': self.stats
            },
            'repositories': [repo.to_dict() for repo in repos]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"结果已保存到: {filepath}")
        return str(filepath)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()
