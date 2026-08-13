import json
import logging

logger = logging.getLogger(__name__)

ARXIV_SEARCH_SCHEMA = {
    "name": "arxiv_search",
    "description": "搜索 ArXiv 学术论文。返回标题、作者、摘要、链接。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，支持关键词、作者、arXiv ID",
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数，默认5",
            },
            "sort_by": {
                "type": "string",
                "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                "description": "排序方式，默认relevance",
            },
        },
        "required": ["query"],
    },
}


def _check_available() -> bool:
    try:
        import arxiv  # noqa: F401
        return True
    except ImportError:
        return False


def _handle_arxiv_search(args: dict, **kw) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return json.dumps({"success": False, "error": "query is required"})

    try:
        import arxiv
    except ImportError:
        return json.dumps({"success": False, "error": "arxiv package not installed — run `pip install arxiv`"})

    max_results = max(1, int(args.get("max_results", 5)))
    sort_by_str = args.get("sort_by", "relevance")

    sort_map = {
        "relevance": arxiv.SortCriterion.Relevance,
        "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
        "submittedDate": arxiv.SortCriterion.SubmittedDate,
    }
    sort_criterion = sort_map.get(sort_by_str, arxiv.SortCriterion.Relevance)

    try:
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_criterion,
        )
        results = []
        for paper in search.results():
            authors = [a.name for a in paper.authors]
            results.append({
                "title": paper.title,
                "authors": authors,
                "summary": paper.summary[:500] if paper.summary else "",
                "published": paper.published.isoformat() if paper.published else "",
                "updated": paper.updated.isoformat() if paper.updated else "",
                "arxiv_id": paper.entry_id.split("/")[-1] if paper.entry_id else "",
                "url": paper.entry_id,
                "pdf_url": paper.pdf_url,
                "categories": paper.categories if hasattr(paper, "categories") else [],
                "comment": paper.comment or "",
            })
    except Exception as exc:
        logger.warning("ArXiv search error: %s", exc)
        return json.dumps({"success": False, "error": f"ArXiv search failed: {exc}"})

    logger.info("ArXiv search '%s': %d results", query, len(results))
    return json.dumps({"success": True, "results": results, "count": len(results)})


def register(ctx) -> None:
    ctx.register_tool(
        name="arxiv_search",
        toolset="arxiv-search",
        schema=ARXIV_SEARCH_SCHEMA,
        handler=_handle_arxiv_search,
        check_fn=_check_available,
        emoji="📄",
    )
    logger.info("arxiv-search plugin registered")
