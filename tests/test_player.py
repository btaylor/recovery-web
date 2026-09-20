from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.player import Player


def song(i, genre="Jazz", starred=None):
    return NS(id=f"s{i}", title=f"T{i}", artist="A", album="Al", genre=genre,
              content_type="audio/mpeg", duration=200, starred=starred)


ALBUM = [song(1), song(2), song(3)]


@pytest.fixture
def p():
    nd, sonos = MagicMock(), MagicMock()
    nd.get_album.return_value = NS(name="Blue Hour", song=ALBUM)
    nd.get_playlist.return_value = NS(name="Dinner", entry=ALBUM)
    nd.get_similar_songs2.return_value = [song(3), song(10), song(11)]  # s3 is on the album
    nd.get_song.side_effect = lambda i: song(i)
    nd.get_stream_url.side_effect = lambda sid, tformat: (f"http://nd/stream?id={sid}", {})
    sonos.now_playing.return_value = {"index": 0, "position": "0:01:00", "duration": "0:05:00"}
    return Player(nd, sonos)


def queued(p):
    (pairs, start), _ = p.sonos.play_songs.call_args
    return [s.id for _, s in pairs], start


def test_album_then_mix_seeded_from_last_song_without_dupes(p):
    p.play_album("al", start=1)
    ids, start = queued(p)
    assert ids == ["s1", "s2", "s3", "s10", "s11"] and start == 1
    p.nd.get_similar_songs2.assert_called_once_with("s3", 50)


def test_playlist_behaves_like_album(p):
    p.play_playlist("pl")
    assert queued(p)[0][:3] == ["s1", "s2", "s3"] and p.source_len == 3


def test_falls_back_to_genre_when_no_similar_songs(p):
    p.nd.get_similar_songs2.return_value = []
    p.nd.get_random_songs.return_value = [song(20)]
    p.play_album("al")
    assert queued(p)[0][-1] == "s20"
    p.nd.get_random_songs.assert_called_once_with(50, genre="Jazz")


def test_follow_on_off_means_album_only(p):
    p.follow_on_default = False
    p.play_album("al")
    assert queued(p)[0] == ["s1", "s2", "s3"]
    p.nd.get_similar_songs2.assert_not_called()
    p.play_album("al", follow_on=True)  # per-play override
    assert len(queued(p)[0]) == 5 and p.follow_on


def test_stop_after_removes_mix_and_can_be_undone(p):
    p.play_album("al")
    p.set_follow_on(False)
    p.sonos.truncate_queue.assert_called_once_with(3)
    assert [s.id for s in p.songs] == ["s1", "s2", "s3"]
    p.set_follow_on(True)
    (pairs,), _ = p.sonos.append_songs.call_args
    assert [s.id for _, s in pairs] == ["s10", "s11"]
    assert len(p.songs) == 5


def test_handoff_banner_only_on_last_track_near_the_end(p):
    p.play_album("al")
    assert p.status()["handoff"] is False  # first track
    p.sonos.now_playing.return_value = {"index": 2, "position": "0:04:32", "duration": "0:05:00"}
    assert p.status()["handoff"] == {"in": 28}
    p.sonos.now_playing.return_value = {"index": 2, "position": "0:01:00", "duration": "0:05:00"}
    assert p.status()["handoff"] is False  # too early
    p.set_follow_on(False)
    p.sonos.now_playing.return_value = {"index": 2, "position": "0:04:50", "duration": "0:05:00"}
    assert p.status()["handoff"] is False  # nothing coming


def test_status_reports_current_song_and_star(p):
    p.play_album("al")
    p.nd.get_song.side_effect = lambda i: song(i, starred="2026-01-01")
    st = p.status()
    assert st["song"].id == "s1" and st["starred"] is True


def test_toggle_star(p):
    assert p.toggle_star("s1") is True
    p.nd.star.assert_called_once_with(["s1"])
    p.nd.get_song.side_effect = lambda i: song(i, starred="x")
    assert p.toggle_star("s1") is False
    p.nd.unstar.assert_called_once_with(["s1"])


def test_playing_an_empty_playlist_is_a_noop(p):
    p.nd.get_playlist.return_value = NS(name="E", entry=None)
    p.play_playlist("empty")
    p.sonos.play_songs.assert_not_called()


def test_status_has_progress_source_and_position_in_source(p):
    p.play_album("al")
    st = p.status()
    assert st["pct"] == 20 and st["source"] == "Blue Hour" and st["of"] == (1, 3)
    p.sonos.now_playing.return_value = {"index": 4, "position": "0:00:10", "duration": "0:03:00"}
    assert p.status()["of"] is None  # in the mix


def test_star_current(p):
    p.play_album("al")
    p.star_current()
    p.nd.star.assert_called_once_with(["s1"])
