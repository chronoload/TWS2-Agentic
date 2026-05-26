from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class EuropePmcAdapter(BaseAdapter):
    api_name = "europe_pmc"
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    def search(self, query: str, pageSize: int = 10) -> ScholarResult:
        params = {"query": query, "pageSize": pageSize, "format": "json"}
        return self._request("GET", f"{self.base_url}/search", params=params)

    def get_by_pmid(self, pmid: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/search", params={"query": f"EXT_ID:{pmid}", "format": "json"})
