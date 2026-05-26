from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class CernAdapter(BaseAdapter):
    api_name = "cern"
    base_url = "http://opendata.cern.ch/api"

    def search(self, query: str, size: int = 10) -> ScholarResult:
        params = {"q": query, "size": size}
        return self._request("GET", f"{self.base_url}/records", params=params)

    def get_record(self, record_id: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/records/{record_id}")
