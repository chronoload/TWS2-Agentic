from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class UniprotAdapter(BaseAdapter):
    api_name = "uniprot"
    base_url = "https://rest.uniprot.org/uniprotkb"

    def search(self, query: str, size: int = 10) -> ScholarResult:
        params = {"query": query, "size": size, "format": "json"}
        return self._request("GET", f"{self.base_url}/search", params=params)

    def get_entry(self, accession: str) -> ScholarResult:
        params = {"format": "json"}
        return self._request("GET", f"{self.base_url}/{accession}", params=params)
