#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检索器模块
提供基于向量存储的文档检索功能
"""

from typing import List, Dict, Any, Optional, Callable
from .document_loader import Document
from .vector_store import VectorStore


class Retriever:
    """检索器基类"""
    
    def retrieve(self, query: str, top_k: int = 4) -> List[Document]:
        """检索相关文档"""
        raise NotImplementedError
    
    def retrieve_with_scores(self, query: str, top_k: int = 4) -> List[tuple]:
        """检索相关文档并返回分数"""
        raise NotImplementedError


class SimilarityRetriever(Retriever):
    """基于相似度的检索器"""
    
    def __init__(
        self,
        vector_store: VectorStore,
        top_k: int = 4,
        search_type: str = "similarity",
        score_threshold: Optional[float] = None
    ):
        self.vector_store = vector_store
        self.top_k = top_k
        self.search_type = search_type
        self.score_threshold = score_threshold
    
    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        """检索相关文档"""
        k = top_k or self.top_k
        return self.vector_store.similarity_search(query, k)
    
    def retrieve_with_scores(self, query: str, top_k: Optional[int] = None) -> List[tuple]:
        """检索相关文档并返回分数"""
        k = top_k or self.top_k
        results = self.vector_store.similarity_search_with_score(query, k)
        
        # 应用分数阈值
        if self.score_threshold is not None:
            results = [
                (doc, score) for doc, score in results
                if score >= self.score_threshold
            ]
        
        return results


class FilteredRetriever(SimilarityRetriever):
    """带元数据过滤的检索器"""
    
    def __init__(
        self,
        vector_store: VectorStore,
        top_k: int = 4,
        default_filter: Optional[Dict[str, Any]] = None
    ):
        super().__init__(vector_store, top_k)
        self.default_filter = default_filter or {}
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """检索相关文档（支持过滤）"""
        k = top_k or self.top_k
        final_filter = {**self.default_filter, **(filter_metadata or {})}
        return self.vector_store.similarity_search(query, k, final_filter)
    
    def retrieve_with_scores(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[tuple]:
        """检索相关文档并返回分数（支持过滤）"""
        k = top_k or self.top_k
        final_filter = {**self.default_filter, **(filter_metadata or {})}
        return self.vector_store.similarity_search_with_score(query, k, final_filter)


class HybridRetriever(Retriever):
    """混合检索器（结合多种检索策略）"""
    
    def __init__(
        self,
        retrievers: List[Retriever],
        weights: Optional[List[float]] = None
    ):
        self.retrievers = retrievers
        self.weights = weights or [1.0 / len(retrievers)] * len(retrievers)
    
    def retrieve(self, query: str, top_k: int = 4) -> List[Document]:
        """混合检索"""
        all_results = {}
        
        for retriever, weight in zip(self.retrievers, self.weights):
            results = retriever.retrieve_with_scores(query, top_k)
            for doc, score in results:
                doc_id = doc.id
                if doc_id not in all_results:
                    all_results[doc_id] = (doc, 0.0)
                all_results[doc_id] = (doc, all_results[doc_id][1] + score * weight)
        
        # 排序
        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [doc for doc, _ in sorted_results[:top_k]]
    
    def retrieve_with_scores(self, query: str, top_k: int = 4) -> List[tuple]:
        """混合检索并返回分数"""
        all_results = {}
        
        for retriever, weight in zip(self.retrievers, self.weights):
            results = retriever.retrieve_with_scores(query, top_k)
            for doc, score in results:
                doc_id = doc.id
                if doc_id not in all_results:
                    all_results[doc_id] = (doc, 0.0)
                all_results[doc_id] = (doc, all_results[doc_id][1] + score * weight)
        
        # 排序
        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return sorted_results[:top_k]
