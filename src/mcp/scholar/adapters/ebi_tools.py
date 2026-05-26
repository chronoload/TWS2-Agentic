import json as _json
from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class EbiToolsAdapter(BaseAdapter):
    api_name = "ebi_tools"
    base_url = "https://www.ebi.ac.uk/Tools/services/rest/clustalo"

    def submit_alignment(self, sequences: str) -> ScholarResult:
        data = {
            "sequence": sequences,
            "format": "fasta",
        }
        encoded = _json.dumps(data)
        return self._request("POST", f"{self.base_url}/run",
                             headers={"Content-Type": "application/json", "Accept": "text/plain"},
                             use_cache=False)

    def get_status(self, job_id: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/status/{job_id}",
                             headers={"Accept": "text/plain"})

    def get_result(self, job_id: str, result_type: str = "aln-clustal") -> ScholarResult:
        return self._request("GET", f"{self.base_url}/result/{job_id}/{result_type}",
                             headers={"Accept": "text/plain"})
