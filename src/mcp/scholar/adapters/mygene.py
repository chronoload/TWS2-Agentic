from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class MyGeneAdapter(BaseAdapter):
    api_name = "mygene"
    base_url = "https://mygene.info/v3"

    def query(self, q: str, size: int = 10) -> ScholarResult:
        params = {"q": q, "size": size}
        return self._request("GET", f"{self.base_url}/query", params=params)

    def get_gene(self, geneid: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/gene/{geneid}")
