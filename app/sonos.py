"""Sonos control. SoCo already does transport (play/pause/next/previous/seek) and
volume (`speaker.volume`, and `coordinator.group.volume` for a proportional master),
so use those directly. This adds only what the app needs on top: the persisted
playback group and loading songs into the queue."""
import json
import logging
import time
from datetime import timedelta
from pathlib import Path

import requests
import soco
from soco import config as soco_config
from soco.exceptions import SoCoException
from soco.data_structures import DidlMusicTrack, DidlResource

# SoCo waits 20s by default; with pollers hitting speakers every 2-3s, one vanished
# speaker would stall the whole UI. Speakers on a LAN answer in milliseconds.
soco_config.REQUEST_TIMEOUT = 5

REDISCOVER_AFTER = 10  # seconds to wait before searching again when no speaker was found

log = logging.getLogger(__name__)


class NoRoom(RuntimeError):
    """No online speaker in the playback group."""


class Sonos:
    def __init__(self, state_dir: str):
        self._state = Path(state_dir) / "sonos.json"
        self._any = None
        self._next_search = 0.0
        self._names = None  # the group in memory; the file only exists to survive restarts

    def zones(self) -> dict[str, soco.SoCo]:
        """Online speakers by room name. Offline ones are simply absent."""
        for _ in range(2):
            if self._any is None:
                if time.monotonic() < self._next_search:
                    return {}
                self._any = soco.discovery.any_soco()
                if self._any is None:
                    self._next_search = time.monotonic() + REDISCOVER_AFTER
                    return {}
            try:
                return {z.player_name: z for z in self._any.visible_zones}
            except (requests.RequestException, SoCoException):
                self._any = None  # the speaker we asked went away; find another one
        return {}

    @property
    def group_names(self) -> list[str]:
        if self._names is not None:
            return self._names
        try:
            return json.loads(self._state.read_text())["group"]
        except (OSError, ValueError, KeyError):
            return []

    def _save(self, names: list[str]) -> None:
        self._names = list(names)
        try:
            self._state.parent.mkdir(parents=True, exist_ok=True)
            self._state.write_text(json.dumps({"group": names}))
        except OSError as e:
            # Still works, it just won't survive a restart. Usually a volume owned by another user.
            log.warning("Can't save the playback group to %s (%s). It will be forgotten when the "
                        "app restarts; check the permissions of STATE_DIR.", self._state, e)

    def set_group(self, names: list[str]) -> soco.SoCo | None:
        """Make `names` the playback group (first online one coordinates) and persist it.
        Names that are offline are kept in the saved group but skipped for now."""
        self._save(names)
        zones = self.zones()
        members = [zones[n] for n in names if n in zones]
        if not members:
            return None
        coord, rest = members[0], members[1:]
        if not coord.is_coordinator:
            coord.unjoin()
        for z in rest:
            z.join(coord)
        for z in zones.values():
            if z not in members and z in coord.group.members:
                z.unjoin()
        return coord

    def coordinator(self) -> soco.SoCo | None:
        """The coordinator of the saved group, as it is right now. Read-only, cheap enough to poll."""
        zones = self.zones()
        online = [zones[n] for n in self.group_names if n in zones]
        return online[0].group.coordinator if online else None

    def mixer(self) -> dict:
        """Everything the speaker mixer shows: master, grouped rooms with volumes, other rooms."""
        zones = self.zones()
        names = [n for n in self.group_names if n in zones]
        coord = self.coordinator()
        return {
            "master": coord.group.volume if coord else 0,
            "grouped": [(n, zones[n].volume) for n in names],
            "others": [n for n in sorted(zones) if n not in names],
        }

    def label(self) -> str:
        """Short room label for the mini bar: "Kitchen", "Kitchen +2"."""
        zones = self.zones()
        names = [n for n in self.group_names if n in zones]
        return "" if not names else names[0] + (f" +{len(names) - 1}" if len(names) > 1 else "")

    def transport(self, action: str) -> None:
        coord = self.coordinator()
        if coord is None:
            return
        try:
            if action == "toggle":
                playing = coord.get_current_transport_info()["current_transport_state"] == "PLAYING"
                (coord.pause if playing else coord.play)()
            elif action == "next":
                coord.next()
            elif action == "prev":
                coord.previous()
        except SoCoException:  # e.g. next at the end of the queue
            pass

    def play_songs(self, urls_and_songs, start: int = 0) -> None:
        """Replace the queue with (stream_url, song) pairs and play from index `start`."""
        coord = self.set_group(self.group_names)  # re-assert the group before starting
        if coord is None:
            raise NoRoom("Choose a room first")
        coord.clear_queue()
        coord.play_mode = "NORMAL"  # albums play in order, whatever the speaker was left on
        coord.add_multiple_to_queue([_didl(url, s) for url, s in urls_and_songs])
        coord.play_from_queue(start)

    def append_songs(self, urls_and_songs) -> None:
        self.coordinator().add_multiple_to_queue([_didl(url, s) for url, s in urls_and_songs])

    def truncate_queue(self, keep: int) -> None:
        """Drop everything after the first `keep` queue items (playback continues)."""
        coord = self.coordinator()
        extra = coord.queue_size - keep
        if extra > 0:
            coord.avTransport.RemoveTrackRangeFromQueue(
                [("InstanceID", 0), ("UpdateID", 0), ("StartingIndex", keep + 1), ("NumberOfTracks", extra)]
            )

    def now_playing(self) -> dict | None:
        coord = self.coordinator()
        if coord is None:
            return None
        t = coord.get_current_track_info()
        return {
            "title": t["title"], "artist": t["artist"], "album": t["album"],
            "position": t["position"], "duration": t["duration"],
            "index": int(t["playlist_position"]) - 1,
            "state": coord.get_current_transport_info()["current_transport_state"],
        }


def _didl(url: str, song) -> DidlMusicTrack:
    mime = song.content_type or "audio/mpeg"
    return DidlMusicTrack(
        title=song.title, parent_id="-1", item_id="-1",
        creator=song.artist or "", album=song.album or "",
        resources=[DidlResource(
            uri=url, protocol_info=f"http-get:*:{mime}:*",
            duration=str(timedelta(seconds=song.duration or 0)),
        )],
    )
