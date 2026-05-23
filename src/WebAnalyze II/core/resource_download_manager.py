"""
资源下载管理器 - 协调资源下载和进度跟踪
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import aiohttp

from core.resource_downloader import ResourceDownloader

logger = logging.getLogger(__name__)


class ResourceDownloadManager:
    """资源下载管理器"""
    
    def __init__(self, download_dir: str = './downloads'):
        self.downloader = ResourceDownloader(download_dir)
        self.download_dir = Path(download_dir)
        self.current_downloads: Dict[str, Dict[str, Any]] = {}
        
    async def download_resources(
        self,
        resources: List[Dict[str, Any]],
        progress_callback: Optional[Callable] = None,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        批量下载资源
        
        Args:
            resources: 资源列表
            progress_callback: 进度回调函数
            max_concurrent: 最大并发数
            
        Returns:
            下载结果列表
        """
        logger.info(f"开始下载 {len(resources)} 个资源，最大并发数: {max_concurrent}")
        
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def download_with_semaphore(resource):
            async with semaphore:
                return await self.downloader.download_resource(
                    resource,
                    progress_callback
                )
        
        tasks = [download_with_semaphore(r) for r in resources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"下载完成，成功: {sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'completed')}")
        
        return results
    
    def get_download_summary(self) -> Dict[str, Any]:
        """获取下载统计"""
        return {
            'total_downloads': len(self.downloader.download_history),
            'successful': sum(1 for d in self.downloader.download_history if d.get('status') == 'completed'),
            'failed': sum(1 for d in self.downloader.download_history if d.get('status') == 'failed'),
            'total_size': sum(d.get('size', 0) for d in self.downloader.download_history if d.get('status') == 'completed')
        }
    
    def get_download_history(self) -> List[Dict[str, Any]]:
        """获取下载历史"""
        return self.downloader.download_history
    
    def filter_resources_by_category(
        self,
        resources: List[Dict[str, Any]],
        category: str
    ) -> List[Dict[str, Any]]:
        """按分类过滤资源"""
        return [r for r in resources if r.get('category') == category]
    
    def filter_resources_by_domain(
        self,
        resources: List[Dict[str, Any]],
        domain: str
    ) -> List[Dict[str, Any]]:
        """按域名过滤资源"""
        return [r for r in resources if r.get('domain') == domain]
