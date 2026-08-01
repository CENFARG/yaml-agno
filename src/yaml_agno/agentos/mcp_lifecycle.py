"""MCPServerLifecycle — wraps MCPServerSettings → MCPServerConfig pipeline.

TASK_004 — SPEC_12 Slice 2, PR 2. Thin wrapper around ``AgentOS.mcp_server``
enable + ``MCPServerConfig`` builder with ``register/start/stop`` methods for
lifespan integration.

Design (sdd/control-plane-s2/design):
    - Maps ``MCPServerSettings`` fields → ``agno.os.config.MCPServerConfig`` fields.
    - ``register(os)`` stores the AgentOS reference for deferred enable.
    - ``start()`` maps settings → config and sets ``os.mcp_server = config``.
    - ``stop()`` is a clean no-op — AgentOS manages the MCP server lifecycle.
    - ``disable()`` is deliberately NOT implemented (AgentOS owns lifecycle).
    - ``tools_to_expose`` maps Agno built-in tool tags to ``include_tags``.

@ai-directive: SSOT is specs/SPEC_12_CONTROL_PLANE.md §5 (MCPServerLifecycle).
    Build ON TOP of Agno — use ``MCPServerConfig``, do not reimplement MCP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agno.os.config import MCPBuiltinTag, MCPServerConfig

from yaml_agno.models.config.agentos_config import MCPServerSettings

if TYPE_CHECKING:
    from agno.os import AgentOS

__all__ = ["MCPServerLifecycle"]

# ═══════════════════════════════════════════════════════════════════════════
# MCPServerLifecycle
# ═══════════════════════════════════════════════════════════════════════════


class MCPServerLifecycle:
    """Thin wrapper around ``AgentOS.mcp_server`` enable + ``MCPServerConfig``.

    Bridges yaml-agno's declarative ``MCPServerSettings`` to Agno's runtime
    ``MCPServerConfig``. Designed for lifespan integration: ``register()``
    stores the target AgentOS, ``start()`` maps and enables, ``stop()`` is
    a no-op.

    Example:
        >>> lifecycle = MCPServerLifecycle(settings)
        >>> lifecycle.register(agentos)
        >>> await lifecycle.start()
    """

    def __init__(self, settings: MCPServerSettings) -> None:
        """Initialize with MCP server settings.

        Args:
            settings: Declarative MCP settings from ``AgentOSConfig.mcp``.
        """
        self._settings = settings
        self._agentos: AgentOS | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, agentos: AgentOS) -> None:
        """Store a reference to the ``AgentOS`` instance for deferred enable.

        Called during lifespan setup before ``start()``. Stores the AgentOS
        reference so ``start()`` can set ``agentos.mcp_server``.

        Args:
            agentos: The ``AgentOS`` instance (or ``YamlAgentOS`` subclass).
        """
        self._agentos = agentos

    async def start(self) -> None:
        """Enable the MCP server on the registered AgentOS.

        If ``MCPServerSettings.enabled`` is ``False``, or ``register()`` was
        never called, this is a no-op.

        When enabled, maps ``MCPServerSettings`` → ``MCPServerConfig`` and
        assigns it via ``agentos.mcp_server = config``.
        """
        if not self._settings.enabled or self._agentos is None:
            return

        config = self._build_config()
        self._agentos.mcp_server = config

    async def stop(self) -> None:
        """No-op — AgentOS manages the MCP server lifecycle.

        The MCP server is torn down when the AgentOS app's lifespan exits.
        There is nothing to explicitly disable or clean up at the component
        level.
        """

    # ------------------------------------------------------------------
    # Builder
    # ------------------------------------------------------------------

    def _build_config(self) -> MCPServerConfig:
        """Map ``MCPServerSettings`` → ``MCPServerConfig``.

        Transforms declarative YAML settings into the runtime configuration
        Agno's ``AgentOS.__init__(mcp_server=...)`` expects.

        Mapping rules:
            - ``tools_to_expose`` → ``include_tags`` (as ``set[MCPBuiltinTag]``).
            - ``auth`` → ``authorize`` callable (left as default ``None`` for
              now — deferred to S3 auth wiring).
            - ``name``, ``instructions``, ``port`` → these are consumed by
              the ``AgentOS`` layer (not ``MCPServerConfig`` fields).

        Returns:
            A configured ``MCPServerConfig`` ready for AgentOS.
        """
        kwargs: dict[str, Any] = {}

        # Map tools_to_expose → include_tags (if entries match MCPBuiltinTag)
        if self._settings.tools_to_expose:
            include_tags: set[MCPBuiltinTag] = set()
            valid_tags = {"core", "session"}
            for tag in self._settings.tools_to_expose:
                if tag in valid_tags:
                    include_tags.add(tag)  # type: ignore[arg-type]
            if include_tags:
                kwargs["include_tags"] = include_tags

        return MCPServerConfig(**kwargs)
