from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("house-music")
except PackageNotFoundError:  # e.g. running straight from source with no install
    __version__ = "unknown"
