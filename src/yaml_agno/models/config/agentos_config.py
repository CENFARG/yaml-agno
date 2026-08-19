"""AgentOSConfig — Pydantic V2 aggregate root for the ``agentos:`` YAML block.

Single source of truth for AgentOS construction parameters per SPEC_12 §2.2.
Defines 19 fields mapping to ``agno.os.AgentOS.__init__``, four nested settings
models, two model-level validators, and ``to_agno_kwargs()`` for forwarding.

Design (Slice 1):
    - ``extra = "forbid"`` via ``ConfigDict`` (matching ``AgentConfig`` pattern).
    - ``ResyncSettings`` MUST be defined above ``AgentOSConfig`` because
      ``Field(default_factory=ResyncSettings)`` is evaluated eagerly at
      class-body time.
    - ``to_agno_kwargs()`` uses ``model_dump(exclude_none=True, exclude_unset=False)``
      so ``None`` values do NOT clobber AgentOS internal defaults but explicit
      ``False`` booleans ARE forwarded.

@ai-directive: SSOT is specs/SPEC_12_CONTROL_PLANE.md §2.2 (AgentOSConfig fields,
validators, to_agno_kwargs). Discrepancies resolve in its favor.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AgentOSConfig",
    "AuthorizationSettings",
    "MCPServerSettings",
    "ResyncSettings",
    "SchedulerSettings",
]


# ---------------------------------------------------------------------------
# Nested Settings Models (defined ABOVE AgentOSConfig — eager default_factory)
# ---------------------------------------------------------------------------


class AuthorizationSettings(BaseModel):
    """Authorization configuration for AgentOS.

    Fields:
        enabled: When True, AgentOS enforces RBAC authorization on all routes.
        config: Opaque auth configuration dict (provider-specific).
        basic_auth: UNSUPPORTED in agno 2.8.7 — ``AuthorizationConfig`` has no
            basic-auth sink, so ``build()`` rejects this field (fail-fast,
            VQ011). Parse-only (never dropped at the schema boundary); removal
            lands in S5a.2 with the dev-only ``BasicAuthMiddleware`` (SPEC_19
            §1.2) as the future sink.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable RBAC authorization.")
    config: dict[str, Any] | None = Field(default=None, description="Provider-specific auth config.")
    basic_auth: dict[str, str] | None = Field(
        default=None,
        description=(
            "UNSUPPORTED in agno 2.8.7: AuthorizationConfig has no basic-auth "
            "sink, so the authorization build rejects this field (fail-fast, "
            "VQ011). Kept parseable until S5a.2 removes it; the future sink is "
            "BasicAuthMiddleware (SPEC_19 §1.2)."
        ),
    )


class MCPServerSettings(BaseModel):
    """MCP (Model Context Protocol) server configuration for AgentOS.

    Fields:
        enabled: When True, AgentOS starts an embedded MCP server.
        name: Server name exposed in MCP discovery.
        instructions: Tool usage instructions for MCP clients.
        tools_to_expose: List of tool names to expose via MCP.
        port: TCP port for the MCP server (None = auto-assign).
        auth: Opaque MCP auth configuration dict.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable embedded MCP server.")
    name: str | None = Field(default=None, description="MCP server name.")
    instructions: str | None = Field(default=None, description="MCP tool instructions.")
    tools_to_expose: list[str] = Field(default_factory=list, description="Tools to expose via MCP.")
    port: int | None = Field(default=None, description="MCP server port (None = auto).")
    auth: dict[str, Any] | None = Field(default=None, description="MCP auth config.")


class SchedulerSettings(BaseModel):
    """Scheduler configuration for AgentOS background task scheduling.

    Fields:
        enabled: When True, AgentOS starts the internal scheduler.
        poll_interval: Seconds between scheduler poll ticks.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable built-in scheduler.")
    poll_interval: int = Field(default=15, ge=1, description="Poll interval in seconds.")


class ResyncSettings(BaseModel):
    """Resync (auto-reload) configuration for AgentOS.

    Fields:
        enabled: When True, AgentOS watches for config changes and reloads.
        watch: Watch filesystem for changes.
        debounce_ms: Debounce window in milliseconds.
        max_concurrent: Max concurrent reload operations.
        failure_threshold: Percentage of failures before stopping resync.
        min_requests: Min requests before evaluating failure threshold.
        recovery_timeout: Seconds to wait before retrying after failure.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable auto-reload on config changes.")
    watch: bool = Field(default=False, description="Watch filesystem for changes.")
    debounce_ms: int = Field(default=500, ge=0, description="Debounce window (ms).")
    max_concurrent: int = Field(default=1, ge=1, description="Max concurrent reloads.")
    failure_threshold: float = Field(default=50.0, ge=0.0, le=100.0, description="Failure % threshold.")
    min_requests: int = Field(default=5, ge=0, description="Min requests before threshold evaluation.")
    recovery_timeout: int = Field(default=30, ge=0, description="Recovery timeout (seconds).")


# ---------------------------------------------------------------------------
# AgentOSConfig — Aggregate Root
# ---------------------------------------------------------------------------


class AgentOSConfig(BaseModel):
    """Pydantic V2 aggregate for the ``agentos:`` YAML configuration block.

    Maps 19 fields to ``agno.os.AgentOS.__init__`` parameters. Four nested
    settings models capture sub-configuration blocks. Two model-level
    validators enforce cross-field invariants.

    Invariants enforced at the boundary:
        - At least one of ``agents``, ``teams``, ``workflows`` must be non-empty.
        - ``cors_allowed_origins`` MUST NOT include ``"*"`` when
          ``authorization.enabled`` is ``True``.

    Note:
        Native-only AgentOS parameters (id, internal_service_token, telemetry,
        registry, on_route_conflict, scheduler_base_url, checkpoint, settings,
        mcp_auth) are deliberately NOT fields on this model and are therefore
        never in the ``to_agno_kwargs()`` output dict.
    """

    model_config = ConfigDict(extra="forbid")

    # --- Identity (1 field) ---
    name: str = Field(..., min_length=1, description="AgentOS instance name.")

    # --- Targets (3 fields) ---
    agents: list[str] = Field(default_factory=list, description="Agent reference names.")
    teams: list[str] = Field(default_factory=list, description="Team reference names.")
    workflows: list[str] = Field(default_factory=list, description="Workflow reference names.")

    # --- Data (2 fields) ---
    db: str | None = Field(default=None, description="Database reference name.")
    knowledge: list[str] = Field(default_factory=list, description="Knowledge base reference names.")

    # --- Interfaces (1 field) ---
    interfaces: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Interface definitions (deferred to InterfaceRegistry).",
    )

    # --- Core app (3 fields) ---
    config: str | None = Field(default=None, description="AgentOS config reference.")
    base_app: str | None = Field(default=None, description="Base FastAPI app import path.")
    lifespan: str | None = Field(default=None, description="Lifespan callable import path.")

    # --- Settings (4 nested models) ---
    authorization: AuthorizationSettings = Field(
        default_factory=AuthorizationSettings,
        description="Authorization configuration.",
    )
    mcp: MCPServerSettings = Field(
        default_factory=MCPServerSettings,
        description="MCP server configuration.",
    )
    scheduler: SchedulerSettings = Field(
        default_factory=SchedulerSettings,
        description="Scheduler configuration.",
    )
    resync: ResyncSettings = Field(
        default_factory=ResyncSettings,
        description="Resync (auto-reload) configuration.",
    )

    # --- Feature flags (5 fields) ---
    a2a_interface: bool = Field(default=False, description="Enable A2A interface.")
    cors_allowed_origins: list[str] | None = Field(default=None, description="CORS allowed origins.")
    auto_provision_dbs: bool = Field(default=True, description="Auto-provision databases.")
    run_hooks_in_background: bool = Field(default=False, description="Run hooks in background.")
    tracing: bool = Field(default=False, description="Enable tracing.")

    # --- Validators ---

    @model_validator(mode="after")
    def _validate_at_least_one_target(self) -> AgentOSConfig:
        """Reject configs with no agents, teams, OR workflows.

        SPEC_12 §2.2 validator 1: the aggregate MUST have at least one
        target entity to serve.
        """
        if not self.agents and not self.teams and not self.workflows:
            raise ValueError(
                "AgentOSConfig must have at least one of agents, teams, or workflows defined. "
                f"Got agents={self.agents}, teams={self.teams}, workflows={self.workflows}."
            )
        return self

    @model_validator(mode="after")
    def _validate_cors_wildcard_under_rbac(self) -> AgentOSConfig:
        """Reject CORS wildcard when RBAC authorization is enabled.

        SPEC_12 §2.2 validator 2: ``"*"`` origin is incompatible with
        RBAC policies. The wildcard is allowed only when authorization
        is disabled (dev-friendly default).
        """
        if (
            self.authorization.enabled
            and self.cors_allowed_origins is not None
            and "*" in self.cors_allowed_origins
        ):
            raise ValueError(
                "CORS wildcard '*' is forbidden when RBAC authorization is enabled. "
                "Specify explicit origin(s) or disable authorization."
            )
        return self

    # --- Serialization ---

    def to_agno_kwargs(self) -> dict[str, Any]:
        """Produce the kwargs dict forwarded to ``AgentOS(**kwargs)``.

        Uses ``model_dump(exclude_none=True, exclude_unset=False)``:
            - Fields with value ``None`` are OMITTED so they do not
              override AgentOS internal defaults.
            - Fields with explicit ``False`` booleans are INCLUDED
              (``exclude_unset=False`` treats them as set).
            - Nested settings models are serialized as dicts.

        Native-only AgentOS parameters are never in this dict because
        they are not fields on this model.

        Returns:
            Dict ready for ``AgentOS(**kwargs)`` construction.
        """
        return self.model_dump(exclude_none=True, exclude_unset=False)
