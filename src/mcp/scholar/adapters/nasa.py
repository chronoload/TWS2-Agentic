from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class NasaAdapter(BaseAdapter):
    api_name = "nasa"
    base_url = "https://api.nasa.gov"

    def search(self, query: str, media_type: str = "image") -> ScholarResult:
        params = {"q": query, "media_type": media_type}
        return self._request("GET", f"{self.base_url}/search", params=params)

    def apod(self, date: Optional[str] = None) -> ScholarResult:
        params = {}
        if date:
            params["date"] = date
        return self._request("GET", f"{self.base_url}/planetary/apod", params=params)
