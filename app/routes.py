from flask import Blueprint, Response, abort, current_app, render_template, request

from . import navidrome

bp = Blueprint("main", __name__)

PAGE = 48  # a multiple of both wall widths (3 phone, 8 desktop) so rows stay full


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
    return render_template("index.html", genres=_genres(), q=q, genre=genre,
                           current=q or genre or "All", **_page(genre, q, 0))


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
