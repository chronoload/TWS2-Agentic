from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class ArxivAdapter(BaseAdapter):
    api_name = "arxiv"
    base_url = "http://export.arxiv.org/api"

    def search(self, query: str, max_results: int = 5, category: Optional[str] = None) -> ScholarResult:
        search_query = query
        if category:
            search_query = f"cat:{category} AND ti:{query}"
        params = {"search_query": search_query, "max_results": max_results, "sortBy": "submittedDate"}
        return self._request("GET", f"{self.base_url}/query", params=params,
                             headers={"Accept": "application/xml"})

    def fetch_by_category(self, category: str, limit: int = 5) -> ScholarResult:
        params = {"search_query": f"cat:{category}", "max_results": limit, "sortBy": "submittedDate"}
        return self._request("GET", f"{self.base_url}/query", params=params,
                             headers={"Accept": "application/xml"})
