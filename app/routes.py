from flask import Blueprint, Response, abort, current_app, render_template, request
from libopensonic.errors import SonicError

from . import navidrome
from .sonos import NoRoom

bp = Blueprint("main", __name__)

PAGE = 48  # a multiple of both wall widths (3 phone, 8 desktop) so rows stay full
RAIL = 15  # genres shown as chips; the rest are in the "all genres" sheet


def _nd():
    return current_app.extensions["nd"]


def _genres():
    return sorted((g for g in _nd().get_genres() if g.album_count), key=lambda g: -g.album_count)


def _albums(genre: str, q: str, offset: int):
    if q:
        return _nd().search3(q, artist_count=0, song_count=0, album_count=PAGE, album_offset=offset).album or []
    if genre:
        return _nd().get_album_list2("byGenre", size=PAGE, offset=offset, genre=genre)
    return _nd().get_album_list2("alphabeticalByArtist", size=PAGE, offset=offset)


@bp.get("/")
def index():
    genre, q = request.args.get("genre", ""), request.args.get("q", "")
    if request.args.get("lists"):
        return render_template("index.html", genres=_genres(), rail=RAIL, q="", genre="", current="Lists",
                               playlists=_nd().get_playlists(), albums=[], next=None)
    return render_template("index.html", genres=_genres(), rail=RAIL, q=q, genre=genre,
                           current=q or genre or "All", **_page(genre, q, 0))


@bp.get("/playlists")
def playlists():
    return render_template("_wall.html", oob=True, current="Lists", playlists=_nd().get_playlists(),
                           albums=[], next=None)


@bp.app_template_filter("mmss")
def mmss(seconds):
    return f"{(seconds or 0) // 60}:{(seconds or 0) % 60:02d}"


def _detail(kind, item, songs, sub, meta):
    sonos = current_app.extensions["sonos"]
    rooms, saved = sorted(sonos.zones()), sonos.group_names
    return render_template(
        "_detail.html", kind=kind, item=item, songs=songs, sub=sub, meta=meta, rooms=rooms,
        room=saved[0] if saved and saved[0] in rooms else "",
        follow_on=current_app.extensions["player"].follow_on_default,
    )


@bp.get("/album/<album_id>")
def album(album_id):
    try:
        a = _nd().get_album(album_id)
    except SonicError:
        abort(404)
    meta = " · ".join(str(x) for x in (a.year, a.genre, f"{a.song_count} tracks", f"{round(a.duration / 60)} min") if x)
    return _detail("album", a, a.song or [], a.artist, meta)


@bp.get("/playlist/<playlist_id>")
def playlist(playlist_id):
    try:
        p = _nd().get_playlist(playlist_id)
    except SonicError:
        abort(404)
    return _detail("playlist", p, p.entry or [], "Playlist", f"{p.song_count} tracks · {round((p.duration or 0) / 60)} min")


@bp.post("/play/<kind>/<item_id>")
def play(kind, item_id):
    player = current_app.extensions["player"]
    start = request.args.get("start", 0, type=int)
    try:
        {"album": player.play_album, "playlist": player.play_playlist}[kind](item_id, start)
    except KeyError:
        abort(404)
    except NoRoom as e:
        return str(e), 409
    return "", 204


@bp.post("/group")
def group():
    room = request.form.get("room", "")
    if room not in current_app.extensions["sonos"].zones():
        abort(404)
    current_app.extensions["sonos"].set_group([room])
    return "", 204


@bp.post("/follow-on")
def follow_on():
    """Flip what the *next* play does after the album/playlist ends (never touches the current queue)."""
    player = current_app.extensions["player"]
    player.follow_on_default = not player.follow_on_default
    return render_template("_follow.html", kind=request.args.get("kind", "album"), follow_on=player.follow_on_default)


@bp.get("/albums")
def albums():
    """Wall fragment: first page swaps the wall (and the pinned genre chip); later pages append."""
    genre, q = request.args.get("genre", ""), request.args.get("q", "")
    offset = request.args.get("offset", 0, type=int)
    return render_template("_wall.html", oob=offset == 0, current=q or genre or "All",
                           genre=genre, q=q, **_page(genre, q, offset))


def _page(genre, q, offset):
    albums = _albums(genre, q, offset)
    return {"albums": albums, "next": offset + PAGE if len(albums) == PAGE else None}


@bp.get("/healthz")
def healthz():
    return {"status": "ok"}


@bp.get("/cover/<cover_id>")
def cover(cover_id):
    r = navidrome.cover_art(
        current_app.extensions["hm_config"], cover_id, request.args.get("size", type=int)
    )
    if not r.ok or not r.headers.get("Content-Type", "").startswith("image/"):
        abort(404)
    # Covers rarely change; let the browser cache the wall.
    return Response(
        r.content,
        content_type=r.headers["Content-Type"],
        headers={"Cache-Control": "public, max-age=86400"},
    )
