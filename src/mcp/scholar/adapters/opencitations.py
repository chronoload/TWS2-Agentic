from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class OpenCitationsAdapter(BaseAdapter):
    api_name = "opencitations"
    base_url = "https://opencitations.net/index/coci/api/v1"

    def get_citations(self, doi: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/citations/{doi}")

    def get_references(self, doi: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/references/{doi}")
