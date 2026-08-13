#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 科研分析模块
支持多种论文格式：PDF、DOCX、TXT、HTML、LaTeX、Markdown
用于辅助科研文本的自动分析、关键词提取、摘要生成等功能
"""

import re
import json
from pathlib import Path
from collections import Counter
import urllib.request
import urllib.parse
from typing import List, Dict, Tuple, Optional

# 可选依赖库的导入
try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def launch_world_map_analyzer():
    """启动WS2世界地图式分析系统（保留向后兼容）"""
    try:
        import tkinter as tk
        from world_map_analyzer import WS2AnalysisGUI
        root = tk.Tk()
        app = WS2AnalysisGUI(root, Path(__file__).parent)
        root.mainloop()
    except Exception as e:
        print(f"⚠️ 启动失败: {e}")


class PaperReader:
    """论文阅读器 - 支持多种格式"""
    
    SUPPORTED_FORMATS = {
        '.pdf': 'PDF文档',
        '.docx': 'Word文档',
        '.txt': '纯文本',
        '.md': 'Markdown',
        '.html': 'HTML网页',
        '.htm': 'HTML网页',
        '.tex': 'LaTeX源码',
    }
    
    def __init__(self):
        self.available_formats = self._check_available_formats()
    
    def _check_available_formats(self) -> Dict[str, bool]:
        """检查可用的格式支持"""
        return {
            '.pdf': HAS_PDF,
            '.docx': HAS_DOCX,
            '.txt': True,
            '.md': True,
            '.html': HAS_BS4,
            '.htm': HAS_BS4,
            '.tex': True,
        }
    
    def get_supported_extensions(self) -> List[str]:
        """获取支持的文件扩展名列表"""
        return list(self.SUPPORTED_FORMATS.keys())
    
    def read_paper(self, file_path: str) -> Optional[str]:
        """读取论文文件（自动识别格式）"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        ext = path.suffix.lower()
        
        if ext == '.pdf':
            return self._read_pdf(file_path)
        elif ext == '.docx':
            return self._read_docx(file_path)
        elif ext in ['.txt', '.md', '.tex']:
            return self._read_text(file_path)
        elif ext in ['.html', '.htm']:
            return self._read_html(file_path)
        else:
            # 默认尝试按文本读取
            return self._read_text(file_path)
    
    def _read_pdf(self, file_path: str) -> Optional[str]:
        """读取PDF文件"""
        if not HAS_PDF:
            raise ImportError("需要安装 PyPDF2: pip install PyPDF2")
        
        text = []
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                try:
                    text.append(page.extract_text())
                except:
                    continue
        return '\n\n'.join(text)
    
    def _read_docx(self, file_path: str) -> Optional[str]:
        """读取Word文档"""
        if not HAS_DOCX:
            raise ImportError("需要安装 python-docx: pip install python-docx")
        
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs]
        return '\n\n'.join(paragraphs)
    
    def _read_text(self, file_path: str) -> Optional[str]:
        """读取纯文本文件"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    
    def _read_html(self, file_path: str) -> Optional[str]:
        """读取HTML文件"""
        if not HAS_BS4:
            raise ImportError("需要安装 beautifulsoup4: pip install beautifulsoup4")
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f, 'html.parser')
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            return soup.get_text(separator='\n\n', strip=True)


class ResearchAnalyzer:
    """科研文本分析器"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.stop_words = self._load_stop_words()
        self.paper_reader = PaperReader()
    
    def _load_stop_words(self) -> set:
        """加载中文和英文停用词"""
        stop_words = {
            '的', '是', '在', '了', '和', '与', '对', '就', '都', 
            '而', '及', '有', '这', '那', '你', '我', '他', '它',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
            'of', 'for', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were',
            'this', 'that', 'these', 'those', 'which', 'what', 'when', 'where',
            'can', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
            '我们', '你们', '他们', '它们', '自己', '因为', '所以', '但是',
            '因此', '然而', '虽然', '如果', '那么', '关于', '对于', '根据'
        }
        return stop_words
    
    def load_paper(self, file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """加载论文文件"""
        try:
            text = self.paper_reader.read_paper(file_path)
            format_name = self.paper_reader.SUPPORTED_FORMATS.get(
                Path(file_path).suffix.lower(), 
                '未知格式'
            )
            return text, format_name
        except Exception as e:
            return None, str(e)
    
    def extract_keywords(self, text: str, top_n: int = 20) -> List[Tuple[str, int]]:
        """从文本中提取关键词"""
        # 清理文本
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = text.split()
        
        # 过滤停用词
        filtered_words = [
            w for w in words 
            if w not in self.stop_words 
            and len(w) > 2
            and not w.isdigit()
        ]
        
        # 统计词频
        word_counts = Counter(filtered_words)
        
        # 返回前N个关键词
        return word_counts.most_common(top_n)
    
    def extract_title(self, text: str) -> Optional[str]:
        """尝试提取论文标题"""
        lines = text.split('\n')
        
        # 查找较短的、可能是标题的行
        for i, line in enumerate(lines[:20]):
            line = line.strip()
            if 5 < len(line) < 200 and line.isprintable():
                # 可能是标题
                if not any(keyword in line.lower() for keyword in 
                          ['abstract', 'introduction', '摘要', '引言', '©', 'http']):
                    return line
        
        return None
    
    def extract_authors(self, text: str) -> List[str]:
        """尝试提取作者信息"""
        authors = []
        
        # 常见作者格式
        patterns = [
            r'([A-Z][a-z]+,?\s*[A-Z]\.?)',  # Smith, J.
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)',  # John Smith
        ]
        
        # 检查前几行
        first_lines = '\n'.join(text.split('\n')[:30])
        for pattern in patterns:
            matches = re.findall(pattern, first_lines)
            authors.extend(matches)
        
        return list(set(authors))[:10]
    
    def extract_abstract(self, text: str) -> Optional[str]:
        """尝试从文本中提取摘要"""
        # 常见摘要标识
        patterns = [
            r'摘要[：:]\s*(.+?)(?=\s*(?:关键词|Abstract|INTRODUCTION|1\.[\s]|$))',
            r'Abstract[：:]\s*(.+?)(?=\s*(?:Keywords|Introduction|1\.[\s]|$))',
            r'ABSTRACT[\s]*[:]?\s*(.+?)(?=\s*(?:KEYWORDS|INTRODUCTION|1\.[\s]|$))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # 如果找不到明确摘要标识，尝试提取开头几段
        paragraphs = [p for p in text.split('\n\n') if len(p.strip()) > 50]
        if paragraphs:
            for p in paragraphs[:3]:
                if len(p) > 100 and not any(keyword in p.lower() for keyword in 
                                          ['title', 'author', 'university', 'abstract']):
                    return p[:1000] if len(p) > 1000 else p
        
        return None
    
    def extract_references(self, text: str) -> List[str]:
        """从文本中提取参考文献"""
        references = []
        
        # 常见引用格式
        patterns = [
            r'\[(\d+)\]\s*([^\[\]]{20,}?)(?=\[\d+\]|\n\s*\n|\Z)',  # [1] Author. Title. Journal, Year
            r'[A-Z][a-z]+,\s*[A-Z]\.?\s*\([0-9]{4}\)\s*[^\.\n]{10,}',  # Author, A. (2024). Title...
        ]
        
        # 查找References部分
        ref_section = self._extract_section(text, ['References', 'REFERENCES', '参考文献', '参考书目'])
        if ref_section:
            text = ref_section
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    match = ' '.join(match)
                if len(match.strip()) > 20:
                    references.append(match.strip())
        
        # 去重并限制数量
        return list(set(references))[:30]
    
    def _extract_section(self, text: str, section_names: List[str]) -> Optional[str]:
        """提取指定章节的内容"""
        for name in section_names:
            pattern = rf'{name}[\s\S]+?(?=\n\s*[A-Z][A-Z0-9\s]+[:\s]|\Z)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None
    
    def analyze_paper_structure(self, text: str) -> Dict:
        """分析论文结构"""
        structure = {
            'has_title': bool(self.extract_title(text)),
            'has_abstract': bool(self.extract_abstract(text)),
            'has_keywords': bool(re.search(r'关键词|Keywords|KEYWORDS', text, re.IGNORECASE)),
            'has_introduction': bool(re.search(r'INTRODUCTION|引言|介绍|1\.[\s]*Introduction', text, re.IGNORECASE)),
            'has_methods': bool(re.search(r'METHODS?|方法|方法论|Methodology', text, re.IGNORECASE)),
            'has_results': bool(re.search(r'RESULTS?|结果|实验结果', text, re.IGNORECASE)),
            'has_discussion': bool(re.search(r'DISCUSSION|讨论', text, re.IGNORECASE)),
            'has_conclusion': bool(re.search(r'CONCLUSION|结论|总结', text, re.IGNORECASE)),
            'has_references': bool(re.search(r'References|REFERENCES|参考文献|参考书目', text, re.IGNORECASE)),
            'has_figures': bool(re.search(r'(Figure|Fig|图)\s*[0-9]+', text, re.IGNORECASE)),
            'has_tables': bool(re.search(r'(Table|Tab|表)\s*[0-9]+', text, re.IGNORECASE)),
            'word_count': len(text.split()),
            'char_count': len(text),
        }
        return structure
    
    def web_search_query(self, keywords: List[str], engine: str = 'google') -> str:
        """生成搜索查询URL"""
        query = ' '.join(keywords)
        encoded_query = urllib.parse.quote(query)
        
        search_urls = {
            'google': f"https://scholar.google.com/scholar?q={encoded_query}",
            'arxiv': f"https://arxiv.org/search/?query={encoded_query}",
            'cnki': f"https://kns.cnki.net/kns8/DefaultResult/Index?kw={encoded_query}",
            'web': f"https://www.google.com/search?q={encoded_query}",
            'bing': f"https://www.bing.com/search?q={encoded_query}",
        }
        
        return search_urls.get(engine, search_urls['web'])
    
    def save_analysis(self, analysis_data: Dict, filename: str):
        """保存分析结果"""
        save_path = self.base_dir / "analysis" / f"{filename}.json"
        save_path.parent.mkdir(exist_ok=True)
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2)
        
        return save_path


class LiteratureNoteBuilder:
    """文献笔记构建器"""
    
    def __init__(self, analyzer: ResearchAnalyzer):
        self.analyzer = analyzer
    
    def create_literature_note(self, title: str, content: str, 
                               author: str = "", source_file: str = "",
                               keywords: List[str] = None) -> str:
        """创建文献笔记模板"""
        
        # 分析内容
        analysis = self.analyzer.analyze_paper_structure(content)
        
        # 自动提取信息
        extracted_title = self.analyzer.extract_title(content)
        extracted_authors = self.analyzer.extract_authors(content)
        extracted_keywords = self.analyzer.extract_keywords(content, 15)
        abstract = self.analyzer.extract_abstract(content) or ""
        
        # 使用提取的信息或用户提供的信息
        final_title = title or extracted_title or "未命名文献"
        final_authors = author or '; '.join(extracted_authors)
        
        # 生成Rmd模板
        template = f"""---
title: "{final_title}"
author: "{final_authors}"
date: "`r Sys.Date()`"
source: "{Path(source_file).name if source_file else ''}"
---

# 文献笔记

## 📋 基本信息
- **标题**: {final_title}
- **作者**: {final_authors}
- **阅读日期**: `r Sys.Date()`
- **来源文件**: {Path(source_file).name if source_file else '直接输入'}

## 📝 摘要
{abstract if abstract else '*请在此添加摘要*'}

## 🔑 关键词分析
"""
        
        # 添加关键词
        if extracted_keywords:
            template += "| 关键词 | 词频 |\n|--------|------|\n"
            for word, count in extracted_keywords:
                template += f"| {word} | {count} |\n"
        else:
            template += "*暂无关键词提取结果*\n"
        
        template += """
## 🏗️ 结构分析
"""
        
        # 结构分析表格
        structure_checks = [
            ('标题', 'has_title'),
            ('摘要', 'has_abstract'),
            ('关键词', 'has_keywords'),
            ('引言', 'has_introduction'),
            ('方法', 'has_methods'),
            ('结果', 'has_results'),
            ('讨论', 'has_discussion'),
            ('结论', 'has_conclusion'),
            ('参考文献', 'has_references'),
            ('图表', 'has_figures'),
            ('表格', 'has_tables'),
        ]
        
        template += "| 部分 | 状态 |\n|------|------|\n"
        for label, key in structure_checks:
            status = '✅' if analysis.get(key, False) else '❌'
            template += f"| {label} | {status} |\n"
        
        template += f"""
- **总字数**: {analysis.get('word_count', 0):,} 字
- **字符数**: {analysis.get('char_count', 0):,} 字符

## 📒 阅读笔记
- 核心观点:
- 创新点:
- 方法:
- 结论:

## 💭 思考与启发

## 🔗 相关搜索
"""
        
        # 添加搜索链接
        search_terms = [kw[0] for kw in extracted_keywords[:5]] if extracted_keywords else []
        if search_terms:
            template += f"- [Google Scholar]({self.analyzer.web_search_query(search_terms, 'google')})\n"
            template += f"- [arXiv]({self.analyzer.web_search_query(search_terms, 'arxiv')})\n"
            template += f"- [CNKI]({self.analyzer.web_search_query(search_terms, 'cnki')})\n"
        
        return template


if __name__ == "__main__":
    import sys
    BASE_DIR = Path(__file__).parent
    
    if len(sys.argv) > 1 and sys.argv[1] in ['worldmap', 'map', 'visualize']:
        print("🌍 启动WS2世界地图式分析系统...")
        launch_world_map_analyzer()
    else:
        analyzer = ResearchAnalyzer(BASE_DIR)
        print("""
╔═══════════════════════════════════════════════════════════╗
║           WS2 科研分析系统                                  ║
╠═══════════════════════════════════════════════════════════╣
║  支持格式:                                                 ║
║    ✓ PDF (.pdf)         ✓ Word (.docx)                     ║
║    ✓ 纯文本 (.txt)      ✓ Markdown (.md)                   ║
║    ✓ HTML (.html/.htm)  ✓ LaTeX (.tex)                     ║
║                                                            ║
║  使用方法:                                                 ║
║    从 WS2 主程序的「科研分析」页面使用                      ║
╚═══════════════════════════════════════════════════════════╝
        """)
        print("📚 科研分析模块已加载！")
