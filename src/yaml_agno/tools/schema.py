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

from pydantic import BaseModel, ConfigDict, Field

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
    """A single custom function declared as a dotted-path callable reference.

    ``path`` is resolved via ``AgnoResolver.resolve_class`` (allowlisted). The
    callable is returned RAW by ``CustomToolLoader`` — ``@tool`` wrapping is the
    ToolFactory's job (slice C), NOT this schema.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["function"] = "function"
    path: str = Field(..., min_length=1, description="Dotted-path callable (e.g. 'my_pkg.tools.fetch').")


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
