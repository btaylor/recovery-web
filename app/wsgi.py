import logging

from . import create_app

app = create_app()

# Bring the saved playback group back after a restart; the network may not be ready.
try:
    app.extensions["sonos"].coordinator()
except Exception:
    logging.getLogger(__name__).warning("Could not restore Sonos group", exc_info=True)
