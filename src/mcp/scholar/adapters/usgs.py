from typing import Optional, Dict
from .base import BaseAdapter, ScholarResult


class UsgsAdapter(BaseAdapter):
    api_name = "usgs"
    base_url = "https://earthquake.usgs.gov/fdsnws/event/1"

    def get_earthquakes(self, min_magnitude: float = 2.5, limit: int = 10,
                        starttime: Optional[str] = None, endtime: Optional[str] = None) -> ScholarResult:
        params = {"format": "geojson", "minmagnitude": min_magnitude, "limit": limit}
        if starttime:
            params["starttime"] = starttime
        if endtime:
            params["endtime"] = endtime
        return self._request("GET", f"{self.base_url}/query", params=params)

    def get_event(self, event_id: str) -> ScholarResult:
        return self._request("GET", f"{self.base_url}/query",
                             params={"eventid": event_id, "format": "geojson"})
