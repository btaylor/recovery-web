import logging

from . import create_app
from .version import __version__

logging.getLogger(__name__).warning("Play %s starting", __version__)  # warning: visible at gunicorn's default level

app = create_app()

# Bring the saved playback group back after a restart; the network may not be ready.
try:
    sonos = app.extensions["sonos"]
    sonos.set_group(sonos.group_names)
except Exception:
    logging.getLogger(__name__).warning("Could not restore Sonos group", exc_info=True)
