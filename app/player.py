"""Playback orchestration. There is no user-visible queue: an album (or playlist) plays
through, then a mix seeded from its last song continues. The album starts straight away;
the mix is built in the background and appended to the Sonos queue when it is ready, which
is still ahead of the album's end, so the handoff stays gapless. "stop after" removes it again."""
import logging
import threading

from . import navidrome
from .errors import NAVIDROME

MIX_SIZE = 50
BANNER_SECONDS = 30

log = logging.getLogger(__name__)


def _seconds(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def _in_background(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


class Player:
    def __init__(self, nd, sonos):
        self.nd, self.sonos = nd, sonos
        self.follow_on_default = True  # what the next play does; set from the album screen
        self.follow_on = True          # whether the queue that is playing now has a mix
        self.songs = []         # what is in the Sonos queue, in order
        self.source_len = 0     # how many of those are the album/playlist (rest is the mix)
        self.label = ""
        self._found = {}        # (title, artist, album) -> Navidrome song, or None, for tracks this app didn't queue
        self._lock = threading.Lock()  # guards songs against the background mix
        self._gen = 0                  # bumped by each new play; a mix for an older play is dropped
        self._run = _in_background     # tests run this inline

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
        with self._lock:
            self.songs, self.source_len = list(songs), len(songs)
            self._gen += 1
        self.sonos.play_songs(self._pairs(self.songs), start)  # the album starts without waiting on the mix
        if self.follow_on:
            self._mix_later()

    def set_follow_on(self, on: bool) -> None:
        """Turn the mix on/off for what is playing now ("stop after" is off)."""
        if on == self.follow_on:
            return
        self.follow_on = on
        if not self.songs:
            return
        if on:
            self._mix_later()
        else:
            with self._lock:
                self.songs = self.songs[: self.source_len]
            self.sonos.truncate_queue(self.source_len)

    def _mix_later(self) -> None:
        with self._lock:
            gen, source = self._gen, list(self.songs[: self.source_len])
        self._run(self._add_mix, gen, source)

    def _add_mix(self, gen: int, source: list) -> None:
        """Runs in the background. A failed or slow lookup just leaves the mix out: the album plays on alone."""
        try:
            mix = self._mix(source)
        except Exception:
            log.warning("Couldn't build the mix after this album; it will play the album only", exc_info=True)
            return
        with self._lock:
            # Only if this is still the play that is on, the mix is still wanted, and it isn't in yet.
            if gen != self._gen or not self.follow_on or len(self.songs) != self.source_len or not mix:
                return
            self.songs += mix
            self.sonos.append_songs(self._pairs(mix))

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
        if np is None:
            return None
        song = self._queued_song(np)
        if song is None:
            # Not something this app queued (the Sonos app, or before a restart): the library song found by
            # title gives the cover and the favourite.
            np["song"] = self._library_song(np)
            np["cover"] = np["song"].cover_art if np["song"] else None
            np["starred"] = bool(np["song"] and np["song"].starred)
            return np
        dur = _seconds(np["duration"])
        left = dur - _seconds(np["position"])
        np["pct"] = round(100 * _seconds(np["position"]) / dur) if dur else 0
        np["source"] = self.label
        np["of"] = (np["index"] + 1, self.source_len) if np["index"] < self.source_len else None
        np["song"] = song
        np["cover"] = song.cover_art
        np["starred"] = bool(song.starred)  # from the song already in memory; no Navidrome call per poll
        np["follow_on"] = self.follow_on
        # Last track of the source, mix coming: warn so it can be refused ("stop after").
        np["handoff"] = (
            self.follow_on and np["index"] == self.source_len - 1 and left <= BANNER_SECONDS
        ) and {"in": left}
        return np

    def _queued_song(self, np):
        """The queued song, if it is the track that is playing. The index alone isn't enough: another queue
        (the Sonos app, or one from before a restart) can have a track at the same index."""
        if not 0 <= np["index"] < len(self.songs):
            return None
        song = self.songs[np["index"]]
        return song if (song.title, song.artist or "") == (np["title"], np["artist"]) else None

    def _library_song(self, np):
        """The Navidrome song for a track this app didn't queue, found by title, artist and album. Cached per
        track so the 2-3s polls don't search again; a failed search isn't cached, so the next poll retries."""
        key = (np["title"], np["artist"], np["album"])
        if key not in self._found:
            try:
                hits = self.nd.search3(np["title"], artist_count=0, album_count=0, song_count=20).song or []
            except NAVIDROME:
                return None
            match = next((s for s in hits if (s.title, s.artist, s.album) == key), None)
            if len(self._found) > 500:
                self._found.clear()
            self._found[key] = match
        return self._found[key]

    def toggle_star(self, song) -> bool:
        """Favourite / unfavourite a song in Navidrome; updates the in-memory copy so later
        polls see it without asking Navidrome again, and returns the new state."""
        new = not song.starred
        (self.nd.star if new else self.nd.unstar)([song.id])
        song.starred = "1" if new else None  # any truthy value reads as starred; the real field is a timestamp
        return new

    def star_current(self) -> None:
        np = self.sonos.now_playing()
        if not np:
            return
        song = self._queued_song(np) or self._library_song(np)
        if song:
            self.toggle_star(song)
