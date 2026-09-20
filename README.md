# House Music

Album-centric Navidrome front-end that plays to the home's Sonos speakers via SoCo.
Flask + htmx. Playback is UPnP-only; there is no local audio.

## Configuration

Set in the environment (see `.env.example`):

| Variable | Required | Notes |
|---|---|---|
| `ND_URL` | yes | e.g. `http://navidrome.local:4533` |
| `ND_USER` | yes | |
| `ND_PASS` | yes | |
| `STATE_DIR` | no | persisted speaker group / preferences (default `./data`) |
| `PORT` | no | default 8000 |

The app exits at startup if a required variable is missing.

## Networking

The host must be on the same LAN as the Sonos speakers (SSDP discovery), and
Navidrome must be reachable **from the speakers**, since they fetch audio directly.
`docker-compose.yml` uses `network_mode: host` for this.

## Run

    python -m venv .venv && . .venv/bin/activate
    pip install -e '.[dev]'
    set -a; . ./.env; set +a
    flask --app app.wsgi run --port 8000
    pytest

Or: `docker compose up --build`.

## Code layout

- `app/navidrome.py` – builds a [py-opensonic](https://pypi.org/project/py-opensonic/) `Connection`
  (available as `app.extensions["nd"]`), plus a stream-URL helper and a cover-art fetch.
- `/cover/<id>?size=N` – cover-art proxy with browser caching.
- `app/sonos.py` – SoCo wrapper: online speakers by room name, the persisted playback group
  (`STATE_DIR/sonos.json`), and loading songs into the queue. Transport and volume use SoCo directly
  (`coordinator.play()`, `speaker.volume`, `coordinator.group.volume` for the proportional master).
- `app/player.py` – playback orchestration (`app.extensions["player"]`): play an album/playlist with the
  mix from `getSimilarSongs2` (genre fallback) appended up front for a gapless handoff; "stop after" removes
  it; `status()` adds the current song, ♥ state and the ~30s handoff banner; `toggle_star()`.
  The follow-on setting is in-memory (resets on restart).
- `app/routes.py` + `templates/` – browse UI. `/` renders the wall; `/albums` returns wall fragments
  (genre / search / `offset` paging) that htmx swaps in, with infinite scroll via `hx-trigger="revealed"`.
  Genre chips, the "⌄ N" sheet (HTML `popover`, no JS) and search all drive the same fragment.
- Album / playlist detail is a panel (`#detail`) swapped in over the wall, so the wall's scroll position
  survives. `POST /play/<album|playlist>/<id>?start=N` plays (tapping a track = `start`), `POST /group`
  picks the room, `POST /follow-on` flips what the *next* play does after the source ends.
- Mini bar (`/player`) and now-playing (`/now`) poll themselves with htmx (2–3s) and refresh instantly
  when an action answers with `HX-Trigger: refresh`. The mixer (`/mixer`) is not polled, so sliders
  aren't disturbed. Master volume uses Sonos group volume (proportional). The first room anchors the group.
- Desktop shortcuts (`static/js/keys.js`): space play/pause, ←/→ previous/next, +/- volume.
