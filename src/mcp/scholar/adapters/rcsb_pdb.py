from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class RcsbPdbAdapter(BaseAdapter):
    api_name = "rcsb_pdb"
    base_url = "https://data.rcsb.org/rest/v1/core"

    def get_entry(self, pdb_id: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/entry/{pdb_id.upper()}")

    def get_pubmed(self, pdb_id: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/pubmed/{pdb_id.upper()}")

    def search(self, query: str, rows: int = 10) -> ScholarResult:
        import json as _json
        search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
        search_body = _json.dumps({
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {"value": query, "attribute": "rcsb_entry_container_info.title"}
            },
            "return_type": "entry",
            "request_options": {"pager": {"start": 0, "rows": rows}},
            "request_info": {"src": "ui"}
        })
        return self._request("POST", search_url,
                             headers={"Content-Type": "application/json"},
                             use_cache=False)
