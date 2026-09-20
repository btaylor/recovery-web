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
