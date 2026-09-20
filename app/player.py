"""Playback orchestration. There is no user-visible queue: an album (or playlist) plays
through, then a mix seeded from its last song continues. The mix is appended to the
Sonos queue up front so the handoff is gapless; "stop after" just removes it again."""
from . import navidrome

MIX_SIZE = 50
BANNER_SECONDS = 30


def _seconds(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


class Player:
    def __init__(self, nd, sonos):
        self.nd, self.sonos = nd, sonos
        self.follow_on_default = True  # what the next play does; set from the album screen
        self.follow_on = True          # whether the queue that is playing now has a mix
        self.songs = []         # what is in the Sonos queue, in order
        self.source_len = 0     # how many of those are the album/playlist (rest is the mix)
        self.label = ""

    def play_album(self, album_id: str, start: int = 0, follow_on: bool | None = None) -> None:
        a = self.nd.get_album(album_id)
        self._play(a.song, start, follow_on, a.name)

    def play_playlist(self, playlist_id: str, start: int = 0, follow_on: bool | None = None) -> None:
        p = self.nd.get_playlist(playlist_id)
        self._play(p.entry, start, follow_on, p.name)

    def _play(self, songs, start, follow_on, label=""):
        if not songs:  # e.g. an empty playlist
            return
        self.follow_on = self.follow_on_default if follow_on is None else follow_on
        self.label = label  # name of the album/playlist, for "Blue Hour · 3 of 9" and "Mix from Blue Hour"
        self.songs, self.source_len = list(songs), len(songs)
        if self.follow_on:
            self.songs += self._mix(songs)
        self.sonos.play_songs(self._pairs(self.songs), start)

    def set_follow_on(self, on: bool) -> None:
        """Turn the mix on/off for what is playing now ("stop after" is off)."""
        if on == self.follow_on:
            return
        self.follow_on = on
        if not self.songs:
            return
        if on:
            mix = self._mix(self.songs[: self.source_len])
            self.songs += mix
            self.sonos.append_songs(self._pairs(mix))
        else:
            self.songs = self.songs[: self.source_len]
            self.sonos.truncate_queue(self.source_len)

    def _mix(self, source):
        seed, seen = source[-1], {s.id for s in source}
        songs = self.nd.get_similar_songs2(seed.id, MIX_SIZE)
        if not songs:  # no similarity data: fall back to the same genre
            songs = self.nd.get_random_songs(MIX_SIZE, genre=seed.genre)
        return [s for s in songs if s.id not in seen]

    def _pairs(self, songs):
        return [(navidrome.stream_url(self.nd, s.id), s) for s in songs]

    def status(self) -> dict | None:
        np = self.sonos.now_playing()
        if np is None or not 0 <= np["index"] < len(self.songs):
            return np
        song = self.songs[np["index"]]
        dur = _seconds(np["duration"])
        left = dur - _seconds(np["position"])
        np["pct"] = round(100 * _seconds(np["position"]) / dur) if dur else 0
        np["source"] = self.label
        np["of"] = (np["index"] + 1, self.source_len) if np["index"] < self.source_len else None
        np["song"] = song
        np["starred"] = bool(self.nd.get_song(song.id).starred)
        np["follow_on"] = self.follow_on
        # Last track of the source, mix coming: warn so it can be refused ("stop after").
        np["handoff"] = (
            self.follow_on and np["index"] == self.source_len - 1 and left <= BANNER_SECONDS
        ) and {"in": left}
        return np

    def toggle_star(self, song_id: str) -> bool:
        """Favourite / unfavourite a song in Navidrome; returns the new state."""
        if self.nd.get_song(song_id).starred:
            self.nd.unstar([song_id])
            return False
        self.nd.star([song_id])
        return True

    def star_current(self) -> None:
        np = self.sonos.now_playing()
        if np and 0 <= np["index"] < len(self.songs):
            self.toggle_star(self.songs[np["index"]].id)
