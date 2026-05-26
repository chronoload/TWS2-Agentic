from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class ChinadoiAdapter(BaseAdapter):
    api_name = "chinadoi"
    base_url = "https://doi.cnki.net"

    def resolve(self, doi: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/doi/{doi}",
                             headers={"Accept": "application/json"})

    def search(self, query: str, limit: int = 10) -> ScholarResult:
        params = {"q": query, "limit": limit}
        return self._request("GET", f"{self.base_url}/search", params=params,
                             headers={"Accept": "application/json"})
