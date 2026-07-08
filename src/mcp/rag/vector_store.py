#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量存储模块
提供文本向量的存储和相似度搜索
"""

import json
import hashlib
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict

from .document_loader import Document


try:
    # 尝试导入 sentence-transformers 用于向量编码
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


@dataclass
class VectorEntry:
    """向量条目"""
    id: str
    vector: List[float]
    document: Document
    created_at: float = field(default_factory=lambda: __import__('time').time())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "vector": self.vector,
            "document": self.document.to_dict(),
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorEntry":
        return cls(
            id=data["id"],
            vector=data["vector"],
            document=Document.from_dict(data["document"]),
            created_at=data.get("created_at", 0.0)
        )


class VectorStore:
    """向量存储基类"""
    
    def add_documents(self, documents: List[Document]) -> List[str]:
        """添加文档并返回ID列表"""
        raise NotImplementedError
    
    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """添加文本"""
        raise NotImplementedError
    
    def similarity_search(
        self,
        query: str,
        k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """相似度搜索"""
        raise NotImplementedError
    
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[Document, float]]:
        """相似度搜索并返回分数"""
        raise NotImplementedError
    
    def delete(self, ids: List[str]) -> None:
        """删除向量"""
        raise NotImplementedError
    
    def persist(self, path: Union[str, Path]) -> None:
        """持久化存储"""
        raise NotImplementedError
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> "VectorStore":
        """加载存储"""
        raise NotImplementedError


class SimpleVectorStore(VectorStore):
    """简单的本地向量存储（纯Python实现，无外部依赖）"""
    
    def __init__(
        self,
        embedding_model: Optional[str] = None,
        persist_directory: Optional[Union[str, Path]] = None
    ):
        self.entries: Dict[str, VectorEntry] = {}
        self.persist_directory = Path(persist_directory) if persist_directory else None
        self._embedding_model = None
        self._embedding_model_name = embedding_model or "paraphrase-multilingual-MiniLM-L12-v2"
        
        # 如果没有 sentence-transformers，使用简单的 TF-IDF 或字符哈希
        if not HAS_SENTENCE_TRANSFORMERS:
            print("警告: sentence-transformers 未安装，使用简单向量编码")
        
        if self.persist_directory:
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取文本的向量表示"""
        if HAS_SENTENCE_TRANSFORMERS and self._embedding_model:
            return self._embedding_model.encode(text).tolist()
        
        # 回退方案：简单的字符级向量
        return self._simple_embedding(text)
    
    def _simple_embedding(self, text: str) -> List[float]:
        """简单的向量编码（基于字符频率）"""
        # 使用固定维度的向量
        dim = 256
        vector = [0.0] * dim
        
        # 字符哈希
        text_bytes = text.encode('utf-8')
        for i, byte in enumerate(text_bytes):
            idx = (byte + i) % dim
            vector[idx] += 1.0
        
        # 归一化
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = [v / norm for v in vector]
        
        return vector
    
    def _load_embedding_model(self) -> None:
        """加载嵌入模型"""
        if HAS_SENTENCE_TRANSFORMERS and self._embedding_model is None:
            try:
                self._embedding_model = SentenceTransformer(self._embedding_model_name)
            except Exception as e:
                print(f"加载嵌入模型失败: {e}，使用简单编码")
    
    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """计算余弦相似度"""
        np_v1 = np.array(v1)
        np_v2 = np.array(v2)
        dot_product = np.dot(np_v1, np_v2)
        norm1 = np.linalg.norm(np_v1)
        norm2 = np.linalg.norm(np_v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)
    
    def add_documents(self, documents: List[Document]) -> List[str]:
        """添加文档"""
        self._load_embedding_model()
        ids = []
        
        for doc in documents:
            vector = self._get_embedding(doc.content)
            entry = VectorEntry(
                id=doc.id,
                vector=vector,
                document=doc
            )
            self.entries[doc.id] = entry
            ids.append(doc.id)
        
        return ids
    
    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """添加文本"""
        import uuid
        metadatas = metadatas or [{} for _ in texts]
        ids = ids or [str(uuid.uuid4()) for _ in texts]
        
        docs = []
        for text, metadata, doc_id in zip(texts, metadatas, ids):
            doc = Document(
                id=doc_id,
                content=text,
                metadata=metadata
            )
            docs.append(doc)
        
        return self.add_documents(docs)
    
    def similarity_search(
        self,
        query: str,
        k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """相似度搜索"""
        results = self.similarity_search_with_score(query, k, filter_metadata)
        return [doc for doc, _ in results]
    
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[Document, float]]:
        """相似度搜索并返回分数"""
        self._load_embedding_model()
        query_vector = self._get_embedding(query)
        
        # 计算所有条目的相似度
        scores = []
        for entry in self.entries.values():
            # 应用元数据过滤
            if filter_metadata:
                match = True
                for key, value in filter_metadata.items():
                    if entry.document.metadata.get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            score = self._cosine_similarity(query_vector, entry.vector)
            scores.append((entry.document, score))
        
        # 按分数排序
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]
    
    def delete(self, ids: List[str]) -> None:
        """删除向量"""
        for doc_id in ids:
            if doc_id in self.entries:
                del self.entries[doc_id]
    
    def persist(self, path: Optional[Union[str, Path]] = None) -> None:
        """持久化存储"""
        save_path = Path(path) if path else self.persist_directory
        if not save_path:
            return
        
        save_path.mkdir(parents=True, exist_ok=True)
        
        # 保存向量数据
        data = {
            "version": "1.0",
            "embedding_model": self._embedding_model_name,
            "entries": [entry.to_dict() for entry in self.entries.values()]
        }
        
        data_file = save_path / "vector_store.json"
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load_from_disk(self) -> None:
        """从磁盘加载"""
        if not self.persist_directory:
            return
        
        data_file = self.persist_directory / "vector_store.json"
        if data_file.exists():
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self._embedding_model_name = data.get("embedding_model", self._embedding_model_name)
                self.entries = {
                    entry["id"]: VectorEntry.from_dict(entry)
                    for entry in data.get("entries", [])
                }
            except Exception as e:
                print(f"加载向量存储失败: {e}")
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> "SimpleVectorStore":
        """加载存储"""
        store = cls(persist_directory=path)
        return store
    
    def __len__(self) -> int:
        return len(self.entries)
    
    def get_all_documents(self) -> List[Document]:
        """获取所有文档"""
        return [entry.document for entry in self.entries.values()]


try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class ChromaVectorStore(VectorStore):
    """基于 ChromaDB 的持久化向量存储"""

    def __init__(self, persist_directory: Optional[Union[str, Path]] = None,
                 collection_name: str = "ts2_documents"):
        if not HAS_CHROMADB:
            raise ImportError("chromadb 未安装，请运行: pip install chromadb")

        self.persist_directory = str(persist_directory) if persist_directory else None
        self.collection_name = collection_name

        client_settings = chromadb.Settings(anonymized_telemetry=False)
        if self.persist_directory:
            self._client = chromadb.PersistentClient(path=self.persist_directory)
        else:
            self._client = chromadb.Client(client_settings)

        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        self._embedding_fn = None
        if HAS_SENTENCE_TRANSFORMERS:
            self._embedding_fn = SentenceTransformer("all-MiniLM-L6-v2")

    def _embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        if self._embedding_fn:
            return self._embedding_fn.encode(texts, show_progress_bar=False).tolist()
        return None

    def add_documents(self, documents: List[Document]) -> List[str]:
        ids = [doc.id for doc in documents]
        texts = [doc.content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        embeddings = self._embed(texts)

        kwargs = {"ids": ids, "documents": texts, "metadatas": metadatas}
        if embeddings:
            kwargs["embeddings"] = embeddings

        self._collection.add(**kwargs)
        return ids

    def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None,
                  ids: Optional[List[str]] = None) -> List[str]:
        import uuid
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        embeddings = self._embed(texts)

        kwargs = {"ids": ids, "documents": texts, "metadatas": metadatas or [{}] * len(texts)}
        if embeddings:
            kwargs["embeddings"] = embeddings

        self._collection.add(**kwargs)
        return ids

    def similarity_search(self, query: str, k: int = 4,
                          filter_metadata: Optional[Dict[str, Any]] = None) -> List[Document]:
        results = self.similarity_search_with_score(query, k, filter_metadata)
        return [doc for doc, _ in results]

    def similarity_search_with_score(self, query: str, k: int = 4,
                                     filter_metadata: Optional[Dict[str, Any]] = None
                                     ) -> List[Tuple[Document, float]]:
        query_embedding = self._embed([query])
        kwargs: Dict[str, Any] = {"n_results": k}
        if query_embedding:
            kwargs["query_embeddings"] = query_embedding
        else:
            kwargs["query_texts"] = [query]
        if filter_metadata:
            kwargs["where"] = filter_metadata

        results = self._collection.query(**kwargs)

        documents = []
        if results and results["documents"] and results["documents"][0]:
            for i, (text, metadata, distance) in enumerate(
                zip(results["documents"][0], results["metadatas"][0], results["distances"][0])
            ):
                doc = Document(
                    id=results["ids"][0][i],
                    content=text,
                    metadata=metadata,
                )
                documents.append((doc, 1.0 - distance))
        return documents

    def delete(self, ids: List[str]) -> None:
        self._collection.delete(ids=ids)

    def persist(self, path: Optional[Union[str, Path]] = None) -> None:
        pass  # ChromaDB PersistentClient 自动持久化

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ChromaVectorStore":
        return cls(persist_directory=path)

    def count(self) -> int:
        return self._collection.count()
