#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 科研分析系统 - 增强版
支持多种科研论文格式：PDF、Word、HTML、TXT、Markdown等
"""

import re
import json
import subprocess
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional, Any
import urllib.parse

# 尝试导入可选依赖
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

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

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class PaperReader:
    """论文阅读器 - 支持多种格式"""
    
    def __init__(self):
        self.supported_formats = {
            '.pdf': 'PDF文档',
            '.docx': 'Word文档',
            '.doc': 'Word文档(旧版)',
            '.txt': '文本文件',
            '.md': 'Markdown',
            '.html': 'HTML页面',
            '.htm': 'HTML页面',
            '.rtf': 'RTF文档',
        }
    
    def read_file(self, file_path: str | Path) -> Optional[str]:
        """读取文件内容，根据格式自动选择解析器"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        suffix = path.suffix.lower()
        
        if suffix == '.pdf':
            return self._read_pdf(path)
        elif suffix in ['.docx']:
            return self._read_docx(path)
        elif suffix == '.doc':
            return self._read_doc(path)
        elif suffix in ['.html', '.htm']:
            return self._read_html(path)
        elif suffix in ['.txt', '.md', '.rtf']:
            return self._read_text(path)
        else:
            return self._read_text(path)
    
    def _read_pdf(self, path: Path) -> Optional[str]:
        """读取PDF文件"""
        if not HAS_PYPDF2:
            return self._fallback_read(path, "PDF解析需要安装 PyPDF2")
        
        try:
            text = ""
            with open(path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    try:
                        page_text = page.extract_text() or ""
                        text += page_text + "\n\n"
                    except:
                        continue
            return text
        except Exception as e:
            print(f"PDF读取失败: {e}")
            return self._fallback_read(path, f"PDF解析失败: {e}")
    
    def _read_docx(self, path: Path) -> Optional[str]:
        """读取Word文档(.docx)"""
        if not HAS_DOCX:
            return self._fallback_read(path, "Word解析需要安装 python-docx")
        
        try:
            doc = Document(path)
            text = "\n".join([para.text for para in doc.paragraphs])
            return text
        except Exception as e:
            print(f"Word读取失败: {e}")
            return self._fallback_read(path, f"Word解析失败: {e}")
    
    def _read_doc(self, path: Path) -> Optional[str]:
        """读取旧版Word文档(.doc) - 需要系统有 antiword 或 textutil"""
        try:
            # 尝试多种方法
            import platform
            system = platform.system()
            
            if system == 'Darwin':
                # macOS 使用 textutil
                result = subprocess.run(
                    ['textutil', '-convert', 'txt', '-stdout', str(path)],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    return result.stdout
            elif system == 'Windows':
                # Windows 尝试使用 pywin32 或直接作为文本
                try:
                    import win32com.client as win32
                    word = win3