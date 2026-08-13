import json
import logging
import re
from typing import Any, Dict
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

BRAVE_SEARCH_SCHEMA = {
    "name": "brave_search",
    "description": "使用 Brave Search 进行网页搜索（免费，无需API密钥）。",
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
        import httpx  # noqa: F401
        return True
    except ImportError:
        return False


def _handle_brave_search(args: dict, **kw) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return json.dumps({"success": False, "error": "query is required"})

    try:
        import httpx
    except ImportError:
        return json.dumps({"success": False, "error": "httpx package not installed — run `pip install httpx`"})

    limit = max(1, int(args.get("limit", 5)))

    try:
        url = f"https://search.brave.com/search?q={quote_plus(query)}&format=json"
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)

        if response.status_code != 200:
            return json.dumps({"success": False, "error": f"Brave search returned status {response.status_code}"})

        data = response.json()
        results = []

        web_results = data.get("web", {}).get("results", [])
        for i, hit in enumerate(web_results[:limit]):
            results.append({
                "title": str(hit.get("title", "")),
                "url": str(hit.get("url", "")),
                "description": str(hit.get("description", "")),
                "position": i + 1,
            })

    except Exception as exc:
        logger.warning("Brave search error: %s", exc)
        return json.dumps({"success": False, "error": f"Brave search failed: {exc}"})

    logger.info("Brave search '%s': %d results", query, len(results))
    return json.dumps({"success": True, "data": {"web": results}})


def register(ctx) -> None:
    ctx.register_tool(
        name="brave_search",
        toolset="brave-free-search",
        schema=BRAVE_SEARCH_SCHEMA,
        handler=_handle_brave_search,
        check_fn=_check_available,
        emoji="🦁",
    )
    logger.info("brave-free-search plugin registered")
