"""
网页内容分析器 - 基于 webscrapy 思路的智能内容提取
"""
import re
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin, urlparse
import logging
from core.debug_manager import debug

logger = logging.getLogger(__name__)


class PageAnalyzer:
    """
    网页内容分析器
    支持智能内容提取、结构分析、实体识别等功能
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def analyze_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        分析网页内容
        
        Args:
            html: 网页HTML内容
            url: 页面URL
            
        Returns:
            分析结果字典
        """
        debug.log_function_call("PageAnalyzer.analyze_page", {"url": url[:50], "html_length": len(html)})
        
        soup = BeautifulSoup(html, 'lxml')
        
        result = {
            'url': url,
            'title': self._extract_title(soup),
            'content': self._extract_main_content(soup),
            'html': html,
            'links': self._extract_links(soup, url),
            'images': self._extract_images(soup, url),
            'meta_keywords': self._extract_meta_keywords(soup),
            'meta_description': self._extract_meta_description(soup),
            'headers': self._extract_headers(soup),
            'word_count': self._count_words(html),
            'readability_score': self._calculate_readability(html),
            'entities': self._extract_entities(html),
            'structure': self._analyze_structure(soup)
        }
        
        debug.log_function_return("PageAnalyzer.analyze_page", f"提取了{len(result.get('links', []))}个链接, {len(result.get('images', []))}个图片")
        
        return result

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取页面标题"""
        if soup.title:
            return soup.title.string.strip() if soup.title.string else ""
        return ""

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """
        提取主要内容 - 优先级选择器算法
        优先级: main > article > content > body
        """
        # 尝试不同的内容选择器
        selectors = [
            'main',
            'article',
            '[class*="content"]',
            '[class*="main"]',
            '[id*="content"]',
            '[id*="main"]'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                # 返回最大的内容块
                content = max(elements, key=lambda x: len(x.get_text(strip=True)))
                return content.get_text(strip=True)
        
        # 如果没有找到特定元素，返回整个body的内容
        return soup.body.get_text(strip=True) if soup.body else ""

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """提取所有链接"""
        links = []
        base_domain = urlparse(base_url).netloc
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            absolute_url = urljoin(base_url, href)
            
            link_info = {
                'url': absolute_url,
                'text': a.get_text(strip=True),
                'is_external': urlparse(absolute_url).netloc != base_domain,
                'nofollow': 'nofollow' in a.get('rel', []),
                'anchor': a.get('name', ''),
                'title': a.get('title', ''),
                'target': a.get('target', ''),
                'type': 'link'
            }
            links.append(link_info)
        
        return links

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """提取所有图片"""
        images = []
        
        for img in soup.find_all('img', src=True):
            src = img['src']
            absolute_url = urljoin(base_url, src)
            
            image_info = {
                'url': absolute_url,
                'alt': img.get('alt', ''),
                'width': int(img.get('width', 0)) if img.get('width') else 0,
                'height': int(img.get('height', 0)) if img.get('height') else 0,
                'title': img.get('title', ''),
                'type': 'image'
            }
            images.append(image_info)
        
        return images

    def _extract_meta_keywords(self, soup: BeautifulSoup) -> List[str]:
        """提取元关键词"""
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords and meta_keywords.get('content'):
            return [kw.strip() for kw in meta_keywords['content'].split(',')]
        return []

    def _extract_meta_description(self, soup: BeautifulSoup) -> Optional[str]:
        """提取元描述"""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        return meta_desc.get('content') if meta_desc else None

    def _extract_headers(self, soup: BeautifulSoup) -> Dict[str, List[str]]:
        """提取标题层级结构"""
        headers = {}
        for level in range(1, 7):
            tags = soup.find_all(f'h{level}')
            headers[f'h{level}'] = [tag.get_text(strip=True) for tag in tags]
        return headers

    def _count_words(self, text: str) -> int:
        """统计字数"""
        # 简单的字数统计，可以改进为更复杂的算法
        return len(text.split())

    def _calculate_readability(self, text: str) -> float:
        """
        计算可读性分数（基于Flesch Reading Ease公式）
        
        返回0.0-1.0之间的分数，分数越高越易读
        """
        words = text.split()
        sentences = re.split(r'[.!?]+', text)
        
        if len(words) == 0 or len(sentences) == 0:
            return 0.0
        
        # 计算音节数（简化版）
        syllables = 0
        for word in words:
            # 简化计算：每3个字母算一个音节
            syllables += max(1, len(word) // 3)
        
        avg_words_per_sentence = len(words) / len(sentences)
        avg_syllables_per_word = syllables / len(words)
        
        # Flesch Reading Ease公式
        score = 206.835 - 1.015 * avg_words_per_sentence - 84.6 * avg_syllables_per_word
        
        # 归一化到0-1范围（0=最难，1=最易）
        normalized_score = max(0, min(100, score)) / 100
        
        return normalized_score

    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        """提取实体信息（邮箱、电话等）"""
        entities = {
            'emails': [],
            'phones': [],
            'dates': []
        }
        
        # 邮箱提取
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        entities['emails'] = list(set(emails))  # 去重
        
        # 电话号码提取（简化版，支持多种格式）
        phones = re.findall(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|\b\d{10}\b', text)
        entities['phones'] = list(set(phones))
        
        # 日期提取（YYYY-MM-DD 格式）
        dates = re.findall(r'\d{4}-\d{2}-\d{2}', text)
        entities['dates'] = list(set(dates))
        
        return entities

    def _analyze_structure(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """分析页面结构"""
        structure = {
            'has_navigation': bool(soup.find('nav') or soup.find(class_=re.compile(r'nav', re.I))),
            'has_sidebar': bool(soup.find('aside') or soup.find(class_=re.compile(r'sidebar', re.I))),
            'has_footer': bool(soup.find('footer') or soup.find(class_=re.compile(r'footer', re.I))),
            'sections_count': len(soup.find_all(['section', 'article'])),
            'lists_count': len(soup.find_all(['ul', 'ol'])),
            'tables_count': len(soup.find_all('table')),
            'forms_count': len(soup.find_all('form')),
            'buttons_count': len(soup.find_all(['button', 'input[type=button]']))
        }
        
        return structure
