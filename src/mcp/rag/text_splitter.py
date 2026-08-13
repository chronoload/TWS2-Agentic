#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文本分割器模块
将文档分割成适合向量化的文本块
"""

import re
from typing import List, Optional, Callable
from .document_loader import Document


class TextSplitter:
    """文本分割器基类"""
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", " ", ""]
    
    def split_text(self, text: str) -> List[str]:
        """分割文本"""
        raise NotImplementedError
    
    def split_document(self, document: Document) -> List[Document]:
        """分割文档"""
        chunks = self.split_text(document.content)
        chunk_docs = []
        
        for i, chunk in enumerate(chunks):
            chunk_metadata = document.metadata.copy()
            chunk_metadata["chunk_index"] = i
            chunk_metadata["total_chunks"] = len(chunks)
            
            chunk_doc = Document(
                id=f"{document.id}_chunk_{i}",
                content=chunk,
                metadata=chunk_metadata,
                source=document.source
            )
            chunk_docs.append(chunk_doc)
        
        return chunk_docs


class RecursiveCharacterTextSplitter(TextSplitter):
    """递归字符文本分割器"""
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None,
        keep_separator: bool = True,
        length_function: Callable[[str], int] = len,
        max_recursion_depth: int = 10
    ):
        super().__init__(chunk_size, chunk_overlap, separators)
        self.keep_separator = keep_separator
        self.length_function = length_function
        self.max_recursion_depth = max_recursion_depth
    
    def split_text(self, text: str, _depth: int = 0) -> List[str]:
        """递归分割文本（带深度限制防无限递归）"""
        if _depth >= self.max_recursion_depth:
            # 达到最大递归深度，直接返回整个文本作为单个块
            return [text]
        
        chunks = []
        separator = self.separators[-1]
        
        # 查找合适的分隔符
        for _sep in self.separators:
            if _sep in text:
                separator = _sep
                break
        
        # 分割文本
        if separator:
            splits = self._split_text_with_separator(text, separator)
        else:
            splits = [text]
        
        # 合并小块
        good_splits = []
        for s in splits:
            if self.length_function(s) < self.chunk_size:
                good_splits.append(s)
            else:
                # 递归分割（带深度限制）
                if separator != self.separators[-1]:
                    recursive_splits = self.split_text(s, _depth + 1)
                    good_splits.extend(recursive_splits)
                else:
                    good_splits.append(s)
        
        # 合并成块
        chunks = self._merge_splits(good_splits, separator)
        
        return chunks
    
    def _split_text_with_separator(self, text: str, separator: str) -> List[str]:
        """使用指定分隔符分割文本"""
        if self.keep_separator and separator:
            splits = []
            start = 0
            while True:
                idx = text.find(separator, start)
                if idx == -1:
                    splits.append(text[start:])
                    break
                splits.append(text[start:idx + len(separator)])
                start = idx + len(separator)
            return splits
        else:
            return text.split(separator) if separator else [text]
    
    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        """合并分割块"""
        chunks = []
        current_chunk = []
        current_length = 0
        
        for s in splits:
            s_length = self.length_function(s)
            
            if current_length + s_length > self.chunk_size:
                if current_chunk:
                    chunk = separator.join(current_chunk)
                    chunks.append(chunk)
                    
                    # 保留重叠
                    while (current_length > self.chunk_overlap or 
                           (current_length + s_length > self.chunk_size and current_length > 0)):
                        removed = current_chunk.pop(0)
                        current_length -= self.length_function(removed)
            
            current_chunk.append(s)
            current_length += s_length
        
        if current_chunk:
            chunk = separator.join(current_chunk)
            chunks.append(chunk)
        
        return chunks


class MarkdownTextSplitter(RecursiveCharacterTextSplitter):
    """Markdown文档专用分割器"""
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        **kwargs
    ):
        separators = [
            "\n## ", "\n### ", "\n#### ", "\n##### ", "\n###### ",
            "\n\n", "\n", " ", ""
        ]
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
            **kwargs
        )
