"""Navidrome access. The Subsonic API itself is py-opensonic's `Connection`;
this module only builds it from config and covers what the library doesn't."""
import hashlib
import secrets
from urllib.parse import urlparse

import requests
from libopensonic import Connection

from .config import Config

API_VERSION = "1.16.1"


def make_client(cfg: Config) -> Connection:
    u = urlparse(cfg.navidrome_url)
    # use_get puts auth in the URL, which is what Sonos needs to fetch a stream.
    return Connection(
        f"{u.scheme}://{u.hostname}",
        username=cfg.navidrome_user,
        password=cfg.navidrome_password,
        port=u.port or (443 if u.scheme == "https" else 80),
        app_name="house-music",
        use_get=True,
    )


def stream_url(client: Connection, song_id: str) -> str:
    """Untranscoded stream URL a Sonos speaker can fetch directly."""
    url, _ = client.get_stream_url(song_id, tformat="raw")
    return url


def cover_art(cfg: Config, cover_id: str, size: int | None = None) -> requests.Response:
    """Fetch cover art bytes (py-opensonic returns an async response, so use requests)."""
    salt = secrets.token_hex(8)
    params = {
        "u": cfg.navidrome_user,
        "t": hashlib.md5((cfg.navidrome_password + salt).encode()).hexdigest(),
        "s": salt,
        "v": API_VERSION,
        "c": "house-music",
        "id": cover_id,
    }
    if size:
        params["size"] = size
    return requests.get(f"{cfg.navidrome_url}/rest/getCoverArt", params=params, timeout=10)
