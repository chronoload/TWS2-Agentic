from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class MyVariantAdapter(BaseAdapter):
    api_name = "myvariant"
    base_url = "https://myvariant.info/v1"

    def query(self, q: str, size: int = 10) -> ScholarResult:
        params = {"q": q, "size": size}
        return self._request("GET", f"{self.base_url}/query", params=params)

    def get_variant(self, variant_id: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/variant/{variant_id}")
