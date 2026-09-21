"""What happens when Navidrome or a speaker can't be reached.

The exception types are the ones the libraries document/raise: aiohttp's ClientError and
TimeoutError from py-opensonic, SonicError subclasses for errors Navidrome reports, and
requests.RequestException / SoCoException from SoCo.
"""
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import aiohttp
import pytest
import requests
from libopensonic.errors import AuthError
from soco.exceptions import SoCoException

from app import create_app
from app.config import Config
from app.sonos import NoRoom, Sonos

ENV = {"ND_URL": "http://nd:4533", "ND_USER": "u", "ND_PASS": "p"}
HX = {"HX-Request": "true"}


@pytest.fixture
def ctx():
    app = create_app(Config.from_env(ENV))
    nd = app.extensions["nd"] = MagicMock()
    sonos = app.extensions["sonos"] = MagicMock()
    player = app.extensions["player"] = MagicMock(follow_on_default=True)
    sonos.zones.return_value = {"Kitchen": 1}
    sonos.group_names = ["Kitchen"]
    sonos.label.return_value = "Kitchen"
    return app.test_client(), nd, sonos, player


@pytest.mark.parametrize("exc", [aiohttp.ClientConnectionError("down"), TimeoutError()])
def test_navidrome_down_shows_a_page_for_navigation(ctx, exc):
    c, nd, *_ = ctx
    nd.get_genres.side_effect = exc
    r = c.get("/")
    assert r.status_code == 502
    assert "Can&#39;t reach Navidrome" in r.text and "ND_URL" in r.text and "Try again" in r.text


def test_navidrome_down_is_a_short_plain_message_for_htmx(ctx):
    c, nd, *_ = ctx
    nd.get_album_list2.side_effect = aiohttp.ClientConnectionError("down")
    r = c.get("/albums?offset=48", headers=HX)
    assert r.status_code == 502 and r.mimetype == "text/plain" and r.text == "Can't reach Navidrome."


def test_wrong_login_says_so_and_is_not_mistaken_for_a_missing_album(ctx):
    c, nd, *_ = ctx
    nd.get_album.side_effect = AuthError("bad credentials")
    r = c.get("/album/al1", headers=HX)
    assert r.status_code == 502 and "username or password" in r.text  # not a 404


@pytest.mark.parametrize("exc", [requests.ConnectionError("gone"), requests.Timeout(), SoCoException("fault")])
def test_speaker_trouble_is_a_short_message_for_actions(ctx, exc):
    c, _, sonos, _ = ctx
    sonos.transport.side_effect = exc
    r = c.post("/transport/toggle", headers=HX)
    assert r.status_code == 502 and r.mimetype == "text/plain" and r.text == "Can't reach the speaker."


def test_no_room_is_a_plain_409_for_the_toast(ctx):
    c, _, _, player = ctx
    player.play_album.side_effect = NoRoom("Choose a room first")
    r = c.post("/play/album/al1", headers=HX)
    assert r.status_code == 409 and r.mimetype == "text/plain" and r.text == "Choose a room first"


@pytest.mark.parametrize("exc", [requests.ConnectionError(), SoCoException(), aiohttp.ClientConnectionError(), TimeoutError()])
def test_pollers_never_fail_they_show_idle(ctx, exc):
    """A poller that errors is dropped by htmx and the UI freezes; it must degrade instead."""
    c, _, sonos, player = ctx
    player.status.side_effect = exc
    sonos.label.side_effect = exc
    bar, top = c.get("/player", headers=HX), c.get("/now/top", headers=HX)
    assert bar.status_code == 200 and "Nothing playing" in bar.text
    assert 'hx-trigger="refresh from:body, every 3s"' in bar.text  # still polling
    assert top.status_code == 200 and 'every 2s' in top.text


def test_cover_proxy_is_a_quiet_502_when_navidrome_is_down(ctx, monkeypatch):
    c, *_ = ctx
    monkeypatch.setattr("app.navidrome.requests.get", MagicMock(side_effect=requests.ConnectionError()))
    assert c.get("/cover/c1").status_code == 502


# --- Sonos.zones(): a cached speaker can vanish -------------------------------------------------

class Gone:
    @property
    def visible_zones(self):
        raise requests.ConnectionError("speaker went away")


def speaker(name):
    return NS(player_name=name)


def test_zones_finds_another_speaker_when_the_cached_one_vanishes(tmp_path, monkeypatch):
    son = Sonos(str(tmp_path))
    son._any = Gone()
    other = NS(visible_zones=[speaker("Kitchen"), speaker("Study")])
    monkeypatch.setattr("soco.discovery.any_soco", lambda: other)
    assert sorted(son.zones()) == ["Kitchen", "Study"]
    assert son._any is other  # remembered for next time


def test_zones_is_empty_and_backs_off_when_nothing_is_found(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("soco.discovery.any_soco", lambda: calls.append(1))  # returns None
    son = Sonos(str(tmp_path))
    assert son.zones() == {} and son.zones() == {} and son.zones() == {}
    assert len(calls) == 1  # not searching the network on every 2s poll


def test_zones_gives_up_after_one_retry(tmp_path, monkeypatch):
    son = Sonos(str(tmp_path))
    son._any = Gone()
    monkeypatch.setattr("soco.discovery.any_soco", lambda: Gone())
    assert son.zones() == {}  # no exception, no infinite loop


# --- Saved group: a state dir the app can't write (e.g. a volume owned by another user) ---------

def test_unwritable_state_dir_only_loses_persistence(tmp_path, caplog):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")                    # STATE_DIR below a file: it can never be created
    son = Sonos(str(blocker / "data"))
    son._any = NS(visible_zones=[])            # no speakers online, which is fine here
    with caplog.at_level("WARNING"):
        assert son.set_group(["Kitchen"]) is None   # no crash
    assert son.group_names == ["Kitchen"]           # still remembered, in memory
    assert "Can't save the playback group" in caplog.text and "STATE_DIR" in caplog.text
