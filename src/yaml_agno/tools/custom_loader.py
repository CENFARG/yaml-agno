"""CustomToolLoader — resolves dotted-path references to callables/classes.

Delegates class resolution to ``AgnoResolver.resolve_class`` (shipped,
allowlisted importlib + cache) — does NOT reimplement importlib. Returns RAW
callables/classes; ``@tool`` wrapping is the ToolFactory's job (slice C).

Slice B: ``load_mcp`` / ``load_mcp_multi`` delegate to ``MCPResolver``
(synchronous, UNCONNECTED instances).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yaml_agno.tools.mcp_resolver import MCPResolver
from yaml_agno.tools.security import SecurityError, is_module_allowed

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver
    from yaml_agno.tools.schema import (
        CustomToolConfig,
        CustomToolkitConfig,
        McpMultiToolConfig,
        McpToolConfig,
    )

__all__ = ["CustomToolLoader"]


class CustomToolLoader:
    """Resolve ``function`` and ``toolkit_class`` tool entries to Agno objects.

    Thin wrapper around ``AgnoResolver.resolve_class`` that adds an explicit
    allowlist guard (defense-in-depth on top of the resolver's own allowlist)
    and a clear ``SecurityError`` on rejection.

    Slice B adds ``load_mcp`` / ``load_mcp_multi`` which delegate to
    ``MCPResolver`` (lazily constructed).
    """

    def __init__(self, resolver: AgnoResolver) -> None:
        """Initialize the loader.

        Args:
            resolver: The AgnoResolver whose ``resolve_class`` performs the
                allowlisted importlib resolution.
        """
        self._resolver = resolver
        self._mcp_resolver: MCPResolver | None = None  # lazy

    def _get_mcp_resolver(self) -> MCPResolver:
        """Lazily build the MCPResolver, reusing the AgnoResolver delegate.

        Returns:
            The cached MCPResolver instance.
        """
        if self._mcp_resolver is None:
            self._mcp_resolver = MCPResolver(self._resolver)
        return self._mcp_resolver

    def load_callable(self, config: CustomToolConfig) -> Any:
        """Resolve a ``function`` entry to its RAW callable.

        Args:
            config: The ``kind: function`` tool entry.

        Returns:
            The resolved callable (NOT wrapped in @tool).

        Raises:
            SecurityError: If the module path is not allowlisted.
        """
        return self._resolve_dotted(config.path)

    def load_toolkit_class(self, config: CustomToolkitConfig) -> type:
        """Resolve a ``toolkit_class`` entry to its class (uninstantiated).

        Args:
            config: The ``kind: toolkit_class`` tool entry.

        Returns:
            The resolved Toolkit class.

        Raises:
            SecurityError: If the module path is not allowlisted.
        """
        resolved = self._resolve_dotted(config.path)
        assert isinstance(resolved, type), f"Expected a class, got {type(resolved).__name__}"
        return resolved

    def load_mcp(self, config: McpToolConfig) -> Any:
        """Resolve a ``kind: mcp`` entry to an UNCONNECTED MCPTools.

        Delegates to ``MCPResolver.resolve_single`` (slice B). The returned
        ``MCPTools`` is constructed but NOT connected — Agent connects it
        during ``aget_tools``.

        Args:
            config: The ``kind: mcp`` tool entry (StdioMcpConfig or HttpMcpConfig).

        Returns:
            An UNCONNECTED ``agno.tools.mcp.MCPTools``.

        Raises:
            SecurityError: If header_provider references a non-allowlisted module.
        """
        return self._get_mcp_resolver().resolve_single(config)

    def load_mcp_multi(self, config: McpMultiToolConfig) -> Any:
        """Resolve a ``kind: mcp_multi`` entry to an UNCONNECTED MultiMCPTools.

        Delegates to ``MCPResolver.resolve_multi`` (slice B). Emits a
        DeprecationWarning (Agno emits it on every MultiMCPTools
        construction).

        Args:
            config: The ``kind: mcp_multi`` tool entry.

        Returns:
            An UNCONNECTED ``agno.tools.mcp.MultiMCPTools``.

        Raises:
            SecurityError: If any server's header_provider is not allowlisted.
        """
        return self._get_mcp_resolver().resolve_multi(config)

    def _resolve_dotted(self, dotted_path: str) -> Any:
        """Split a dotted path into (module, name) and resolve via the resolver.

        Args:
            dotted_path: e.g. 'my_pkg.tools.fetch' or 'agno.tools.calculator.CalculatorTools'.

        Returns:
            The resolved callable or class.

        Raises:
            SecurityError: If the module half is not allowlisted.
            ValueError: If the path has no module.name structure.
        """
        if "." not in dotted_path:
            raise ValueError(f"Invalid dotted path: {dotted_path!r}. Expected 'module.name'.")
        module_path, _, name = dotted_path.rpartition(".")
        if not is_module_allowed(module_path):
            raise SecurityError(
                f"Module {module_path!r} is not in the tool allowlist. Custom tools must "
                f"reference allowlisted modules (configure the allowlist at bootstrap)."
            )
        return self._resolver.resolve_class(module_path, name)
