from flask import Blueprint, Response, abort, current_app, render_template, request

from . import navidrome

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


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
