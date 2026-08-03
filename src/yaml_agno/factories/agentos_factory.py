"""AgentOSFactory — builds ``agno.os.AgentOS`` from ``AgentOSConfig``.

Slice 2 (PR 3) integrates InterfaceRegistry and MCPServerLifecycle into
the build pipeline. Interfaces are resolved via ``InterfaceRegistry.build_all``
when config declares them; MCP lifecycle registration is called post-build
when mcp.enabled.

Design:
    - Constructor-injected registries (SOLID DI — no global state).
    - ``build(config) -> AgentOS``: resolves refs → builds kwargs dict
      → ``AgentOS(**resolved_kwargs)``.
    - Fail-fast on missing/duplicate refs.
    - Follows ``AgentFactory`` naming convention (``_factory.py`` suffix).

@ai-directive: SSOT is specs/SPEC_12_CONTROL_PLANE.md §2.3 (AgentOSFactory)
and sdd/control-plane/design §2.3 (class hierarchy).
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING, Any, Protocol

from agno.os import AgentOS
from agno.os.config import AuthorizationConfig, MCPServerConfig

from yaml_agno.agentos.interfaces import InterfaceRegistry, InterfaceSpec
from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle

if TYPE_CHECKING:
    from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter
    from yaml_agno.agentos.resync_manager import ResyncManager
    from yaml_agno.models.config.agentos_config import AgentOSConfig

__all__ = [
    "AgentOSFactory",
    "AgentRegistry",
    "DatabaseManager",
    "KnowledgeRegistry",
    "TeamRegistry",
    "WorkflowRegistry",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry Protocols — structural subtyping (no inheritance required)
# ---------------------------------------------------------------------------


class AgentRegistry(Protocol):
    """Resolves an agent ref string to a constructed ``agno.Agent`` (or compatible).

    Raises ``KeyError`` when the ref is unknown.
    """

    def get(self, ref: str) -> Any:
        """Look up an agent by its reference name."""
        ...


class TeamRegistry(Protocol):
    """Resolves a team ref string to a constructed ``agno.Team`` (or compatible)."""

    def get(self, ref: str) -> Any:
        """Look up a team by its reference name."""
        ...


class WorkflowRegistry(Protocol):
    """Resolves a workflow ref string to a constructed ``agno.Workflow`` (or compatible)."""

    def get(self, ref: str) -> Any:
        """Look up a workflow by its reference name."""
        ...


class KnowledgeRegistry(Protocol):
    """Resolves a knowledge ref string to constructed ``agno.Knowledge``."""

    def get(self, ref: str) -> Any:
        """Look up a knowledge base by its reference name."""
        ...


class DatabaseManager(Protocol):
    """Resolves a database ref string to an ``agno.db.BaseDb`` instance.

    Provided by core-cenf's ``DatabaseManager`` or a SPEC_03 adapter.
    """

    def get_db(self, ref: str) -> Any:
        """Look up a database connection by its reference name."""
        ...


# ---------------------------------------------------------------------------
# AgentOSFactory
# ---------------------------------------------------------------------------


class AgentOSFactory:
    """Builds ``agno.os.AgentOS`` from a validated ``AgentOSConfig``.

    Constructor receives registries via dependency injection. Each
    registry resolves string references into live Agno objects. The
    ``build()`` method orchestrates resolution and constructs the
    ``AgentOS`` instance.

    Slice 2 scope (PR 3):
        - InterfaceRegistry.build_all() resolves interface specs.
        - MCPServerLifecycle.register() wires MCP post-build.
        - Both are OPTIONAL (``None`` → graceful skip).

    Raises:
        ValueError: Duplicate refs in target lists.
        ValueError: Registry returns ``KeyError`` for an unknown ref.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        team_registry: TeamRegistry,
        workflow_registry: WorkflowRegistry,
        knowledge_registry: KnowledgeRegistry,
        db_manager: DatabaseManager,
        interface_registry: InterfaceRegistry | None = None,
        mcp_lifecycle: MCPServerLifecycle | None = None,
        authorization_adapter: AuthorizationAdapter | None = None,
        resync_manager: ResyncManager | None = None,
    ) -> None:
        """Wire the factory with its dependency registries.

        The five core registries are REQUIRED. Optional integration points
        are injected for Slice 2 (interfaces, MCP) and Slice 3 (auth, resync).

        Args:
            agent_registry: Resolves agent ref strings → Agent objects.
            team_registry: Resolves team ref strings → Team objects.
            workflow_registry: Resolves workflow ref strings → Workflow objects.
            knowledge_registry: Resolves knowledge ref strings → Knowledge.
            db_manager: Resolves db ref strings → BaseDb instances.
            interface_registry: Optional InterfaceRegistry for resolving
                interface specs (Slice 2). If ``None``, interfaces in config
                are logged at WARNING and skipped.
            mcp_lifecycle: Optional MCPServerLifecycle for MCP server
                registration post-build (Slice 2). If ``None``, MCP config
                is still mapped to ``MCPServerConfig`` (Slice 1 behavior).
            authorization_adapter: Optional AuthorizationAdapter for RBAC
                secret resolution (Slice 3). If ``None``, legacy config
                forwarding is used (no secret resolution).
            resync_manager: Optional ResyncManager for hot-reload (Slice 3).
                If ``None`` and ``config.resync.enabled``, a WARNING is logged.
        """
        self._agent_registry = agent_registry
        self._team_registry = team_registry
        self._workflow_registry = workflow_registry
        self._knowledge_registry = knowledge_registry
        self._interface_registry = interface_registry
        self._db_manager = db_manager
        self._mcp_lifecycle = mcp_lifecycle
        self._authorization_adapter = authorization_adapter
        self._resync_manager = resync_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, config: AgentOSConfig) -> AgentOS:
        """Build a fully-resolved ``agno.os.AgentOS`` from the validated config.

        Resolution pipeline:

        1. ``config.to_agno_kwargs()`` → raw dict (primitives + unresolved refs).
        2. Strip factory-owned keys, validate no duplicate targets.
        3. Resolve each ref via the corresponding registry.
        4. Map nested settings → Agno-native config objects.
        5. Resolve interfaces via ``InterfaceRegistry.build_all`` (Slice 2).
        6. Strip Slice-3-deferred fields (resync — log at WARNING).
        7. ``AgentOS(**resolved_kwargs)``.
        8. Post-build: ``MCPServerLifecycle.register(agentos)`` (Slice 2).

        Args:
            config: A validated ``AgentOSConfig``.

        Returns:
            A constructed ``agno.os.AgentOS`` instance.

        Raises:
            ValueError: Duplicate refs or unresolved ref.
        """
        kwargs: dict[str, Any] = config.to_agno_kwargs()
        # Strip before resolution (keys we own vs AgentOS's own params):
        self._pop_owned_keys(kwargs)

        # --- 2. Duplicate detection (pre-resolution) ---
        self._check_duplicates(config)

        # --- 3. Resolve refs ---
        kwargs["agents"] = self._resolve_refs(
            config.agents, self._agent_registry, "agent"
        )
        kwargs["teams"] = self._resolve_refs(
            config.teams, self._team_registry, "team"
        )
        kwargs["workflows"] = self._resolve_refs(
            config.workflows, self._workflow_registry, "workflow"
        )

        if config.knowledge:
            kwargs["knowledge"] = self._resolve_refs(
                config.knowledge, self._knowledge_registry, "knowledge"
            )

        if config.db is not None:
            kwargs["db"] = self._resolve_db_ref(config.db)

        # --- 4. Map nested settings → Agno-native objects ---
        if config.authorization.enabled:
            kwargs["authorization"] = True
            kwargs["authorization_config"] = self._build_authorization_config(
                config
            )
        # If authorization is disabled, rely on to_agno_kwargs exclusion
        # of None values. authorization_config is not forwarded.

        if config.mcp.enabled:
            kwargs["mcp_server"] = self._build_mcp_config(config)
        # When disabled, mcp_server is not forwarded (AgentOS default: False).

        kwargs["scheduler"] = config.scheduler.enabled
        kwargs["scheduler_poll_interval"] = config.scheduler.poll_interval

        # --- 5. Resolve interfaces (Slice 2) ---
        if config.interfaces and self._interface_registry is not None:
            specs = [InterfaceSpec(**iface) for iface in config.interfaces]
            kwargs["interfaces"] = self._interface_registry.build_all(
                specs, self._resolve_target
            )
        elif config.interfaces and self._interface_registry is None:
            logger.warning(
                "AgentOSFactory: %d interface(s) in config but no "
                "InterfaceRegistry injected — skipping interface resolution.",
                len(config.interfaces),
            )
        # When no interfaces declared, nothing to forward.

        # --- 6. ResyncManager wiring (Slice 3) ---
        if config.resync.enabled:
            if self._resync_manager is not None:
                # attach() called AFTER AgentOS construction (Step 7)
                pass
            else:
                logger.warning(
                    "AgentOSFactory: resync enabled but no ResyncManager "
                    "injected."
                )
        kwargs.pop("resync", None)

        # "config" is our internal YAML config reference, NOT the same as
        # AgentOS's "config" parameter. Strip it to avoid collision.
        kwargs.pop("config", None)

        # --- 7. Construct ---
        agentos = AgentOS(**kwargs)

        # --- 8. Post-build: MCP lifecycle registration (Slice 2) ---
        if self._mcp_lifecycle is not None and config.mcp.enabled:
            self._mcp_lifecycle.register(agentos)

        # --- 9. Post-build: ResyncManager attach (Slice 3) ---
        if self._resync_manager is not None and config.resync.enabled:
            self._resync_manager.attach(agentos)

        return agentos

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_target(self, ref: str) -> Any:
        """Resolve an interface target ref to an agent, team, or workflow.

        Tries each registry in order: agent → team → workflow. The first
        registry that returns a result for the ref wins. This is used as
        the ``resolve_target`` callable passed to ``InterfaceRegistry``.

        Args:
            ref: The target reference name (e.g. "researcher").

        Returns:
            The resolved Agno object (Agent, Team, or Workflow).

        Raises:
            ValueError: When the ref is not found in any registry.
        """
        for registry in (self._agent_registry, self._team_registry, self._workflow_registry):
            try:
                return registry.get(ref)
            except (KeyError, AttributeError):
                continue
        raise ValueError(f"Unresolved target ref: {ref!r}")

    @staticmethod
    def _pop_owned_keys(kwargs: dict[str, Any]) -> None:
        """Remove keys from the kwargs dict that the factory owns (not AgentOS params).

        These are fields on AgentOSConfig that must be transformed before
        forwarding to AgentOS. Removing them now prevents accidental
        passthrough of raw types.
        """
        for key in (
            "agents",
            "teams",
            "workflows",
            "knowledge",
            "db",
            "interfaces",
            "authorization",
            "mcp",
            "scheduler",
            "resync",
            "config",
        ):
            kwargs.pop(key, None)

    @staticmethod
    def _check_duplicates(config: AgentOSConfig) -> None:
        """Reject duplicate refs within each target list.

        Duplicates are detected independently per list — a name appearing
        in both ``agents`` and ``teams`` is NOT considered a duplicate.

        Raises:
            ValueError: When any list contains duplicate entries.
        """
        for kind, refs in [
            ("agents", config.agents),
            ("teams", config.teams),
            ("workflows", config.workflows),
            ("knowledge", config.knowledge),
        ]:
            counts = Counter(refs)
            dupes = [r for r, c in counts.items() if c > 1]
            if dupes:
                raise ValueError(
                    f"Duplicate {kind} refs: {dupes!r}. "
                    f"Each ref must appear at most once per list.",
                )

    @staticmethod
    def _resolve_refs(
        refs: list[str],
        registry: Any,
        kind: str,
    ) -> list[Any]:
        """Resolve a list of string refs through a registry.

        Each ref is resolved via ``registry.get(ref)``. ``KeyError`` from
        the registry is wrapped as ``ValueError`` with diagnostic context.

        Args:
            refs: List of reference strings to resolve.
            registry: Any object with a ``.get(ref) -> Any`` method.
            kind: Human-readable kind label for error messages.

        Returns:
            List of resolved objects (same order as input refs).

        Raises:
            ValueError: When any ref raises ``KeyError``.
        """
        resolved: list[Any] = []
        for ref in refs:
            try:
                resolved.append(registry.get(ref))
            except KeyError as exc:
                raise ValueError(
                    f"Unresolved {kind} ref {ref!r}: {exc}"
                ) from exc
        return resolved

    def _resolve_db_ref(self, db_ref: str) -> Any:
        """Resolve a single database reference through DatabaseManager.

        Args:
            db_ref: Database reference name (e.g. "sqlite_db").

        Returns:
            A ``BaseDb`` instance.

        Raises:
            ValueError: When the db ref is unknown.
        """
        try:
            return self._db_manager.get_db(db_ref)
        except KeyError as exc:
            raise ValueError(
                f"Unresolved db ref {db_ref!r}: {exc}"
            ) from exc

    def _build_authorization_config(self, config: AgentOSConfig) -> AuthorizationConfig:
        """Build ``AuthorizationConfig`` with optional secret resolution.

        When ``authorization_adapter`` is injected (Slice 3), delegates
        to the adapter for ``${SECRET:...}`` resolution. Otherwise falls
        back to the legacy direct mapping (no secret resolution).

        Args:
            config: The full AgentOSConfig (to access ``authorization``).

        Returns:
            A configured ``AuthorizationConfig`` instance.
        """
        if self._authorization_adapter is not None:
            enabled, auth_config = self._authorization_adapter.build(
                config.authorization
            )
            if not enabled:
                raise ValueError(
                    "AuthorizationAdapter returned disabled when config says enabled"
                )
            return auth_config

        # Legacy path: direct mapping without secret resolution
        logger.warning(
            "AgentOSFactory: AuthorizationAdapter not injected — "
            "secrets NOT resolved."
        )
        return AgentOSFactory._build_authorization_config_legacy(config)

    @staticmethod
    def _build_authorization_config_legacy(config: AgentOSConfig) -> AuthorizationConfig:
        """Legacy direct mapping (no secret resolution)."""
        auth = config.authorization
        auth_kwargs: dict[str, Any] = {}
        if auth.basic_auth is not None:
            auth_kwargs["basic_auth"] = auth.basic_auth
        if auth.config is not None:
            auth_kwargs["config"] = auth.config
        return AuthorizationConfig(**auth_kwargs)

    @staticmethod
    def _build_mcp_config(config: AgentOSConfig) -> MCPServerConfig:
        """Build ``MCPServerConfig`` from the MCP settings model.

        Maps ``MCPServerSettings`` fields to the Agno-native
        ``MCPServerConfig`` (different field names — intentional). Fields
        without a direct mapping (name, instructions, port, auth) are
        logged at WARNING and excluded.

        Args:
            config: The full AgentOSConfig (to access ``mcp``).

        Returns:
            A configured ``MCPServerConfig`` instance.
        """
        mcp = config.mcp
        mcp_kwargs: dict[str, Any] = {}

        if mcp.tools_to_expose:
            mcp_kwargs["tools"] = mcp.tools_to_expose

        # Fields without a direct Agno-native MCP mapping — warn once
        # so operators know they have no effect at the AgentOS level.
        unmapped: list[str] = []
        if mcp.name is not None:
            unmapped.append(f"name={mcp.name!r}")
        if mcp.instructions is not None:
            unmapped.append("instructions")
        if mcp.port is not None:
            unmapped.append(f"port={mcp.port}")
        if mcp.auth is not None:
            unmapped.append("auth")
        if unmapped:
            logger.warning(
                "AgentOSFactory: MCP fields without Agno-native mapping "
                "ignored — %s",
                ", ".join(unmapped),
            )

        return MCPServerConfig(**mcp_kwargs)
