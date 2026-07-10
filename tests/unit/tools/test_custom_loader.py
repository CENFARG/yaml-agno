"""Unit tests for ``yaml_agno.tools.custom_loader`` — SPEC_11 slice A.

CustomToolLoader delegates class resolution to AgnoResolver.resolve_class
and returns RAW callables/classes (no @tool wrapping). Tested with a stubbed
resolver that records resolve_class calls.
"""

from __future__ import annotations

import pytest

from yaml_agno.tools.custom_loader import CustomToolLoader
from yaml_agno.tools.schema import CustomToolConfig, CustomToolkitConfig
from yaml_agno.tools.security import SecurityError


class _StubResolver:
    """Records resolve_class calls; returns a sentinel."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def resolve_class(self, module_path: str, class_name: str) -> type:
        self.calls.append((module_path, class_name))

        class _Sentinel:
            pass

        return _Sentinel


def _build_loader() -> tuple[CustomToolLoader, _StubResolver]:
    resolver = _StubResolver()
    return CustomToolLoader(resolver), resolver


@pytest.mark.unit
def test_load_callable_resolves_and_returns_raw() -> None:
    """load_callable delegates to resolve_class and returns the raw object."""
    loader, resolver = _build_loader()
    config = CustomToolConfig(path="agno.tools.calculator.add")
    result = loader.load_callable(config)
    assert resolver.calls == [("agno.tools.calculator", "add")]
    assert result.__name__ == "_Sentinel"  # raw, no @tool wrapping


@pytest.mark.unit
def test_load_toolkit_class_resolves() -> None:
    """load_toolkit_class resolves the class (uninstantiated)."""
    loader, resolver = _build_loader()
    config = CustomToolkitConfig(path="agno.tools.calculator.CalculatorTools")
    result = loader.load_toolkit_class(config)
    assert resolver.calls == [("agno.tools.calculator", "CalculatorTools")]
    assert isinstance(result, type)


@pytest.mark.unit
def test_non_allowlisted_module_raises_security_error() -> None:
    """A module outside agno.tools.* is rejected with SecurityError."""
    loader, _resolver = _build_loader()
    config = CustomToolConfig(path="evil_pkg.tools.steal")
    with pytest.raises(SecurityError, match="not in the tool allowlist"):
        loader.load_callable(config)


@pytest.mark.unit
def test_no_dot_in_path_raises_value_error() -> None:
    """A path without a module.name structure raises ValueError."""
    loader, _resolver = _build_loader()
    config = CustomToolConfig(path="nodot")
    with pytest.raises(ValueError, match="Invalid dotted path"):
        loader.load_callable(config)


@pytest.mark.unit
def test_load_mcp_raises_not_implemented() -> None:
    """MCP single-server resolution is DEFERRED to slice B (W3)."""
    from yaml_agno.tools.schema import McpToolConfig

    loader, _resolver = _build_loader()
    with pytest.raises(NotImplementedError, match="slice B"):
        loader.load_mcp(McpToolConfig())


@pytest.mark.unit
def test_load_mcp_multi_raises_not_implemented() -> None:
    """MultiMCPTools resolution is DEFERRED to slice B (W3)."""
    from yaml_agno.tools.schema import McpMultiToolConfig

    loader, _resolver = _build_loader()
    with pytest.raises(NotImplementedError, match="slice B"):
        loader.load_mcp_multi(McpMultiToolConfig())
