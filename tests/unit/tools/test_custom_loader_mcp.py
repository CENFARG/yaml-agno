"""Unit tests for CustomToolLoader MCP delegation — SPEC_11 slice B.

Covers load_mcp/load_mcp_multi delegation to MCPResolver, lazy construction
of the _mcp_resolver, and the no-NotImplementedError invariant.
"""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

from yaml_agno.tools.custom_loader import CustomToolLoader
from yaml_agno.tools.schema import (
    McpMultiToolConfig,
    StdioMcpConfig,
)


class _StubResolver:
    """Stub AgnoResolver for CustomToolLoader."""

    def resolve_class(self, module_path: str, class_name: str) -> type:
        class _Sentinel:
            pass

        return _Sentinel


def _build_loader() -> CustomToolLoader:
    return CustomToolLoader(_StubResolver())


# --- load_mcp delegation ----------------------------------------------------


@pytest.mark.unit
def test_load_mcp_delegates_to_resolve_single() -> None:
    """load_mcp delegates to MCPResolver.resolve_single."""
    loader = _build_loader()
    mock_mcp_resolver = MagicMock()
    sentinel = object()
    mock_mcp_resolver.resolve_single.return_value = sentinel
    loader._mcp_resolver = mock_mcp_resolver

    config = StdioMcpConfig(command="echo hi")
    result = loader.load_mcp(config)

    mock_mcp_resolver.resolve_single.assert_called_once_with(config)
    assert result is sentinel


@pytest.mark.unit
def test_load_mcp_does_not_raise_not_implemented() -> None:
    """load_mcp no longer raises NotImplementedError."""
    loader = _build_loader()
    # With a mock resolver, load_mcp should succeed.
    loader._mcp_resolver = MagicMock()
    loader._mcp_resolver.resolve_single.return_value = object()
    config = StdioMcpConfig(command="echo hi")
    result = loader.load_mcp(config)  # must NOT raise NotImplementedError
    assert result is not None


@pytest.mark.unit
def test_load_mcp_multi_delegates_to_resolve_multi() -> None:
    """load_mcp_multi delegates to MCPResolver.resolve_multi."""
    loader = _build_loader()
    mock_mcp_resolver = MagicMock()
    sentinel = object()
    mock_mcp_resolver.resolve_multi.return_value = sentinel
    loader._mcp_resolver = mock_mcp_resolver

    config = McpMultiToolConfig(servers=[StdioMcpConfig(command="echo hi")])
    result = loader.load_mcp_multi(config)

    mock_mcp_resolver.resolve_multi.assert_called_once_with(config)
    assert result is sentinel


@pytest.mark.unit
def test_load_mcp_multi_does_not_raise_not_implemented() -> None:
    """load_mcp_multi no longer raises NotImplementedError."""
    loader = _build_loader()
    loader._mcp_resolver = MagicMock()
    loader._mcp_resolver.resolve_multi.return_value = object()
    config = McpMultiToolConfig(servers=[StdioMcpConfig(command="echo hi")])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = loader.load_mcp_multi(config)
    assert result is not None


# --- Lazy construction ------------------------------------------------------


@pytest.mark.unit
def test_mcp_resolver_lazy_construction() -> None:
    """_get_mcp_resolver constructs the MCPResolver lazily (once)."""
    loader = _build_loader()
    assert loader._mcp_resolver is None  # not yet constructed
    resolver1 = loader._get_mcp_resolver()
    resolver2 = loader._get_mcp_resolver()
    assert resolver1 is resolver2  # same instance (cached)
    assert loader._mcp_resolver is not None  # now cached
