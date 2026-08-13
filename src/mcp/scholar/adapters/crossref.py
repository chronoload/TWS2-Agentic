import urllib.parse
from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class CrossrefAdapter(BaseAdapter):
    api_name = "crossref"
    base_url = "https://api.crossref.org"

    def search(self, query: str, rows: int = 10) -> ScholarResult:
        params = {"query": query, "rows": rows}
        return self._request("GET", f"{self.base_url}/works", params=params)

    def get_by_doi(self, doi: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/works/{urllib.parse.quote(doi, safe='')}")
