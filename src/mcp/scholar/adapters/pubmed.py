from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class PubMedAdapter(BaseAdapter):
    api_name = "pubmed"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def search(self, query: str, max_results: int = 10) -> ScholarResult:
        params = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
        return self._request("GET", f"{self.base_url}/esearch.fcgi", params=params)

    def fetch_details(self, pmid: str) -> ScholarResult:
        params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
        return self._request("GET", f"{self.base_url}/efetch.fcgi", params=params)
