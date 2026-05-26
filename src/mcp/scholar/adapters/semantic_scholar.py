from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class SemanticScholarAdapter(BaseAdapter):
    api_name = "semantic_scholar"
    base_url = "https://api.semanticscholar.org/graph/v1"

    def get_by_doi(self, doi: str) -> ScholarResult:
        params = {"fields": "title,authors,year,abstract,citationCount,referenceCount,openAccessPdf,url"}
        return self._request("GET", f"{self.base_url}/paper/DOI:{doi}", params=params)

    def search(self, query: str, limit: int = 10) -> ScholarResult:
        params = {"query": query, "limit": limit,
                  "fields": "title,authors,year,abstract,citationCount,openAccessPdf"}
        return self._request("GET", f"{self.base_url}/paper/search", params=params)
