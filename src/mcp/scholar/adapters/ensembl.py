from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class EnsemblAdapter(BaseAdapter):
    api_name = "ensembl"
    base_url = "https://rest.ensembl.org"

    def get_overlap_region(self, species: str, chrom: str, start: int, end: int,
                           feature_type: str = "gene") -> ScholarResult:
        region = f"{chrom}:{start}-{end}"
        params = {"feature": feature_type}
        return self._request("GET", f"{self.base_url}/overlap/region/{species}/{region}",
                             params=params, headers={"Content-Type": "application/json"})

    def get_lookup(self, symbol: str, species: str = "human") -> ScholarResult:
        params = {"symbol": symbol, "species": species}
        return self._request("GET", f"{self.base_url}/lookup/symbol/{species}/{symbol}",
                             headers={"Content-Type": "application/json"})

    def get_sequence(self, region: str, species: str = "human") -> ScholarResult:
        return self._request("GET", f"{self.base_url}/sequence/region/{species}/{region}",
                             headers={"Content-Type": "text/plain"})
