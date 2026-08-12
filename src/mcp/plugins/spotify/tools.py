import json
import logging
import os
from typing import Any, Dict, List

from .client import SpotifyClient, SpotifyError, SpotifyAuthRequiredError, SpotifyAPIError, normalize_spotify_id, normalize_spotify_uri

logger = logging.getLogger(__name__)


def _check_spotify_available() -> bool:
    return bool(os.environ.get("SPOTIFY_ACCESS_TOKEN"))


def _spotify_client() -> SpotifyClient:
    token = os.environ.get("SPOTIFY_ACCESS_TOKEN")
    if not token:
        raise SpotifyAuthRequiredError("SPOTIFY_ACCESS_TOKEN not set")
    return SpotifyClient(token)


def _tool_result(data) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False)


def _tool_error(msg: str) -> str:
    return json.dumps({"success": False, "error": msg})


def _coerce_limit(raw, default=20, minimum=1, maximum=50) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _coerce_bool(raw, default=False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        cleaned = raw.strip().lower()
        if cleaned in {"1", "true", "yes", "on"}:
            return True
        if cleaned in {"0", "false", "no", "off"}:
            return False
    return default


def _as_list(raw) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [str(raw).strip()] if str(raw).strip() else []


def _handle_spotify_playback(args: dict, **kw) -> str:
    action = str(args.get("action") or "get_state").strip().lower()
    try:
        client = _spotify_client()
        if action == "get_state":
            return _tool_result(client.get_playback_state(market=args.get("market")))
        if action == "get_currently_playing":
            return _tool_result(client.get_currently_playing(market=args.get("market")))
        if action == "play":
            uris = [normalize_spotify_uri(u, "track") for u in _as_list(args.get("uris"))] if args.get("uris") else None
            context_uri = normalize_spotify_uri(args["context_uri"]) if args.get("context_uri") else None
            return _tool_result(client.start_playback(
                device_id=args.get("device_id"), context_uri=context_uri,
                uris=uris, offset=args.get("offset"), position_ms=args.get("position_ms")))
        if action == "pause":
            return _tool_result(client.pause_playback(device_id=args.get("device_id")))
        if action == "next":
            return _tool_result(client.skip_next(device_id=args.get("device_id")))
        if action == "previous":
            return _tool_result(client.skip_previous(device_id=args.get("device_id")))
        if action == "seek":
            if args.get("position_ms") is None:
                return _tool_error("position_ms required for seek")
            return _tool_result(client.seek(position_ms=int(args["position_ms"]), device_id=args.get("device_id")))
        if action == "set_repeat":
            state = str(args.get("state") or "").strip().lower()
            if state not in {"track", "context", "off"}:
                return _tool_error("state must be track/context/off")
            return _tool_result(client.set_repeat(state=state, device_id=args.get("device_id")))
        if action == "set_shuffle":
            return _tool_result(client.set_shuffle(state=_coerce_bool(args.get("state")), device_id=args.get("device_id")))
        if action == "set_volume":
            if args.get("volume_percent") is None:
                return _tool_error("volume_percent required")
            return _tool_result(client.set_volume(volume_percent=max(0, min(100, int(args["volume_percent"]))), device_id=args.get("device_id")))
        if action == "recently_played":
            return _tool_result(client.get_recently_played(limit=_coerce_limit(args.get("limit"), default=20)))
        return _tool_error(f"Unknown action: {action}")
    except SpotifyAuthRequiredError as exc:
        return _tool_error(str(exc))
    except SpotifyAPIError as exc:
        return _tool_error(f"Spotify API error ({exc.status_code}): {exc}")
    except Exception as exc:
        return _tool_error(f"Spotify error: {exc}")


def _handle_spotify_devices(args: dict, **kw) -> str:
    action = str(args.get("action") or "list").strip().lower()
    try:
        client = _spotify_client()
        if action == "list":
            return _tool_result(client.get_devices())
        if action == "transfer":
            device_id = str(args.get("device_id") or "").strip()
            if not device_id:
                return _tool_error("device_id required for transfer")
            return _tool_result(client.transfer_playback(device_id=device_id, play=_coerce_bool(args.get("play"))))
        return _tool_error(f"Unknown action: {action}")
    except Exception as exc:
        return _tool_error(str(exc))


def _handle_spotify_queue(args: dict, **kw) -> str:
    action = str(args.get("action") or "get").strip().lower()
    try:
        client = _spotify_client()
        if action == "get":
            return _tool_result(client.get_queue())
        if action == "add":
            uri = normalize_spotify_uri(str(args.get("uri") or ""))
            return _tool_result(client.add_to_queue(uri=uri, device_id=args.get("device_id")))
        return _tool_error(f"Unknown action: {action}")
    except Exception as exc:
        return _tool_error(str(exc))


def _handle_spotify_search(args: dict, **kw) -> str:
    try:
        client = _spotify_client()
        query = str(args.get("query") or "").strip()
        if not query:
            return _tool_error("query required")
        raw_types = _as_list(args.get("types") or args.get("type") or ["track"])
        search_types = [t.lower() for t in raw_types if t.lower() in {"album", "artist", "playlist", "track", "show", "episode", "audiobook"}]
        if not search_types:
            return _tool_error("types must contain valid Spotify types")
        return _tool_result(client.search(
            query=query, search_types=search_types,
            limit=_coerce_limit(args.get("limit"), default=10),
            offset=max(0, int(args.get("offset") or 0)),
            market=args.get("market")))
    except Exception as exc:
        return _tool_error(str(exc))


def _handle_spotify_playlists(args: dict, **kw) -> str:
    action = str(args.get("action") or "list").strip().lower()
    try:
        client = _spotify_client()
        if action == "list":
            return _tool_result(client.get_my_playlists(limit=_coerce_limit(args.get("limit")), offset=max(0, int(args.get("offset") or 0))))
        if action == "get":
            playlist_id = normalize_spotify_id(str(args.get("playlist_id") or ""), "playlist")
            return _tool_result(client.get_playlist(playlist_id=playlist_id, market=args.get("market")))
        if action == "create":
            name = str(args.get("name") or "").strip()
            if not name:
                return _tool_error("name required for create")
            return _tool_result(client.create_playlist(name=name, public=_coerce_bool(args.get("public")),
                                                        collaborative=_coerce_bool(args.get("collaborative")),
                                                        description=args.get("description")))
        if action == "add_items":
            playlist_id = normalize_spotify_id(str(args.get("playlist_id") or ""), "playlist")
            uris = [normalize_spotify_uri(u) for u in _as_list(args.get("uris"))]
            return _tool_result(client.add_playlist_items(playlist_id=playlist_id, uris=uris, position=args.get("position")))
        if action == "remove_items":
            playlist_id = normalize_spotify_id(str(args.get("playlist_id") or ""), "playlist")
            uris = [normalize_spotify_uri(u) for u in _as_list(args.get("uris"))]
            return _tool_result(client.remove_playlist_items(playlist_id=playlist_id, uris=uris, snapshot_id=args.get("snapshot_id")))
        return _tool_error(f"Unknown action: {action}")
    except Exception as exc:
        return _tool_error(str(exc))


def _handle_spotify_albums(args: dict, **kw) -> str:
    action = str(args.get("action") or "get").strip().lower()
    try:
        client = _spotify_client()
        album_id = normalize_spotify_id(str(args.get("album_id") or args.get("id") or ""), "album")
        if action == "get":
            return _tool_result(client.get_album(album_id=album_id, market=args.get("market")))
        if action == "tracks":
            return _tool_result(client.get_album_tracks(album_id=album_id, limit=_coerce_limit(args.get("limit")),
                                                         offset=max(0, int(args.get("offset") or 0)), market=args.get("market")))
        return _tool_error(f"Unknown action: {action}")
    except Exception as exc:
        return _tool_error(str(exc))


def _handle_spotify_library(args: dict, **kw) -> str:
    kind = str(args.get("kind") or "").strip().lower()
    if kind not in {"tracks", "albums"}:
        return _tool_error("kind must be tracks or albums")
    action = str(args.get("action") or "list").strip().lower()
    try:
        client = _spotify_client()
        if action == "list":
            limit = _coerce_limit(args.get("limit"), default=20)
            offset = max(0, int(args.get("offset") or 0))
            market = args.get("market")
            if kind == "tracks":
                return _tool_result(client.get_saved_tracks(limit=limit, offset=offset, market=market))
            return _tool_result(client.get_saved_albums(limit=limit, offset=offset, market=market))
        if action == "save":
            uris = [normalize_spotify_uri(u) for u in _as_list(args.get("uris") or args.get("items"))]
            return _tool_result(client.save_library_items(uris=uris))
        if action == "remove":
            ids = [normalize_spotify_id(i, "track" if kind == "tracks" else "album") for i in _as_list(args.get("ids") or args.get("items"))]
            if not ids:
                return _tool_error("ids/items required for remove")
            if kind == "tracks":
                return _tool_result(client.remove_saved_tracks(track_ids=ids))
            return _tool_result(client.remove_saved_albums(album_ids=ids))
        return _tool_error(f"Unknown action: {action}")
    except Exception as exc:
        return _tool_error(str(exc))


COMMON_STRING = {"type": "string"}

SPOTIFY_PLAYBACK_SCHEMA = {
    "name": "spotify_playback",
    "description": "控制 Spotify 播放、查看播放状态、最近播放记录。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get_state", "get_currently_playing", "play", "pause", "next", "previous", "seek", "set_repeat", "set_shuffle", "set_volume", "recently_played"]},
            "device_id": COMMON_STRING, "market": COMMON_STRING, "context_uri": COMMON_STRING,
            "uris": {"type": "array", "items": COMMON_STRING}, "offset": {"type": "object"},
            "position_ms": {"type": "integer"}, "state": {"oneOf": [{"type": "string"}, {"type": "boolean"}]},
            "volume_percent": {"type": "integer"}, "limit": {"type": "integer"},
        },
        "required": ["action"],
    },
}

SPOTIFY_DEVICES_SCHEMA = {
    "name": "spotify_devices",
    "description": "列出 Spotify Connect 设备或切换播放设备。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "transfer"]},
            "device_id": COMMON_STRING, "play": {"type": "boolean"},
        },
        "required": ["action"],
    },
}

SPOTIFY_QUEUE_SCHEMA = {
    "name": "spotify_queue",
    "description": "查看播放队列或添加曲目。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get", "add"]},
            "uri": COMMON_STRING, "device_id": COMMON_STRING,
        },
        "required": ["action"],
    },
}

SPOTIFY_SEARCH_SCHEMA = {
    "name": "spotify_search",
    "description": "搜索 Spotify 曲目、专辑、艺术家、播放列表。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": COMMON_STRING, "types": {"type": "array", "items": COMMON_STRING},
            "type": COMMON_STRING, "limit": {"type": "integer"}, "offset": {"type": "integer"},
            "market": COMMON_STRING,
        },
        "required": ["query"],
    },
}

SPOTIFY_PLAYLISTS_SCHEMA = {
    "name": "spotify_playlists",
    "description": "管理 Spotify 播放列表。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "get", "create", "add_items", "remove_items", "update_details"]},
            "playlist_id": COMMON_STRING, "market": COMMON_STRING, "limit": {"type": "integer"},
            "offset": {"type": "integer"}, "name": COMMON_STRING, "description": COMMON_STRING,
            "public": {"type": "boolean"}, "collaborative": {"type": "boolean"},
            "uris": {"type": "array", "items": COMMON_STRING}, "position": {"type": "integer"},
            "snapshot_id": COMMON_STRING,
        },
        "required": ["action"],
    },
}

SPOTIFY_ALBUMS_SCHEMA = {
    "name": "spotify_albums",
    "description": "获取 Spotify 专辑信息或曲目列表。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get", "tracks"]},
            "album_id": COMMON_STRING, "id": COMMON_STRING, "market": COMMON_STRING,
            "limit": {"type": "integer"}, "offset": {"type": "integer"},
        },
        "required": ["action"],
    },
}

SPOTIFY_LIBRARY_SCHEMA = {
    "name": "spotify_library",
    "description": "管理 Spotify 收藏的曲目或专辑。",
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["tracks", "albums"]},
            "action": {"type": "string", "enum": ["list", "save", "remove"]},
            "limit": {"type": "integer"}, "offset": {"type": "integer"}, "market": COMMON_STRING,
            "uris": {"type": "array", "items": COMMON_STRING},
            "ids": {"type": "array", "items": COMMON_STRING},
            "items": {"type": "array", "items": COMMON_STRING},
        },
        "required": ["kind", "action"],
    },
}
