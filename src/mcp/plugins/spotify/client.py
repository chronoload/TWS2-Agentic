import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

logger = logging.getLogger(__name__)


class SpotifyError(RuntimeError):
    pass


class SpotifyAuthRequiredError(SpotifyError):
    pass


class SpotifyAPIError(SpotifyError):
    def __init__(self, message: str, *, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.path = None


class SpotifyClient:
    BASE_URL = "https://api.spotify.com/v1"

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, *, params=None, json_body=None,
                allow_retry_on_401: bool = True, empty_response=None) -> Any:
        if not _HAS_HTTPX:
            raise SpotifyError("httpx package is required — run `pip install httpx`")

        url = f"{self.BASE_URL}{path}"
        response = httpx.request(
            method, url, headers=self._headers(),
            params=_strip_none(params) if params else None,
            json=_strip_none(json_body) if json_body else None,
            timeout=30.0,
        )

        if response.status_code == 401 and allow_retry_on_401:
            raise SpotifyAuthRequiredError("Spotify access token expired or invalid. Set a new SPOTIFY_ACCESS_TOKEN.")

        if response.status_code >= 400:
            self._raise_api_error(response, method=method, path=path)

        if response.status_code == 204 or not response.content:
            return empty_response or {"success": True, "status_code": response.status_code, "empty": True}

        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return {"success": True, "text": response.text}

    def _raise_api_error(self, response, *, method: str, path: str):
        detail = response.text.strip()
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error_obj = payload.get("error")
                if isinstance(error_obj, dict):
                    detail = str(error_obj.get("message") or detail)
                elif isinstance(error_obj, str):
                    detail = error_obj
        except Exception:
            pass
        error = SpotifyAPIError(detail, status_code=response.status_code, response_body=response.text.strip())
        error.path = path
        raise error

    def get_devices(self) -> Any:
        return self.request("GET", "/me/player/devices")

    def transfer_playback(self, *, device_id: str, play: bool = False) -> Any:
        return self.request("PUT", "/me/player", json_body={"device_ids": [device_id], "play": play})

    def get_playback_state(self, *, market=None) -> Any:
        return self.request("GET", "/me/player", params={"market": market},
                           empty_response={"status_code": 204, "empty": True, "message": "No active playback."})

    def get_currently_playing(self, *, market=None) -> Any:
        return self.request("GET", "/me/player/currently-playing", params={"market": market},
                           empty_response={"status_code": 204, "empty": True, "message": "Nothing playing."})

    def start_playback(self, *, device_id=None, context_uri=None, uris=None, offset=None, position_ms=None) -> Any:
        return self.request("PUT", "/me/player/play", params={"device_id": device_id},
                           json_body={"context_uri": context_uri, "uris": uris, "offset": offset, "position_ms": position_ms})

    def pause_playback(self, *, device_id=None) -> Any:
        return self.request("PUT", "/me/player/pause", params={"device_id": device_id})

    def skip_next(self, *, device_id=None) -> Any:
        return self.request("POST", "/me/player/next", params={"device_id": device_id})

    def skip_previous(self, *, device_id=None) -> Any:
        return self.request("POST", "/me/player/previous", params={"device_id": device_id})

    def seek(self, *, position_ms: int, device_id=None) -> Any:
        return self.request("PUT", "/me/player/seek", params={"position_ms": position_ms, "device_id": device_id})

    def set_repeat(self, *, state: str, device_id=None) -> Any:
        return self.request("PUT", "/me/player/repeat", params={"state": state, "device_id": device_id})

    def set_shuffle(self, *, state: bool, device_id=None) -> Any:
        return self.request("PUT", "/me/player/shuffle", params={"state": str(bool(state)).lower(), "device_id": device_id})

    def set_volume(self, *, volume_percent: int, device_id=None) -> Any:
        return self.request("PUT", "/me/player/volume", params={"volume_percent": volume_percent, "device_id": device_id})

    def get_queue(self) -> Any:
        return self.request("GET", "/me/player/queue")

    def add_to_queue(self, *, uri: str, device_id=None) -> Any:
        return self.request("POST", "/me/player/queue", params={"uri": uri, "device_id": device_id})

    def search(self, *, query: str, search_types: list, limit: int = 10, offset: int = 0,
               market=None, include_external=None) -> Any:
        return self.request("GET", "/search", params={
            "q": query, "type": ",".join(search_types), "limit": limit,
            "offset": offset, "market": market, "include_external": include_external,
        })

    def get_my_playlists(self, *, limit: int = 20, offset: int = 0) -> Any:
        return self.request("GET", "/me/playlists", params={"limit": limit, "offset": offset})

    def get_playlist(self, *, playlist_id: str, market=None) -> Any:
        return self.request("GET", f"/playlists/{playlist_id}", params={"market": market})

    def create_playlist(self, *, name: str, public: bool = False, collaborative: bool = False, description=None) -> Any:
        return self.request("POST", "/me/playlists", json_body={
            "name": name, "public": public, "collaborative": collaborative, "description": description,
        })

    def add_playlist_items(self, *, playlist_id: str, uris: list, position=None) -> Any:
        return self.request("POST", f"/playlists/{playlist_id}/items", json_body={"uris": uris, "position": position})

    def remove_playlist_items(self, *, playlist_id: str, uris: list, snapshot_id=None) -> Any:
        return self.request("DELETE", f"/playlists/{playlist_id}/items",
                           json_body={"items": [{"uri": uri} for uri in uris], "snapshot_id": snapshot_id})

    def update_playlist_details(self, *, playlist_id: str, name=None, public=None, collaborative=None, description=None) -> Any:
        return self.request("PUT", f"/playlists/{playlist_id}", json_body={
            "name": name, "public": public, "collaborative": collaborative, "description": description,
        })

    def get_album(self, *, album_id: str, market=None) -> Any:
        return self.request("GET", f"/albums/{album_id}", params={"market": market})

    def get_album_tracks(self, *, album_id: str, limit: int = 20, offset: int = 0, market=None) -> Any:
        return self.request("GET", f"/albums/{album_id}/tracks",
                           params={"limit": limit, "offset": offset, "market": market})

    def get_saved_tracks(self, *, limit: int = 20, offset: int = 0, market=None) -> Any:
        return self.request("GET", "/me/tracks", params={"limit": limit, "offset": offset, "market": market})

    def save_library_items(self, *, uris: list) -> Any:
        return self.request("PUT", "/me/library", params={"uris": ",".join(uris)})

    def get_saved_albums(self, *, limit: int = 20, offset: int = 0, market=None) -> Any:
        return self.request("GET", "/me/albums", params={"limit": limit, "offset": offset, "market": market})

    def remove_saved_tracks(self, *, track_ids: list) -> Any:
        uris = [f"spotify:track:{tid}" for tid in track_ids]
        return self.request("DELETE", "/me/library", params={"uris": ",".join(uris)})

    def remove_saved_albums(self, *, album_ids: list) -> Any:
        uris = [f"spotify:album:{aid}" for aid in album_ids]
        return self.request("DELETE", "/me/library", params={"uris": ",".join(uris)})

    def get_recently_played(self, *, limit: int = 20, after=None, before=None) -> Any:
        return self.request("GET", "/me/player/recently-played",
                           params={"limit": limit, "after": after, "before": before})


def _strip_none(payload):
    if not payload:
        return {}
    return {k: v for k, v in payload.items() if v is not None}


def normalize_spotify_id(value: str, expected_type=None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise SpotifyError("Spotify id/uri/url is required.")
    if cleaned.startswith("spotify:"):
        parts = cleaned.split(":")
        if len(parts) >= 3:
            return parts[2]
    if "open.spotify.com" in cleaned:
        parsed = urlparse(cleaned)
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) >= 2:
            return path_parts[1]
    return cleaned


def normalize_spotify_uri(value: str, expected_type=None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise SpotifyError("Spotify URI required.")
    if cleaned.startswith("spotify:"):
        return cleaned
    item_id = normalize_spotify_id(cleaned, expected_type)
    if expected_type:
        return f"spotify:{expected_type}:{item_id}"
    return cleaned
