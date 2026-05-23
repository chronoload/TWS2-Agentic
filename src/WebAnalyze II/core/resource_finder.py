"""
资源发现器 - 从网页中发现和分类资源
支持多种资源类型的识别和提取
"""
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
from core.debug_manager import debug

logger = logging.getLogger(__name__)


class ResourceFinder:
    """资源发现器 - 从网页中发现和分类资源"""
    
    # 资源类型定义
    RESOURCE_TYPES = {
        'document': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.odt', '.ods'],
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff', '.psd'],
        'video': ['.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm', '.m4v', '.3gp'],
        'audio': ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma', '.opus'],
        'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'],
        'executable': ['.exe', '.msi', '.dmg', '.apk', '.app', '.sh', '.bat'],
        'code': ['.py', '.js', '.html', '.css', '.json', '.xml', '.java', '.cpp', '.h', '.c'],
        'font': ['.ttf', '.otf', '.woff', '.woff2', '.eot']
    }
    
    # 资源图标
    TYPE_ICONS = {
        'document': '📄',
        'image': '🖼️',
        'video': '🎬',
        'audio': '🎵',
        'archive': '📦',
        'executable': '⚙️',
        'code': '💻',
        'font': '🔤',
        'webpage': '🌐',
        'unknown': '📎'
    }
    
    def __init__(self):
        self.resources: Dict[str, List[Dict[str, Any]] = {
            resource_type: [] for resource_type in self.RESOURCE_TYPES.keys()
        }
        self.all_resources: List[Dict[str, Any]] = []
        self.webpages: List[Dict[str, Any]] = []  # 所有网页链接
        self.all_links: List[Dict[str, Any]] = []  # 所有链接
    
    def find_resources_in_text(self, text: str, base_url: str = '') -> None:
        """
        在文本中查找所有资源链接
        
        Args:
            text: 包含链接的文本
            base_url: 基础URL，用于相对路径转换
        """
        debug.log_function_call("ResourceFinder.find_resources_in_text", {"text_length": len(text), "base_url": base_url[:50]})
        
        # 匹配所有URL（包括http/https）
        url_pattern = r'https?://[^\s<>"\'\)]+\.[a-z]{2,}(?:/[^\s<>"\'\)]*)?'
        urls = re.findall(url_pattern, text, re.IGNORECASE)
        
        debug.log_step("发现URL", {"count": len(urls)})
        
        for url in urls:
            # 归类链接
            self._classify_and_add_link(url, base_url)
    
    def _classify_and_add_link(self, url: str, base_url: str = '') -> None:
        """
        分类链接并添加到相应列表
        
        Args:
            url: 链接URL
            base_url: 来源页面URL
        """
        parsed = urlparse(url)
        
        # 1. 检查是否是资源文件
        resource_type = self.classify_resource(url)
        if resource_type:
            resource = self._create_resource_info(url, base_url)
            if resource:
                self._add_resource(resource)
                logger.debug(f"发现资源: {resource['type']} - {url[:50]}")
            return
        
        # 2. 检查是否是网页链接
        path_lower = parsed.path.lower()
        if not path_lower or path_lower.endswith(('/', '.html', '.htm', '.php', '.asp', '.aspx', '.jsp', '')):
            # 这可能是网页链接
            self._add_webpage_link(url, base_url)
        
        # 3. 其他所有链接都记录
        self._add_all_link(url, base_url)
    
    def _add_webpage_link(self, url: str, base_url: str = '') -> None:
        """添加网页链接"""
        parsed = urlparse(url)
        
        link_info = {
            'url': url,
            'type': 'webpage',
            'icon': self.TYPE_ICONS.get('webpage', '🌐'),
            'title': self._extract_filename(parsed.path) or '页面',
            'domain': parsed.netloc,
            'base_url': base_url,
            'found_at': '',
            'status': 'pending'
        }
        
        # 避免重复
        for existing in self.webpages:
            if existing['url'] == url:
                return
        
        self.webpages.append(link_info)
        debug.log_step("添加网页链接", {"url": url[:50]})
        """添加所有链接（包括无法分类的）"""
        parsed = urlparse(url)
        
        link_info = {
            'url': url,
            'type': 'unknown',
            'icon': self.TYPE_ICONS.get('unknown', '📎'),
            'title': self._extract_filename(parsed.path) or '未知',
            'domain': parsed.netloc,
            'base_url': base_url,
            'found_at': '',
            'status': 'pending'
        }
        
        # 避免重复
        for existing in self.all_links:
            if existing['url'] == url:
                return
        
        self.all_links.append(link_info)
        debug.log_step("添加未知链接", {"url": url[:50]})
        """
        根据URL后缀分类资源类型
        
        Args:
            url: 资源URL
            
        Returns:
            资源类型，如果无法识别则返回None
        """
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        for resource_type, extensions in self.RESOURCE_TYPES.items():
            if any(path.endswith(ext) for ext in extensions):
                return resource_type
        
        return None
    
    def _create_resource_info(self, url: str, base_url: str = '') -> Optional[Dict[str, Any]]:
        """
        创建资源信息字典
        
        Args:
            url: 资源URL
            base_url: 基础URL
            
        Returns:
            资源信息字典，如果无法识别类型则返回None
        """
        resource_type = self.classify_resource(url)
        if not resource_type:
            return None
        
        parsed = urlparse(url)
        
        return {
            'url': url,
            'type': resource_type,
            'icon': self.TYPE_ICONS.get(resource_type, '📎'),
            'filename': self._extract_filename(parsed.path),
            'extension': self._extract_extension(parsed.path),
            'size': 0,  # 需要请求获取
            'domain': parsed.netloc,
            'base_url': base_url,
            'found_at': '',
            'status': 'pending'  # pending, downloading, completed, failed
        }
    
    def _extract_filename(self, path: str) -> str:
        """从路径中提取文件名"""
        filename = Path(path).name
        return filename if filename else 'unknown'
    
    def _extract_extension(self, path: str) -> str:
        """从路径中提取扩展名"""
        return Path(path).suffix.lower()
    
    def _add_resource(self, resource: Dict[str, Any]) -> None:
        """
        添加资源到列表中
        
        Args:
            resource: 资源信息字典
        """
        resource_type = resource['type']
        
        # 避免重复
        for existing in self.resources[resource_type]:
            if existing['url'] == resource['url']:
                return
        
        self.resources[resource_type].append(resource)
        self.all_resources.append(resource)
    
    def get_resources_by_type(self, resource_type: str) -> List[Dict[str, Any]]:
        """
        获取指定类型的资源列表
        
        Args:
            resource_type: 资源类型
            
        Returns:
            该类型的资源列表
        """
        return self.resources.get(resource_type, [])
    
    def get_resource_summary(self) -> Dict[str, int]:
        """
        获取资源统计摘要
        
        Returns:
            各类型资源的数量统计
        """
        return {
            resource_type: len(resources)
            for resource_type, resources in self.resources.items()
        }
    
    def get_full_summary(self) -> Dict[str, Any]:
        """
        获取完整统计摘要（包括所有链接）
        
        Returns:
            完整的统计信息
        """
        return {
            'resources': self.get_resource_summary(),
            'webpages': len(self.webpages),
            'all_links': len(self.all_links),
            'total_resources': len(self.all_resources)
        }
    
    def get_all_resources(self) -> List[Dict[str, Any]]:
        """获取所有资源列表"""
        return self.all_resources
    
    def get_webpages(self) -> List[Dict[str, Any]]:
        """获取所有网页链接"""
        return self.webpages
    
    def get_all_links(self) -> List[Dict[str, Any]]:
        """获取所有链接"""
        return self.all_links
    
    def clear(self) -> None:
        """清空所有资源"""
        self.resources = {resource_type: [] for resource_type in self.RESOURCE_TYPES.keys()}
        self.all_resources.clear()
        self.webpages.clear()
        self.all_links.clear()
    
    def export_resources(self, output_file: str) -> None:
        """
        导出资源列表到JSON文件
        
        Args:
            output_file: 输出文件路径
        """
        import json
        
        export_data = {
            'summary': self.get_full_summary(),
            'resources_by_type': self.resources,
            'all_resources': self.all_resources,
            'webpages': self.webpages,
            'all_links': self.all_links
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"资源列表已导出到: {output_file}")
        
        # 打印到控制台
        print(f"\n{'='*70}")
        print("资源发现统计")
        print(f"{'='*70}")
        summary = self.get_full_summary()
        print(f"总链接数: {summary['all_links']}")
        print(f"网页链接: {summary['webpages']}")
        print(f"资源文件: {summary['total_resources']}")
        print(f"\n资源分类:")
        for res_type, count in summary['resources'].items():
            if count > 0:
                icon = self.TYPE_ICONS.get(res_type, '📎')
                print(f"  {icon} {res_type}: {count}")
        print(f"{'='*70}\n")
