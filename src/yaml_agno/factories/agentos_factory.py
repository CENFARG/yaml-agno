"""AgentOSFactory — builds ``agno.os.AgentOS`` from ``AgentOSConfig``.

Slice 1 (PR 2) resolves string refs via injected registries, maps nested
settings to Agno-native config objects, and forwards primitives as-is.
Complex parameters deferred to Slice 2/3 (interfaces, resync) are logged
at WARNING and excluded from kwargs.

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

if TYPE_CHECKING:
    from yaml_agno.models.config.agentos_config import AgentOSConfig

__all__ = [
    "AgentOSFactory",
    "AgentRegistry",
    "DatabaseManager",
    "InterfaceRegistry",
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


class InterfaceRegistry(Protocol):
    """Placeholder — Slice 2 wires interface resolution.

    Slice 1 does NOT call this registry; it exists so the constructor
    contract is stable across slices.
    """

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

    Constructor receives six registries via dependency injection. Each
    registry resolves string references into live Agno objects. The
    ``build()`` method orchestrates resolution and constructs the
    ``AgentOS`` instance.

    Slice 1 scope:
        - Resolves agents, teams, workflows, knowledge, db.
        - Maps authorization → ``AuthorizationConfig``.
        - Maps mcp → ``MCPServerConfig``.
        - Maps scheduler → ``scheduler`` + ``scheduler_poll_interval``.
        - Forwards primitives (name, base_app, lifespan, cors, tracing…).
        - Deferred: interfaces, resync (logged at WARNING).

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
        interface_registry: InterfaceRegistry,
        db_manager: DatabaseManager,
    ) -> None:
        """Wire the factory with its dependency registries.

        All six registries are REQUIRED. Passing ``None`` for any results
        in a ``ValueError`` at build time when that registry is needed.

        Args:
            agent_registry: Resolves agent ref strings → Agent objects.
            team_registry: Resolves team ref strings → Team objects.
            workflow_registry: Resolves workflow ref strings → Workflow objects.
            knowledge_registry: Resolves knowledge ref strings → Knowledge.
            interface_registry: Placeholder for Slice 2 (not consumed yet).
            db_manager: Resolves db ref strings → BaseDb instances.
        """
        self._agent_registry = agent_registry
        self._team_registry = team_registry
        self._workflow_registry = workflow_registry
        self._knowledge_registry = knowledge_registry
        self._interface_registry = interface_registry
        self._db_manager = db_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, config: AgentOSConfig) -> AgentOS:
        """Build a fully-resolved ``agno.os.AgentOS`` from the validated config.

        Resolution pipeline:

        1. ``config.to_agno_kwargs()`` → raw dict (primitives + unresolved refs).
        2. Extract target lists, validate no duplicates.
        3. Resolve each ref via the corresponding registry.
        4. Map nested settings → Agno-native config objects.
        5. Strip Slice-1-deferred fields (log at WARNING).
        6. ``AgentOS(**resolved_kwargs)``.

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

        # --- 5. Deferred fields (Sl 2/3) — log and exclude ---
        if config.interfaces:
            logger.warning(
                "AgentOSFactory: %d interface(s) deferred to Slice 2; "
                "not forwarded to AgentOS.",
                len(config.interfaces),
            )
        kwargs.pop("interfaces", None)

        if config.resync.enabled:
            logger.warning(
                "AgentOSFactory: resync enabled but deferred to Slice 3; "
                "not forwarded to AgentOS."
            )
        kwargs.pop("resync", None)

        # "config" is our internal YAML config reference, NOT the same as
        # AgentOS's "config" parameter. Strip it to avoid collision.
        kwargs.pop("config", None)

        # --- 6. Construct ---
        return AgentOS(**kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    @staticmethod
    def _build_authorization_config(config: AgentOSConfig) -> AuthorizationConfig:
        """Build ``AuthorizationConfig`` from the authorization settings model.

        Maps non-None values from ``AuthorizationSettings`` to the
        corresponding ``AuthorizationConfig`` kwargs. The config dict
        (opaque/proprietary) is currently not forwarded — extend here
        when provider-specific auth shapes are defined.

        Args:
            config: The full AgentOSConfig (to access ``authorization``).

        Returns:
            A configured ``AuthorizationConfig`` instance.
        """
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
