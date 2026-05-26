#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档加载器模块
支持多种格式文档的加载和处理
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Document:
    """文档数据类"""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "source": self.source,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        return cls(**data)


class DocumentLoader:
    """文档加载器基类"""
    
    def load(self, path: Union[str, Path]) -> List[Document]:
        """加载文档"""
        raise NotImplementedError
    
    def load_text(self, text: str, source: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Document:
        """从文本加载文档"""
        import uuid
        doc_id = str(uuid.uuid4())
        return Document(
            id=doc_id,
            content=text,
            metadata=metadata or {},
            source=source
        )


class TextDocumentLoader(DocumentLoader):
    """文本文件加载器"""
    
    def load(self, path: Union[str, Path]) -> List[Document]:
        path = Path(path)
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        
        content = None
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            raise ValueError(f"无法解码文件: {path}")
        
        doc = self.load_text(
            text=content,
            source=str(path),
            metadata={
                "file_path": str(path),
                "file_name": path.name,
                "file_type": path.suffix.lower(),
                "file_size": path.stat().st_size
            }
        )
        return [doc]


class MarkdownDocumentLoader(DocumentLoader):
    """Markdown文档加载器"""
    
    def load(self, path: Union[str, Path]) -> List[Document]:
        text_loader = TextDocumentLoader()
        docs = text_loader.load(path)
        
        for doc in docs:
            doc.metadata["is_markdown"] = True
            # 提取标题
            headings = self._extract_headings(doc.content)
            if headings:
                doc.metadata["headings"] = headings
                if headings:
                    doc.metadata["title"] = headings[0]
        
        return docs
    
    def _extract_headings(self, content: str) -> List[str]:
        """提取Markdown标题"""
        headings = []
        pattern = r'^#{1,6}\s+(.+)$'
        for line in content.split('\n'):
            match = re.match(pattern, line.strip())
            if match:
                headings.append(match.group(1))
        return headings


class JSONDocumentLoader(DocumentLoader):
    """JSON文档加载器"""
    
    def load(self, path: Union[str, Path]) -> List[Document]:
        path = Path(path)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        docs = []
        
        if isinstance(data, dict):
            # 单个文档
            content = json.dumps(data, ensure_ascii=False, indent=2)
            doc = self.load_text(
                text=content,
                source=str(path),
                metadata={
                    "file_path": str(path),
                    "file_name": path.name,
                    "file_type": ".json",
                    "data_type": "dict"
                }
            )
            docs.append(doc)
        elif isinstance(data, list):
            # 多个文档
            for i, item in enumerate(data):
                content = json.dumps(item, ensure_ascii=False, indent=2)
                doc = self.load_text(
                    text=content,
                    source=f"{str(path)}#item_{i}",
                    metadata={
                        "file_path": str(path),
                        "file_name": path.name,
                        "file_type": ".json",
                        "data_type": "list",
                        "item_index": i
                    }
                )
                docs.append(doc)
        
        return docs


def get_loader_for_file(file_path: Union[str, Path]) -> DocumentLoader:
    """根据文件类型获取对应的加载器"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    if suffix == '.md':
        return MarkdownDocumentLoader()
    elif suffix == '.json':
        return JSONDocumentLoader()
    else:
        return TextDocumentLoader()
