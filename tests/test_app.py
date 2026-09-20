import pytest

from app import create_app
from app.config import Config, ConfigError

ENV = {
    "ND_URL": "http://nd.local:4533/",
    "ND_USER": "u",
    "ND_PASS": "p",
}


def test_config_reads_env_and_strips_trailing_slash():
    cfg = Config.from_env(ENV)
    assert cfg.navidrome_url == "http://nd.local:4533"
    assert cfg.state_dir == "./data"


@pytest.mark.parametrize("key", list(ENV))
def test_config_fails_fast_when_missing(key):
    env = {k: v for k, v in ENV.items() if k != key}
    with pytest.raises(ConfigError, match=key):
        Config.from_env(env)


def test_healthz():
    client = create_app(Config.from_env(ENV)).test_client()
    assert client.get("/healthz").json == {"status": "ok"}


def test_stream_url_is_direct_raw_and_authenticated():
    from app import navidrome

    url = navidrome.stream_url(navidrome.make_client(Config.from_env(ENV)), "song1")
    assert url.startswith("http://nd.local:4533/rest/stream.view?")
    for part in ("id=song1", "format=raw", "u=u", "t=", "s="):
        assert part in url


def test_cover_proxy(monkeypatch):
    class R:
        ok = True
        content = b"IMG"
        headers = {"Content-Type": "image/jpeg"}

    seen = {}

    def fake_get(url, params, timeout):
        seen.update(url=url, params=params)
        return R()

    monkeypatch.setattr("app.navidrome.requests.get", fake_get)
    resp = create_app(Config.from_env(ENV)).test_client().get("/cover/c1?size=300")
    assert resp.data == b"IMG" and resp.mimetype == "image/jpeg"
    assert "max-age" in resp.headers["Cache-Control"]
    assert seen["url"] == "http://nd.local:4533/rest/getCoverArt"
    assert seen["params"]["id"] == "c1" and seen["params"]["size"] == 300
    assert "p" not in seen["params"].values()  # password is never sent, only token+salt


def test_cover_404_when_navidrome_returns_non_image(monkeypatch):
    class R:
        ok = True
        content = b"{}"
        headers = {"Content-Type": "application/json"}

    monkeypatch.setattr("app.navidrome.requests.get", lambda *a, **k: R())
    assert create_app(Config.from_env(ENV)).test_client().get("/cover/nope").status_code == 404
