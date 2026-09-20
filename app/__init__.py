from flask import Flask

from .config import Config
from .navidrome import make_client


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)
    cfg = app.extensions["hm_config"] = config or Config.from_env()
    app.extensions["nd"] = make_client(cfg)

    from .routes import bp

    app.register_blueprint(bp)
    return app
