"""PyFr reference service."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("reference-service")
except PackageNotFoundError:  # pragma: no cover - only when not installed
    __version__ = "0.0.0"

__all__ = ["__version__"]
