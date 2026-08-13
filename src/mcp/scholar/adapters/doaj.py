import urllib.parse
from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class DoajAdapter(BaseAdapter):
    api_name = "doaj"
    base_url = "https://doaj.org/api/search/articles"

    def search(self, query: str, pageSize: int = 10) -> ScholarResult:
        params = {"q": query, "pageSize": pageSize}
        return self._request("GET", f"{self.base_url}/{urllib.parse.quote(query)}", params={"pageSize": pageSize})
