from flask import Flask

from .config import Config
from .navidrome import make_client
from .player import Player
from .sonos import Sonos


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)
    cfg = app.extensions["hm_config"] = config or Config.from_env()
    app.extensions["nd"] = make_client(cfg)
    app.extensions["sonos"] = Sonos(cfg.state_dir)
    app.extensions["player"] = Player(app.extensions["nd"], app.extensions["sonos"])

    from . import errors
    from .routes import bp

    errors.register(app)
    app.register_blueprint(bp)
    return app
