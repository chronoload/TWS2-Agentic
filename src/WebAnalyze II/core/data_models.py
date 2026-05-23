"""
统一数据模型 - 网页分析和资源管理
兼容Scrapy Item结构，同时保持向后兼容
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from urllib.parse import urlparse
import hashlib
import json


# ============================================================================
# 页面数据模型
# ============================================================================

@dataclass
class PageItem:
    """
    统一的页面数据模型
    兼容Scrapy Item结构
    
    设计原则：
    1. 冗余存储 - 同时保存原始和解析数据
    2. 类型安全 - 使用dataclass和类型注解
    3. 兼容性 - 提供to_dict/from_dict方法
    4. 可扩展 - 预留extra字段
    """
    
    # ========== 基础信息 ==========
    url: str                                    # 完整URL
    title: str = ""                              # 页面标题
    html: str = ""                               # 原始HTML（冗余存储）
    
    # ========== 元数据 ==========
    meta_description: Optional[str] = None        # SEO描述
    meta_keywords: List[str] = field(default_factory=list)  # SEO关键词
    canonical_url: Optional[str] = None         # 规范化URL
    
    # ========== 内容分析 ==========
    main_content: str = ""                       # 主要内容（提取后）
    content_type: str = "text/html"             # 内容类型
    encoding: str = "utf-8"                     # 编码
    word_count: int = 0                         # 字数统计
    char_count: int = 0                         # 字符统计
    
    # ========== 结构分析 ==========
    headers: Dict[str, List[str]] = field(default_factory=dict)  # 标题层级
    structure: Dict[str, Any] = field(default_factory=dict)       # 页面结构
    
    # ========== 链接信息 ==========
    internal_links: List[Dict[str, Any]] = field(default_factory=list)  # 内部链接
    external_links: List[Dict[str, Any]] = field(default_factory=list)  # 外部链接
    all_links_count: int = 0                   # 总链接数
    
    # ========== 资源信息 ==========
    images: List[Dict[str, Any]] = field(default_factory=list)  # 图片列表
    scripts: List[Dict[str, Any]] = field(default_factory=list) # 脚本列表
    stylesheets: List[Dict[str, Any]] = field(default_factory=list) # 样式表
    
    # ========== 实体提取 ==========
    entities: Dict[str, List[str]] = field(default_factory=dict)  # 实体（邮箱、电话等）
    
    # ========== 性能指标 ==========
    load_time: float = 0.0                      # 加载时间（秒）
    size: int = 0                               # 响应大小（字节）
    status_code: int = 200                       # HTTP状态码
    
    # ========== 可读性 ==========
    readability_score: float = 0.0               # 可读性分数（0-1）
    
    # ========== 爬取信息 ==========
    depth: int = 0                              # 爬取深度
    crawl_timestamp: datetime = field(default_factory=datetime.now)  # 爬取时间
    spider_name: str = "webanalyzer"           # 爬虫标识
    
    # ========== Scrapy兼容字段 ==========
    response_url: str = ""                       # 响应URL（可能重定向）
    request_url: str = ""                       # 请求URL
    redirect_chain: List[str] = field(default_factory=list)  # 重定向链
    
    # ========== 唯一标识 ==========
    fingerprint: str = ""                        # 内容指纹（去重用）
    
    # ========== 扩展字段 ==========
    extra: Dict[str, Any] = field(default_factory=dict)  # 扩展数据
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.fingerprint:
            self._generate_fingerprint()
        if not self.response_url:
            self.response_url = self.url
        if not self.request_url:
            self.request_url = self.url
        
        # 计算衍生数据
        self._calculate_derived_fields()
    
    def _generate_fingerprint(self):
        """生成内容指纹（用于去重）"""
        content = f"{self.url}{self.title}{len(self.html)}"
        self.fingerprint = hashlib.md5(content.encode()).hexdigest()
    
    def _calculate_derived_fields(self):
        """计算衍生字段"""
        # 统计链接数
        self.all_links_count = len(self.internal_links) + len(self.external_links)
        
        # 统计字数
        if self.main_content:
            self.word_count = len(self.main_content.split())
            self.char_count = len(self.main_content)
        
        # 统计HTML大小
        if self.html:
            self.size = len(self.html.encode('utf-8'))
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（兼容现有代码）
        
        Returns:
            字典格式的页面数据
        """
        return {
            # 基础信息
            'url': self.url,
            'title': self.title,
            'html': self.html,
            
            # 元数据
            'meta_description': self.meta_description,
            'meta_keywords': self.meta_keywords,
            'canonical_url': self.canonical_url,
            
            # 内容
            'content': self.main_content,
            'word_count': self.word_count,
            'char_count': self.char_count,
            'content_type': self.content_type,
            
            # 链接（合并为旧格式，保持兼容）
            'links': self.internal_links + self.external_links,
            'links_count': self.all_links_count,
            
            # 图片
            'images': self.images,
            'images_count': len(self.images),
            
            # 结构
            'headers': self.headers,
            'structure': self.structure,
            
            # 实体
            'entities': self.entities,
            
            # 性能
            'load_time': self.load_time,
            'size': self.size,
            'status_code': self.status_code,
            
            # 可读性
            'readability_score': self.readability_score,
            
            # 爬取
            'depth': self.depth,
            
            # 扩展统计（新增）
            'internal_links_count': len(self.internal_links),
            'external_links_count': len(self.external_links),
            'scripts_count': len(self.scripts),
            'stylesheets_count': len(self.stylesheets),
            'fingerprint': self.fingerprint,
            'crawl_timestamp': self.crawl_timestamp.isoformat() if self.crawl_timestamp else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PageItem':
        """
        从字典创建（兼容现有代码）
        
        Args:
            data: 字典数据
            
        Returns:
            PageItem实例
        """
        # 将旧版 Dict 数据适配为 PageItem
        from urllib.parse import urlparse

        url = data.get('url', '')
        raw_links = data.get('links', []) or []
        internal_links = []
        external_links = []

        # 按域名粗略区分内外部链接，保持与现有 Dict 结构兼容
        base_domain = urlparse(url).netloc if url else ""
        for link in raw_links:
            if isinstance(link, dict):
                link_url = link.get('url') or ""
            else:
                link_url = str(link)
                link = {'url': link_url}

            if not link_url:
                continue

            domain = urlparse(link_url).netloc
            if base_domain and domain and domain != base_domain:
                external_links.append(link)
            else:
                internal_links.append(link)

        item = cls(
            url=url,
            title=data.get('title', ''),
            html=data.get('html', ''),
            main_content=data.get('content', ''),
            meta_description=data.get('meta_description'),
            meta_keywords=data.get('meta_keywords', []),
            canonical_url=data.get('canonical_url'),
            headers=data.get('headers', {}),
            structure=data.get('structure', {}),
            entities=data.get('entities', {}),
            word_count=data.get('word_count', 0),
            char_count=data.get('char_count', 0),
            load_time=data.get('load_time', 0.0),
            size=data.get('size', 0),
            status_code=data.get('status_code', 200),
            readability_score=data.get('readability_score', 0.0),
            depth=data.get('depth', 0),
            internal_links=internal_links,
            external_links=external_links,
            images=data.get('images', []) or [],
        )

        return item
    
    def to_scrapy_item(self) -> Dict[str, Any]:
        """
        转换为Scrapy Item格式
        
        Returns:
            Scrapy兼容的Item字典
        """
        return {
            'url': self.url,
            'title': self.title,
            'html': self.html,
            'depth': self.depth,
            'response': {
                'url': self.response_url,
                'status': self.status_code,
                'headers': {'Content-Type': self.content_type},
                'body': self.html,
            },
            'content': self.main_content,
            'meta': {
                'description': self.meta_description,
                'keywords': self.meta_keywords,
                'canonical': self.canonical_url,
                'fingerprint': self.fingerprint,
            },
            'links': self.internal_links + self.external_links,
            'images': self.images,
            'stats': {
                'word_count': self.word_count,
                'char_count': self.char_count,
                'load_time': self.load_time,
                'size': self.size,
            },
        }
    
    def to_json(self) -> str:
        """序列化为JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PageItem':
        """从JSON反序列化"""
        data = json.loads(json_str)
        return cls.from_dict(data)


# ============================================================================
# 资源数据模型
# ============================================================================

@dataclass
class ResourceItem:
    """
    统一的资源数据模型
    支持多种资源类型（文档、图片、视频等）
    
    设计原则：
    1. 多类型支持 - 适配各种资源
    2. 状态追踪 - 下载状态管理
    3. 元数据丰富 - 支持扩展信息
    """
    
    # ========== 核心信息 ==========
    url: str                                    # 资源URL
    resource_type: str                           # 资源类型（document/image/video等）
    category_name: str                           # 分类名称
    icon: str = "📎"                           # 显示图标
    
    # ========== 文件信息 ==========
    filename: Optional[str] = None              # 文件名
    file_extension: Optional[str] = None         # 文件扩展名
    file_size: Optional[int] = None             # 文件大小（字节）
    mime_type: Optional[str] = None             # MIME类型
    
    # ========== 来源信息 ==========
    source_page: str = ""                       # 来源页面URL
    source_domain: str = ""                      # 来源域名
    source_text: str = ""                       # 锚文本（如果是链接）
    
    # ========== 发现信息 ==========
    found_timestamp: datetime = field(default_factory=datetime.now)  # 发现时间
    found_count: int = 1                       # 出现次数
    
    # ========== 下载状态 ==========
    download_status: str = "pending"             # pending/downloading/completed/failed
    download_path: Optional[str] = None          # 下载路径
    download_time: Optional[float] = None        # 下载耗时
    download_error: Optional[str] = None         # 错误信息
    
    # ========== 元数据 ==========
    title: str = ""                             # 资源标题
    description: Optional[str] = None            # 描述
    tags: List[str] = field(default_factory=list)  # 标签
    
    # ========== 图片特有 ==========
    width: Optional[int] = None                 # 宽度
    height: Optional[int] = None                # 高度
    alt_text: str = ""                          # Alt文本
    
    # ========== 链接特有 ==========
    is_external: bool = False                    # 是否外部链接
    is_nofollow: bool = False                   # 是否nofollow
    rel_attributes: List[str] = field(default_factory=list)  # rel属性
    
    # ========== 扩展字段 ==========
    extra: Dict[str, Any] = field(default_factory=dict)  # 扩展数据
    
    def __post_init__(self):
        """初始化后处理"""
        if self.source_page:
            parsed = urlparse(self.source_page)
            self.source_domain = parsed.netloc
        
        if self.filename:
            # 提取扩展名
            parts = self.filename.rsplit('.', 1)
            if len(parts) > 1:
                self.file_extension = '.' + parts[1]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（兼容现有代码）"""
        return {
            # 核心信息
            'url': self.url,
            'category': self.resource_type,
            'category_name': self.category_name,
            'icon': self.icon,
            
            # 文件信息
            'title': self.title,
            'filename': self.filename,
            'domain': self.source_domain,
            'size': self.file_size,
            
            # 来源信息
            'source_page': self.source_page,
            'source_text': self.source_text,
            'found_count': self.found_count,
            
            # 下载状态
            'download_status': self.download_status,
            'download_path': self.download_path,
            'download_error': self.download_error,
            
            # 图片字段
            'width': self.width,
            'height': self.height,
            'alt': self.alt_text,
            
            # 链接字段
            'is_external': self.is_external,
            'nofollow': self.is_nofollow,
            
            # 扩展
            'found_timestamp': self.found_timestamp.isoformat() if self.found_timestamp else None,
            
            # 兼容旧代码
            'type': self.resource_type,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceItem':
        """从字典创建（兼容现有代码）"""
        return cls(
            url=data.get('url', ''),
            resource_type=data.get('category', data.get('type', 'unknown')),
            category_name=data.get('category_name', '未知'),
            icon=data.get('icon', '📎'),
            filename=data.get('filename'),
            title=data.get('title', ''),
            source_domain=data.get('domain', ''),
            source_page=data.get('source_page', ''),
            file_size=data.get('size'),
            found_count=data.get('found_count', 1),
            width=data.get('width'),
            height=data.get('height'),
            alt_text=data.get('alt', ''),
            is_external=data.get('is_external', False),
            is_nofollow=data.get('nofollow', False),
        )
    
    def to_json(self) -> str:
        """序列化为JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ResourceItem':
        """从JSON反序列化"""
        data = json.loads(json_str)
        return cls.from_dict(data)


# ============================================================================
# 类型定义
# ============================================================================

class ResourceTypes:
    """资源类型常量"""
    DOCUMENT = 'document'
    IMAGE = 'image'
    VIDEO = 'video'
    AUDIO = 'audio'
    ARCHIVE = 'archive'
    EXECUTABLE = 'executable'
    CODE = 'code'
    FONT = 'font'
    WEBPAGE = 'webpage'
    UNKNOWN = 'unknown'


class DownloadStatus:
    """下载状态常量"""
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


# ============================================================================
# 辅助函数
# ============================================================================

def create_page_item_from_analysis(
    html: str,
    url: str,
    analysis_result: Dict[str, Any],
    depth: int = 0
) -> PageItem:
    """
    从分析结果创建PageItem
    
    Args:
        html: 原始HTML
        url: 页面URL
        analysis_result: PageAnalyzer的分析结果
        depth: 爬取深度
        
    Returns:
        PageItem实例
    """
    from urllib.parse import urlparse

    links = analysis_result.get('links', []) or []
    images = analysis_result.get('images', []) or []

    # 根据域名区分内部 / 外部链接
    base_domain = urlparse(url).netloc if url else ""
    internal_links = []
    external_links = []
    for link in links:
        if not isinstance(link, dict):
            continue
        link_url = link.get('url') or ""
        if not link_url:
            continue
        domain = urlparse(link_url).netloc
        if base_domain and domain and domain != base_domain:
            external_links.append(link)
        else:
            internal_links.append(link)

    item = PageItem(
        url=url,
        title=analysis_result.get('title', ''),
        html=html,
        main_content=analysis_result.get('content', ''),
        meta_description=analysis_result.get('meta_description'),
        meta_keywords=analysis_result.get('meta_keywords', []),
        headers=analysis_result.get('headers', {}),
        entities=analysis_result.get('entities', {}),
        structure=analysis_result.get('structure', {}),
        word_count=analysis_result.get('word_count', 0),
        readability_score=analysis_result.get('readability_score', 0.0),
        depth=depth,
        internal_links=internal_links,
        external_links=external_links,
        images=images,
    )

    return item


def create_resource_items_from_links(
    links: List[Dict[str, Any]],
    source_page: str,
    category_map: Dict[str, str] = None
) -> List[ResourceItem]:
    """
    从链接列表创建ResourceItem列表
    
    Args:
        links: 链接字典列表
        source_page: 来源页面URL
        category_map: 自定义分类映射
        
    Returns:
        ResourceItem列表
    """
    if category_map is None:
        category_map = {}
    
    resources = []
    
    for link_info in links:
        url = link_info.get('url', '')
        if not url:
            continue
        
        # 确定资源类型
        resource_type = link_info.get('category', ResourceTypes.UNKNOWN)
        if resource_type in category_map:
            category_name = category_map[resource_type]
        else:
            category_name = link_info.get('category_name', '未知')
        
        resource = ResourceItem(
            url=url,
            resource_type=resource_type,
            category_name=category_name,
            icon=link_info.get('icon', '📎'),
            title=link_info.get('title', ''),
            filename=link_info.get('filename'),
            source_page=source_page,
            source_text=link_info.get('text', ''),
            is_external=link_info.get('is_external', False),
            is_nofollow=link_info.get('nofollow', False),
            file_size=link_info.get('size'),
            width=link_info.get('width'),
            height=link_info.get('height'),
            alt_text=link_info.get('alt', ''),
        )
        
        resources.append(resource)
    
    return resources
