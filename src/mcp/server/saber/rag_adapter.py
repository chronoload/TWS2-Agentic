"""
SaberSystem RAG Adapter — 对接 TS2 现有 RAGEngine/AutoRAGManager

不另写检索逻辑，直接调用 TS2 RAG 基础设施：
- RAGEngine.retrieve(query, top_k) → List[Document]
- AutoRAGManager.should_retrieve(query) → bool
- AutoRAGManager.retrieve(query) → (summary, sources)

认知层级过滤（K-C-T-S-W）通过 metadata['cognitive_layer'] 实现。
"""
from __future__ import annotations
from typing import Any

from mcp.server.saber.models import CognitiveLayer


class SaberRAGAdapter:
    """SaberSystem 万有 RAG 适配器

    用法：
        adapter = SaberRAGAdapter(rag_engine, auto_rag)
        docs = adapter.retrieve_cognitive("transformer attention", CognitiveLayer.K)
        context = adapter.inject_plan_context(plan)
    """

    def __init__(self, rag_engine=None, auto_rag=None):
        self._rag_engine = rag_engine
        self._auto_rag = auto_rag

    @property
    def is_ready(self) -> bool:
        return self._rag_engine is not None

    def retrieve_cognitive(
        self, query: str, layer: CognitiveLayer | None = None, top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """按认知层级检索，结果含 metadata['cognitive_layer'] 过滤"""
        if not self._rag_engine:
            return []
        docs = self._rag_engine.retrieve(query, top_k=top_k)
        results = []
        for d in docs:
            meta = d.metadata or {}
            doc_layer = meta.get("cognitive_layer", "")
            if layer is not None and doc_layer and doc_layer != layer.value:
                continue
            results.append({
                "id": d.id,
                "content": d.content[:500],
                "layer": doc_layer or "unknown",
                "score": meta.get("score", 0.0),
                "source": meta.get("source", ""),
            })
        return results

    def should_auto_retrieve(self, query: str) -> bool:
        if self._auto_rag is None:
            return False
        return self._auto_rag.should_retrieve(query)

    def auto_retrieve(self, query: str) -> dict[str, Any]:
        if self._auto_rag is None:
            return {"summary": "", "sources": []}
        summary, sources = self._auto_rag.retrieve(query)
        return {"summary": summary, "sources": sources}

    def inject_plan_context(self, plan) -> str:
        """为 Plan 自动检索相关认知养料，返回摘要文本"""
        if not self._rag_engine:
            return ""
        query = f"{plan.title} {plan.cognitive_focus.value}"
        docs = self._rag_engine.retrieve(query, top_k=3)
        if not docs:
            return ""
        parts = ["[万有 RAG 养料]"]
        for d in docs:
            parts.append(f"- {d.content[:200]}")
        return "\n".join(parts)
