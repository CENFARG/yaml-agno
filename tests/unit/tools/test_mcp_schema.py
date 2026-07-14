"""Unit tests for MCP schema — SPEC_11 slice B.

Covers the dual-discriminator routing (kind=mcp outer, transport=stdio|sse|
streamable-http inner), StdioMcpConfig extra=forbid (rejects headers/
header_provider/url/timeout), HttpMcpConfig golden paths, and
McpMultiToolConfig servers min_length=1.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from yaml_agno.tools.schema import (
    HttpMcpConfig,
    McpMultiToolConfig,
    McpToolConfig,
    StdioMcpConfig,
    ToolEntry,
)

# --- Dual-discriminator routing: kind=mcp + transport narrows ---------------


@pytest.mark.unit
def test_dual_discriminator_stdio_routes_to_stdio_config() -> None:
    """kind=mcp + transport=stdo -> StdioMcpConfig."""
    ta = TypeAdapter(McpToolConfig)
    result = ta.validate_python(
        {"kind": "mcp", "transport": "stdio", "command": "echo hi"}
    )
    assert isinstance(result, StdioMcpConfig)
    assert result.command == "echo hi"


@pytest.mark.unit
def test_dual_discriminator_sse_routes_to_http_config() -> None:
    """kind=mcp + transport=sse -> HttpMcpConfig."""
    ta = TypeAdapter(McpToolConfig)
    result = ta.validate_python(
        {"kind": "mcp", "transport": "sse", "url": "http://localhost:8000/sse"}
    )
    assert isinstance(result, HttpMcpConfig)
    assert result.transport == "sse"


@pytest.mark.unit
def test_dual_discriminator_streamable_http_routes_to_http_config() -> None:
    """kind=mcp + transport=streamable-http -> HttpMcpConfig."""
    ta = TypeAdapter(McpToolConfig)
    result = ta.validate_python(
        {
            "kind": "mcp",
            "transport": "streamable-http",
            "url": "https://docs.agno.com/mcp",
        }
    )
    assert isinstance(result, HttpMcpConfig)
    assert result.transport == "streamable-http"


@pytest.mark.unit
def test_dual_discriminator_via_tool_entry() -> None:
    """The outer ToolEntry union routes kind=mcp into the McpToolConfig branch,
    then transport narrows."""
    entry_stdio = TypeAdapter(ToolEntry).validate_python(
        {"kind": "mcp", "transport": "stdio", "command": "echo"}
    )
    entry_sse = TypeAdapter(ToolEntry).validate_python(
        {"kind": "mcp", "transport": "sse", "url": "http://x"}
    )
    assert isinstance(entry_stdio, StdioMcpConfig)
    assert isinstance(entry_sse, HttpMcpConfig)


# --- StdioMcpConfig: golden + extra=forbid rejections (decision 10.5) -------


@pytest.mark.unit
def test_stdio_golden_with_command_and_env() -> None:
    """Golden: stdio with command + env."""
    config = StdioMcpConfig(
        command="uvx mcp-server-git", env={"GIT_REPO_PATH": "/repo"}
    )
    assert config.command == "uvx mcp-server-git"
    assert config.env == {"GIT_REPO_PATH": "/repo"}
    assert config.transport == "stdio"


@pytest.mark.unit
def test_stdio_rejects_headers() -> None:
    """RED: stdio with headers is rejected (extra=forbid, decision 10.5)."""
    with pytest.raises(ValidationError) as exc_info:
        StdioMcpConfig(command="echo", headers={"X-Custom": "1"})  # type: ignore[call-arg]
    assert "headers" in str(exc_info.value)


@pytest.mark.unit
def test_stdio_rejects_header_provider() -> None:
    """RED: stdio with header_provider is rejected (extra=forbid)."""
    with pytest.raises(ValidationError) as exc_info:
        StdioMcpConfig(command="echo", header_provider="myapp.headers.fn")  # type: ignore[call-arg]
    assert "header_provider" in str(exc_info.value)


@pytest.mark.unit
def test_stdio_rejects_url() -> None:
    """RED: stdio with url is rejected (extra=forbid)."""
    with pytest.raises(ValidationError):
        StdioMcpConfig(command="echo", url="http://x")  # type: ignore[call-arg]


@pytest.mark.unit
def test_stdio_rejects_timeout() -> None:
    """RED: stdio with timeout is rejected (extra=forbid)."""
    with pytest.raises(ValidationError):
        StdioMcpConfig(command="echo", timeout=5.0)  # type: ignore[call-arg]


@pytest.mark.unit
def test_stdio_requires_command() -> None:
    """RED: stdio without command fails."""
    with pytest.raises(ValidationError):
        StdioMcpConfig()  # type: ignore[call-arg]


# --- HttpMcpConfig: golden paths + extra=forbid -----------------------------


@pytest.mark.unit
def test_http_streamable_golden_with_headers() -> None:
    """Golden: streamable-http with headers + refresh_connection."""
    config = HttpMcpConfig(
        transport="streamable-http",
        url="https://docs.agno.com/mcp",
        headers={"Authorization": "Bearer x"},
        refresh_connection=True,
    )
    assert config.transport == "streamable-http"
    assert config.url == "https://docs.agno.com/mcp"
    assert config.headers == {"Authorization": "Bearer x"}
    assert config.refresh_connection is True


@pytest.mark.unit
def test_http_sse_golden_with_timeout() -> None:
    """Golden: SSE with timeout + sse_read_timeout."""
    config = HttpMcpConfig(
        transport="sse",
        url="http://localhost:8000/sse",
        timeout=5.0,
        sse_read_timeout=300.0,
    )
    assert config.transport == "sse"
    assert config.timeout == 5.0
    assert config.sse_read_timeout == 300.0


@pytest.mark.unit
def test_http_rejects_extra_fields() -> None:
    """RED: http with an extra field is rejected (extra=forbid)."""
    with pytest.raises(ValidationError):
        HttpMcpConfig(
            transport="sse", url="http://x", bogus_field=True  # type: ignore[call-arg]
        )


@pytest.mark.unit
def test_http_requires_url() -> None:
    """RED: http without url fails."""
    with pytest.raises(ValidationError):
        HttpMcpConfig(transport="sse")  # type: ignore[call-arg]


# --- McpMultiToolConfig: servers validation ---------------------------------


@pytest.mark.unit
def test_mcp_multi_golden_with_two_servers() -> None:
    """Golden: McpMultiToolConfig with 2 stdio servers + allow_partial_failure."""
    config = McpMultiToolConfig(
        servers=[
            StdioMcpConfig(command="npx airbnb"),
            StdioMcpConfig(command="npx gmaps"),
        ],
        allow_partial_failure=True,
    )
    assert len(config.servers) == 2
    assert all(isinstance(s, StdioMcpConfig) for s in config.servers)
    assert config.allow_partial_failure is True


@pytest.mark.unit
def test_mcp_multi_empty_servers_rejected() -> None:
    """RED: servers=[] is rejected (min_length=1)."""
    with pytest.raises(ValidationError) as exc_info:
        McpMultiToolConfig(servers=[])
    assert "min_length" in str(exc_info.value).lower() or "at least" in str(
        exc_info.value
    ).lower()


@pytest.mark.unit
def test_mcp_multi_missing_servers_rejected() -> None:
    """RED: servers field is required."""
    with pytest.raises(ValidationError):
        McpMultiToolConfig()  # type: ignore[call-arg]


@pytest.mark.unit
def test_mcp_multi_rejects_extra_fields() -> None:
    """RED: extra field on McpMultiToolConfig rejected (extra=forbid)."""
    with pytest.raises(ValidationError):
        McpMultiToolConfig(
            servers=[StdioMcpConfig(command="echo")],
            cache_results=True,  # type: ignore[call-arg]
        )


# --- transport discriminator edge cases --------------------------------------


@pytest.mark.unit
def test_transport_missing_rejected() -> None:
    """RED: transport absent -> ValidationError."""
    with pytest.raises(ValidationError):
        TypeAdapter(McpToolConfig).validate_python(
            {"kind": "mcp", "command": "echo"}
        )


@pytest.mark.unit
def test_transport_invalid_rejected() -> None:
    """RED: transport='websocket' -> ValidationError."""
    with pytest.raises(ValidationError):
        TypeAdapter(McpToolConfig).validate_python(
            {"kind": "mcp", "transport": "websocket", "url": "http://x"}
        )


@pytest.mark.unit
def test_mcp_multi_from_dict_with_mixed_servers() -> None:
    """ToolEntry routes kind=mcp_multi with mixed stdio+http servers."""
    entry = TypeAdapter(ToolEntry).validate_python(
        {
            "kind": "mcp_multi",
            "servers": [
                {"transport": "stdio", "command": "echo hi"},
                {"transport": "sse", "url": "http://localhost:8000/sse"},
            ],
        }
    )
    assert isinstance(entry, McpMultiToolConfig)
    assert isinstance(entry.servers[0], StdioMcpConfig)
    assert isinstance(entry.servers[1], HttpMcpConfig)
