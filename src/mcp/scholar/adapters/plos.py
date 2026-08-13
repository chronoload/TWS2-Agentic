from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class PlosAdapter(BaseAdapter):
    api_name = "plos"
    base_url = "http://api.plos.org/search"

    def search(self, query: str, rows: int = 10) -> ScholarResult:
        params = {"q": query, "rows": rows, "wt": "json"}
        return self._request("GET", self.base_url, params=params)
