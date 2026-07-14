"""MCPResolver — maps validated MCP configs to UNCONNECTED Agno instances.

Synchronous, construct-only: builds ``MCPTools`` / ``MultiMCPTools`` with
the correct ``ClientParams`` (SSE=float timeouts, StreamableHTTP=timedelta)
and resolves ``header_provider`` dotted-paths via the slice-A allowlist.
Does NOT call ``connect()`` — Agent owns the async connect/close
lifecycle (it auto-connects during ``aget_tools``; verified obs-2018).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from agno.tools.mcp import MCPTools, MultiMCPTools
from agno.tools.mcp.params import SSEClientParams, StreamableHTTPClientParams

from yaml_agno.tools.security import SecurityError, is_module_allowed

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver
    from yaml_agno.tools.schema import HttpMcpConfig, McpMultiToolConfig, McpToolConfig, StdioMcpConfig

__all__ = ["MCPResolver"]


class MCPResolver:
    """Resolve ``kind: mcp`` / ``kind: mcp_multi`` entries to Agno objects.

    Thin constructor-layer over Agno's ``MCPTools`` / ``MultiMCPTools``.
    Reuses the slice-A allowlist (``security.is_module_allowed``) for
    ``header_provider`` dotted-path resolution — same mechanism as
    ``CustomToolLoader._resolve_dotted``.
    """

    def __init__(self, resolver: AgnoResolver) -> None:
        """Initialize the resolver.

        Args:
            resolver: The AgnoResolver whose ``resolve_class`` performs the
                allowlisted importlib resolution for ``header_provider``.
        """
        self._resolver = resolver

    def resolve_single(self, config: McpToolConfig) -> MCPTools:
        """Build a single UNCONNECTED ``MCPTools`` from a ``kind: mcp`` entry.

        Args:
            config: The validated ``McpToolConfig`` (StdioMcpConfig or
                HttpMcpConfig, discriminated by ``transport``).

        Returns:
            A constructed but UNCONNECTED ``MCPTools``. Agent connects it
            during ``aget_tools``.

        Raises:
            SecurityError: If ``header_provider`` references a non-allowlisted module.
            ValueError: If ``header_provider`` lacks the ``module.name`` structure.
        """
        transport = config.transport
        if transport == "stdio":
            return self._build_stdio(config)  # type: ignore[arg-type]
        return self._build_http(config)  # type: ignore[arg-type]

    def resolve_multi(self, config: McpMultiToolConfig) -> MultiMCPTools:
        """Build a single UNCONNECTED ``MultiMCPTools`` from a ``kind: mcp_multi`` entry.

        Fans each server in ``config.servers`` out to its MCPTools shape,
        collects ``commands`` (stdio) and ``server_params_list`` (http),
        and constructs one ``MultiMCPTools``.

        Args:
            config: The validated ``McpMultiToolConfig``.

        Returns:
            A constructed but UNCONNECTED ``MultiMCPTools``. Agent connects
            it during ``aget_tools``.

        Raises:
            SecurityError: If any http server's ``header_provider`` is not allowlisted.
            ValueError: If any ``header_provider`` lacks ``module.name`` structure.

        Warnings:
            DeprecationWarning: ``MultiMCPTools`` emits this on EVERY
                construction (verified Agno 2.6.22). Callers and tests
                MUST filter or assert it.
        """
        commands: list[str] = []
        server_params_list: list[Any] = []
        urls: list[str] = []
        urls_transports: list[str] = []

        for server in config.servers:
            if server.transport == "stdio":
                commands.append(server.command)
            else:
                params, url, transport = self._build_http_params(server)
                server_params_list.append(params)
                urls.append(url)
                urls_transports.append(transport)

        return MultiMCPTools(
            commands=commands or None,
            urls=urls or None,
            urls_transports=urls_transports or None,  # type: ignore[arg-type]
            server_params_list=server_params_list or None,
            allow_partial_failure=config.allow_partial_failure,
            refresh_connection=config.refresh_connection,
        )

    # --- internals -----------------------------------------------------

    def _build_stdio(self, config: StdioMcpConfig) -> MCPTools:
        """Construct an MCPTools for a stdio server.

        Args:
            config: The validated StdioMcpConfig.

        Returns:
            UNCONNECTED MCPTools(command=..., env=...).
        """
        return MCPTools(command=config.command, env=config.env)

    def _build_http(self, config: HttpMcpConfig) -> MCPTools:
        """Construct an MCPTools for an HTTP (streamable-http or SSE) server.

        Args:
            config: The validated HttpMcpConfig.

        Returns:
            UNCONNECTED MCPTools(server_params=..., transport=...,
            refresh_connection=..., header_provider=...).

        Raises:
            SecurityError: If header_provider is set but not allowlisted.
        """
        server_params, _, _ = self._build_http_params(config)
        header_provider = self._resolve_header_provider(config)
        return MCPTools(
            server_params=server_params,
            transport=config.transport,
            refresh_connection=config.refresh_connection,
            header_provider=header_provider,
        )

    def _build_http_params(
        self, config: HttpMcpConfig
    ) -> tuple[Any, str, str]:
        """Build the correct ClientParams for the transport.

        SSE uses float timeouts; StreamableHTTP wraps them in timedelta
        (verified Agno 2.6.22, obs-2018). Returns (params, url, transport)
        so resolve_multi can also populate urls / urls_transports.

        Args:
            config: The validated HttpMcpConfig.

        Returns:
            Tuple of (SSEClientParams | StreamableHTTPClientParams, url, transport).
        """
        if config.transport == "sse":
            params: SSEClientParams | StreamableHTTPClientParams = SSEClientParams(
                url=config.url,
                headers=config.headers,
                timeout=config.timeout,
                sse_read_timeout=config.sse_read_timeout,
            )
        else:
            # streamable-http: wrap float seconds into timedelta.
            timeout_td = (
                timedelta(seconds=config.timeout)
                if config.timeout is not None
                else None
            )
            sse_read_td = (
                timedelta(seconds=config.sse_read_timeout)
                if config.sse_read_timeout is not None
                else None
            )
            params = StreamableHTTPClientParams(
                url=config.url,
                headers=config.headers,
                timeout=timeout_td,
                sse_read_timeout=sse_read_td,
            )
        return params, config.url, config.transport

    def _resolve_header_provider(
        self, config: HttpMcpConfig
    ) -> Callable[..., dict[str, str]] | None:
        """Resolve a header_provider dotted-path to a Callable via the allowlist.

        Reuses the slice-A split: rpartition on '.', guard the module half
        with ``is_module_allowed``, resolve the name via
        ``resolver.resolve_class``. Returns None when no provider is set.

        Args:
            config: The validated HttpMcpConfig.

        Returns:
            The resolved Callable[..., dict], or None if header_provider is unset.

        Raises:
            ValueError: If the path has no ``module.name`` structure.
            SecurityError: If the module half is not allowlisted.
        """
        if config.header_provider is None:
            return None
        return self._resolve_dotted(config.header_provider)

    def _resolve_dotted(self, dotted_path: str) -> Callable[..., dict[str, str]]:
        """Split a dotted path into (module, name) and resolve via the resolver.

        Mirrors ``CustomToolLoader._resolve_dotted`` — same allowlist guard,
        same rpartition split — so header_provider and custom tools share
        one security boundary.

        Args:
            dotted_path: e.g. 'myapp.mcp_headers.run_headers'.

        Returns:
            The resolved Callable[..., dict].

        Raises:
            ValueError: If the path has no module.name structure.
            SecurityError: If the module half is not allowlisted.
        """
        if "." not in dotted_path:
            raise ValueError(
                f"Invalid dotted path: {dotted_path!r}. Expected 'module.name'."
            )
        module_path, _, name = dotted_path.rpartition(".")
        if not is_module_allowed(module_path):
            raise SecurityError(
                f"Module {module_path!r} is not in the tool allowlist. header_provider "
                f"must reference an allowlisted module (configure the allowlist at bootstrap)."
            )
        return self._resolver.resolve_class(module_path, name)
