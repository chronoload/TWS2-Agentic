from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class NgdcAdapter(BaseAdapter):
    api_name = "ngdc"
    base_url = "https://ngdc.cncb.ac.cn/api"

    def search(self, database: str, query: str, limit: int = 10) -> ScholarResult:
        params = {"q": query, "limit": limit}
        return self._request("GET", f"{self.base_url}/{database}", params=params,
                             headers={"Accept": "application/json"})

    def get_record(self, database: str, accession: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/{database}/{accession}",
                             headers={"Accept": "application/json"})
