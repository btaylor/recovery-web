# Play

An album-first web player for a [Navidrome](https://www.navidrome.org/) library that plays to the
home's Sonos speakers. Flask + htmx + [SoCo](https://github.com/SoCo/SoCo). There is no local audio:
the browser is only a remote control, and the speakers fetch the music from Navidrome themselves.

- Edge-to-edge cover wall with a genre rail, search and playlists ("▤ Lists").
- Tap an album to play it start to finish; when it ends a mix seeded from its last song continues
  (`getSimilarSongs2`, falling back to the same genre). Tap a track to start the album from there.
- Mini player, now-playing screen, and a mixer with a slider per room plus a proportional master.
- ♥ favourites are stored in Navidrome. The room group survives restarts; offline speakers are hidden.

## Configuration

Set these in the environment (copy `.env.example` to `.env`):

| Variable | Required | Notes |
|---|---|---|
| `ND_URL` | yes | e.g. `http://navidrome.local:4533` |
| `ND_USER` | yes | |
| `ND_PASS` | yes | |
| `STATE_DIR` | no | where the playback group is saved (default `./data`, `/data` in Docker) |
| `PORT` | no | default 8000 (Docker) |

The app refuses to start if a required variable is missing.

## Networking (read this first)

- **The app must be on the same LAN as the speakers.** SoCo finds them with SSDP multicast.
- **Navidrome must be reachable from the speakers**, not just from the app: Sonos downloads each
  track from the stream URL itself. Use a hostname or IP the speakers can resolve, in `ND_URL`.
- The stream URLs carry a Subsonic token and salt (never the password) in the query string,
  because Sonos can't send auth headers.
- **Docker:** `docker-compose.yml` uses `network_mode: host` so multicast works. That works on a
  Linux host or NAS. Docker Desktop on macOS/Windows runs containers in a VM and does not put them on
  your LAN, so run the app natively there. Host networking also means the app takes a port on the host
  itself (`PORT`, default 8000) and `ports:` in compose has no effect. If something already uses 8000 you'll
  see `Address already in use` in `docker logs`; set another port, e.g. `PORT=8123` in `.env`.
- **There is no login.** Anyone who can reach the port can control your speakers. Keep it on the LAN.

## Run

Natively:

    python -m venv .venv && . .venv/bin/activate
    pip install -e '.[dev]'
    set -a; . ./.env; set +a
    flask --app app.wsgi run --port 8000

With Docker (Linux host), using the published image (`linux/amd64` and `linux/arm64`):

    cp .env.example .env   # then edit it
    docker compose pull && docker compose up -d

To build from source instead: `docker compose up --build -d`. To update later, run the pull and up
commands again.

Then open `http://<host>:8000`. Tests: `pytest`.

Run a single worker (the Dockerfile does): the player remembers what it queued in memory.

## Using it

- **Wall:** genre chips scroll sideways; "⌄ N" lists every genre with album counts; ⌕ searches.
  Long-press (or hover on desktop) a cover to see its title. The "All" wall is a fresh random shuffle
  every time the page loads (Navidrome's `random` list; genre views keep Navidrome's own order).
  Scrolling far can occasionally repeat an album, because the API doesn't define paging for `random`.
- **Album / playlist:** opens as a panel over the wall, so your scroll position is kept.
  "Then: mix from this album — change" sets what happens after it ends, for the next play.
- **Rooms:** pick a room in the album panel, or tap the room name in the mini bar to open the mixer.
  Tick other rooms to bring them into the group (they join mid-track). The first room anchors the group.
- **Now playing:** tap the mini bar. The "After this album" switch changes the mix for the current queue;
  on the last track a banner counts down to the mix and offers "stop after".
- **Desktop keys:** space play/pause, ←/→ previous/next, `+`/`-` volume. (Browsers can't see hardware
  volume keys, so those aren't supported.)

## Install it as an app

Play is an installable web app (it has a manifest and icons, and no service worker):

- **iPhone / iPad:** open it in Safari, tap Share, then **Add to Home Screen**. It opens full-screen like an app.
- **Mac:** open it in Safari (macOS 14 or later), then **File → Add to Dock**.

Use an address that won't change (a fixed IP or a hostname): an installed app is tied to the address it
was installed from. Plain `http://` on the LAN is fine for installing. It needs no HTTPS, but there is
also no offline mode, since the app is only a remote control and needs the server.

## When things go wrong

- **Navidrome unreachable or wrong login:** a full page says so (with a hint) on navigation; failed
  actions show a short toast. The mini bar and now-playing keep polling and show "Nothing playing"
  until things recover. Covers just don't load.
- **A speaker vanishes:** it disappears from the room list. Actions that reach it show
  "Can't reach the speaker." Speaker requests time out after 5 seconds (SoCo's default is 20).
  If no speaker is found the app searches again at most every 10 seconds.
- **No room chosen:** Play says "Choose a room first".

## Known limits

- The "then: mix / stop" default resets to "mix" when the app restarts.
- After a restart the app no longer knows what it queued, so the now-playing cover, ♥ and handoff banner
  come back on the next play. Sonos keeps playing meanwhile.
- Joining a room that is grouped in the Sonos app (e.g. a home-theatre set) pulls it out of that group.
- Genres with fewer than 3 albums (`MIN_GENRE_ALBUMS` in `app/routes.py`) are left out of the genre rail
  and sheet, with a note in the sheet saying how many. Their albums still appear under "All" and in search.
- Genre names are matched exactly, so "pop" and "Pop" are separate genres.

## Code layout

- `app/config.py` – environment settings.
- `app/navidrome.py` – builds a [py-opensonic](https://pypi.org/project/py-opensonic/) connection
  (`app.extensions["nd"]`), plus stream-URL and cover-art helpers.
- `app/sonos.py` – SoCo wrapper: online speakers by room name, the saved playback group
  (`STATE_DIR/sonos.json`), the mixer view, and loading songs into the queue. Transport and volume use
  SoCo directly.
- `app/player.py` – playback orchestration: album/playlist + mix, "stop after", status for the pollers, ♥.
- `app/routes.py`, `app/templates/`, `app/static/` – the UI. Pages are server-rendered; htmx swaps
  fragments (`/albums`, `/album/<id>`, `/player`, `/now/top`, `/mixer`, ...).
- `app/errors.py` – maps library exceptions to what the user sees.
- `tests/` – unit tests with mocked Navidrome and Sonos.
