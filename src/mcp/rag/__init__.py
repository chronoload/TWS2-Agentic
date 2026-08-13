"""
WS2 RAG (Retrieval-Augmented Generation) 系统
内部知识检索和增强生成
"""

from .document_loader import Document, DocumentLoader
from .text_splitter import TextSplitter, RecursiveCharacterTextSplitter
from .vector_store import VectorStore, SimpleVectorStore
from .retriever import Retriever, SimilarityRetriever
from .rag_engine import RAGEngine, create_rag_engine
from .auto_rag import AutoRAGManager, RetrievalConfig, get_auto_rag, initialize_rag_for_agent

__version__ = "1.0.0"

__all__ = [
    "Document",
    "DocumentLoader",
    "TextSplitter",
    "RecursiveCharacterTextSplitter",
    "VectorStore",
    "SimpleVectorStore",
    "Retriever",
    "SimilarityRetriever",
    "RAGEngine",
    "create_rag_engine",
    "AutoRAGManager",
    "RetrievalConfig",
    "get_auto_rag",
    "initialize_rag_for_agent",
]
