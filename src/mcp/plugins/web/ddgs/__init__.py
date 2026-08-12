import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

WEB_SEARCH_SCHEMA = {
    "name": "web_search",
    "description": "使用 DuckDuckGo 进行网页搜索。无需 API 密钥。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询词",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果数量，默认5",
            },
        },
        "required": ["query"],
    },
}


def _check_available() -> bool:
    try:
        import ddgs  # noqa: F401
        return True
    except ImportError:
        return False


def _handle_web_search(args: dict, **kw) -> str:
    import json

    query = (args.get("query") or "").strip()
    if not query:
        return json.dumps({"success": False, "error": "query is required"})

    try:
        from ddgs import DDGS
    except ImportError:
        return json.dumps({"success": False, "error": "ddgs package not installed — run `pip install ddgs`"})

    limit = max(1, int(args.get("limit", 5)))

    try:
        web_results = []
        with DDGS() as client:
            for i, hit in enumerate(client.text(query, max_results=limit)):
                if i >= limit:
                    break
                url = str(hit.get("href") or hit.get("url") or "")
                web_results.append({
                    "title": str(hit.get("title", "")),
                    "url": url,
                    "description": str(hit.get("body", "")),
                    "position": i + 1,
                })
    except Exception as exc:
        logger.warning("DDGS search error: %s", exc)
        return json.dumps({"success": False, "error": f"DuckDuckGo search failed: {exc}"})

    logger.info("DDGS search '%s': %d results", query, len(web_results))
    return json.dumps({"success": True, "data": {"web": web_results}})


def register(ctx) -> None:
    ctx.register_tool(
        name="web_search",
        toolset="web-ddgs",
        schema=WEB_SEARCH_SCHEMA,
        handler=_handle_web_search,
        check_fn=_check_available,
        emoji="🔍",
    )
    logger.info("web-ddgs plugin registered")
