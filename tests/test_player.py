from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.player import Player


def song(i, genre="Jazz", starred=None):
    return NS(id=f"s{i}", title=f"T{i}", artist="A", album="Al", genre=genre, cover_art=f"c{i}",
              content_type="audio/mpeg", duration=200, starred=starred)


@pytest.fixture
def p():
    # Fresh song objects per test: toggle_star()/status() now mutate a song's `.starred` in
    # place, so tests sharing one module-level list would leak state into each other.
    album = [song(1), song(2), song(3)]
    nd, sonos = MagicMock(), MagicMock()
    nd.get_album.return_value = NS(name="Blue Hour", song=album)
    nd.get_playlist.return_value = NS(name="Dinner", entry=album)
    nd.get_similar_songs2.return_value = [song(3), song(10), song(11)]  # s3 is on the album
    nd.get_stream_url.side_effect = lambda sid, tformat: (f"http://nd/stream?id={sid}", {})
    sonos.now_playing.return_value = {"index": 0, "position": "0:01:00", "duration": "0:05:00",
                                      "title": "T1", "artist": "A", "album": "Al"}  # song 1 of the album
    p = Player(nd, sonos)
    p._run = lambda fn, *args: fn(*args)  # the background mix runs right away in tests
    return p


def appended(p):
    """The mix as it was added to the queue after the album started."""
    calls = p.sonos.append_songs.call_args_list
    return [s.id for _, s in calls[-1].args[0]] if calls else []


def queued(p):
    (pairs, start), _ = p.sonos.play_songs.call_args
    return [s.id for _, s in pairs], start


def test_album_starts_at_once_then_mix_is_added_seeded_from_last_song_without_dupes(p):
    p.play_album("al", start=1)
    ids, start = queued(p)
    assert ids == ["s1", "s2", "s3"] and start == 1      # the album goes to the speakers first
    assert appended(p) == ["s10", "s11"]                   # then the mix joins the queue
    p.nd.get_similar_songs2.assert_called_once_with("s3", 50)


def test_album_plays_before_the_mix_is_even_looked_up(p):
    order = []
    p.sonos.play_songs.side_effect = lambda *a, **k: order.append("play")
    p.nd.get_similar_songs2.side_effect = lambda *a: order.append("mix") or []
    p.nd.get_random_songs.return_value = []
    p.play_album("al")
    assert order[0] == "play"


def test_mix_that_fails_leaves_the_album_playing_alone(p):
    p.nd.get_similar_songs2.side_effect = TimeoutError("slow")
    p.play_album("al")
    assert queued(p)[0] == ["s1", "s2", "s3"] and len(p.songs) == 3
    p.sonos.append_songs.assert_not_called()


def test_mix_for_an_earlier_album_is_dropped_if_another_starts_first(p):
    later = []
    p._run = lambda fn, *args: later.append((fn, args))   # hold the background work until we say so
    p.play_album("al")
    p.play_album("al")                                     # a new play before the first mix is ready
    for fn, args in later:
        fn(*args)
    assert p.sonos.append_songs.call_count == 1           # only the current play's mix is added


def test_playlist_behaves_like_album(p):
    p.play_playlist("pl")
    assert queued(p)[0][:3] == ["s1", "s2", "s3"] and p.source_len == 3


def test_falls_back_to_genre_when_no_similar_songs(p):
    p.nd.get_similar_songs2.return_value = []
    p.nd.get_random_songs.return_value = [song(20)]
    p.play_album("al")
    assert appended(p)[-1] == "s20"
    p.nd.get_random_songs.assert_called_once_with(50, genre="Jazz")


def test_follow_on_off_means_album_only(p):
    p.follow_on_default = False
    p.play_album("al")
    assert queued(p)[0] == ["s1", "s2", "s3"]
    p.nd.get_similar_songs2.assert_not_called()
    p.play_album("al", follow_on=True)  # per-play override
    assert len(p.songs) == 5 and p.follow_on


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
    p.sonos.now_playing.return_value = {"index": 2, "position": "0:04:32", "duration": "0:05:00", "title": "T3", "artist": "A", "album": "Al"}
    assert p.status()["handoff"] == {"in": 28}
    p.sonos.now_playing.return_value = {"index": 2, "position": "0:01:00", "duration": "0:05:00", "title": "T3", "artist": "A", "album": "Al"}
    assert p.status()["handoff"] is False  # too early
    p.set_follow_on(False)
    p.sonos.now_playing.return_value = {"index": 2, "position": "0:04:50", "duration": "0:05:00", "title": "T3", "artist": "A", "album": "Al"}
    assert p.status()["handoff"] is False  # nothing coming


def test_status_reports_current_song_and_star_without_asking_navidrome(p):
    p.play_album("al")
    p.songs[0].starred = "2026-01-01"  # as Navidrome returned it when the album was fetched
    st = p.status()
    assert st["song"].id == "s1" and st["starred"] is True
    p.nd.get_song.assert_not_called()  # every 2-3s poll used to hit Navidrome just for this


def test_toggle_star_updates_the_in_memory_song_so_the_next_poll_sees_it(p):
    s = song(1)
    assert p.toggle_star(s) is True and s.starred
    p.nd.star.assert_called_once_with(["s1"])
    assert p.toggle_star(s) is False and not s.starred
    p.nd.unstar.assert_called_once_with(["s1"])


def test_playing_an_empty_playlist_is_a_noop(p):
    p.nd.get_playlist.return_value = NS(name="E", entry=None)
    p.play_playlist("empty")
    p.sonos.play_songs.assert_not_called()


EXTERNAL = {"index": 40, "position": "0:01:00", "duration": "0:05:00", "title": "T1", "artist": "A", "album": "Al"}


def test_art_is_found_by_title_for_a_track_this_app_did_not_queue(p):
    p.sonos.now_playing.return_value = EXTERNAL
    p.nd.search3.return_value = NS(song=[NS(title="T1", artist="A", album="Al", cover_art="c9", starred=None)])
    assert p.status()["cover"] == "c9"
    p.status()
    p.nd.search3.assert_called_once()  # cached: the 2-3s polls don't search again


def test_same_index_in_another_queue_does_not_borrow_our_song_art(p):
    p.play_album("al1")                                     # our queue: index 0 is T1 by A (cover c1)
    p.sonos.now_playing.return_value = {"index": 0, "position": "0:01:00", "duration": "0:05:00",
                                        "title": "Star Wars", "artist": "John Williams", "album": "Star Wars"}
    p.nd.search3.return_value = NS(song=[NS(id="jw1", title="Star Wars", artist="John Williams",
                                            album="Star Wars", cover_art="jw1", starred=None)])
    st = p.status()
    assert st["cover"] == "jw1" and st["song"].id == "jw1"  # the library song, not our song 1
    p.star_current()
    p.nd.star.assert_called_once_with(["jw1"])              # the favourite acts on that song, not song 1


def test_favourite_works_for_a_track_from_elsewhere(p):
    p.sonos.now_playing.return_value = EXTERNAL
    lib = NS(id="jw9", title="T1", artist="A", album="Al", cover_art="c9", starred=None)
    p.nd.search3.return_value = NS(song=[lib])
    st = p.status()
    assert st["song"] is lib and st["starred"] is False      # the heart shows, unfavourited
    p.star_current()
    p.nd.star.assert_called_once_with(["jw9"])
    assert p.status()["starred"] is True                    # the next poll sees it, with no new search
    p.nd.search3.assert_called_once()


def test_art_search_failure_shows_no_art_and_is_retried_next_poll(p):
    from libopensonic.errors import SonicError
    p.sonos.now_playing.return_value = EXTERNAL
    p.nd.search3.side_effect = SonicError("down")
    assert p.status()["cover"] is None
    p.nd.search3.side_effect = None
    p.nd.search3.return_value = NS(song=[NS(title="T1", artist="A", album="Al", cover_art="c9", starred=None)])
    assert p.status()["cover"] == "c9"


def test_status_has_progress_source_and_position_in_source(p):
    p.play_album("al")
    st = p.status()
    assert st["pct"] == 20 and st["source"] == "Blue Hour" and st["of"] == (1, 3)
    p.sonos.now_playing.return_value = {"index": 4, "position": "0:00:10", "duration": "0:03:00", "title": "T11", "artist": "A", "album": "Al"}
    assert p.status()["of"] is None  # in the mix


def test_star_current(p):
    p.play_album("al")
    p.star_current()
    p.nd.star.assert_called_once_with(["s1"])
    assert p.songs[0].starred  # so status() reflects it on the very next poll, no extra call needed
