from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from app.sonos import Sonos


def speaker(name):
    s = MagicMock(name=name)
    s.player_name = name
    s.is_coordinator = True
    return s


def make(tmp_path, *names):
    son = Sonos(str(tmp_path))
    spk = {n: speaker(n) for n in names}
    son._any = NS(visible_zones=set(spk.values()))
    return son, spk


def test_set_group_joins_members_and_unjoins_others(tmp_path):
    son, s = make(tmp_path, "Kitchen", "Study", "Patio")
    s["Kitchen"].group.members = {s["Kitchen"], s["Patio"]}  # Patio is stuck in the group
    coord = son.set_group(["Kitchen", "Study"])
    assert coord is s["Kitchen"]
    s["Study"].join.assert_called_once_with(s["Kitchen"])
    s["Patio"].unjoin.assert_called_once()
    s["Kitchen"].unjoin.assert_not_called()  # already a coordinator
    s["Study"].unjoin.assert_not_called()


def test_non_coordinator_first_member_is_split_out_first(tmp_path):
    son, s = make(tmp_path, "Kitchen", "Study")
    s["Kitchen"].is_coordinator = False
    s["Kitchen"].group.members = {s["Kitchen"]}
    son.set_group(["Kitchen", "Study"])
    s["Kitchen"].unjoin.assert_called_once()


def test_group_survives_restart_and_offline_speakers_are_skipped(tmp_path):
    son, _ = make(tmp_path, "Kitchen", "Study")
    son.set_group(["Kitchen", "Study"])

    restarted, s = make(tmp_path, "Study")  # Kitchen is offline now
    assert restarted.group_names == ["Kitchen", "Study"]  # still remembered
    s["Study"].group.members = {s["Study"]}
    assert restarted.coordinator() is s["Study"]
    assert "Kitchen" not in restarted.zones()


def test_no_online_members_returns_none(tmp_path):
    son, _ = make(tmp_path, "Study")
    assert son.set_group(["Kitchen"]) is None
    assert son.now_playing() is None


def test_play_songs_replaces_queue_and_starts_at_index(tmp_path):
    son, s = make(tmp_path, "Kitchen")
    s["Kitchen"].group.members = {s["Kitchen"]}
    song = NS(title="Low Ceiling", artist="The Meridians", album="Blue Hour", content_type="audio/flac", duration=320)
    son.set_group(["Kitchen"])
    son.play_songs([("http://nd/stream?id=1", song)], start=0)
    k = s["Kitchen"]
    k.clear_queue.assert_called_once()
    (items,), _ = k.add_multiple_to_queue.call_args
    assert items[0].title == "Low Ceiling"
    assert items[0].resources[0].uri == "http://nd/stream?id=1"
    assert "audio/flac" in items[0].resources[0].protocol_info
    assert items[0].resources[0].duration == "0:05:20"
    assert k.play_mode == "NORMAL"
    k.play_from_queue.assert_called_once_with(0)
