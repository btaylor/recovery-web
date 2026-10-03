"""What the user sees when Navidrome or a speaker can't be reached.

Exception types come from the libraries' own docs/source:
- py-opensonic lets aiohttp's errors through (`ClientError`, `TimeoutError`) and raises
  `SonicError` subclasses for errors Navidrome reports (wrong login, not found, ...).
- SoCo raises `SoCoException` for UPnP faults and `requests.RequestException` when a
  speaker doesn't answer.
The cover-art proxy uses `requests` for Navidrome and handles its own failures.
"""
import logging

import aiohttp
import requests
from flask import render_template, request
from libopensonic.errors import AuthError, CredentialError, SonicError
from soco.exceptions import SoCoException

NAVIDROME = (aiohttp.ClientError, TimeoutError, SonicError)
SPEAKER = (requests.RequestException, SoCoException)

# The toast doesn't say why, so the server log is the only record of the underlying error.
log = logging.getLogger(__name__)


def _fail(message: str, hint: str = ""):
    """502 for htmx calls (shown as a toast by toast.js); a full page for normal navigation."""
    if request.headers.get("HX-Request"):
        return message, 502, {"Content-Type": "text/plain; charset=utf-8"}
    return render_template("error.html", message=message, hint=hint), 502


def _navidrome(e):
    log.warning("Navidrome failed on %s %s: %r", request.method, request.path, e)
    if isinstance(e, (AuthError, CredentialError)):
        return _fail("Navidrome rejected the username or password.", "Check ND_USER and ND_PASS.")
    return _fail("Can't reach Navidrome.", "Check that it's running and that ND_URL is right.")


def _speaker(e):
    log.warning("Speaker failed on %s %s: %r", request.method, request.path, e)
    return _fail("Can't reach the speaker.", "It may be offline. Reload to look for speakers again.")


def register(app):
    for exc in NAVIDROME:
        app.register_error_handler(exc, _navidrome)
    for exc in SPEAKER:
        app.register_error_handler(exc, _speaker)
