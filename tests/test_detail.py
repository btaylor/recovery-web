from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from libopensonic.errors import SonicError

from app import create_app
from app.config import Config
from app.sonos import NoRoom

ENV = {"ND_URL": "http://nd:4533", "ND_USER": "u", "ND_PASS": "p"}
SONGS = [NS(title="Opening", artist="A", duration=252), NS(title="Paper Radio", artist="B", duration=227)]


@pytest.fixture
def ctx():
    app = create_app(Config.from_env(ENV))
    nd = app.extensions["nd"] = MagicMock()
    sonos = app.extensions["sonos"] = MagicMock()
    player = app.extensions["player"] = MagicMock(follow_on_default=True)
    sonos.zones.return_value = {"Kitchen": 1, "Study": 2}
    sonos.group_names = ["Study"]
    nd.get_album.return_value = NS(id="al1", name="Blue Hour", artist="The Meridians", year=1974, genre="Jazz",
                                   song_count=2, duration=479, cover_art="c1", song=SONGS)
    nd.get_playlist.return_value = NS(id="pl1", name="Dinner", song_count=2, duration=479, cover_art="pl-1", entry=SONGS)
    nd.get_playlists.return_value = [NS(id="pl1", name="Dinner", song_count=2, duration=479, cover_art="pl-1")]
    nd.get_genres.return_value = []
    nd.get_album_list2.return_value = []
    return app.test_client(), nd, sonos, player


def test_album_detail(ctx):
    c, *_ = ctx
    html = c.get("/album/al1").text
    assert "Blue Hour" in html and "1974 · Jazz · 2 tracks · 8 min" in html
    assert 'hx-post="/play/album/al1"' in html               # the one Play action
    assert "/play/album/al1?start=1" in html                  # tapping track 2 starts the album there
    assert "4:12" in html and "Then: mix from this album" in html
    assert '<option selected>Study</option>' in html          # saved room preselected


def test_no_saved_room_prompts_for_one(ctx):
    c, _, sonos, _ = ctx
    sonos.group_names = []
    assert "Choose room" in c.get("/album/al1").text


def test_device_room_cookie_is_preselected_over_the_shared_group(ctx):
    c, _, _, _ = ctx
    c.set_cookie("room", "Kitchen")                           # the group is Study, this device's own is Kitchen
    assert '<option selected>Kitchen</option>' in c.get("/album/al1").text


def test_play_anchors_the_device_room_only_when_it_has_one(ctx):
    c, _, sonos, _ = ctx
    c.post("/play/album/al1")
    sonos.anchor.assert_not_called()
    c.set_cookie("room", "Kitchen")
    c.post("/play/album/al1")
    sonos.anchor.assert_called_once_with("Kitchen")


def test_missing_album_is_404(ctx):
    c, nd, *_ = ctx
    nd.get_album.side_effect = SonicError("nope")
    assert c.get("/album/zzz").status_code == 404


def test_playlist_detail_shows_artist_per_track(ctx):
    c, *_ = ctx
    html = c.get("/playlist/pl1").text
    assert "Dinner" in html and "<small>B</small>" in html and "/play/playlist/pl1" in html
    assert "Then: mix from this playlist" in html


def test_play_starts_playback(ctx):
    c, _, _, player = ctx
    assert c.post("/play/album/al1?start=3").status_code == 204
    player.play_album.assert_called_once_with("al1", 3)
    c.post("/play/playlist/pl1")
    player.play_playlist.assert_called_once_with("pl1", 0)


def test_play_without_a_room_is_409_and_bad_kind_404(ctx):
    c, _, _, player = ctx
    player.play_album.side_effect = NoRoom("Choose a room first")
    r = c.post("/play/album/al1")
    assert r.status_code == 409 and r.text == "Choose a room first"
    assert c.post("/play/song/x").status_code == 404


def test_room_picker_sets_group_and_rejects_unknown_rooms(ctx):
    c, _, sonos, _ = ctx
    assert c.post("/group", data={"room": "Kitchen"}).status_code == 204
    sonos.set_group.assert_called_once_with(["Kitchen"])
    assert c.post("/group", data={"room": "Garage"}).status_code == 404


def test_room_picker_remembers_the_room_on_this_device(ctx):
    c, *_ = ctx
    r = c.post("/group", data={"room": "Kitchen"})
    assert r.headers["Set-Cookie"].startswith("room=Kitchen") and "HttpOnly" in r.headers["Set-Cookie"]


def test_change_follow_on_sets_default_only(ctx):
    c, _, sonos, player = ctx
    assert "Then: stop" in c.post("/follow-on?kind=album").text
    assert player.follow_on_default is False
    player.set_follow_on.assert_not_called()  # the queue that is playing now is untouched


def test_playlists_wall_and_full_page(ctx):
    c, *_ = ctx
    frag = c.get("/playlists").text
    assert 'hx-get="/playlist/pl1"' in frag and "Dinner" in frag and "2 tracks" in frag
    assert 'class="chip chip--lists on"' in c.get("/?lists=1").text


def test_empty_playlist_does_not_crash(ctx):
    c, nd, *_ = ctx
    nd.get_playlist.return_value = NS(id="pl2", name="Empty", song_count=0, duration=0, cover_art=None, entry=None)
    assert "Empty" in c.get("/playlist/pl2").text
