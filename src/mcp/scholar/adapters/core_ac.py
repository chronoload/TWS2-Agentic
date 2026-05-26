from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class CoreAcAdapter(BaseAdapter):
    api_name = "core_ac"
    base_url = "https://api.core.ac.uk/v3"

    def search(self, query: str, limit: int = 10) -> ScholarResult:
        params = {"q": query, "limit": limit}
        return self._request("GET", f"{self.base_url}/search/works", params=params)
