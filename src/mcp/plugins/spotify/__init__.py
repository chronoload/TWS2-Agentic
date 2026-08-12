import logging

from .tools import (
    SPOTIFY_ALBUMS_SCHEMA, SPOTIFY_DEVICES_SCHEMA, SPOTIFY_LIBRARY_SCHEMA,
    SPOTIFY_PLAYBACK_SCHEMA, SPOTIFY_PLAYLISTS_SCHEMA, SPOTIFY_QUEUE_SCHEMA,
    SPOTIFY_SEARCH_SCHEMA, _check_spotify_available, _handle_spotify_albums,
    _handle_spotify_devices, _handle_spotify_library, _handle_spotify_playback,
    _handle_spotify_playlists, _handle_spotify_queue, _handle_spotify_search,
)

logger = logging.getLogger(__name__)

_TOOLS = (
    ("spotify_playback",  SPOTIFY_PLAYBACK_SCHEMA,  _handle_spotify_playback,  "🎵"),
    ("spotify_devices",   SPOTIFY_DEVICES_SCHEMA,   _handle_spotify_devices,   "🔈"),
    ("spotify_queue",     SPOTIFY_QUEUE_SCHEMA,     _handle_spotify_queue,     "📻"),
    ("spotify_search",    SPOTIFY_SEARCH_SCHEMA,    _handle_spotify_search,    "🔎"),
    ("spotify_playlists", SPOTIFY_PLAYLISTS_SCHEMA, _handle_spotify_playlists, "📚"),
    ("spotify_albums",    SPOTIFY_ALBUMS_SCHEMA,    _handle_spotify_albums,    "💿"),
    ("spotify_library",   SPOTIFY_LIBRARY_SCHEMA,   _handle_spotify_library,   "❤️"),
)


def register(ctx) -> None:
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="spotify",
            schema=schema,
            handler=handler,
            check_fn=_check_spotify_available,
            emoji=emoji,
        )
    logger.info("spotify plugin registered")
