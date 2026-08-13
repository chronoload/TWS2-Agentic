from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class UnpaywallAdapter(BaseAdapter):
    api_name = "unpaywall"
    base_url = "https://api.unpaywall.org/v2"

    def get_oa_status(self, doi: str) -> ScholarResult:
        params = {"email": "scholar-mcp@example.com"}
        return self._request("GET", f"{self.base_url}/{doi}", params=params)
