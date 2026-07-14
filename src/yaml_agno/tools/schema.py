"""Tool entry schemas (SPEC_11 slices A + B) — discriminated union for
the ``tools:`` YAML list.

De-opacifies ``AgentConfig.tools`` from raw dicts to a validated union
discriminated by ``kind``. Three ``kind`` resolve in slice A (builtin /
function / toolkit_class); slice B adds the real MCP schemas (mcp /
mcp_multi) with transport discrimination and the ``MCPResolver``.

NOTE: this schema ships standalone. ``AgentConfig.tools`` stays the
opaque ``list[dict]``; wiring is slice C (mirrors how model-config-
schema left ``AgentConfig.model`` untouched).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "BuiltinToolConfig",
    "CustomToolConfig",
    "CustomToolkitConfig",
    "HttpMcpConfig",
    "McpMultiToolConfig",
    "McpToolConfig",
    "StdioMcpConfig",
    "ToolEntry",
]


class BuiltinToolConfig(BaseModel):
    """A built-in Agno toolkit declared by name (e.g. ``calculator``).

    The ``name`` MUST be a key in ``BUILTIN_REGISTRY``. ``init_args`` are
    forwarded to the toolkit constructor (after alias normalization + signature
    filtering by the registry adapter). ``extra`` is allowed so the YAML can
    carry toolkit-specific flags directly.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["builtin"] = "builtin"
    name: str = Field(..., min_length=1, description="BUILTIN_REGISTRY key (e.g. 'calculator').")
    init_args: dict[str, Any] = Field(
        default_factory=dict, description="Toolkit constructor kwargs (alias-normalized + filtered)."
    )


class CustomToolConfig(BaseModel):
    """A custom ``@tool`` function declared as a dotted-path callable reference.

    ``path`` is resolved via ``CustomToolLoader.load_callable`` (allowlisted
    importlib, slice A) and returned RAW. ``ToolFactory._wrap_tool`` applies
    ``@tool(**flags)`` from the remaining fields (SPEC_11 §3.1, slice C).

    The HITL mutual-exclusivity constraint (SPEC_11 §3.1: at most one of
    ``requires_confirmation`` / ``requires_user_input`` /
    ``external_execution`` may be ``True``) is enforced at the schema
    boundary via a ``model_validator(mode="after")`` — fail-early, fail-loud,
    before ``@tool`` is applied.

    NOTE: ``tool_hooks``, ``pre_hook``, and ``post_hook`` are INTENTIONALLY
    ABSENT (DEFER to slice D, TASK_005). ``extra="forbid"`` rejects them
    until slice D adds the ``ToolHookRef`` schema + resolution.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["function"] = "function"
    path: str = Field(
        ...,
        min_length=1,
        max_length=400,
        description="Dotted-path callable (e.g. 'my_pkg.tools.fetch').",
    )

    # --- @tool identity overrides (SPEC_11 §3.1) ---
    name: str | None = Field(
        default=None,
        max_length=200,
        description="Override the function name exposed to the model.",
    )
    description: str | None = Field(
        default=None,
        description="Override the docstring exposed to the model.",
    )

    # --- @tool behavior flags (SPEC_11 §3.1) ---
    requires_confirmation: bool = Field(
        default=False,
        description="HITL: prompt the user for confirmation before execution.",
    )
    requires_user_input: bool = Field(
        default=False,
        description="HITL: collect user input before execution.",
    )
    user_input_fields: list[str] = Field(
        default_factory=list,
        description="Fields that require user input (used with requires_user_input).",
    )
    external_execution: bool = Field(
        default=False,
        description="HITL: the tool runs outside the agent's control.",
    )
    external_execution_silent: bool | None = Field(
        default=None,
        description="Silence the external_execution feedback message.",
    )
    show_result: bool | None = Field(
        default=None,
        description="Show the result in the response. Agno default None; "
        "auto-set to True only when stop_after_tool_call=True.",
    )
    stop_after_tool_call: bool = Field(
        default=False,
        description="Stop the run after this tool is called.",
    )

    # --- @tool caching flags (per-call; cross-run LRU is slice D, TASK_013) ---
    cache_results: bool = Field(
        default=False,
        description="Cache the tool result (Agno applies per-call).",
    )
    cache_dir: str | None = Field(
        default=None,
        description="Cache directory for results.",
    )
    cache_ttl: int | None = Field(
        default=None,
        ge=1,
        description="Cache TTL in seconds.",
    )

    @model_validator(mode="after")
    def _validate_hitl_mutual_exclusivity(self) -> "CustomToolConfig":
        """Enforce SPEC_11 §3.1: at most one HITL flag may be True.

        Agno's ``@tool`` decorator raises ``ValueError`` if more than one of
        ``requires_confirmation`` / ``requires_user_input`` /
        ``external_execution`` is ``True``. yaml-agno replicates this check
        at the schema boundary so YAML authors fail at parse time, not at
        wrap time (SPEC_11 §3.1: "yaml-agno replica esta validación en el
        boundary").

        Returns:
            self (unchanged) if the constraint holds.

        Raises:
            ValueError: If two or more HITL flags are True simultaneously.
        """
        hitl_active = sum(
            1
            for flag in (
                self.requires_confirmation,
                self.requires_user_input,
                self.external_execution,
            )
            if flag
        )
        if hitl_active > 1:
            raise ValueError(
                "HITL mutual-exclusivity violation (SPEC_11 §3.1): at most one of "
                "'requires_confirmation', 'requires_user_input', 'external_execution' "
                "may be True. Got: "
                f"requires_confirmation={self.requires_confirmation}, "
                f"requires_user_input={self.requires_user_input}, "
                f"external_execution={self.external_execution}."
            )
        return self


class CustomToolkitConfig(BaseModel):
    """A custom toolkit class declared as a dotted-path reference.

    Like ``function`` but resolves a Toolkit CLASS (instantiated with
    ``init_args`` after signature filtering), not a bare callable.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["toolkit_class"] = "toolkit_class"
    path: str = Field(..., min_length=1, description="Dotted-path toolkit class (e.g. 'my_pkg.MyToolkit').")
    init_args: dict[str, Any] = Field(default_factory=dict, description="Toolkit constructor kwargs.")


# --- SPEC_11 slice B: MCP single-server config -------------------------------


class StdioMcpConfig(BaseModel):
    """A single MCP server reached over stdio (subprocess).

    ``extra="forbid"`` enforces SPEC_11 decision 10.5: stdio rejects
    headers at the schema layer (no ``headers`` field, no extras
    allowed). The resolver builds ``MCPTools(command=..., env=...)``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["mcp"] = "mcp"
    transport: Literal["stdio"] = "stdio"
    command: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Shell command to launch the MCP server (e.g. 'uvx mcp-server-git').",
    )
    env: dict[str, str] | None = Field(
        default=None,
        description="Environment variables forwarded to the subprocess.",
    )


class HttpMcpConfig(BaseModel):
    """A single MCP server reached over HTTP (streamable-http or SSE).

    ``MCPTools`` does NOT accept top-level ``headers`` / ``timeout`` /
    ``sse_read_timeout`` (SPEC_11 §6.5); those live on the
    ``ClientParams`` dataclass built by the resolver. ``header_provider``
    is a dotted-path string resolved through the slice-A allowlist.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["mcp"] = "mcp"
    transport: Literal["streamable-http", "sse"]
    url: str = Field(..., min_length=1, description="MCP server URL (e.g. 'http://localhost:8000/sse').")
    headers: dict[str, str] | None = Field(
        default=None,
        description="Static HTTP headers attached to every request (dynamic headers use header_provider).",
    )
    timeout: float | None = Field(
        default=None,
        ge=1,
        description="Connect timeout in seconds. SSE=float; streamable-http is wrapped into timedelta by the resolver.",
    )
    sse_read_timeout: float | None = Field(
        default=None,
        ge=1,
        description="Read timeout in seconds. Same float->timedelta wrapping as timeout for streamable-http.",
    )
    header_provider: str | None = Field(
        default=None,
        description="Dotted-path to a Callable[..., dict] resolved via the tool allowlist (e.g. 'myapp.mcp_headers.run_headers').",
    )
    refresh_connection: bool = Field(
        default=False,
        description="Forwarded to MCPTools; Agno reconnects automatically if the connection drops.",
    )


# Pydantic V2 discriminated union on ``transport``. SPEC_11 §6.9.
# The outer ``kind: Literal["mcp"]`` on BOTH leaves lets the ToolEntry
# union route ``kind: mcp`` into this branch; ``transport`` then narrows
# stdio vs http internally.
McpToolConfig = Annotated[
    StdioMcpConfig | HttpMcpConfig,
    Field(discriminator="transport"),
]
"""Single-server MCP config. Discriminated by ``transport``:
``stdio`` -> StdioMcpConfig, ``streamable-http``/``sse`` -> HttpMcpConfig."""


# --- SPEC_11 slice B: MCP multi-server config --------------------------------


class McpMultiToolConfig(BaseModel):
    """Multiple MCP servers aggregated into one Agno MultiMCPTools entry.

    Each entry in ``servers`` is a single-server ``McpToolConfig`` (stdio
    or http, independently). The resolver fans each server out to its
    MCPTools constructor shape and aggregates them into one
    ``MultiMCPTools`` instance.

    NOTE: ``MultiMCPTools`` emits a ``DeprecationWarning`` on every
    construction (verified Agno 2.6.22, obs-2018). Tests MUST filter or
    assert the warning. ``header_provider`` is NOT supported here — Agno
    applies it uniformly across all servers, so per-server headers
    require multiple ``kind: mcp`` entries instead (R-MCP-4).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["mcp_multi"] = "mcp_multi"
    servers: list[McpToolConfig] = Field(
        ...,
        min_length=1,
        description="One or more single-server MCP configs (stdio or http).",
    )
    allow_partial_failure: bool = Field(
        default=False,
        description="Forwarded to MultiMCPTools; if True, a failing server does not fail the whole entry.",
    )
    refresh_connection: bool = Field(
        default=False,
        description="Forwarded to MultiMCPTools; reconnect on connection drop.",
    )


# Discriminated union. Pydantic V2 routes by the ``kind`` Literal.
ToolEntry = (
    BuiltinToolConfig
    | CustomToolConfig
    | CustomToolkitConfig
    | McpToolConfig
    | McpMultiToolConfig
)
