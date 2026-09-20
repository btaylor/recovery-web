"""Sonos control. SoCo already does transport (play/pause/next/previous/seek) and
volume (`speaker.volume`, and `coordinator.group.volume` for a proportional master),
so use those directly. This adds only what the app needs on top: the persisted
playback group and loading songs into the queue."""
import json
from datetime import timedelta
from pathlib import Path

import soco
from soco.data_structures import DidlMusicTrack, DidlResource


class NoRoom(RuntimeError):
    """No online speaker in the playback group."""


class Sonos:
    def __init__(self, state_dir: str):
        self._state = Path(state_dir) / "sonos.json"
        self._any = None

    def zones(self) -> dict[str, soco.SoCo]:
        """Online speakers by room name. Offline ones are simply absent."""
        if self._any is None:
            self._any = soco.discovery.any_soco()
            if self._any is None:
                return {}
        return {z.player_name: z for z in self._any.visible_zones}

    @property
    def group_names(self) -> list[str]:
        try:
            return json.loads(self._state.read_text())["group"]
        except (OSError, ValueError, KeyError):
            return []

    def set_group(self, names: list[str]) -> soco.SoCo | None:
        """Make `names` the playback group (first online one coordinates) and persist it.
        Names that are offline are kept in the saved group but skipped for now."""
        self._state.parent.mkdir(parents=True, exist_ok=True)
        self._state.write_text(json.dumps({"group": names}))
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
        return self.set_group(self.group_names)

    def play_songs(self, urls_and_songs, start: int = 0) -> None:
        """Replace the queue with (stream_url, song) pairs and play from index `start`."""
        coord = self.coordinator()
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
