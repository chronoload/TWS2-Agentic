from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class OpenAlexAdapter(BaseAdapter):
    api_name = "openalex"
    base_url = "https://api.openalex.org"

    def search(self, query: str, per_page: int = 10) -> ScholarResult:
        params = {"search": query, "per_page": per_page}
        return self._request("GET", f"{self.base_url}/works", params=params)

    def get_by_doi(self, doi: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/works/doi:{doi}")
