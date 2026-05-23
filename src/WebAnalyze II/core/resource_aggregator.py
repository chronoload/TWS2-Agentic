"""
资源聚合器 - 全局收集和管理所有资源
支持跨页面的资源统计、分类和去重
"""
from typing import List, Dict, Any, Optional
from collections import defaultdict
from urllib.parse import urlparse
import logging
from core.debug_manager import debug

logger = logging.getLogger(__name__)


class ResourceAggregator:
    """资源聚合器 - 收集和管理所有资源"""
    
    # 链接类型分类
    LINK_CATEGORIES = {
        'document': {
            'extensions': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.odt', '.ods'],
            'icon': '📄',
            'name': '文档'
        },
        'image': {
            'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff', '.psd'],
            'icon': '🖼️',
            'name': '图片'
        },
        'video': {
            'extensions': ['.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm', '.m4v', '.3gp'],
            'icon': '🎬',
            'name': '视频'
        },
        'audio': {
            'extensions': ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma', '.opus'],
            'icon': '🎵',
            'name': '音频'
        },
        'archive': {
            'extensions': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'],
            'icon': '📦',
            'name': '压缩包'
        },
        'executable': {
            'extensions': ['.exe', '.msi', '.dmg', '.apk', '.app', '.sh', '.bat'],
            'icon': '⚙️',
            'name': '可执行文件'
        },
        'code': {
            'extensions': ['.py', '.js', '.html', '.css', '.json', '.xml', '.java', '.cpp', '.h', '.c'],
            'icon': '💻',
            'name': '代码文件'
        },
        'font': {
            'extensions': ['.ttf', '.otf', '.woff', '.woff2', '.eot'],
            'icon': '🔤',
            'name': '字体'
        },
        'webpage': {
            'extensions': ['', '.html', '.htm', '.php', '.asp', '.aspx', '.jsp'],
            'icon': '🌐',
            'name': '网页链接'
        }
    }
    
    def __init__(self):
        debug.log_function_call("ResourceAggregator.__init__")
        
        self.resources_by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.all_resources: List[Dict[str, Any]] = []
        self.resource_urls: set = set()  # 用于去重
        
        # 统计信息
        self.stats = {
            'total_resources': 0,
            'by_type': defaultdict(int),
            'by_domain': defaultdict(int)
        }
        
        debug.log_function_return("ResourceAggregator.__init__", "初始化完成")
    
    def add_resources_from_analysis(self, page_url: str, analysis_result: Dict[str, Any]) -> None:
        """
        从页面分析结果中添加资源
        
        Args:
            page_url: 页面URL
            analysis_result: PageAnalyzer的分析结果
        """
        # 处理链接
        links = analysis_result.get('links', [])
        for link in links:
            self._add_link(link, page_url)
        
        # 处理图片
        images = analysis_result.get('images', [])
        for image in images:
            self._add_link(image, page_url)
    
    def _add_link(self, link_info: Dict[str, Any], source_page: str) -> None:
        """添加单个链接"""
        url = link_info.get('url', '')
        if not url or url in self.resource_urls:
            return
        
        self.resource_urls.add(url)
        
        # 分类链接
        category = self._classify_link(url)
        
        # 创建资源信息
        resource = {
            'url': url,
            'category': category,
            'category_name': self.LINK_CATEGORIES.get(category, {}).get('name', '其他'),
            'icon': self.LINK_CATEGORIES.get(category, {}).get('icon', '📎'),
            'title': self._extract_title(url),
            'filename': self._extract_filename(url),
            'domain': urlparse(url).netloc,
            'source_page': source_page,
            'size': link_info.get('size'),
            'found_count': 1,
            'type': link_info.get('type', 'unknown')
        }
        
        # 添加到列表
        self.all_resources.append(resource)
        self.resources_by_type[category].append(resource)
        
        # 更新统计
        self.stats['total_resources'] += 1
        self.stats['by_type'][category] += 1
        self.stats['by_domain'][resource['domain']] += 1
        
        logger.debug(f"添加资源: {category} - {url[:50]}")
        debug.log_step("添加资源", {"category": category, "url": url[:50], "total": self.stats['total_resources']})
    
    def _classify_link(self, url: str) -> str:
        """
        分类链接（简化版，减少误判）
        
        Args:
            url: 链接URL
            
        Returns:
            资源类型分类
        """
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # 1. 首先检查是否是明确的资源文件（根据扩展名）
        for category, info in self.LINK_CATEGORIES.items():
            if category == 'webpage':
                continue  # 跳过webpage类型，最后处理
            if any(path.endswith(ext) for ext in info['extensions']):
                return category
        
        # 2. 其他情况都归为网页
        # 包括：明确网页扩展名、无扩展名的URL、查询参数等
        return 'webpage'
    
    def _extract_title(self, url: str) -> str:
        """提取URL的标题"""
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        
        if not path:
            return parsed.netloc or url
        
        # 获取最后一个路径段
        parts = path.split('/')
        filename = parts[-1] if parts else ''
        
        if filename:
            # 移除扩展名
            name = filename.rsplit('.', 1)[0] if '.' in filename else filename
            return name or filename
        
        return url[:30]
    
    def _extract_filename(self, url: str) -> str:
        """提取文件名"""
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        
        if not path:
            return parsed.netloc.replace('.', '_') + '.html'
        
        parts = path.split('/')
        filename = parts[-1] if parts else ''
        
        if filename:
            return filename
        
        return parsed.netloc.replace('.', '_') + '.html'
    
    def get_resources_by_category(self, category: Optional[str] = None) -> Dict[str, Any]:
        """
        获取分类资源
        
        Args:
            category: 特定分类，如果为None则返回所有分类
            
        Returns:
            分类资源字典
        """
        if category:
            return {
                'category': category,
                'name': self.LINK_CATEGORIES.get(category, {}).get('name', category),
                'icon': self.LINK_CATEGORIES.get(category, {}).get('icon', '📎'),
                'resources': self.resources_by_type.get(category, []),
                'count': len(self.resources_by_type.get(category, []))
            }
        else:
            result = {}
            for cat in self.LINK_CATEGORIES.keys():
                result[cat] = {
                    'name': self.LINK_CATEGORIES[cat].get('name', cat),
                    'icon': self.LINK_CATEGORIES[cat].get('icon', '📎'),
                    'count': len(self.resources_by_type.get(cat, [])),
                    'resources': self.resources_by_type.get(cat, [])
                }
            return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_resources': self.stats['total_resources'],
            'by_type': dict(self.stats['by_type']),
            'by_domain': dict(self.stats['by_domain']),
            'unique_domains': len(self.stats['by_domain'])
        }
    
    def get_top_domains(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取资源最多的域名"""
        sorted_domains = sorted(
            self.stats['by_domain'].items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [
            {'domain': domain, 'count': count}
            for domain, count in sorted_domains[:limit]
        ]
    
    def get_summary(self) -> str:
        """获取友好的总结文本"""
        summary = f"资源统计摘要\n"
        summary += f"{'='*50}\n"
        summary += f"总资源数: {self.stats['total_resources']}\n"
        summary += f"资源类型数: {len(self.stats['by_type'])}\n"
        summary += f"涉及域名数: {len(self.stats['by_domain'])}\n\n"
        
        summary += f"按类型统计:\n"
        for category in sorted(self.stats['by_type'].keys()):
            count = self.stats['by_type'][category]
            cat_info = self.LINK_CATEGORIES.get(category, {})
            name = cat_info.get('name', category)
            icon = cat_info.get('icon', '📎')
            summary += f"  {icon} {name}: {count}\n"
        
        summary += f"\n资源最多的域名:\n"
        for item in self.get_top_domains(5):
            summary += f"  {item['domain']}: {item['count']}\n"
        
        return summary
