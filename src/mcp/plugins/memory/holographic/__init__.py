import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from .store import MemoryStore
from .retrieval import FactRetriever

logger = logging.getLogger(__name__)

FACT_STORE_SCHEMA = {
    "name": "fact_store",
    "description": (
        "深度结构化记忆，支持代数推理。"
        "ACTIONS:\n"
        "• add — 存储一个事实\n"
        "• search — 关键词搜索\n"
        "• probe — 实体探查：某个人/物的所有事实\n"
        "• related — 与实体结构关联的事实\n"
        "• reason — 组合查询：同时关联多个实体的事实\n"
        "• contradict — 矛盾检测：发现冲突的事实\n"
        "• update/remove/list — CRUD操作\n\n"
        "重要：回答关于用户的问题前，务必先 probe 或 reason。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "search", "probe", "related", "reason", "contradict", "update", "remove", "list"],
            },
            "content": {"type": "string", "description": "事实内容 (add 必填)"},
            "query": {"type": "string", "description": "搜索查询 (search 必填)"},
            "entity": {"type": "string", "description": "实体名称 (probe/related)"},
            "entities": {"type": "array", "items": {"type": "string"}, "description": "实体列表 (reason)"},
            "fact_id": {"type": "integer", "description": "事实ID (update/remove)"},
            "category": {"type": "string", "enum": ["user_pref", "project", "tool", "general"]},
            "tags": {"type": "string", "description": "逗号分隔标签"},
            "trust_delta": {"type": "number", "description": "信任度调整 (update)"},
            "min_trust": {"type": "number", "description": "最低信任度过滤 (默认0.3)"},
            "limit": {"type": "integer", "description": "最大结果数 (默认10)"},
        },
        "required": ["action"],
    },
}

FACT_FEEDBACK_SCHEMA = {
    "name": "fact_feedback",
    "description": "评价一个事实：helpful=准确，unhelpful=过时。训练记忆系统——好的上升，坏的下降。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["helpful", "unhelpful"]},
            "fact_id": {"type": "integer", "description": "要评价的事实ID"},
        },
        "required": ["action", "fact_id"],
    },
}

_DEFAULT_DB = str(Path.cwd() / ".ts2_data" / "memory_store.db")


class HolographicMemoryPlugin:
    def __init__(self, db_path: str = _DEFAULT_DB, default_trust: float = 0.5,
                 hrr_dim: int = 1024, min_trust_threshold: float = 0.3,
                 temporal_decay_half_life: int = 0):
        self._db_path = db_path
        self._default_trust = default_trust
        self._hrr_dim = hrr_dim
        self._min_trust = min_trust_threshold
        self._half_life = temporal_decay_half_life
        self._store: MemoryStore = None
        self._retriever: FactRetriever = None

    def initialize(self) -> None:
        self._store = MemoryStore(
            db_path=self._db_path,
            default_trust=self._default_trust,
            hrr_dim=self._hrr_dim,
        )
        self._retriever = FactRetriever(
            store=self._store,
            temporal_decay_half_life=self._half_life,
            hrr_dim=self._hrr_dim,
        )

    def _ensure_initialized(self) -> None:
        if self._store is None:
            self.initialize()

    def handle_fact_store(self, args: dict, **kw) -> str:
        self._ensure_initialized()
        try:
            action = args["action"]
            store = self._store
            retriever = self._retriever

            if action == "add":
                fact_id = store.add_fact(
                    args["content"],
                    category=args.get("category", "general"),
                    tags=args.get("tags", ""),
                )
                return json.dumps({"fact_id": fact_id, "status": "added"})

            elif action == "search":
                results = retriever.search(
                    args["query"],
                    category=args.get("category"),
                    min_trust=float(args.get("min_trust", self._min_trust)),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "probe":
                results = retriever.probe(
                    args["entity"],
                    category=args.get("category"),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "related":
                results = retriever.related(
                    args["entity"],
                    category=args.get("category"),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "reason":
                entities = args.get("entities", [])
                if not entities:
                    return json.dumps({"success": False, "error": "reason requires 'entities' list"})
                results = retriever.reason(
                    entities,
                    category=args.get("category"),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "contradict":
                results = retriever.contradict(
                    category=args.get("category"),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"results": results, "count": len(results)})

            elif action == "update":
                updated = store.update_fact(
                    int(args["fact_id"]),
                    content=args.get("content"),
                    trust_delta=float(args["trust_delta"]) if "trust_delta" in args else None,
                    tags=args.get("tags"),
                    category=args.get("category"),
                )
                return json.dumps({"updated": updated})

            elif action == "remove":
                removed = store.remove_fact(int(args["fact_id"]))
                return json.dumps({"removed": removed})

            elif action == "list":
                facts = store.list_facts(
                    category=args.get("category"),
                    min_trust=float(args.get("min_trust", 0.0)),
                    limit=int(args.get("limit", 10)),
                )
                return json.dumps({"facts": facts, "count": len(facts)})

            else:
                return json.dumps({"success": False, "error": f"Unknown action: {action}"})

        except KeyError as exc:
            return json.dumps({"success": False, "error": f"Missing required argument: {exc}"})
        except Exception as exc:
            return json.dumps({"success": False, "error": str(exc)})

    def handle_fact_feedback(self, args: dict, **kw) -> str:
        self._ensure_initialized()
        try:
            fact_id = int(args["fact_id"])
            helpful = args["action"] == "helpful"
            result = self._store.record_feedback(fact_id, helpful=helpful)
            return json.dumps(result)
        except KeyError as exc:
            return json.dumps({"success": False, "error": f"Missing required argument: {exc}"})
        except Exception as exc:
            return json.dumps({"success": False, "error": str(exc)})


_plugin: HolographicMemoryPlugin = None


def _get_plugin() -> HolographicMemoryPlugin:
    global _plugin
    if _plugin is None:
        _plugin = HolographicMemoryPlugin()
        _plugin.initialize()
    return _plugin


def _handle_fact_store(args: dict, **kw) -> str:
    return _get_plugin().handle_fact_store(args, **kw)


def _handle_fact_feedback(args: dict, **kw) -> str:
    return _get_plugin().handle_fact_feedback(args, **kw)


def _check_available() -> bool:
    return True


def register(ctx) -> None:
    ctx.register_tool(
        name="fact_store",
        toolset="holographic-memory",
        schema=FACT_STORE_SCHEMA,
        handler=_handle_fact_store,
        check_fn=_check_available,
        emoji="🧠",
    )
    ctx.register_tool(
        name="fact_feedback",
        toolset="holographic-memory",
        schema=FACT_FEEDBACK_SCHEMA,
        handler=_handle_fact_feedback,
        check_fn=_check_available,
        emoji="👍",
    )
    logger.info("holographic-memory plugin registered")
