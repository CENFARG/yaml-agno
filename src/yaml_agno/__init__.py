"""yaml-agno: declarative YAML-driven agent orchestration on top of Agno."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("yaml-agno")
except PackageNotFoundError:  # pragma: no cover - editable install fallback
    __version__ = "0.0.0"

__all__ = ["__version__"]
