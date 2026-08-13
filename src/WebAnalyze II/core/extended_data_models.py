"""
扩展数据模型 - 全场景支持
兼容数据分析、网页统计、格式转换、pandoc集成
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Set
from datetime import datetime
from urllib.parse import urlparse
import hashlib
import json
from enum import Enum


# ============================================================================
# 枚举定义
# ============================================================================

class DocumentFormat(Enum):
    """文档格式枚举"""
    HTML = 'html'
    MARKDOWN = 'md'
    PDF = 'pdf'
    DOCX = 'docx'
    TXT = 'txt'
    JSON = 'json'
    XML = 'xml'
    RTF = 'rtf'
    EPUB = 'epub'
    LATEX = 'tex'


class AnalysisLevel(Enum):
    """分析级别"""
    BASIC = 'basic'           # 基础信息
    STANDARD = 'standard'     # 标准分析
    ADVANCED = 'advanced'     # 高级分析
    COMPREHENSIVE = 'comprehensive'  # 全面分析


class ExportTarget(Enum):
    """导出目标平台"""
    PANDOC = 'pandoc'         # 文档转换
    PANDAS = 'pandas'         # 数据分析
    MATPLOTLIB = 'matplotlib'  # 数据可视化
    SCRAPY = 'scrapy'         # 爬虫框架
    ELASTICSEARCH = 'elasticsearch'  # 搜索引擎
    DATABASE = 'database'      # 数据库


# ============================================================================
# 扩展页面数据模型
# ============================================================================

@dataclass
class ExtendedPageItem:
    """
    扩展的页面数据模型 - 全场景支持
    
    设计原则：
    1. 超冗余 - 存储所有可能的元数据
    2. 多格式兼容 - 支持多种导出格式
    3. 分析友好 - 支持pandas数据分析
    4. 转换支持 - 兼容pandoc格式转换
    """
    
    # ========== 基础信息（必需） ==========
    url: str                                    # 完整URL
    title: str = ""                              # 页面标题
    html: str = ""                               # 原始HTML
    
    # ========== 元数据（冗余） ==========
    meta_description: Optional[str] = None        # SEO描述
    meta_keywords: List[str] = field(default_factory=list)  # SEO关键词
    meta_author: Optional[str] = None             # 作者
    meta_robots: Optional[str] = None            # robots指令
    meta_og_title: Optional[str] = None         # OpenGraph标题
    meta_og_description: Optional[str] = None    # OpenGraph描述
    meta_og_image: Optional[str] = None         # OpenGraph图片
    meta_og_type: Optional[str] = None          # OpenGraph类型
    meta_twitter_card: Optional[str] = None      # Twitter卡片
    canonical_url: Optional[str] = None         # 规范化URL
    alternate_urls: List[str] = field(default_factory=list)  # 备用URL
    
    # ========== 内容分析（多维度） ==========
    main_content: str = ""                       # 主要内容
    plain_text: str = ""                        # 纯文本（去HTML）
    content_snippet: str = ""                    # 内容摘要
    content_type: str = "text/html"             # 内容类型
    encoding: str = "utf-8"                     # 编码
    charset: Optional[str] = None                # 字符集
    
    # ========== 统计信息（pandas友好） ==========
    word_count: int = 0                         # 字数
    char_count: int = 0                         # 字符数
    char_count_no_spaces: int = 0                # 去空格字符数
    paragraph_count: int = 0                     # 段落数
    sentence_count: int = 0                      # 句子数
    line_count: int = 0                         # 行数
    whitespace_count: int = 0                    # 空白字符数
    
    # ========== 结构分析 ==========
    headers: Dict[str, List[str]] = field(default_factory=dict)  # 标题层级
    structure: Dict[str, Any] = field(default_factory=dict)       # 页面结构
    headings_hierarchy: List[Dict[str, Any]] = field(default_factory=list)  # 标题层级结构
    
    # ========== 链接信息（详细） ==========
    internal_links: List[Dict[str, Any]] = field(default_factory=list)  # 内部链接
    external_links: List[Dict[str, Any]] = field(default_factory=list)  # 外部链接
    all_links_count: int = 0                   # 总链接数
    broken_links: List[str] = field(default_factory=list)  # 失效链接
    slow_links: List[Dict[str, Any]] = field(default_factory=list)  # 慢速链接
    
    # ========== 资源信息（详细） ==========
    images: List[Dict[str, Any]] = field(default_factory=list)  # 图片列表
    scripts: List[Dict[str, Any]] = field(default_factory=list) # 脚本列表
    stylesheets: List[Dict[str, Any]] = field(default_factory=list) # 样式表
    videos: List[Dict[str, Any]] = field(default_factory=list)  # 视频列表
    audios: List[Dict[str, Any]] = field(default_factory=list)  # 音频列表
    iframes: List[Dict[str, Any]] = field(default_factory=list) # iframe列表
    forms: List[Dict[str, Any]] = field(default_factory=list)   # 表单列表
    tables: List[Dict[str, Any]] = field(default_factory=list)  # 表格列表
    
    # ========== 实体提取（NLP） ==========
    entities: Dict[str, List[str]] = field(default_factory=dict)  # 实体
    named_entities: List[Dict[str, Any]] = field(default_factory=list)  # 命名实体
    sentiment: Optional[Dict[str, float]] = None  # 情感分析
    topics: List[str] = field(default_factory=list)  # 主题关键词
    key_phrases: List[str] = field(default_factory=list)  # 关键短语
    
    # ========== 性能指标 ==========
    load_time: float = 0.0                      # 加载时间（秒）
    size: int = 0                               # 响应大小（字节）
    status_code: int = 200                       # HTTP状态码
    response_headers: Dict[str, str] = field(default_factory=dict)  # 响应头
    request_headers: Dict[str, str] = field(default_factory=dict)  # 请求头
    ttfb: float = 0.0                          # Time to First Byte
    dom_content_loaded: float = 0.0               # DOM内容加载时间
    dom_complete: float = 0.0                     # DOM完成时间
    
    # ========== 质量指标 ==========
    readability_score: float = 0.0               # 可读性分数（0-1）
    seo_score: float = 0.0                       # SEO分数（0-100）
    performance_score: float = 0.0                 # 性能分数（0-100）
    accessibility_score: float = 0.0               # 可访问性分数（0-100）
    quality_score: float = 0.0                     # 综合质量分数（0-100）
    
    # ========== 爬取信息 ==========
    depth: int = 0                              # 爬取深度
    crawl_timestamp: datetime = field(default_factory=datetime.now)  # 爬取时间
    spider_name: str = "webanalyzer"           # 爬虫标识
    crawl_id: str = ""                          # 爬取批次ID
    
    # ========== 技术信息 ==========
    server: Optional[str] = None                 # 服务器信息
    technology_stack: List[str] = field(default_factory=list)  # 技术栈
    frameworks: List[str] = field(default_factory=list)  # 框架
    libraries: List[str] = field(default_factory=list)  # 库
    language: Optional[str] = None              # 检测的语言
    content_hash: str = ""                       # 内容哈希
    
    # ========== 响应式设计 ==========
    is_responsive: bool = False                  # 是否响应式
    mobile_friendly: bool = False               # 是否移动友好
    viewport: Optional[Dict[str, Any]] = None   # 视口信息
    
    # ========== 安全信息 ==========
    has_https: bool = False                     # 是否HTTPS
    has_csp: bool = False                      # 是否有CSP
    ssl_info: Optional[Dict[str, Any]] = None    # SSL证书信息
    security_headers: Dict[str, str] = field(default_factory=dict)  # 安全头
    
    # ========== 社交信息 ==========
    social_links: Dict[str, str] = field(default_factory=dict)  # 社交链接
    share_count: Dict[str, int] = field(default_factory=dict)  # 分享数
    
    # ========== 评分和标签 ==========
    tags: Set[str] = field(default_factory=set)  # 自定义标签
    custom_scores: Dict[str, float] = field(default_factory=dict)  # 自定义评分
    notes: str = ""                             # 备注
    rating: int = 0                             # 评分（1-5）
    
    # ========== 版本控制 ==========
    version: int = 1                            # 数据版本
    last_modified: Optional[datetime] = None      # 最后修改时间
    etag: Optional[str] = None                   # ETag
    
    # ========== 扩展字段（重要） ==========
    extra: Dict[str, Any] = field(default_factory=dict)  # 扩展数据
    raw_data: Dict[str, Any] = field(default_factory=dict)  # 原始数据
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.content_hash:
            self._generate_content_hash()
        
        if not self.crawl_id:
            self._generate_crawl_id()
        
        # 计算衍生数据
        self._calculate_all_stats()
        self._detect_technology()
        self._calculate_quality_scores()
    
    def _generate_content_hash(self):
        """生成内容哈希"""
        content = f"{self.url}{self.title}{len(self.html)}"
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()
    
    def _generate_crawl_id(self):
        """生成爬取批次ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.crawl_id = f"{self.spider_name}_{timestamp}"
    
    def _calculate_all_stats(self):
        """计算所有统计数据"""
        if self.main_content:
            text = self.main_content
            
            # 基础统计
            self.word_count = len(text.split())
            self.char_count = len(text)
            self.char_count_no_spaces = len(text.replace(' ', '').replace('\t', '').replace('\n', ''))
            self.line_count = len(text.split('\n'))
            self.paragraph_count = len([p for p in text.split('\n\n') if p.strip()])
            
            # 句子统计（简单版）
            import re
            sentences = re.split(r'[.!?]+', text)
            self.sentence_count = len([s for s in sentences if s.strip()])
            
            # 空白统计
            self.whitespace_count = len(re.findall(r'\s', text))
        
        # 链接统计
        self.all_links_count = len(self.internal_links) + len(self.external_links)
        
        # HTML大小
        if self.html:
            self.size = len(self.html.encode('utf-8'))
        
        # HTTPS检测
        self.has_https = self.url.startswith('https://')
    
    def _detect_technology(self):
        """检测技术栈（简化版）"""
        if self.html:
            html_lower = self.html.lower()
            
            # 检测框架
            if 'vue' in html_lower:
                self.frameworks.append('Vue.js')
            if 'react' in html_lower:
                self.frameworks.append('React')
            if 'angular' in html_lower:
                self.frameworks.append('Angular')
            if 'jquery' in html_lower:
                self.libraries.append('jQuery')
            if 'bootstrap' in html_lower:
                self.libraries.append('Bootstrap')
            if 'tailwind' in html_lower:
                self.libraries.append('Tailwind CSS')
    
    def _calculate_quality_scores(self):
        """计算质量分数"""
        # SEO分数（简化）
        seo_score = 0
        if self.title:
            seo_score += 20
        if self.meta_description:
            seo_score += 20
        if self.meta_keywords:
            seo_score += 10
        if self.headers and any(self.headers.values()):
            seo_score += 10
        if self.images:
            seo_score += 10
        seo_score = min(seo_score, 100)
        self.seo_score = seo_score
        
        # 性能分数（简化）
        perf_score = 100
        if self.load_time > 3.0:
            perf_score -= 30
        elif self.load_time > 1.0:
            perf_score -= 10
        if self.size > 500000:  # 500KB
            perf_score -= 20
        self.performance_score = max(perf_score, 0)
        
        # 可访问性分数（简化）
        a11y_score = 100
        if not self.alt_texts_present():
            a11y_score -= 30
        if not self.headers:
            a11y_score -= 20
        self.accessibility_score = max(a11y_score, 0)
        
        # 综合质量分数
        self.quality_score = (
            self.readability_score * 40 +
            self.seo_score * 30 +
            self.performance_score * 20 +
            self.accessibility_score * 10
        ) / 100
    
    def alt_texts_present(self) -> bool:
        """检查图片是否有Alt文本"""
        for img in self.images:
            if not img.get('alt'):
                return False
        return True
    
    # ========== 转换方法 ==========
    
    def to_dataframe_row(self) -> Dict[str, Any]:
        """
        转换为pandas DataFrame行
        
        Returns:
            适合pandas的字典
        """
        return {
            # 基础信息
            'url': self.url,
            'title': self.title,
            'domain': urlparse(self.url).netloc,
            
            # 统计信息
            'word_count': self.word_count,
            'char_count': self.char_count,
            'sentence_count': self.sentence_count,
            'paragraph_count': self.paragraph_count,
            'line_count': self.line_count,
            
            # 链接和资源
            'internal_links_count': len(self.internal_links),
            'external_links_count': len(self.external_links),
            'all_links_count': self.all_links_count,
            'images_count': len(self.images),
            'videos_count': len(self.videos),
            'audios_count': len(self.audios),
            'tables_count': len(self.tables),
            'forms_count': len(self.forms),
            
            # 性能
            'load_time': self.load_time,
            'size': self.size,
            'status_code': self.status_code,
            'ttfb': self.ttfb,
            
            # 质量指标
            'readability_score': self.readability_score,
            'seo_score': self.seo_score,
            'performance_score': self.performance_score,
            'accessibility_score': self.accessibility_score,
            'quality_score': self.quality_score,
            
            # 爬取信息
            'depth': self.depth,
            'crawl_timestamp': self.crawl_timestamp,
            'crawl_id': self.crawl_id,
            
            # 元数据
            'meta_description': self.meta_description,
            'meta_keywords': ', '.join(self.meta_keywords),
            'meta_og_title': self.meta_og_title,
            
            # 技术
            'server': self.server,
            'has_https': self.has_https,
            'is_responsive': self.is_responsive,
            'mobile_friendly': self.mobile_friendly,
            
            # 标签
            'tags': ', '.join(self.tags) if self.tags else '',
            'rating': self.rating,
            'notes': self.notes,
        }
    
    def to_markdown(self) -> str:
        """
        转换为Markdown格式
        
        Returns:
            Markdown文本
        """
        md = f"# {self.title}\n\n"
        md += f"**URL:** {self.url}\n\n"
        md += f"**Domain:** {urlparse(self.url).netloc}\n\n"
        
        if self.meta_description:
            md += f"**Description:** {self.meta_description}\n\n"
        
        md += "## 内容摘要\n\n"
        md += f"{self.content_snippet or self.main_content[:500]}...\n\n"
        
        md += "## 统计信息\n\n"
        md += f"- 字数: {self.word_count}\n"
        md += f"- 段落数: {self.paragraph_count}\n"
        md += f"- 链接数: {self.all_links_count}\n"
        md += f"- 图片数: {len(self.images)}\n"
        
        md += "## 质量评分\n\n"
        md += f"- 可读性: {self.readability_score:.2f}\n"
        md += f"- SEO: {self.seo_score:.0f}/100\n"
        md += f"- 性能: {self.performance_score:.0f}/100\n"
        md += f"- 可访问性: {self.accessibility_score:.0f}/100\n"
        
        return md
    
    def to_html_export(self) -> str:
        """
        转换为干净的HTML（适合导出）
        
        Returns:
            清理后的HTML
        """
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #333; }}
        .meta {{ background: #f4f4f4; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .stats {{ display: flex; flex-wrap: wrap; gap: 20px; }}
        .stat {{ background: #e8f4f8; padding: 10px; border-radius: 5px; flex: 1; min-width: 150px; }}
    </style>
</head>
<body>
    <h1>{self.title}</h1>
    <div class="meta">
        <p><strong>URL:</strong> <a href="{self.url}">{self.url}</a></p>
        <p><strong>描述:</strong> {self.meta_description or '无'}</p>
    </div>
    <div class="stats">
        <div class="stat"><strong>字数:</strong> {self.word_count}</div>
        <div class="stat"><strong>段落数:</strong> {self.paragraph_count}</div>
        <div class="stat"><strong>链接数:</strong> {self.all_links_count}</div>
        <div class="stat"><strong>图片数:</strong> {len(self.images)}</div>
    </div>
    <hr>
    <main>
        {self.main_content}
    </main>
    <footer>
        <p><small>抓取时间: {self.crawl_timestamp.strftime('%Y-%m-%d %H:%M:%S')}</small></p>
    </footer>
</body>
</html>"""
        return html
    
    def to_pandoc_metadata(self) -> str:
        """
        转换为Pandoc YAML元数据
        
        Returns:
            YAML格式的元数据
        """
        yaml = f"""---
title: {self.title}
author: {self.meta_author or 'Unknown'}
date: {self.crawl_timestamp.strftime('%Y-%m-%d')}
url: {self.url}
description: {self.meta_description or ''}
keywords:
"""
        for kw in self.meta_keywords:
            yaml += f"  - {kw}\n"
        
        yaml += f"tags:\n"
        for tag in self.tags:
            yaml += f"  - {tag}\n"
        
        yaml += f"statistics:\n"
        yaml += f"  word_count: {self.word_count}\n"
        yaml += f"  char_count: {self.char_count}\n"
        yaml += f"  links_count: {self.all_links_count}\n"
        yaml += f"  images_count: {len(self.images)}\n"
        
        yaml += "---\n"
        return yaml
    
    def to_elasticsearch_doc(self) -> Dict[str, Any]:
        """
        转换为Elasticsearch文档
        
        Returns:
            ES文档格式
        """
        return {
            '_index': 'webpages',
            '_id': self.content_hash,
            '_source': {
                'url': self.url,
                'title': self.title,
                'content': self.main_content,
                'description': self.meta_description,
                'keywords': self.meta_keywords,
                'domain': urlparse(self.url).netloc,
                'crawl_timestamp': self.crawl_timestamp.isoformat(),
                'statistics': {
                    'word_count': self.word_count,
                    'char_count': self.char_count,
                    'links_count': self.all_links_count,
                },
                'quality': {
                    'readability': self.readability_score,
                    'seo': self.seo_score,
                    'performance': self.performance_score,
                    'overall': self.quality_score,
                },
                'meta': {
                    'og_title': self.meta_og_title,
                    'og_image': self.meta_og_image,
                    'twitter_card': self.meta_twitter_card,
                },
                'tags': list(self.tags),
                'extra': self.extra,
            }
        }
    
    def to_database_record(self) -> Dict[str, Any]:
        """
        转换为数据库记录
        
        Returns:
            数据库记录格式
        """
        return {
            'id': self.content_hash,
            'url': self.url,
            'title': self.title,
            'content': self.main_content,
            'html': self.html,
            'meta_description': self.meta_description,
            'meta_keywords': json.dumps(self.meta_keywords),
            'word_count': self.word_count,
            'char_count': self.char_count,
            'links_count': self.all_links_count,
            'images_count': len(self.images),
            'load_time': self.load_time,
            'size': self.size,
            'status_code': self.status_code,
            'readability_score': self.readability_score,
            'seo_score': self.seo_score,
            'quality_score': self.quality_score,
            'depth': self.depth,
            'crawl_timestamp': self.crawl_timestamp,
            'crawl_id': self.crawl_id,
            'tags': json.dumps(list(self.tags)),
            'rating': self.rating,
            'notes': self.notes,
            'version': self.version,
            'extra': json.dumps(self.extra),
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为完整字典（兼容旧代码，同时包含原始分析数据）"""
        data = {
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
            'plain_text': self.plain_text,
            'content_snippet': self.content_snippet,
            
            # 统计
            'word_count': self.word_count,
            'char_count': self.char_count,
            'paragraph_count': self.paragraph_count,
            'sentence_count': self.sentence_count,
            'line_count': self.line_count,
            
            # 链接
            'links': self.internal_links + self.external_links,
            'links_count': self.all_links_count,
            
            # 图片
            'images': self.images,
            'images_count': len(self.images),
            
            # 性能
            'load_time': self.load_time,
            'size': self.size,
            'status_code': self.status_code,
            
            # 质量指标
            'readability_score': self.readability_score,
            'seo_score': self.seo_score,
            'performance_score': self.performance_score,
            'accessibility_score': self.accessibility_score,
            'quality_score': self.quality_score,
            
            # 爬取
            'depth': self.depth,
            'crawl_timestamp': self.crawl_timestamp.isoformat() if self.crawl_timestamp else None,
            'crawl_id': self.crawl_id,
            
            # 扩展
            'broken_links': self.broken_links,
            'videos': self.videos,
            'audios': self.audios,
            'tables': self.tables,
            'forms': self.forms,
            'named_entities': self.named_entities,
            'sentiment': self.sentiment,
            'topics': self.topics,
            'technology_stack': self.technology_stack,
            'social_links': self.social_links,
        }
        
        # 保存原始分析结果，方便下游导出/调试使用
        if self.raw_data:
            data['analysis'] = self.raw_data
        
        return data


# ============================================================================
# 批量分析数据模型
# ============================================================================

@dataclass
class BatchAnalysisResult:
    """
    批量分析结果
    用于多页面统计和分析
    """
    
    crawl_id: str                              # 爬取批次ID
    pages: List[ExtendedPageItem] = field(default_factory=list)  # 页面列表
    
    # ========== 汇总统计 ==========
    total_pages: int = 0                        # 总页数
    total_words: int = 0                        # 总字数
    total_size: int = 0                         # 总大小
    total_links: int = 0                        # 总链接数
    total_images: int = 0                       # 总图片数
    
    # ========== 域名统计 ==========
    domains: Dict[str, int] = field(default_factory=dict)  # 域名分布
    unique_domains: int = 0                       # 唯一域名数
    
    # ========== 性能统计 ==========
    avg_load_time: float = 0.0                  # 平均加载时间
    max_load_time: float = 0.0                  # 最大加载时间
    min_load_time: float = 0.0                  # 最小加载时间
    avg_size: int = 0                           # 平均大小
    
    # ========== 质量统计 ==========
    avg_readability: float = 0.0                # 平均可读性
    avg_seo: float = 0.0                       # 平均SEO
    avg_quality: float = 0.0                     # 平均质量
    
    # ========== 时间统计 ==========
    start_time: Optional[datetime] = None         # 开始时间
    end_time: Optional[datetime] = None           # 结束时间
    duration: float = 0.0                       # 持续时间（秒）
    
    # ========== 标签统计 ==========
    all_tags: Set[str] = field(default_factory=set)  # 所有标签
    tag_distribution: Dict[str, int] = field(default_factory=dict)  # 标签分布
    
    # ========== 资源统计 ==========
    all_resources: List[Dict[str, Any]] = field(default_factory=list)  # 所有资源
    resources_by_type: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)  # 按类型分类
    
    def add_page(self, page: ExtendedPageItem):
        """添加页面到批量结果"""
        self.pages.append(page)
        
        # 更新统计
        self.total_pages += 1
        self.total_words += page.word_count
        self.total_size += page.size
        self.total_links += page.all_links_count
        self.total_images += len(page.images)
        
        # 更新域名统计
        domain = urlparse(page.url).netloc
        self.domains[domain] = self.domains.get(domain, 0) + 1
        self.unique_domains = len(self.domains)
        
        # 更新性能统计
        if page.load_time:
            if self.total_pages == 1:
                self.min_load_time = page.load_time
                self.max_load_time = page.load_time
            else:
                self.min_load_time = min(self.min_load_time, page.load_time)
                self.max_load_time = max(self.max_load_time, page.load_time)
        
        # 更新标签
        if page.tags:
            self.all_tags.update(page.tags)
            for tag in page.tags:
                self.tag_distribution[tag] = self.tag_distribution.get(tag, 0) + 1
    
    def finalize(self):
        """完成分析，计算汇总数据"""
        if not self.pages:
            return
        
        # 计算平均值
        self.avg_load_time = sum(p.load_time for p in self.pages) / len(self.pages)
        self.avg_size = self.total_size // len(self.pages)
        self.avg_readability = sum(p.readability_score for p in self.pages) / len(self.pages)
        self.avg_seo = sum(p.seo_score for p in self.pages) / len(self.pages)
        self.avg_quality = sum(p.quality_score for p in self.pages) / len(self.pages)
        
        # 计算持续时间
        if self.start_time and self.end_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
    
    def to_pandas_dataframe(self):
        """
        转换为pandas DataFrame
        
        Returns:
            pandas DataFrame
        """
        try:
            import pandas as pd
            
            rows = [page.to_dataframe_row() for page in self.pages]
            df = pd.DataFrame(rows)
            
            # 添加汇总信息
            df.attrs['summary'] = {
                'total_pages': self.total_pages,
                'total_words': self.total_words,
                'total_size': self.total_size,
                'unique_domains': self.unique_domains,
                'avg_load_time': self.avg_load_time,
                'duration': self.duration,
            }
            
            return df
        except ImportError:
            raise ImportError("pandas未安装，无法创建DataFrame")
    
    def generate_statistics_report(self) -> str:
        """生成统计报告"""
        report = "="*70 + "\n"
        report += "批量分析报告\n"
        report += "="*70 + "\n\n"
        
        report += f"爬取批次ID: {self.crawl_id}\n"
        report += f"总页数: {self.total_pages}\n"
        report += f"唯一域名: {self.unique_domains}\n"
        report += f"持续时间: {self.duration:.2f}秒\n\n"
        
        report += "内容统计:\n"
        report += f"  总字数: {self.total_words}\n"
        report += f"  总大小: {self.total_size / 1024:.2f} KB\n"
        report += f"  平均大小: {self.avg_size / 1024:.2f} KB\n"
        report += f"  总链接: {self.total_links}\n"
        report += f"  总图片: {self.total_images}\n\n"
        
        report += "性能统计:\n"
        report += f"  平均加载时间: {self.avg_load_time:.2f}秒\n"
        report += f"  最快加载: {self.min_load_time:.2f}秒\n"
        report += f"  最慢加载: {self.max_load_time:.2f}秒\n\n"
        
        report += "质量统计:\n"
        report += f"  平均可读性: {self.avg_readability:.2f}\n"
        report += f"  平均SEO: {self.avg_seo:.1f}/100\n"
        report += f"  平均质量: {self.avg_quality:.1f}/100\n\n"
        
        if self.tag_distribution:
            report += "热门标签:\n"
            sorted_tags = sorted(self.tag_distribution.items(), key=lambda x: x[1], reverse=True)[:10]
            for tag, count in sorted_tags:
                report += f"  {tag}: {count}\n"
        
        return report


# ============================================================================
# 辅助函数
# ============================================================================

def create_extended_page_item_from_analysis(
    html: str,
    url: str,
    analysis_result: Dict[str, Any],
    depth: int = 0
) -> ExtendedPageItem:
    """
    从 PageAnalyzer 的分析结果创建 ExtendedPageItem

    说明：
    - 将 PageAnalyzer 的字典结果映射到扩展数据模型
    - 同时填充分词统计、链接、图片等基础字段
    - 保持与现有 Dict 结构兼容（后续可通过 to_dict() 输出）
    """
    from urllib.parse import urlparse as _urlparse

    links = analysis_result.get('links', []) or []
    images = analysis_result.get('images', []) or []

    base_domain = _urlparse(url).netloc if url else ""
    internal_links: List[Dict[str, Any]] = []
    external_links: List[Dict[str, Any]] = []

    for link in links:
        if not isinstance(link, dict):
            continue
        link_url = link.get('url') or ""
        if not link_url:
            continue
        domain = _urlparse(link_url).netloc
        if base_domain and domain and domain != base_domain:
            external_links.append(link)
        else:
            internal_links.append(link)

    item = ExtendedPageItem(
        # 基础信息
        url=url,
        title=analysis_result.get('title', ''),
        html=html,

        # 元数据
        meta_description=analysis_result.get('meta_description'),
        meta_keywords=analysis_result.get('meta_keywords', []),

        # 内容
        main_content=analysis_result.get('content', '') or "",
        plain_text=analysis_result.get('content', '') or "",

        # 结构
        headers=analysis_result.get('headers', {}),
        structure=analysis_result.get('structure', {}),

        # 实体
        entities=analysis_result.get('entities', {}),

        # 统计与质量
        word_count=analysis_result.get('word_count', 0),
        readability_score=analysis_result.get('readability_score', 0.0),

        # 链接与资源
        internal_links=internal_links,
        external_links=external_links,
        images=images,

        # 爬取信息
        depth=depth,
        
        # 保存原始分析结果，便于导出和调试
        raw_data=analysis_result,
    )

    return item
