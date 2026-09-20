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


def test_healthz_and_index():
    client = create_app(Config.from_env(ENV)).test_client()
    assert client.get("/healthz").json == {"status": "ok"}
    assert b"House Music" in client.get("/").data
