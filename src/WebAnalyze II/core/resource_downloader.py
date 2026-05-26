"""
资源下载器 - 支持批量下载和断点续传
"""
import asyncio
import aiohttp
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import urlparse
import sys
from datetime import datetime

# 导入配置常量
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import (
    REQUEST_TIMEOUT, CONNECT_TIMEOUT, MAX_RETRIES, DEFAULT_RETRY_DELAY,
    DEFAULT_USER_AGENT
)
from core.debug_manager import debug

logger = logging.getLogger(__name__)


class ResourceDownloader:
    """资源下载器 - 支持批量下载和断点续传"""
    
    def __init__(self, download_dir: str = './downloads'):
        """
        初始化下载器
        
        Args:
            download_dir: 下载目录
        """
        debug.log_function_call("ResourceDownloader.__init__", {"download_dir": download_dir})
        
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        self.active_downloads: Dict[str, Dict[str, Any]] = {}
        self.download_history: List[Dict[str, Any]] = []
        
        logger.info(f"下载器初始化完成，下载目录: {self.download_dir}")
        debug.log_function_return("ResourceDownloader.__init__", "初始化完成")
    
    async def download_resource(
        self,
        resource: Dict[str, Any],
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        下载单个资源（支持断点续传）
        
        Args:
            resource: 资源信息字典
            progress_callback: 进度回调函数 callback(downloaded_bytes, total_bytes, resource)
            
        Returns:
            下载结果字典
        """
        debug.log_function_call("ResourceDownloader.download_resource", {
            "url": resource.get('url', '')[:50],
            "filename": resource.get('filename', 'unknown')
        })
        
        url = resource['url']
        filename = resource['filename']
        
        # 创建文件路径
        file_path = self.download_dir / filename
        
        # 检查文件是否已部分下载
        downloaded_size = 0
        mode = 'wb'  # 写入二进制模式
        headers = {'User-Agent': DEFAULT_USER_AGENT}
        
        if file_path.exists():
            # 文件已存在，获取已下载的大小
            existing_size = file_path.stat().st_size
            if existing_size > 0:
                # 尝试断点续传
                headers['Range'] = f'bytes={existing_size}-'
                mode = 'ab'  # 追加二进制模式
                downloaded_size = existing_size
                logger.info(f"检测到部分下载，将尝试断点续传: {filename} (已下载: {existing_size} bytes)")
            else:
                # 空文件，删除重新下载
                file_path.unlink()
                logger.warning(f"检测到空文件，将重新下载: {filename}")
        else:
            logger.debug(f"开始新下载: {filename}")
        
        # 记录下载开始
        download_id = f"{datetime.now().timestamp()}-{filename}"
        self.active_downloads[download_id] = {
            'resource': resource,
            'start_time': datetime.now(),
            'status': 'downloading',
            'downloaded': downloaded_size,
            'total': 0
        }
        
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                timeout = aiohttp.ClientTimeout(
                    total=REQUEST_TIMEOUT,
                    connect=CONNECT_TIMEOUT
                )
                
                async with session.get(url, timeout=timeout) as response:
                    # 检查响应状态
                    if response.status == 200:
                        # 全新下载或服务器不支持断点续传
                        if downloaded_size > 0:
                            logger.info("服务器不支持断点续传，将重新下载")
                            file_path.unlink()
                            mode = 'wb'
                            downloaded_size = 0
                    elif response.status == 206:
                        # Partial Content - 服务器支持断点续传
                        logger.info(f"服务器支持断点续传: {filename}")
                    elif response.status == 416:
                        # Range Not Satisfiable - 文件已完整下载
                        logger.info(f"文件已完整下载: {filename}")
                        total_size = downloaded_size
                    else:
                        raise Exception(f"HTTP {response.status}")
                    
                    # 获取文件总大小
                    total_size = int(response.headers.get('Content-Length', 0))
                    if response.status == 206:
                        # 对于断点续传，Content-Range包含总大小
                        content_range = response.headers.get('Content-Range', '')
                        if '/' in content_range:
                            total_size = int(content_range.split('/')[1])
                    
                    self.active_downloads[download_id]['total'] = total_size
                    
                    # 流式下载
                    with open(file_path, mode) as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            self.active_downloads[download_id]['downloaded'] = downloaded_size
                            
                            # 调用进度回调
                            if progress_callback:
                                progress_callback(downloaded_size, total_size, resource)
                    
                    # 下载完成
                    self.active_downloads[download_id]['status'] = 'completed'
                    
                    # 判断是否为断点续传
                    if mode == 'ab':
                        status_note = "断点续传完成"
                    else:
                        status_note = "下载完成"
                    
                    result = {
                        'url': url,
                        'status': 'completed',
                        'file_path': str(file_path),
                        'size': downloaded_size,
                        'download_time': str(datetime.now() - self.active_downloads[download_id]['start_time']),
                        'resume_mode': mode == 'ab'
                    }
                    
                    logger.info(f"{status_note}: {filename} ({downloaded_size} bytes)")
                    debug.log_step(status_note, {"filename": filename, "size": downloaded_size})
                    
                    # 记录到历史
                    self.download_history.append(result)
                    
                    # 清理活动下载
                    del self.active_downloads[download_id]
                    
                    debug.log_function_return("ResourceDownloader.download_resource", f"完成: {filename}")
                    
                    return result
        
        except Exception as e:
            # 下载失败
            self.active_downloads[download_id]['status'] = 'failed'
            error_result = {
                'url': url,
                'status': 'failed',
                'error': str(e),
                'error_type': type(e).__name__,
                'downloaded_bytes': downloaded_size
            }
            
            logger.error(f"下载失败: {filename} - {e}")
            
            # 记录到历史
            self.download_history.append(error_result)
            
            # 保留部分下载的文件（用于后续断点续传）
            if downloaded_size > 0:
                logger.info(f"保留部分下载的文件供后续恢复: {filename} (已下载: {downloaded_size} bytes)")
            elif file_path.exists():
                # 完全失败，删除文件
                file_path.unlink()
            
            # 清理活动下载
            if download_id in self.active_downloads:
                del self.active_downloads[download_id]
            
            return error_result
    
    async def download_batch(
        self,
        resources: List[Dict[str, Any]],
        max_concurrent: int = 5,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        批量下载资源
        
        Args:
            resources: 资源列表
            max_concurrent: 最大并发数
            progress_callback: 进度回调函数
            
        Returns:
            下载结果列表
        """
        logger.info(f"开始批量下载 {len(resources)} 个资源，并发数: {max_concurrent}")
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def download_with_semaphore(resource):
            async with semaphore:
                return await self.download_resource(resource, progress_callback)
        
        results = await asyncio.gather(
            *[download_with_semaphore(resource) for resource in resources],
            return_exceptions=True
        )
        
        # 处理异常
        final_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"下载异常: {result}")
                final_results.append({
                    'status': 'failed',
                    'error': str(result)
                })
            else:
                final_results.append(result)
        
        # 统计结果
        completed = sum(1 for r in final_results if r.get('status') == 'completed')
        failed = sum(1 for r in final_results if r.get('status') in ['failed', 'skipped'])
        
        logger.info(f"批量下载完成 - 成功: {completed}, 失败/跳过: {failed}")
        
        return final_results
    
    def get_download_status(self) -> Dict[str, Any]:
        """
        获取下载状态
        
        Returns:
            下载状态信息
        """
        return {
            'active_downloads': len(self.active_downloads),
            'download_history': len(self.download_history),
            'active_details': list(self.active_downloads.values())
        }
    
    def get_download_summary(self) -> Dict[str, int]:
        """
        获取下载摘要
        
        Returns:
            下载统计信息
        """
        summary = {
            'total': len(self.download_history),
            'completed': 0,
            'failed': 0,
            'skipped': 0
        }
        
        for download in self.download_history:
            status = download.get('status', 'unknown')
            if status in summary:
                summary[status] += 1
        
        return summary
    
    def clear_history(self) -> None:
        """清空下载历史"""
        self.download_history.clear()
        logger.info("下载历史已清空")
