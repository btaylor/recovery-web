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
