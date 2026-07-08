"""PDF 智能阅读服务 — 文本提取 + RAG 索引 + 问答"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..rag.rag_engine import RAGEngine
from ..rag.document_loader import PdfDocumentLoader

logger = logging.getLogger(__name__)

# 全局 RAG 引擎（懒加载）
_pdf_rag: Optional[RAGEngine] = None


def get_pdf_rag(workspace_dir: str) -> RAGEngine:
    """获取或初始化 PDF RAG 引擎"""
    global _pdf_rag
    if _pdf_rag is None:
        from ..rag.vector_store import ChromaVectorStore, SimpleVectorStore

        persist_dir = os.path.join(workspace_dir, ".ts2_data", "chroma_pdf")
        os.makedirs(persist_dir, exist_ok=True)

        try:
            vector_store = ChromaVectorStore(
                persist_directory=persist_dir,
                collection_name="ts2_pdf_docs"
            )
        except (ImportError, Exception) as e:
            logger.warning(f"ChromaDB 不可用，回退到 SimpleVectorStore: {e}")
            vector_store = SimpleVectorStore(persist_directory=Path(persist_dir))

        _pdf_rag = RAGEngine(vector_store=vector_store)
    return _pdf_rag


def extract_pdf_text(file_path: str) -> Dict[str, Any]:
    """提取 PDF 文本，返回按页组织的内容"""
    loader = PdfDocumentLoader()
    documents = loader.load(file_path)

    pages = []
    for doc in documents:
        pages.append({
            "page": doc.metadata.get("page_number", 0),
            "text": doc.content,
            "is_scanned": doc.metadata.get("is_scanned", False),
        })

    return {
        "file_path": file_path,
        "total_pages": documents[0].metadata.get("total_pages", 0) if documents else 0,
        "pages": pages,
    }


def index_pdf(file_path: str, workspace_dir: str) -> Dict[str, Any]:
    """将 PDF 索引到 RAG 引擎"""
    rag = get_pdf_rag(workspace_dir)
    doc_ids = rag.add_file(file_path)
    return {
        "file_path": file_path,
        "chunk_count": len(doc_ids),
        "doc_ids": doc_ids,
    }


def query_pdf(query: str, workspace_dir: str, top_k: int = 4) -> Dict[str, Any]:
    """对已索引的 PDF 内容进行 RAG 查询"""
    rag = get_pdf_rag(workspace_dir)
    results = rag.retrieve_with_scores(query, top_k=top_k)

    contexts = []
    for doc, score in results:
        contexts.append({
            "content": doc.content,
            "score": round(score, 4),
            "source": doc.source,
            "page": doc.metadata.get("page_number", 0),
            "file_name": doc.metadata.get("file_name", ""),
        })

    return {
        "query": query,
        "results": contexts,
    }
