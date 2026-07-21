---
change: mcp-integration
spec: SPEC_11
artifact: design
status: designed
artifact_store: hybrid
depends_on:
  - exploration: engram sdd/mcp-integration/explore (obs-2018)
  - shipped_slice_a_schema: src/yaml_agno/tools/schema.py (McpToolConfig/McpMultiToolConfig placeholders, lines 76-103)
  - shipped_slice_a_loader: src/yaml_agno/tools/custom_loader.py (load_mcp/load_mcp_multi NotImplementedError, lines 73-90)
  - shipped_slice_a_security: src/yaml_agno/tools/security.py (is_module_allowed, _resolve_dotted pattern)
  - normative_ssot: specs/SPEC_11_TOOLS_AND_MCP.md (§6.5, §6.6, §6.9, §6.10, §9.6, decisions 10.2/10.5/10.7)
  - proposal: pending (sdd/mcp-integration/proposal — parallel run; not yet persisted)
  - spec_delta: pending (sdd/mcp-integration/spec — parallel run; not yet persisted)
---

# Design: mcp-integration (SPEC_11 slice B — MCP server resolution)

> **@ai-directive**: This document is the technical HOW. The normative SSOT is
> `specs/SPEC_11_TOOLS_AND_MCP.md` (read-only) plus this change's delta spec
> (pending). The code shown here is **living documentation** — `sdd-apply`
> creates the `.py` files verbatim. Any discrepancy resolves in favor of the
> spec + the REAL Agno 2.6.22 API (verified in exploration obs-2018, NOT docs).
> Where this design DIVERGES from SPEC_11 §9.6 (`async resolve_single` +
> `await tools.connect()`), the divergence is explicit and justified in A1.

## Technical Approach

SPEC_11 slice B replaces the two MCP placeholders shipped in slice A
(`McpToolConfig` / `McpMultiToolConfig` in `schema.py`, plus the
`NotImplementedError` stubs in `CustomToolLoader.load_mcp` /
`load_mcp_multi`) with a **real discriminated MCP config union** and a
**synchronous `MCPResolver` that returns UNCONNECTED instances**.

The resolver is a thin constructor-layer over Agno's `MCPTools` /
`MultiMCPTools`: it maps a validated `McpToolConfig` to the right Agno
constructor call, builds the correct `ClientParams` dataclass when the
transport is HTTP (branching `timeout` type: `float` for SSE,
`timedelta` for StreamableHTTP), resolves the optional
`header_provider` dotted-path through the SAME allowlist mechanism slice
A shipped (`security.is_module_allowed` + the `_resolve_dotted` split),
and returns the constructed instance **without calling `connect()`**.
Agent owns the async connect/close lifecycle (it already does —
`agent/_tools.py` auto-connects `MCPTools` / `MultiMCPTools` during
`aget_tools` and disconnects post-run; verified in obs-2018).

This keeps the resolver **sync**, mirroring slice A's `CustomToolLoader`
pattern and avoiding an async ToolFactory in slice C (reconciles SPEC_11
§9.6 and decision 10.2 — see A1).

### Flujo de datos

```
YAML dict ──► ToolEntry union (Pydantic discrimina por ``kind``)
                │
                ├─ kind: mcp ─► McpToolConfig union
                │               Pydantic discrimina por ``transport``
                │               ├─ StdioMcpConfig  ─► MCPTools(command=, env=)
                │               └─ HttpMcpConfig   ─► build ClientParams
                │                                      ├─ sse             timeout: float
                │                                      └─ streamable-http timeout: timedelta
                │                                   + resolve header_provider (allowlist)
                │                                   ─► MCPTools(server_params=, transport=,
                │                                              refresh_connection=, header_provider=)
                │               MCPResolver.resolve_single ─► MCPTools  (UNCONNECTED)
                │
                └─ kind: mcp_multi ─► McpMultiToolConfig
                                      servers: list[McpToolConfig]
                                      ─► fan-out each server to its MCPTools shape
                                      ─► collect commands[] / server_params_list[]
                                      ─► MultiMCPTools(commands=..., server_params_list=...,
                                                       allow_partial_failure=,
                                                       refresh_connection=)
                                      MCPResolver.resolve_multi ─► MultiMCPTools (UNCONNECTED)

[run time, NOT this slice]
Agent.aget_tools ──► detects MCPTools/MultiMCPTools by MRO name check
                  ──► await tool.connect() if not tool.initialized
                  ──► disconnect_mcp_tools post-run
```

## Architecture Decisions

### A1 — SYNC resolver returns UNCONNECTED instances (Agent owns connect)

**Choice**: `MCPResolver.resolve_single(config) -> MCPTools` and
`resolve_multi(config) -> MultiMCPTools` are **synchronous** and
**construct-only** — they never `await connect()`. Agent connects at run
time via its existing `aget_tools` → `connect_mcp_tools` lifecycle.

**Alternatives considered**:
- SPEC_11 §9.6 literal (`async resolve_single` + `await tools.connect()`):
  forces the ToolFactory to be async-aware NOW (decision 10.2), couples
  YAML parsing to network I/O at construction, and blocks config
  validation behind a live server.
- Sync resolver that connects synchronously: impossible — `connect()` is
  a coroutine (verified obs-2018); there is no sync connect path.

**Rationale**: matches the slice-A `CustomToolLoader` sync pattern
(consistency across the tools layer). Agent ALREADY auto-connects
`MCPTools`/`MultiMCPTools` during `aget_tools` (verified in obs-2018:
MRO name check, `await tool.connect()` when `not tool.initialized`,
`disconnect_mcp_tools` post-run). Defering connect to Agent:
(a) keeps slice C's `ToolFactory` sync, (b) lets YAML validation run
offline, (c) aligns with how Agno itself expects callers to manage the
lifecycle. This RECONCILES decision 10.2 ("ToolFactory must be
async-aware") — that only holds if the resolver awaits connect; a
sync-unconnected resolver makes the ToolFactory stay sync. The delta
spec for this change MUST amend SPEC_11 §9.6 to remove `await
tools.connect()` from the resolver (open item, see Open Questions).

### A2 — `transport` discriminator: StdioMcpConfig vs HttpMcpConfig

**Choice**: `McpToolConfig` is an `Annotated` union of
`StdioMcpConfig` (`transport: Literal["stdio"]`) and `HttpMcpConfig`
(`transport: Literal["streamable-http", "sse"]`), discriminated by the
`transport` field. `StdioMcpConfig` uses `extra="forbid"` so a YAML
carrying `headers` under stdio fails validation (decision 10.5).

**Alternatives considered**:
- Single `McpToolConfig` with optional `command`/`url`/`headers`:
  ambiguous, loses the stdio-rejectsheaders invariant, and forces
  runtime branching instead of Pydantic discrimination.
- Discriminate by `kind` instead of `transport`: `kind` is already
  consumed by the outer `ToolEntry` union; reusing it would collide.

**Rationale**: SPEC_11 §6.9 prescribes this exact two-model split.
`extra="forbid"` on `StdioMcpConfig` encodes decision 10.5 (stdio
rejects headers) at the schema layer — no validator code needed.

### A3 — `timeout` type branching: float (SSE) vs timedelta (StreamableHTTP)

**Choice**: the resolver inspects `config.transport` to build the
correct `ClientParams`. For SSE it passes `timeout` / `sse_read_timeout`
as `float` (matching `SSEClientParams.timeout: Optional[float]`). For
StreamableHTTP it wraps both into `datetime.timedelta` (matching
`StreamableHTTPClientParams.timeout: Optional[timedelta]`). The YAML
schema carries `float | None` for both (SPEC_11 §6.9); the type
conversion happens ONLY in the resolver.

**Alternatives considered**:
- Two schema fields (`timeout_seconds: float`, `timeout_timedelta`):
  leaks the Agno API divergence into YAML.
- Carry `timedelta` in YAML: unparseable as a YAML scalar without
  custom tags; hostile to users.

**Rationale**: verified in obs-2018 — `SSEClientParams.timeout` is
`Optional[float]=5`, `StreamableHTTPClientParams.timeout` is
`Optional[timedelta]=timedelta(seconds=30)`. Passing a float where
timedelta is expected raises at the Agno layer; passing timedelta where
float is expected likewise. The resolver is the single branch point.
YAML stays ergonomic (seconds as float), the conversion is encapsulated.

### A4 — `header_provider` resolved via the SAME allowlist as slice A

**Choice**: the YAML carries `header_provider: str` (dotted-path, e.g.
`"myapp.mcp_headers.run_headers"`). The resolver reuses the slice-A
`security.is_module_allowed` guard + the `_resolve_dotted` split
(`rpartition(".")` → module + name → `resolver.resolve_class`) to
obtain the `Callable[..., dict]`. No new import path, no new allowlist.

**Alternatives considered**:
- A separate `header_allowlist`: doubles the security surface; invites
  drift between the tool allowlist and the header allowlist.
- Inline Python in YAML (`eval`): categorically rejected (SPEC_00 — the
  30% Python lives in modules, not in YAML strings).

**Rationale**: the header_provider is functionally identical to a
custom tool entry — it's a user-supplied Python callable referenced by
dotted-path. Reusing `_resolve_dotted` is defense-in-depth via the same
allowlist that already gates `function` / `toolkit_class`. Agno itself
inspects the callable's signature at call time and passes
`run_context` / `agent` / `team` only if declared (obs-2018) —
yaml-agno does not need to replicate that inspection.

### A5 — DEFER: ToolFactory (C), hooks/caching/concurrency (D), connect/close (Agent)

**Choice**: slice B implements ONLY the config schemas + `MCPResolver`.
It does NOT implement:
- **Slice C** — `ToolFactory` orchestration: wiring `MCPResolver` output
  into `Agent.tools`, `@tool` wrapping for `function` kind, `AgentConfig.
  tools` narrowing from opaque `list[dict]` to `list[ToolEntry]`.
- **Slice D** — hooks, `cache_callables` / `cache_results` (decision
  10.4), `asyncio.TaskGroup` for parallel tool calls (decision 10.7).
- **Agent runtime** — `connect()` / `close()` lifecycle. Agent owns
  this; slice B does not touch it.

`refresh_connection` and `allow_partial_failure` are forwarded as
pass-through flags (Agno handles their runtime semantics); slice B does
not implement the reconnection behavior itself.

**Alternatives considered**:
- Implement `connect()` in the resolver now (SPEC_11 §9.6 literal):
  rejected per A1.
- Implement `ToolFactory` in slice B: inflates scope, couples schema +
  resolver + factory in one review (violates the 400-line review budget
  guard).

**Rationale**: clear slice boundaries (DECISIONES.md §2.6, "build ON
TOP, never frankenstein"). Each slice ships one concern end-to-end.

### A6 — Reconciling `McpMultiToolConfig` schema vs SPEC_11 §6.9 vs Agno reality

**Choice**: `McpMultiToolConfig` carries `servers: list[McpToolConfig]`
(`min_length=1`), `allow_partial_failure: bool = False`, and
`refresh_connection: bool = False`. `extra="forbid"`.

SPEC_11 §6.9 lists `cache_results: bool = False` instead. The explore
(obs-2018) verified `MultiMCPTools.__init__` accepts
`allow_partial_failure` and `refresh_connection` but NOT `cache_results`
(caching is decision 10.4, slice D). This design:
- ADDS `allow_partial_failure` + `refresh_connection` (real Agno params).
- OMITS `cache_results` (deferred to slice D with the rest of caching).
- Enforces `servers` homogeneity via the nested `McpToolConfig` union
  (each server independently stdio or http).

**Alternatives considered**:
- Follow SPEC_11 §6.9 literally (ship `cache_results`): would forward a
  kwarg `MultiMCPTools` rejects, raising at construction.
- Ship both: one field dead (`cache_results` ignored) — confusing.

**Rationale**: code must match the REAL Agno API (obs-2018), not the
spec's aspirational shape. The delta spec for this change MUST amend
SPEC_11 §6.9 (`McpMultiToolConfig`) to swap `cache_results` for
`allow_partial_failure` + `refresh_connection` (open item).

## Class-by-Class Model (target Python code)

> The code below is faithful to the spec + verification against Agno
> 2.6.22 (obs-2018). `sdd-apply` creates these files literally.

### 1. MODIFY `src/yaml_agno/tools/schema.py`

Replace the `McpToolConfig` placeholder (lines 76-86) and the
`McpMultiToolConfig` placeholder (lines 88-93) with the real models.
Keep `BuiltinToolConfig`, `CustomToolConfig`, `CustomToolkitConfig`
unchanged. Update the module docstring (lines 1-12) and `__all__`
(lines 20-27) to add `StdioMcpConfig`, `HttpMcpConfig`.

Full replacement of the MCP-related sections (the rest of the file —
imports, `BuiltinToolConfig`, `CustomToolConfig`, `CustomToolkitConfig`
— stays as shipped in slice A):

```python
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


# --- BuiltinToolConfig / CustomToolConfig / CustomToolkitConfig -------
# (UNCHANGED from slice A — keep the existing class bodies verbatim.)
# class BuiltinToolConfig(BaseModel): ...      # kind: Literal["builtin"]
# class CustomToolConfig(BaseModel): ...       # kind: Literal["function"]
# class CustomToolkitConfig(BaseModel): ...    # kind: Literal["toolkit_class"]


# --- SPEC_11 slice B: MCP single-server config -----------------------


class StdioMcpConfig(BaseModel):
    """A single MCP server reached over stdio (subprocess).

    ``extra="forbid"`` enforces SPEC_11 decision 10.5: stdio rejects
    headers at the schema layer (no ``headers`` field, no extras
    allowed). The resolver builds ``MCPTools(command=..., env=...)``.
    """

    model_config = ConfigDict(extra="forbid")

    transport: Literal["stdio"] = "stdio"
    command: str = Field(..., min_length=1, max_length=500, description="Shell command to launch the MCP server (e.g. 'uvx mcp-server-git').")
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
McpToolConfig = Annotated[
    StdioMcpConfig | HttpMcpConfig,
    Field(discriminator="transport"),
]
"""Single-server MCP config. Discriminated by ``transport``:
``stdio`` -> StdioMcpConfig, ``streamable-http``/``sse`` -> HttpMcpConfig."""


# --- SPEC_11 slice B: MCP multi-server config ------------------------


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
```

**NOTE on the `kind` field**: `McpToolConfig` is a union, NOT a
`BaseModel`, so the outer `ToolEntry` discriminator (`kind`) applies via
the two leaves that carry it: `StdioMcpConfig` / `HttpMcpConfig` need a
`kind: Literal["mcp"] = "mcp"` field added (mirroring slice A's
placeholder), OR `ToolEntry` must be re-expressed as an `Annotated`
union with `Field(discriminator="kind")`. The latter is the clean
Pydantic V2 pattern. Concretely, `sdd-apply` MUST add
`kind: Literal["mcp"] = "mcp"` to BOTH `StdioMcpConfig` and
`HttpMcpConfig` (shown omitted above only to avoid repetition — they
are required for the outer `kind` discrimination to route `mcp`
entries into this branch). The `transport` discriminator then narrows
stdio vs http. `sdd-tasks` should make this dual-discriminator
structure an explicit RED test (a dict with `kind: mcp, transport: stdio`
routes to `StdioMcpConfig`; `kind: mcp, transport: sse` routes to
`HttpMcpConfig`).

### 2. NEW `src/yaml_agno/tools/mcp_resolver.py`

```python
"""MCPResolver — maps validated MCP configs to UNCONNECTED Agno instances.

Synchronous, construct-only: builds ``MCPTools`` / ``MultiMCPTools`` with
the correct ``ClientParams`` (SSE=float timeouts, StreamableHTTP=timedelta)
and resolves ``header_provider`` dotted-paths via the slice-A allowlist.
Does NOT call ``connect()`` — Agent owns the async connect/close
lifecycle (it auto-connects during ``aget_tools``; verified obs-2018).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Callable

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

    def __init__(self, resolver: "AgnoResolver") -> None:
        """Initialize the resolver.

        Args:
            resolver: The AgnoResolver whose ``resolve_class`` performs the
                allowlisted importlib resolution for ``header_provider``.
        """
        self._resolver = resolver

    def resolve_single(self, config: "McpToolConfig") -> MCPTools:
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
            return self._build_stdio(config)
        return self._build_http(config)

    def resolve_multi(self, config: "McpMultiToolConfig") -> MultiMCPTools:
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
            urls_transports=urls_transports or None,
            server_params_list=server_params_list or None,
            allow_partial_failure=config.allow_partial_failure,
            refresh_connection=config.refresh_connection,
        )

    # --- internals -----------------------------------------------------

    def _build_stdio(self, config: "StdioMcpConfig") -> MCPTools:
        """Construct an MCPTools for a stdio server.

        Args:
            config: The validated StdioMcpConfig.

        Returns:
            UNCONNECTED MCPTools(command=..., env=...).
        """
        return MCPTools(command=config.command, env=config.env)

    def _build_http(self, config: "HttpMcpConfig") -> MCPTools:
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
        self, config: "HttpMcpConfig"
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
            params = SSEClientParams(
                url=config.url,
                headers=config.headers,
                timeout=config.timeout,
                sse_read_timeout=config.sse_read_timeout,
            )
        else:
            # streamable-http: wrap float seconds into timedelta.
            timeout_td = timedelta(seconds=config.timeout) if config.timeout is not None else None
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

    def _resolve_header_provider(self, config: "HttpMcpConfig") -> Callable[..., dict] | None:
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

    def _resolve_dotted(self, dotted_path: str) -> Callable[..., dict]:
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
            raise ValueError(f"Invalid dotted path: {dotted_path!r}. Expected 'module.name'.")
        module_path, _, name = dotted_path.rpartition(".")
        if not is_module_allowed(module_path):
            raise SecurityError(
                f"Module {module_path!r} is not in the tool allowlist. header_provider "
                f"must reference an allowlisted module (configure the allowlist at bootstrap)."
            )
        return self._resolver.resolve_class(module_path, name)
```

### 3. MODIFY `src/yaml_agno/tools/custom_loader.py`

Replace `load_mcp` (lines 73-83) and `load_mcp_multi` (lines 85-90) to
delegate to `MCPResolver`. Keep `load_callable`, `load_toolkit_class`,
and `_resolve_dotted` unchanged.

```python
# --- Replace the two NotImplementedError stubs with delegation. -------

# New import at top of file (add to existing imports):
from yaml_agno.tools.mcp_resolver import MCPResolver

# In CustomToolLoader.__init__, accept an optional MCPResolver OR
# construct one from the existing AgnoResolver. Preferred: construct
# lazily so slice-A callers that never touch MCP pay no import cost.
#
# Updated __init__:
    def __init__(self, resolver: "AgnoResolver") -> None:
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

# Updated load_mcp:
    def load_mcp(self, config: "McpToolConfig") -> Any:
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

# Updated load_mcp_multi:
    def load_mcp_multi(self, config: "McpMultiToolConfig") -> Any:
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
```

### 4. MODIFY `src/yaml_agno/tools/__init__.py`

Re-export `MCPResolver` and the two new config leaves.

```python
"""yaml-agno tools layer — SPEC_11 (slices A + B).

Public API:
    from yaml_agno.tools import (
        ToolEntry, BUILTIN_REGISTRY, CustomToolLoader, ToolkitAdapter,
        MCPResolver, StdioMcpConfig, HttpMcpConfig,
    )
"""

from yaml_agno.tools.custom_loader import CustomToolLoader
from yaml_agno.tools.mcp_resolver import MCPResolver
from yaml_agno.tools.registry import BUILTIN_REGISTRY, ToolkitAdapter, UnknownBuiltinError
from yaml_agno.tools.schema import (
    BuiltinToolConfig,
    CustomToolConfig,
    CustomToolkitConfig,
    HttpMcpConfig,
    McpMultiToolConfig,
    McpToolConfig,
    StdioMcpConfig,
    ToolEntry,
)
from yaml_agno.tools.security import SecurityError, is_module_allowed

__all__ = [
    "BUILTIN_REGISTRY",
    "BuiltinToolConfig",
    "CustomToolConfig",
    "CustomToolkitConfig",
    "CustomToolLoader",
    "HttpMcpConfig",
    "MCPResolver",
    "McpMultiToolConfig",
    "McpToolConfig",
    "SecurityError",
    "StdioMcpConfig",
    "ToolEntry",
    "ToolkitAdapter",
    "UnknownBuiltinError",
    "is_module_allowed",
]
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/tools/schema.py` | Modify | Replace McpToolConfig/McpMultiToolConfig placeholders with StdioMcpConfig + HttpMcpConfig (transport union) + real McpMultiToolConfig. Update docstring + `__all__`. |
| `src/yaml_agno/tools/mcp_resolver.py` | Create | MCPResolver — sync `resolve_single` / `resolve_multi` returning UNCONNECTED MCPTools/MultiMCPTools. Builds SSE/StreamableHTTPClientParams with correct timeout types. Resolves header_provider via allowlist. |
| `src/yaml_agno/tools/custom_loader.py` | Modify | load_mcp / load_mcp_multi delegate to MCPResolver (remove NotImplementedError). Lazy MCPResolver construction in __init__. |
| `src/yaml_agno/tools/__init__.py` | Modify | Re-export MCPResolver + StdioMcpConfig + HttpMcpConfig. |
| `tests/unit/tools/test_mcp_schema.py` | Create | Dual-discriminator routing (kind=mcp → transport=stdio/sse), stdio rejects headers, multi min_length=1. |
| `tests/unit/tools/test_mcp_resolver.py` | Create | resolve_single (stdio/http/SSE), timeout type branching (float vs timedelta), header_provider allowlist + SecurityError, resolve_multi fan-out, DeprecationWarning handling. |
| `tests/unit/tools/test_custom_loader_mcp.py` | Create | load_mcp / load_mcp_multi delegation (stubbed MCPResolver). |

**Total**: 4 src (1 new + 3 modify) + 3 tests. `AgentConfig.tools` is
NOT touched (opaque `list[dict]` stays — wiring is slice C).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Dual discriminator: `kind: mcp` + `transport: stdio` → StdioMcpConfig | `TypeAdapter(McpToolConfig)` / `TypeAdapter(ToolEntry)` from dict. |
| Unit | stdio rejects headers (decision 10.5) | StdioMcpConfig with `headers: {...}` → ValidationError (extra forbidden). |
| Unit | resolve_single stdio | Stub `MCPTools.__init__` (or monkeypatch) — assert called with `command=, env=`. No connect. |
| Unit | resolve_single http — SSE keeps float timeout | Assert SSEClientParams built with `timeout=float`. |
| Unit | resolve_single http — StreamableHTTP wraps timedelta | Assert StreamableHTTPClientParams.timeout is `timedelta`. |
| Unit | header_provider resolved via allowlist | Real callable under `agno.tools.*` prefix; assert passed to MCPTools. |
| Unit | header_provider SecurityError on non-allowlisted | Module outside `agno.tools.` → raises SecurityError. |
| Unit | resolve_multi fans out mixed stdio+http | 2 servers → MultiMCPTools gets `commands=[stdio]` + `server_params_list=[http params]`. |
| Unit | MultiMCPTools DeprecationWarning | `pytest.warns(DeprecationWarning)` OR `warnings.filterwarnings("ignore", ...)`. |
| Unit | load_mcp / load_mcp_multi delegation | Stubbed MCPResolver — assert delegation, no NotImplementedError. |
| Integration | Real MCPTools construction (no network) | stdio MCPTools(command="echo hi") constructs without connecting; assert `not tool.initialized`. |

### Stub strategy for unit tests

The resolver imports `MCPTools` / `MultiMCPTools` / `SSEClientParams` /
`StreamableHTTPClientParams` from `agno.tools.mcp`. Unit tests stub the
resolver's BEHAVIOR via:
1. A fake `AgnoResolver` (`InMemoryDependencyAdapter` pattern from
   slice A) so `_resolve_dotted` returns a known callable without real
   importlib.
2. Where construction must be observed without a real subprocess /
   network, monkeypatch `MCPTools.__init__` / `MultiMCPTools.__init__`
   to capture kwargs. (Construction itself is synchronous and does NOT
   connect — verified obs-2018 — so this is safe.)

Where feasible (no network at construct), prefer the REAL
`MCPTools(command=...)` constructor to catch Agno API drift.

### DeprecationWarning handling

`MultiMCPTools.__init__` emits `DeprecationWarning` unconditionally
(R-MCP-3). Tests touching `resolve_multi` MUST either:
- `with pytest.warns(DeprecationWarning):` when the warning is the
  subject of the test, OR
- `warnings.filterwarnings("ignore", category=DeprecationWarning)` at
  module scope otherwise.

`pyproject.toml` / `pytest` config may promote unintentional warnings
to errors — `sdd-apply` must verify the suite is green with the filter
in place (RISK004).

## TDD Approach (RED → GREEN → REFACTOR)

Strict TDD (project target 100% coverage). Per component:

1. **schema.py (MCP schemas)** — RED: TypeAdapter(McpToolConfig) /
   TypeAdapter(ToolEntry) routing tests fail (ImportError on
   StdioMcpConfig/HttpMcpConfig). GREEN: literal two-model union.
   Branch tests: stdio rejects headers; http accepts headers;
   transport discriminator routes correctly; McpMultiToolConfig
   servers min_length=1.
2. **mcp_resolver.py** — RED: resolve_single/resolve_multi tests fail.
   GREEN: literal MCPResolver with timeout-type branching and
   allowlist-backed header_provider. Branch tests: stdio path, SSE
   float, StreamableHTTP timedelta, header_provider None/present/
   SecurityError, resolve_multi mixed servers.
3. **custom_loader.py (delegation)** — RED: load_mcp/load_mcp_multi
   still raise NotImplementedError. GREEN: delegate to MCPResolver.
4. **__init__.py** — smoke import test (cold-import regression).

## Verification Strategy

1. `python -m pytest -m unit` — green. Coverage 100% on touched files.
2. `ruff check .` — clean.
3. `mypy src/yaml_agno` — clean.
4. Smoke:
   `python -c "from yaml_agno.tools import MCPResolver, StdioMcpConfig, HttpMcpConfig, McpToolConfig, McpMultiToolConfig; print('OK')"`.
5. Agno import sanity (confirms import path used in resolver):
   `python -c "from agno.tools.mcp import MCPTools, MultiMCPTools; from agno.tools.mcp.params import SSEClientParams, StreamableHTTPClientParams; print('OK')"`.
   If this FAILS, the resolver import is wrong — find the real path
   before shipping (the explore verified this path against 2.6.22; a
   different Agno version may have moved it).
6. Cold-import regression (the slice-#4 circular-import lesson):
   `python -c "from yaml_agno.tools import *"` AND
   `python -c "from yaml_agno.models import AgentConfig"`.
7. `git diff --name-only src/yaml_agno/models/config/agent_config.py`
   → EMPTY (AgentConfig untouched; wiring is slice C).
8. Dual discriminator sanity:
   `python -c "from pydantic import TypeAdapter; from yaml_agno.tools import McpToolConfig; ta=TypeAdapter(McpToolConfig); print(ta.validate_python({'kind':'mcp','transport':'stdio','command':'echo hi'})); print(ta.validate_python({'kind':'mcp','transport':'sse','url':'http://x'}))"`.

## Migration / Rollback

**No migration.** Slice B is additive: it replaces two placeholder
schemas (that parsed but could not resolve) and two `NotImplementedError`
stubs with real implementations. `AgentConfig.tools` stays opaque
(wiring is slice C), so no existing test fixtures break.

**Rollback** = `git revert` of the slice B commits. The placeholders
from slice A remain valid (they would simply re-appear). No data, no
feature flags, no dependents (ToolFactory is slice C).

**Risk register**:
- **R-MCP-1**: SPEC_11 §9.6 shows `async resolve_single` +
  `await tools.connect()`. This design DIVERGES (sync, unconnected).
  The delta spec MUST amend §9.6 (open item). Until then, the spec
  and the implementation disagree on the resolver shape.
- **R-MCP-2**: timeout type divergence (float vs timedelta) — handled
  in the resolver (`_build_http_params`). If Agno changes the param
  types in a future version, this branch breaks loudly at construction.
- **R-MCP-3**: `MultiMCPTools` DeprecationWarning on every construction.
  Tests filter it; documented in the McpMultiToolConfig docstring.
- **R-MCP-4**: `header_provider` on MultiMCPTools applies uniformly to
  ALL servers; per-server headers require multiple `kind: mcp` entries.
  Documented in McpMultiToolConfig docstring.
- **R-MCP-5**: `allow_partial_failure` only on MultiMCPTools (MCPTools
  has no equivalent). Schema only exposes it on McpMultiToolConfig.
- **R-MCP-6**: Agent's connect failure is `log_warning`, not raise —
  MCP tools may silently not be available. Slice B does not surface
  this; slice C/D verification should consider it.

## Open Questions

- [ ] **SPEC_11 §9.6 reconciliation**: the delta spec for this change
  MUST amend §9.6 to (a) make `resolve_single` / `resolve_multi` SYNC,
  (b) remove `await tools.connect()` from the resolver (Agent owns
  connect), (c) reconcile decision 10.2 ("ToolFactory must be
  async-aware") with the sync-resolver choice. `sdd-spec` owns this;
  this design assumes the reconciliation lands.
- [ ] **SPEC_11 §6.9 `McpMultiToolConfig` reconciliation**: the delta
  spec MUST swap `cache_results` for `allow_partial_failure` +
  `refresh_connection` (real Agno params; caching is slice D).
- [ ] **Dual-discriminator clarity**: confirm at apply time that
  `StdioMcpConfig` / `HttpMcpConfig` both carry
  `kind: Literal["mcp"] = "mcp"` so the outer `ToolEntry` union routes
  `kind: mcp` into the `McpToolConfig` branch, and the inner
  `transport` discriminator then narrows stdio vs http. This is the
  one non-obvious Pydantic V2 pattern in the slice; it deserves an
  explicit RED test.
