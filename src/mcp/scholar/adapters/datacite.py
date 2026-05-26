from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class DataCiteAdapter(BaseAdapter):
    api_name = "datacite"
    base_url = "https://api.datacite.org"

    def resolve(self, doi: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/dois/{doi}")

    def search(self, query: str, pageSize: int = 10) -> ScholarResult:
        params = {"query": query, "page[size]": pageSize}
        return self._request("GET", f"{self.base_url}/dois", params=params)
