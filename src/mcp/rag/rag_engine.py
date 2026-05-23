#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG引擎模块
整合文档加载、分割、存储和检索功能
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from .document_loader import (
    Document,
    DocumentLoader,
    get_loader_for_file
)
from .text_splitter import (
    TextSplitter,
    RecursiveCharacterTextSplitter,
    MarkdownTextSplitter
)
from .vector_store import VectorStore, SimpleVectorStore
from .retriever import Retriever, SimilarityRetriever

logger = logging.getLogger(__name__)


class RAGEngine:
    """RAG引擎 - 整合所有RAG功能"""
    
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        text_splitter: Optional[TextSplitter] = None,
        retriever: Optional[Retriever] = None,
        persist_directory: Optional[Union[str, Path]] = None
    ):
        self.persist_directory = Path(persist_directory) if persist_directory else None
        
        # 初始化向量存储
        self.vector_store = vector_store or SimpleVectorStore(
            persist_directory=self.persist_directory
        )
        
        # 初始化文本分割器
        self.text_splitter = text_splitter or RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        
        # 初始化检索器
        self.retriever = retriever or SimilarityRetriever(
            vector_store=self.vector_store,
            top_k=4
        )
    
    def add_file(
        self,
        file_path: Union[str, Path],
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """添加单个文件到RAG系统"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 获取适当的加载器
        loader = get_loader_for_file(file_path)
        
        # 加载文档
        documents = loader.load(file_path)
        
        # 添加额外的元数据
        if metadata:
            for doc in documents:
                doc.metadata.update(metadata)
        
        # 分割文档
        all_chunks = []
        for doc in documents:
            # 根据文件类型选择分割器
            if file_path.suffix.lower() == '.md':
                splitter = MarkdownTextSplitter()
            else:
                splitter = self.text_splitter
            
            chunks = splitter.split_document(doc)
            all_chunks.extend(chunks)
        
        # 添加到向量存储
        ids = self.vector_store.add_documents(all_chunks)
        
        logger.info(f"添加文件: {file_path.name}, {len(all_chunks)} 个文本块")
        
        return ids
    
    def add_directory(
        self,
        directory_path: Union[str, Path],
        extensions: Optional[List[str]] = None,
        recursive: bool = True
    ) -> Dict[str, List[str]]:
        """添加整个目录的文件到RAG系统"""
        directory_path = Path(directory_path)
        if not directory_path.exists():
            raise FileNotFoundError(f"目录不存在: {directory_path}")
        
        if extensions is None:
            extensions = ['.txt', '.md', '.json']
        
        results = {}
        
        # 查找文件
        if recursive:
            files = []
            for ext in extensions:
                files.extend(directory_path.rglob(f'*{ext}'))
        else:
            files = []
            for ext in extensions:
                files.extend(directory_path.glob(f'*{ext}'))
        
        # 添加文件
        for file_path in files:
            try:
                ids = self.add_file(file_path)
                results[str(file_path)] = ids
            except Exception as e:
                logger.error(f"添加文件失败 {file_path}: {e}")
                results[str(file_path)] = []
        
        return results
    
    def add_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加单段文本到RAG系统"""
        doc_id = self.vector_store.add_texts([text], [metadata] if metadata else None)[0]
        return doc_id
    
    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """添加多段文本到RAG系统"""
        return self.vector_store.add_texts(texts, metadatas)
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> List[Document]:
        """检索相关文档"""
        return self.retriever.retrieve(query, top_k)
    
    def retrieve_with_scores(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> List[tuple]:
        """检索相关文档并返回分数"""
        return self.retriever.retrieve_with_scores(query, top_k)
    
    def query(
        self,
        query: str,
        top_k: int = 4
    ) -> Dict[str, Any]:
        """查询并返回格式化结果"""
        documents = self.retrieve(query, top_k)
        
        # 格式化结果
        result = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "count": len(documents),
            "documents": []
        }
        
        for i, doc in enumerate(documents):
            doc_info = {
                "index": i + 1,
                "id": doc.id,
                "content": doc.content,
                "metadata": doc.metadata,
                "source": doc.source
            }
            result["documents"].append(doc_info)
        
        return result
    
    def get_context_for_prompt(
        self,
        query: str,
        top_k: int = 4,
        max_context_length: int = 999999
    ) -> str:
        """获取格式化的上下文用于提示词（不截断）"""
        documents = self.retrieve(query, top_k)
        
        context_parts = []
        
        for i, doc in enumerate(documents):
            content = doc.content
            source = doc.metadata.get("file_name", doc.source or f"document_{i}")
            context_part = f"【来源: {source}】\n{content}\n"
            context_parts.append(context_part)
        
        return "\n".join(context_parts)
    
    def persist(self, path: Optional[Union[str, Path]] = None) -> None:
        """持久化RAG系统"""
        save_path = Path(path) if path else self.persist_directory
        self.vector_store.persist(save_path)
        logger.info(f"RAG系统已持久化到: {save_path}")
    
    def clear(self) -> None:
        """清空RAG系统"""
        all_ids = [doc.id for doc in self.vector_store.get_all_documents()]
        self.vector_store.delete(all_ids)
        logger.info("RAG系统已清空")
    
    def get_document_count(self) -> int:
        """获取文档数量"""
        return len(self.vector_store)
    
    def get_all_documents(self) -> List[Document]:
        """获取所有文档"""
        return self.vector_store.get_all_documents()
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> "RAGEngine":
        """加载已持久化的RAG系统"""
        vector_store = SimpleVectorStore.load(path)
        return cls(
            vector_store=vector_store,
            persist_directory=Path(path)
        )


def create_rag_engine(
    persist_directory: Optional[Union[str, Path]] = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    top_k: int = 4
) -> RAGEngine:
    """创建RAG引擎的便捷函数"""
    # 创建文本分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    
    # 创建向量存储
    vector_store = SimpleVectorStore(persist_directory=persist_directory)
    
    # 创建检索器
    retriever = SimilarityRetriever(
        vector_store=vector_store,
        top_k=top_k
    )
    
    # 创建并返回RAG引擎
    return RAGEngine(
        vector_store=vector_store,
        text_splitter=text_splitter,
        retriever=retriever,
        persist_directory=persist_directory
    )
