import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_pyproject():
    from app.version import __version__

    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert __version__ == declared


def test_wsgi_logs_the_version_before_creating_the_app():
    # Read the source rather than import wsgi.py directly: importing it for real runs
    # create_app() and Sonos discovery against the actual network, same as booting the app.
    src = (ROOT / "app" / "wsgi.py").read_text()
    assert 'logging.getLogger(__name__).warning("Play %s starting", __version__)' in src
    log_line, create_line = src.index("__version__"), src.index("create_app()")
    assert log_line < create_line  # logged even if create_app() then fails to start
