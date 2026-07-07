"""Smoke test: package is importable and version metadata is wired correctly."""

import yaml_agno


def test_package_version_matches_pyproject() -> None:
    """yaml_agno.__version__ MUST resolve to the version declared in pyproject.toml."""
    assert yaml_agno.__version__ == "0.1.0"


def test_package_is_importable() -> None:
    """The package namespace MUST be importable after pip install -e ."""
    assert hasattr(yaml_agno, "__version__")
    assert isinstance(yaml_agno.__version__, str)
    assert yaml_agno.__version__  # non-empty
