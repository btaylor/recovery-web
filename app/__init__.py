from flask import Flask

from .config import Config


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)
    app.extensions["hm_config"] = config or Config.from_env()

    from .routes import bp

    app.register_blueprint(bp)
    return app
