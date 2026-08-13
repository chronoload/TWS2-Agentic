#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识图谱增强 RAG — 参考 LightRAG 的图增强检索

核心思路（来自 LightRAG）:
  文档 → 实体关系抽取 → 知识图谱 + 向量索引 → 混合检索

四种存储（LightRAG 模式）:
  KV_STORAGE      — LLM 缓存、文本块
  VECTOR_STORAGE   — 实体/关系/块嵌入
  GRAPH_STORAGE    — 实体-关系网络
  DOC_STATUS       — 文档处理状态

两种索引:
  Index-1: 向量索引  — 快速语义检索（原有）
  Index-2: 图谱索引  — 结构化关系检索（新增）
"""
from __future__ import annotations

import json
import uuid
import sqlite3
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import threading


# ============================================================
# Knowledge Graph Structures
# ============================================================

@dataclass
class Entity:
    """知识实体"""
    entity_id: str
    name: str
    entity_type: str          # concept / method / class / file / person / tool
    description: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    source_doc: str = ""
    source_chunk: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "properties": self.properties,
            "source_doc": self.source_doc,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        return cls(**data)


@dataclass
class Relation:
    """实体关系"""
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str       # uses / depends_on / implements / extends / references
    description: str = ""
    weight: float = 1.0
    source_doc: str = ""

    def to_dict(self) -> dict:
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "description": self.description,
            "weight": self.weight,
            "source_doc": self.source_doc,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Relation":
        return cls(**data)


# ============================================================
# Graph Store (SQLite-backed)
# ============================================================

class GraphStore:
    """图存储 — 轻量级 NetworkX 替代"""

    def __init__(self, db_path: Optional[Path] = None):
        db_path = db_path or Path("data/knowledge_graph.db")
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._lock = threading.Lock()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    properties TEXT DEFAULT '{}',
                    source_doc TEXT DEFAULT '',
                    source_chunk TEXT DEFAULT '',
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relations (
                    relation_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    weight REAL DEFAULT 1.0,
                    source_doc TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES entities(entity_id),
                    FOREIGN KEY (target_id) REFERENCES entities(entity_id)
                );

                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
                CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
                CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(source_id);
                CREATE INDEX IF NOT EXISTS idx_relations_tgt ON relations(target_id);
                CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
            """)

    # ---- Entities ----

    def upsert_entity(self, entity: Entity):
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO entities
                (entity_id, name, entity_type, description, properties,
                 source_doc, source_chunk, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity.entity_id, entity.name, entity.entity_type,
                entity.description, json.dumps(entity.properties, ensure_ascii=False),
                entity.source_doc, entity.source_chunk, entity.confidence,
                datetime.now().isoformat(),
            ))

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM entities WHERE entity_id=?", (entity_id,)
            ).fetchone()
            if row:
                return Entity(
                    entity_id=row["entity_id"], name=row["name"],
                    entity_type=row["entity_type"],
                    description=row["description"] or "",
                    properties=json.loads(row["properties"] or "{}"),
                    source_doc=row["source_doc"] or "",
                    source_chunk=row["source_chunk"] or "",
                    confidence=row["confidence"],
                )
        return None

    def search_entities(self, name_fragment: str, entity_type: str = "",
                        limit: int = 20) -> List[Entity]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if entity_type:
                rows = conn.execute(
                    "SELECT * FROM entities WHERE name LIKE ? AND entity_type=? "
                    "LIMIT ?",
                    (f"%{name_fragment}%", entity_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM entities WHERE name LIKE ? LIMIT ?",
                    (f"%{name_fragment}%", limit),
                ).fetchall()
            return [Entity(
                entity_id=r["entity_id"], name=r["name"],
                entity_type=r["entity_type"],
                description=r["description"] or "",
                properties=json.loads(r["properties"] or "{}"),
                source_doc=r["source_doc"] or "",
                source_chunk=r["source_chunk"] or "",
                confidence=r["confidence"],
            ) for r in rows]

    def entity_count(self) -> int:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM entities").fetchone()
            return row[0] if row else 0

    def list_entities(self, limit: int = 100) -> List[Entity]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM entities ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [Entity(
                entity_id=r["entity_id"], name=r["name"],
                entity_type=r["entity_type"],
                description=r["description"] or "",
                properties=json.loads(r["properties"] or "{}"),
                source_doc=r["source_doc"] or "",
                source_chunk=r["source_chunk"] or "",
                confidence=r["confidence"],
            ) for r in rows]

    # ---- Relations ----

    def add_relation(self, rel: Relation):
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO relations
                (relation_id, source_id, target_id, relation_type,
                 description, weight, source_doc, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rel.relation_id, rel.source_id, rel.target_id,
                rel.relation_type, rel.description, rel.weight,
                rel.source_doc, datetime.now().isoformat(),
            ))

    def get_neighbors(self, entity_id: str, direction: str = "both",
                      relation_types: Optional[List[str]] = None) -> List[Tuple[Relation, Entity]]:
        """获取实体的邻居"""
        results = []
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            if direction in ("outgoing", "both"):
                query = "SELECT * FROM relations WHERE source_id=?"
                params = [entity_id]
                if relation_types:
                    placeholders = ",".join(["?"] * len(relation_types))
                    query += f" AND relation_type IN ({placeholders})"
                    params.extend(relation_types)
                for row in conn.execute(query, params).fetchall():
                    rel = Relation(
                        relation_id=row["relation_id"],
                        source_id=row["source_id"],
                        target_id=row["target_id"],
                        relation_type=row["relation_type"],
                        description=row["description"] or "",
                        weight=row["weight"],
                        source_doc=row["source_doc"] or "",
                    )
                    entity = self.get_entity(row["target_id"])
                    if entity:
                        results.append((rel, entity))

            if direction in ("incoming", "both"):
                query = "SELECT * FROM relations WHERE target_id=?"
                params = [entity_id]
                if relation_types:
                    placeholders = ",".join(["?"] * len(relation_types))
                    query += f" AND relation_type IN ({placeholders})"
                    params.extend(relation_types)
                for row in conn.execute(query, params).fetchall():
                    rel = Relation(
                        relation_id=row["relation_id"],
                        source_id=row["source_id"],
                        target_id=row["target_id"],
                        relation_type=row["relation_type"],
                        description=row["description"] or "",
                        weight=row["weight"],
                        source_doc=row["source_doc"] or "",
                    )
                    entity = self.get_entity(row["source_id"])
                    if entity:
                        results.append((rel, entity))

        return results

    def get_subgraph(self, entity_ids: List[str], depth: int = 2,
                     max_nodes: int = 50) -> Dict[str, Any]:
        """获取子图（BFS遍历）"""
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(eid, 0) for eid in entity_ids]
        nodes: List[Entity] = []
        edges: List[Relation] = []

        while queue and len(visited) < max_nodes:
            current_id, d = queue.pop(0)
            if current_id in visited or d > depth:
                continue
            visited.add(current_id)

            entity = self.get_entity(current_id)
            if entity:
                nodes.append(entity)

            for rel, neighbor in self.get_neighbors(current_id, "both"):
                edges.append(rel)
                if neighbor.entity_id not in visited and d < depth:
                    queue.append((neighbor.entity_id, d + 1))

        return {
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
        }

    # ---- Stats ----

    def stats(self) -> dict:
        with sqlite3.connect(str(self.db_path)) as conn:
            e_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            r_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            types = conn.execute(
                "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
            ).fetchall()
        return {
            "entities": e_count,
            "relations": r_count,
            "entity_types": {t: c for t, c in types},
        }


# ============================================================
# Knowledge Graph RAG Engine
# ============================================================

class KGRAGEngine:
    """
    知识图谱增强 RAG

    检索模式:
      vector_only  — 纯向量检索（原有）
      graph_only   — 纯图遍历
      hybrid       — 向量 + 图 融合（推荐）
      local        — 上下文相关（按实体）
      global       — 社区/摘要检索
    """

    def __init__(self, graph_store: Optional[GraphStore] = None,
                 vector_store=None, llm_call=None):
        self.graph_store = graph_store or GraphStore()
        self.vector_store = vector_store
        self.llm_call = llm_call
        self._doc_cache: Dict[str, Any] = {}

    def retrieve(self, query: str, mode: str = "hybrid",
                 top_k: int = 5, graph_depth: int = 2) -> Dict[str, Any]:
        """
        混合检索
        """
        result: Dict[str, Any] = {
            "mode": mode,
            "vector_results": [],
            "graph_results": {"nodes": [], "edges": []},
            "merged_context": "",
        }

        # 向量检索
        if mode in ("vector_only", "hybrid", "local"):
            if self.vector_store:
                try:
                    vector_results = self._vector_search(query, top_k)
                    result["vector_results"] = vector_results
                except Exception:
                    pass

        # 图检索
        if mode in ("graph_only", "hybrid", "local"):
            if self.graph_store and self.graph_store.entity_count() > 0:
                graph_results = self._graph_search(query, top_k, graph_depth)
                result["graph_results"] = graph_results

        # 合并上下文
        result["merged_context"] = self._merge_context(
            result["vector_results"],
            result["graph_results"],
        )

        return result

    def _vector_search(self, query: str, top_k: int) -> List[dict]:
        results = []
        try:
            docs = self.vector_store.similarity_search(query, k=top_k)
            for doc in docs:
                results.append({
                    "content": doc.page_content if hasattr(doc, "page_content") else str(doc),
                    "metadata": doc.metadata if hasattr(doc, "metadata") else {},
                    "score": getattr(doc, "score", 0.0),
                })
        except Exception:
            pass
        return results

    def _graph_search(self, query: str, top_k: int, depth: int) -> dict:
        # 搜索匹配的实体
        entities = self.graph_store.search_entities(query, limit=top_k)

        # 如果没有精确匹配，尝试更宽泛的搜索
        if not entities and len(query) > 3:
            entities = self.graph_store.search_entities(
                query[:len(query)//2], limit=top_k,
            )

        entity_ids = [e.entity_id for e in entities]
        subgraph = self.graph_store.get_subgraph(entity_ids, depth=depth)
        return subgraph

    def _merge_context(self, vector_results: List[dict],
                       graph_results: dict) -> str:
        parts = []

        if graph_results.get("nodes"):
            parts.append("## 知识图谱相关实体")
            for node in graph_results["nodes"][:10]:
                parts.append(
                    f"- **{node['name']}** ({node['entity_type']}): "
                    f"{node.get('description', '')[:200]}"
                )
            parts.append("")

        if vector_results:
            parts.append("## 相关文档片段")
            for i, doc in enumerate(vector_results[:5], 1):
                content = (doc.get("content") or "")[:500]
                parts.append(f"### 片段 {i}")
                parts.append(content)
                parts.append("")

        return "\n".join(parts)

    # ---- Entity Relation Extraction ----

    def extract_entities(self, text: str, source_doc: str = "",
                         source_chunk: str = "") -> List[Tuple[Entity, List[Relation]]]:
        """
        从文本中提取实体和关系（使用 LLM）

        返回: [(entity, [relations]), ...]
        """
        if not self.llm_call:
            return self._heuristic_extract(text, source_doc, source_chunk)

        prompt = f"""从以下文本中提取结构化知识（实体和关系）:

文本:
{text[:3000]}

请以 JSON 格式返回:

{{
  "entities": [
    {{
      "name": "实体名称",
      "entity_type": "concept/method/class/file/tool",
      "description": "简短描述"
    }}
  ],
  "relations": [
    {{
      "source": "源实体名称",
      "target": "目标实体名称",
      "relation_type": "uses/depends_on/implements/extends/references",
      "description": "关系描述"
    }}
  ]
}}

只返回 JSON，不要其他内容。"""

        try:
            response = self.llm_call(prompt)
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            entity_map: Dict[str, Entity] = {}
            results: List[Tuple[Entity, List[Relation]]] = []

            for e_data in data.get("entities", []):
                name = e_data["name"]
                eid = hashlib.md5(f"{source_doc}:{name}".encode()).hexdigest()[:16]
                entity = Entity(
                    entity_id=eid,
                    name=name,
                    entity_type=e_data.get("entity_type", "concept"),
                    description=e_data.get("description", ""),
                    source_doc=source_doc,
                    source_chunk=source_chunk,
                )
                entity_map[name] = entity
                results.append((entity, []))

            for r_data in data.get("relations", []):
                src_name = r_data["source"]
                tgt_name = r_data["target"]
                if src_name in entity_map and tgt_name in entity_map:
                    rel = Relation(
                        relation_id=str(uuid.uuid4())[:16],
                        source_id=entity_map[src_name].entity_id,
                        target_id=entity_map[tgt_name].entity_id,
                        relation_type=r_data.get("relation_type", "references"),
                        description=r_data.get("description", ""),
                        source_doc=source_doc,
                    )
                    # 找到对应 entity 的 tuple 并追加 relation
                    for i, (ent, rels) in enumerate(results):
                        if ent.name == src_name:
                            results[i] = (ent, rels + [rel])

            return results
        except Exception:
            return self._heuristic_extract(text, source_doc, source_chunk)

    def _heuristic_extract(self, text: str, source_doc: str,
                           source_chunk: str) -> List[Tuple[Entity, List[Relation]]]:
        """启发式实体提取（不用 LLM）"""
        import re
        results = []

        # 简单模式匹配: 大写驼峰 = 类名, snake_case = 函数/变量
        class_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9]{2,})\b')
        func_pattern = re.compile(r'\bdef\s+([a-z_][a-z0-9_]{2,})\b')
        import_pattern = re.compile(r'\b(?:from|import)\s+([a-z_][a-z0-9_.]{2,})')

        for match in class_pattern.finditer(text):
            name = match.group(1)
            eid = hashlib.md5(f"class:{name}:{source_doc}".encode()).hexdigest()[:16]
            results.append((Entity(
                entity_id=eid, name=name, entity_type="class",
                source_doc=source_doc, source_chunk=source_chunk,
            ), []))

        for match in func_pattern.finditer(text):
            name = match.group(1)
            eid = hashlib.md5(f"func:{name}:{source_doc}".encode()).hexdigest()[:16]
            results.append((Entity(
                entity_id=eid, name=name, entity_type="method",
                source_doc=source_doc, source_chunk=source_chunk,
            ), []))

        for match in import_pattern.finditer(text):
            name = match.group(1)
            eid = hashlib.md5(f"import:{name}:{source_doc}".encode()).hexdigest()[:16]
            results.append((Entity(
                entity_id=eid, name=name, entity_type="module",
                source_doc=source_doc, source_chunk=source_chunk,
            ), []))

        return results

    @staticmethod
    def _extract_json(text: str) -> str:
        """从 LLM 响应中提取 JSON"""
        import re
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        # 找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start:end + 1]
        return text

    # ---- Ingest Pipeline ----

    def ingest(self, documents: List[dict], llm_call=None):
        """
        文档摄取管道:
          分块 → 向量化 → 实体提取 → 图存储

        Args:
            documents: [{"content": "...", "source": "..."}, ...]
        """
        if llm_call:
            self.llm_call = llm_call

        for doc in documents:
            content = doc.get("content", "")
            source = doc.get("source", "")

            # 实体提取
            extractions = self.extract_entities(content, source)

            for entity, relations in extractions:
                self.graph_store.upsert_entity(entity)
                for rel in relations:
                    self.graph_store.add_relation(rel)

    def ingest_file(self, file_path: str, llm_call=None) -> int:
        """摄取单个文件，返回提取的实体数"""
        p = Path(file_path)
        if not p.exists():
            return 0
        content = p.read_text(encoding="utf-8", errors="replace")
        self.ingest([{"content": content, "source": file_path}], llm_call)
        return 1


# ============================================================
# Singleton
# ============================================================

_kg_rag: Optional[KGRAGEngine] = None
_graph_store: Optional[GraphStore] = None


def get_kg_rag(db_path: Optional[Path] = None, vector_store=None,
               llm_call=None) -> KGRAGEngine:
    global _kg_rag, _graph_store
    if _kg_rag is None:
        if db_path is None:
            db_path = Path("data/knowledge_graph.db")
        _graph_store = GraphStore(db_path)
        _kg_rag = KGRAGEngine(_graph_store, vector_store, llm_call)
    return _kg_rag


def get_graph_store(db_path: Optional[Path] = None) -> GraphStore:
    global _graph_store
    if _graph_store is None:
        _graph_store = GraphStore(db_path)
    return _graph_store


__all__ = [
    "Entity", "Relation", "GraphStore", "KGRAGEngine",
    "get_kg_rag", "get_graph_store",
]