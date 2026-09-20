from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app import create_app
from app.config import Config

ENV = {"ND_URL": "http://nd:4533", "ND_USER": "u", "ND_PASS": "p"}
SONG = NS(id="s1", cover_art="c1")
ST = {"title": "Low Ceiling", "artist": "The Meridians", "album": "Blue Hour", "position": "0:02:14",
      "duration": "0:05:20", "index": 2, "state": "PLAYING", "song": SONG, "starred": True, "pct": 42,
      "source": "Blue Hour", "of": (3, 9), "follow_on": True, "handoff": False}
MIXER = {"master": 46, "grouped": [("Kitchen", 62), ("Study", 30)], "others": ["Patio"]}


@pytest.fixture
def ctx():
    app = create_app(Config.from_env(ENV))
    player = app.extensions["player"] = MagicMock()
    sonos = app.extensions["sonos"] = MagicMock()
    player.status.return_value = dict(ST)
    sonos.label.return_value = "Kitchen +1"
    sonos.mixer.return_value = MIXER
    sonos.group_names = ["Kitchen", "Study"]
    sonos.zones.return_value = {"Kitchen": MagicMock(), "Study": MagicMock(), "Patio": MagicMock()}
    return app.test_client(), player, sonos


def test_mini_bar_shows_track_room_and_transport(ctx):
    c, *_ = ctx
    html = c.get("/player").text
    assert "Low Ceiling" in html and "The Meridians" in html and "Kitchen +1" in html
    assert 'hx-get="/speakers"' in html            # room name is its own tap target
    assert html.count('hx-get="/now"') == 2         # cover + title open now-playing
    assert 'class="heart on"' in html and "⏸" in html
    assert 'hx-trigger="refresh from:body, every 3s"' in html
    # The bar swaps itself with outerHTML; its buttons must not inherit that, or opening a panel
    # replaces #detail itself and the close handlers (getElementById("detail")) find nothing.
    assert 'hx-disinherit="hx-swap"' in html


def test_mini_bar_idle_and_paused(ctx):
    c, player, _ = ctx
    player.status.return_value = None
    assert "Nothing playing" in c.get("/player").text
    player.status.return_value = dict(ST, state="PAUSED_PLAYBACK")
    assert "▶" in c.get("/player").text


def test_now_playing_shows_progress_position_and_follow_on(ctx):
    c, *_ = ctx
    html = c.get("/now/top").text
    assert "Blue Hour · 3 of 9" in html and "width: 42%" in html
    assert "2:14" in html and "5:20" in html
    assert "Mix from Blue Hour" in html and 'aria-checked="true"' in html
    assert "banner" not in html


def test_handoff_banner_offers_stop_after(ctx):
    c, player, _ = ctx
    player.status.return_value = dict(ST, handoff={"in": 28})
    html = c.get("/now/top").text
    assert "Up next · in 0:28" in html and "stop after" in html


def test_transport_star_and_follow_on_refresh_pollers(ctx):
    c, player, sonos = ctx
    for url in ("/transport/toggle", "/transport/next", "/transport/prev", "/star", "/now/follow-on"):
        r = c.post(url)
        assert r.status_code == 204 and r.headers["HX-Trigger"] == "refresh"
    sonos.transport.assert_any_call("next")
    player.star_current.assert_called_once()
    player.set_follow_on.assert_called_once_with(not player.follow_on)
    assert c.post("/transport/explode").status_code == 404


def test_mixer_anchor_room_cannot_be_unchecked(ctx):
    c, *_ = ctx
    html = c.get("/mixer").text
    assert html.count("disabled") == 1 and "Not in group" in html and "Patio" in html
    assert 'hx-post="/volume/Study"' in html and 'hx-post="/volume"' in html


def test_join_and_leave_rooms(ctx):
    c, _, sonos = ctx
    c.post("/group/toggle", data={"room": "Patio"})
    sonos.set_group.assert_called_with(["Kitchen", "Study", "Patio"])
    c.post("/group/toggle", data={"room": "Study"})
    sonos.set_group.assert_called_with(["Kitchen"])
    assert c.post("/group/toggle", data={"room": "Kitchen"}).status_code == 404  # anchor
    assert c.post("/group/toggle", data={"room": "Garage"}).status_code == 404


def test_volume_master_and_rooms(ctx):
    c, _, sonos = ctx
    group = sonos.coordinator.return_value.group
    c.post("/volume", data={"v": "150"})
    assert group.volume == 100                       # clamped
    c.post("/volume?delta=-2")
    group.set_relative_volume.assert_called_once_with(-2)
    c.post("/volume/Study", data={"v": "30"})
    assert sonos.zones.return_value["Study"].volume == 30
    assert c.post("/volume/Garage", data={"v": "5"}).status_code == 404
