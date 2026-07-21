"""Unit tests for MCPResolver — SPEC_11 slice B.

Covers resolve_single (stdio/http/SSE), timeout type branching (float vs
timedelta), header_provider allowlist resolution + SecurityError, resolve_multi
fan-out (mixed stdio+http), DeprecationWarning handling, and the UNCONNECTED
invariant (no connect() call).
"""

from __future__ import annotations

import inspect
import warnings
from datetime import timedelta
from typing import Any

import pytest
from agno.tools.mcp import MCPTools, MultiMCPTools
from agno.tools.mcp.params import SSEClientParams, StreamableHTTPClientParams

from yaml_agno.tools.mcp_resolver import MCPResolver
from yaml_agno.tools.schema import (
    HttpMcpConfig,
    McpMultiToolConfig,
    StdioMcpConfig,
)
from yaml_agno.tools.security import SecurityError

# --- Helpers -----------------------------------------------------------------


class _FakeResolver:
    """Stub AgnoResolver: returns a known callable for resolve_class."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def resolve_class(self, module_path: str, name: str) -> Any:
        self.calls.append((module_path, name))

        def _header_provider() -> dict[str, str]:
            return {"X-Test": "value"}

        return _header_provider


def _make_resolver() -> tuple[MCPResolver, _FakeResolver]:
    fake = _FakeResolver()
    return MCPResolver(fake), fake


# --- resolve_single: stdio ---------------------------------------------------


@pytest.mark.unit
def test_resolve_single_stdio_returns_unconnected_mcp_tools() -> None:
    """resolve_single stdio returns MCPTools, NOT connected.

    MCPTools stores the command inside server_params (StdioServerParameters).
    """
    resolver, _ = _make_resolver()
    config = StdioMcpConfig(command="uvx mcp-server-git", env={"CUSTOM_VAR": "val"})
    result = resolver.resolve_single(config)
    assert isinstance(result, MCPTools)
    # The command is parsed into StdioServerParameters.command + .args.
    sp = result.server_params
    assert sp.command == "uvx"
    assert sp.args == ["mcp-server-git"]
    # env is merged with os.environ; verify our custom var is present.
    assert sp.env is not None
    assert sp.env.get("CUSTOM_VAR") == "val"
    # UNCONNECTED invariant: not initialized.
    assert not result.initialized


@pytest.mark.unit
def test_resolve_single_is_synchronous() -> None:
    """resolve_single is a SYNC function (not a coroutine)."""
    assert not inspect.iscoroutinefunction(MCPResolver.resolve_single)


@pytest.mark.unit
def test_resolve_single_stdio_does_not_call_connect() -> None:
    """resolve_single stdio must NOT call connect()."""
    resolver, _ = _make_resolver()
    config = StdioMcpConfig(command="echo hi")
    result = resolver.resolve_single(config)
    # MCPTools.connect is a coroutine; assert it was never invoked.
    assert not result.initialized


# --- resolve_single: http streamable-http -----------------------------------


@pytest.mark.unit
def test_resolve_single_streamable_http_builds_client_params() -> None:
    """resolve_single streamable-http constructs StreamableHTTPClientParams and
    passes server_params + transport to MCPTools."""
    resolver, _ = _make_resolver()
    config = HttpMcpConfig(
        transport="streamable-http",
        url="https://docs.agno.com/mcp",
        headers={"Authorization": "Bearer x"},
    )
    result = resolver.resolve_single(config)
    assert isinstance(result, MCPTools)
    assert isinstance(result.server_params, StreamableHTTPClientParams)
    assert result.server_params.url == "https://docs.agno.com/mcp"
    assert result.server_params.headers == {"Authorization": "Bearer x"}
    assert result.transport == "streamable-http"
    assert not result.initialized


@pytest.mark.unit
def test_resolve_single_streamable_http_timeout_is_timedelta() -> None:
    """StreamableHTTP timeout is wrapped into timedelta."""
    resolver, _ = _make_resolver()
    config = HttpMcpConfig(
        transport="streamable-http",
        url="https://docs.agno.com/mcp",
        timeout=30.0,
    )
    result = resolver.resolve_single(config)
    params = result.server_params
    assert isinstance(params, StreamableHTTPClientParams)
    assert isinstance(params.timeout, timedelta)
    assert params.timeout == timedelta(seconds=30)


# --- resolve_single: http SSE ------------------------------------------------


@pytest.mark.unit
def test_resolve_single_sse_builds_sse_client_params() -> None:
    """resolve_single SSE constructs SSEClientParams."""
    resolver, _ = _make_resolver()
    config = HttpMcpConfig(
        transport="sse",
        url="http://localhost:8000/sse",
        headers={"X-Custom": "1"},
    )
    result = resolver.resolve_single(config)
    assert isinstance(result, MCPTools)
    assert isinstance(result.server_params, SSEClientParams)
    assert result.server_params.url == "http://localhost:8000/sse"


@pytest.mark.unit
def test_resolve_single_sse_timeout_stays_float() -> None:
    """SSE timeout stays as float (NOT wrapped in timedelta)."""
    resolver, _ = _make_resolver()
    config = HttpMcpConfig(
        transport="sse",
        url="http://localhost:8000/sse",
        timeout=5.0,
    )
    result = resolver.resolve_single(config)
    params = result.server_params
    assert isinstance(params, SSEClientParams)
    assert params.timeout == 5.0
    assert isinstance(params.timeout, float)


# --- header_provider: allowlist resolution ----------------------------------


@pytest.mark.unit
def test_header_provider_resolved_via_allowlist() -> None:
    """header_provider under agno.tools.* prefix is resolved to a Callable."""
    resolver, _ = _make_resolver()
    config = HttpMcpConfig(
        transport="streamable-http",
        url="https://docs.agno.com/mcp",
        header_provider="agno.tools.mcp_headers.run_headers",
    )
    result = resolver.resolve_single(config)
    assert result.header_provider is not None
    assert callable(result.header_provider)


@pytest.mark.unit
def test_header_provider_none_no_security_error() -> None:
    """header_provider=None is a short path (no SecurityError)."""
    resolver, fake = _make_resolver()
    config = HttpMcpConfig(
        transport="sse",
        url="http://localhost:8000/sse",
    )
    resolver.resolve_single(config)
    # resolve_class should NOT have been called for header_provider.
    assert len(fake.calls) == 0


@pytest.mark.unit
def test_header_provider_not_allowlisted_raises_security_error() -> None:
    """header_provider with non-allowlisted module -> SecurityError."""
    resolver, _ = _make_resolver()
    config = HttpMcpConfig(
        transport="streamable-http",
        url="https://docs.agno.com/mcp",
        header_provider="evil.steal",
    )
    with pytest.raises(SecurityError, match="not in the tool allowlist"):
        resolver.resolve_single(config)


@pytest.mark.unit
def test_header_provider_no_dot_raises_value_error() -> None:
    """header_provider without dot structure -> ValueError."""
    resolver, _ = _make_resolver()
    config = HttpMcpConfig(
        transport="streamable-http",
        url="https://docs.agno.com/mcp",
        header_provider="nodot",
    )
    with pytest.raises(ValueError, match="Invalid dotted path"):
        resolver.resolve_single(config)


# --- resolve_multi ----------------------------------------------------------


@pytest.mark.unit
def test_resolve_multi_is_synchronous() -> None:
    """resolve_multi is a SYNC function (not a coroutine)."""
    assert not inspect.iscoroutinefunction(MCPResolver.resolve_multi)


@pytest.mark.unit
def test_resolve_multi_with_two_stdio_servers() -> None:
    """resolve_multi with 2 stdio servers -> MultiMCPTools with commands."""
    resolver, _ = _make_resolver()
    config = McpMultiToolConfig(
        servers=[
            StdioMcpConfig(command="echo hi"),
            StdioMcpConfig(command="echo bye"),
        ],
        allow_partial_failure=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = resolver.resolve_multi(config)
    assert isinstance(result, MultiMCPTools)
    assert result.commands == ["echo hi", "echo bye"]
    assert result.allow_partial_failure is True
    assert not result.initialized


@pytest.mark.unit
def test_resolve_multi_does_not_call_connect() -> None:
    """resolve_multi must NOT call connect()."""
    resolver, _ = _make_resolver()
    config = McpMultiToolConfig(servers=[StdioMcpConfig(command="echo hi")])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = resolver.resolve_multi(config)
    assert not result.initialized


@pytest.mark.unit
def test_resolve_multi_mixed_servers_populates_commands_and_params() -> None:
    """resolve_multi with 1 stdio + 1 http populates commands, urls, and server_params_list.

    MultiMCPTools internally converts commands into StdioServerParameters and
    merges them into server_params_list alongside the http params. So we check
    commands, urls, and that a StreamableHTTPClientParams is present in the list.
    """
    resolver, _ = _make_resolver()
    config = McpMultiToolConfig(
        servers=[
            StdioMcpConfig(command="echo hi"),
            HttpMcpConfig(
                transport="streamable-http",
                url="https://docs.agno.com/mcp",
            ),
        ]
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = resolver.resolve_multi(config)
    assert isinstance(result, MultiMCPTools)
    assert "echo hi" in (result.commands or [])
    assert result.urls == ["https://docs.agno.com/mcp"]
    # server_params_list contains BOTH the stdio-derived params AND the http params.
    assert result.server_params_list is not None
    http_params = [
        p
        for p in result.server_params_list
        if isinstance(p, StreamableHTTPClientParams)
    ]
    # At least one StreamableHTTPClientParams with our URL.
    assert any(p.url == "https://docs.agno.com/mcp" for p in http_params)


@pytest.mark.unit
def test_resolve_multi_emits_deprecation_warning() -> None:
    """MultiMCPTools construction emits DeprecationWarning; resolver does NOT suppress it."""
    resolver, _ = _make_resolver()
    config = McpMultiToolConfig(servers=[StdioMcpConfig(command="echo hi")])
    with pytest.warns(DeprecationWarning):
        resolver.resolve_multi(config)


@pytest.mark.unit
def test_resolve_multi_forwards_refresh_connection() -> None:
    """resolve_multi forwards refresh_connection to MultiMCPTools."""
    resolver, _ = _make_resolver()
    config = McpMultiToolConfig(
        servers=[StdioMcpConfig(command="echo hi")],
        refresh_connection=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = resolver.resolve_multi(config)
    assert result.refresh_connection is True
