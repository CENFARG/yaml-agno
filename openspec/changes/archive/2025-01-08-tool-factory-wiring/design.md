---
change: tool-factory-wiring
spec: SPEC_11
status: designed
artifact_store: hybrid
depends_on:
  - openspec/specs/tools-slice-a-schema-resolver
  - openspec/specs/mcp-integration
  - openspec/specs/agent-config-schema
ai-directive: SSOT for HOW (literal code). Specs/SPEC_11_TOOLS_AND_MCP.md resolves
  discrepancies on flag semantics; shipped code (schema.py path field, custom_loader
  raw return) resolves on naming. This design is slice C only — hooks/caching/
  concurrency/tool_call_limit are DEFER to slice D.
---

# Design: ToolFactory Wiring (SPEC_11 Slice C)

## Technical Approach

Slice C closes the loop opened by slices A+B: those slices ship a validated
`ToolEntry` union and four resolvers (BUILTIN_REGISTRY, CustomToolLoader,
MCPResolver) that return native Agno objects, but nothing wires `cfg.tools`
into `agno.Agent(tools=...)`. This slice adds one orchestrator
(`ToolFactory.build`), widens `CustomToolConfig` to carry the `@tool` flags
SPEC_11 §3.1 requires, applies `@tool(**flags)` at the factory (not the loader),
and threads an optional `resolver` param through `AgentFactory.build()`.

The factory is **synchronous**: `MCPResolver` (slice B) returns UNCONNECTED
`MCPTools` / `MultiMCPTools` and `agno.Agent` auto-connects them during
`aget_tools` (MRO name-check + `await tool.connect()`, verified obs-2018).
There is no `await` on the construction path, so a sync `ToolFactory` is viable.

`AgentConfig.tools` stays opaque (`list[dict[str, Any]]`) per Option B: the
`ToolEntry` validation boundary moves from config-parse to factory-build via
`TypeAdapter(ToolEntry)`, which keeps the 9-opaque-slots symmetry and breaks
zero existing tests.

## Architecture Decisions

### A1: Option B — opaque `AgentConfig.tools`, resolve at factory time

| Option | Tradeoff | Decision |
|--------|----------|----------|
| A. Widen `AgentConfig.tools` to `list[ToolEntry]` | Couples SPEC_02 to SPEC_11 at type level, breaks the 9-opaque-slots symmetry, costs 5 test rewrites (`test_agent_config.py`, `test_agent_factory.py` use kindless dicts) | Rejected |
| **B. Keep opaque, resolve in `ToolFactory.build()`** | Validation boundary moves to factory-build; `TypeAdapter` parses each dict | **Chosen** |

**Rationale**: AgentConfig is a pure YAML-shape schema (PHIL002) that NAMES
slots; it does not semantically resolve sub-systems. Widening only `tools`
while the other 8 stay opaque is inconsistent. Option B breaks zero shipped
tests — the union is still validated, only the WHERE changes.

### A2: SYNC `ToolFactory` — MCP UNCONNECTED + Agent auto-connect

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Async `ToolFactory.build()` | Forces `await` through AgentFactory and every caller; `MCPResolver` would need an async path | Rejected |
| **SYNC `ToolFactory.build()`** | Viable because `MCPResolver` returns UNCONNECTED instances and Agent auto-connects at run time | **Chosen** |

**Rationale**: verified Agno 2.6.22 (obs-2018, archived MCP design A1). Agent's
`aget_tools` detects `MCPTools` / `MultiMCPTools` by MRO name and calls
`await tool.connect()` when `not tool.initialized`. No `await` is needed at
construction, so the factory and `AgentFactory.build()` stay sync.

### A3: Widen `CustomToolConfig` with `@tool` flags + HITL validator

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Read flags from a side config at wrap time | Two sources of truth; `extra="forbid"` would reject them | Rejected |
| **Widen `CustomToolConfig` in `schema.py`** | Schema-breaking WITHIN the tools layer (does NOT touch AgentConfig); early HITL failure at schema boundary | **Chosen** |

**Rationale**: SPEC_11 §3.1 mandates "yaml-agno replica esta validación en el
boundary". A `model_validator(mode="after")` enforces the HITL
mutual-exclusivity (at most one of `requires_confirmation` /
`requires_user_input` / `external_execution` is `True`) BEFORE `@tool` is
applied — fail-early, fail-loud. `tool_hooks` / `pre_hook` / `post_hook` are
OMITTED (DEFER to slice D per A5); `extra="forbid"` rejects them until slice D
adds them explicitly.

**Field naming**: keep `path` (shipped convention, consistent with
`CustomToolkitConfig`), NOT `module` (SPEC_11 §3.3 uses `module` but the
shipped slice-A code — `custom_loader.py:73`, `test_schema.py:38` — already
reads `config.path`). Follow the existing shipped pattern.

### A4: `@tool` wrapping in `ToolFactory`, not in `CustomToolLoader`

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Wrap in `CustomToolLoader.load_callable()` | Couples import to decoration; cannot cache raw callables separately later | Rejected |
| **Wrap in `ToolFactory._wrap_tool()`** | Separation of concerns: loader imports (security boundary), factory decorates (behavior boundary) | **Chosen** |

**Rationale**: SPEC_11 §9.5 is explicit — the loader returns the RAW callable
and "the ToolFactory is responsible for wrapping the returned callable with
`@tool(**config_flags)`". This separation is what will let slice D cache the
final decorated object independently of the import allowlist guard.

### A5: DEFER hooks / caching / concurrency / `tool_call_limit` to slice D

| Concern | Status | Reason |
|---------|--------|--------|
| `tool_hooks` / `pre_hook` / `post_hook` | DEFER (TASK_005) | Requires hook resolution + registry; schema OMITS the field (`extra="forbid"` rejects) |
| Cross-run caching (`cache_callables`, `callable_tools_cache_key`) | DEFER (TASK_013) | `cache_results` / `cache_dir` / `cache_ttl` ARE declared (Agno applies them per-call); cross-run LRU is slice D |
| `asyncio.TaskGroup` parallel tool calls | DEFER (TASK_012) | Concurrency optimization; sync path is correct |
| `tool_call_limit` forwarding | DEFER (TASK_011) | `AgentConfig` has no `tool_call_limit` field; requires SPEC_02 evolution |
| Registry expansion to 120+ | DEFER (TASK_003) | Stays at 5 adapters |

**Rationale**: slice C is the wiring slice — it closes the loop with the
minimum surface to make `cfg.tools` reach `Agent(tools=...)`. Everything else
builds on top of this wiring existing.

## Data Flow

```
YAML agent.tools (list[dict])
        │
        ▼
AgentConfig.tools  (opaque list[dict[str, Any]] — UNCHANGED, Option B)
        │
        ▼
AgentFactory.build(cfg, resolver=None)
        │  if cfg.tools and resolver is not None:
        ▼
ToolFactory(resolver).build(cfg.tools)
        │
        │  for each dict: TypeAdapter(ToolEntry).validate_python(dict)
        │  → ToolEntry instance (kind-discriminated)
        │
        │  dispatch by isinstance:
        ├── BuiltinToolConfig     → BUILTIN_REGISTRY[name].build(resolver, init_args) → Toolkit
        ├── CustomToolConfig      → loader.load_callable(cfg) → _wrap_tool(raw, cfg) → Function
        ├── CustomToolkitConfig   → loader.load_toolkit_class(cfg) → cls(**init_args) → Toolkit
        ├── StdioMcpConfig        → loader.load_mcp(cfg)  → MCPTools (UNCONNECTED)
        ├── HttpMcpConfig         → loader.load_mcp(cfg)  → MCPTools (UNCONNECTED)
        └── McpMultiToolConfig    → loader.load_mcp_multi(cfg) → MultiMCPTools (UNCONNECTED)
        │
        ▼
list[Any]  (mixed: Toolkit | Function | MCPTools | MultiMCPTools)
        │
        ▼
Agent(tools=mixed_list or None)
        │
        ▼  (at run() time, NOT construction)
Agent.aget_tools()  → auto-connects MCPTools/MultiMCPTools via await tool.connect()
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/tools/tool_factory.py` | Create | `ToolFactory(resolver).build(entries)` orchestrator + `_wrap_tool(raw, config)`. Dispatches by `kind`, validates raw dicts via `TypeAdapter(ToolEntry)`, collects mixed list. |
| `src/yaml_agno/tools/schema.py` | Modify | Widen `CustomToolConfig` with `@tool` flags + `model_validator` HITL mutual-exclusivity. `path` kept; `tool_hooks` OMITTED (DEFER). |
| `src/yaml_agno/factories/agent_factory.py` | Modify | `build(cfg, resolver=None)`: when `resolver` provided + `cfg.tools` non-empty, build `ToolFactory(resolver)`, forward resolved list to `Agent(tools=...)`. Default `None` preserves current behavior. |
| `src/yaml_agno/tools/__init__.py` | Modify | Re-export `ToolFactory`. |

## Interfaces / Contracts

### NEW `src/yaml_agno/tools/tool_factory.py`

```python
"""ToolFactory — orchestrates ``ToolEntry`` dispatch to Agno objects (SPEC_11 C).

The factory is the SINGLE wiring point between the validated ``ToolEntry``
union (slices A+B) and ``agno.Agent(tools=...)``. It accepts either raw dicts
(opaque ``AgentConfig.tools`` per Option B) or pre-parsed ``ToolEntry``
instances, validates raw dicts via ``TypeAdapter(ToolEntry)``, dispatches each
entry by ``kind`` to the correct resolver (BUILTIN_REGISTRY /
CustomToolLoader / MCPResolver), applies ``@tool(**flags)`` for ``function``
entries, and returns the mixed list ``agno.Agent`` accepts.

Synchronous by design: ``MCPResolver`` returns UNCONNECTED ``MCPTools`` /
``MultiMCPTools`` instances, and ``agno.Agent`` auto-connects them during
``aget_tools`` (verified obs-2018). No ``await`` is needed on the construction
path.

@ai-directive: SSOT is specs/SPEC_11_TOOLS_AND_MCP.md §3 (custom @tool),
§9.5 (CustomToolLoader raw return contract). Slice D adds hooks, cross-run
caching, concurrency, and tool_call_limit forwarding — do NOT add them here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agno.tools.decorator import tool as agno_tool
from pydantic import TypeAdapter

from yaml_agno.tools.custom_loader import CustomToolLoader
from yaml_agno.tools.registry import BUILTIN_REGISTRY, UnknownBuiltinError
from yaml_agno.tools.schema import (
    BuiltinToolConfig,
    CustomToolConfig,
    CustomToolkitConfig,
    McpMultiToolConfig,
    StdioMcpConfig,
    HttpMcpConfig,
    ToolEntry,
)

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver

__all__ = ["ToolFactory"]


# Reusable validator: raw dict -> ToolEntry instance. Built ONCE at import
# (TypeAdapter is the documented Pydantic V2 pattern for validating unions
# outside a model field). Option B: validation boundary lives here, NOT in
# AgentConfig.
_ENTRY_ADAPTER: TypeAdapter[ToolEntry] = TypeAdapter(ToolEntry)


class ToolFactory:
    """Orchestrate ``ToolEntry`` dispatch into the mixed list Agent accepts.

    Construction is cheap (one ``CustomToolLoader``); ``resolver`` is the
    shared dependency. The factory holds no tool-level state — each
    ``build()`` call is independent (caching is slice D).

    Slice C scope: dispatch + ``@tool`` wrapping. Hooks (``tool_hooks``,
    ``pre_hook`` / ``post_hook``), cross-run caching (``cache_callables``),
    concurrency (``asyncio.TaskGroup``), and ``tool_call_limit`` forwarding
    are DEFER to slice D.

    Attributes:
        _loader: The ``CustomToolLoader`` for ``function`` / ``toolkit_class``
            / ``mcp`` / ``mcp_multi`` resolution. Wraps the injected resolver.
    """

    def __init__(self, resolver: AgnoResolver) -> None:
        """Initialize the factory with the shared resolver.

        Args:
            resolver: The ``AgnoResolver`` whose ``resolve_class`` performs
                allowlisted importlib resolution for custom tools, toolkit
                classes, and MCP ``header_provider`` dotted-paths.
        """
        self._loader = CustomToolLoader(resolver)

    def build(self, tool_entries: list[dict[str, Any] | ToolEntry]) -> list[Any]:
        """Dispatch each tool entry to its resolver, collect into Agent's mixed list.

        Accepts EITHER raw dicts (opaque ``AgentConfig.tools``, Option B) or
        pre-parsed ``ToolEntry`` instances. Raw dicts are validated against
        the ``ToolEntry`` union via ``TypeAdapter`` (the validation boundary
        moves from config-parse to factory-build; it does NOT disappear).

        Args:
            tool_entries: The raw ``AgentConfig.tools`` list (dicts) or a list
                of already-parsed ``ToolEntry`` instances. Empty list is safe
                and returns ``[]``.

        Returns:
            The mixed list ``agno.Agent(tools=...)`` accepts. Item types by
            ``kind``:

            - ``builtin``       -> Toolkit instance (e.g. ``CalculatorTools``)
            - ``function``      -> ``agno.tools.function.Function`` (wrapped)
            - ``toolkit_class`` -> Toolkit instance (custom subclass)
            - ``mcp``           -> UNCONNECTED ``MCPTools``
            - ``mcp_multi``     -> UNCONNECTED ``MultiMCPTools``

        Raises:
            UnknownBuiltinError: If a ``builtin`` entry's ``name`` is not in
                ``BUILTIN_REGISTRY``.
            SecurityError: If a custom tool / ``header_provider`` dotted-path
                references a non-allowlisted module.
            ValidationError: If a raw dict does not match any ``ToolEntry``
                branch (re-raised from ``TypeAdapter.validate_python``).
        """
        result: list[Any] = []
        for raw in tool_entries:
            entry = _ENTRY_ADAPTER.validate_python(raw) if isinstance(raw, dict) else raw
            if isinstance(entry, BuiltinToolConfig):
                # BUILTIN_REGISTRY[name] raises UnknownBuiltinError if absent.
                adapter = BUILTIN_REGISTRY[entry.name]
                result.append(adapter.build(self._loader._resolver, entry.init_args))
            elif isinstance(entry, CustomToolConfig):
                raw_callable = self._loader.load_callable(entry)
                result.append(self._wrap_tool(raw_callable, entry))
            elif isinstance(entry, CustomToolkitConfig):
                cls = self._loader.load_toolkit_class(entry)
                # CustomToolkitConfig already carries init_args; the registry's
                # signature-filtering lives on ToolkitAdapter (builtins). Custom
                # toolkit classes are user-owned; init_args are forwarded as-is.
                result.append(cls(**entry.init_args))
            elif isinstance(entry, (StdioMcpConfig, HttpMcpConfig)):
                # UNCONNECTED — Agent auto-connects during aget_tools (A2).
                result.append(self._loader.load_mcp(entry))
            elif isinstance(entry, McpMultiToolConfig):
                # UNCONNECTED — emits DeprecationWarning (RISK004, slice B).
                result.append(self._loader.load_mcp_multi(entry))
            else:  # pragma: no cover - exhaustive union, unreachable
                raise TypeError(f"Unsupported ToolEntry kind: {type(entry).__name__}")
        return result

    def _wrap_tool(self, raw_callable: Any, config: CustomToolConfig) -> Any:
        """Apply ``@tool(**flags)`` from ``CustomToolConfig`` to a raw callable.

        The ``CustomToolLoader`` returns the RAW callable by design (A4,
        SPEC_11 §9.5); this method is the single place where the ``@tool``
        decorator is applied. Flags set to ``None`` are DROPPED so Agno uses
        its own defaults (matches SPEC_11 §3.1: ``show_result`` default
        ``None``, ``name``/``description`` default to function name/docstring).

        Args:
            raw_callable: The bare callable resolved by
                ``CustomToolLoader.load_callable``.
            config: The validated ``CustomToolConfig`` carrying the ``@tool``
                flags. The HITL mutual-exclusivity was already enforced at
                schema-validation time (``model_validator``), so no runtime
                re-check is needed here.

        Returns:
            An ``agno.tools.function.Function`` object (the type
            ``@tool`` returns per TECH011).
        """
        flags = {
            "name": config.name,
            "description": config.description,
            "requires_confirmation": config.requires_confirmation,
            "requires_user_input": config.requires_user_input,
            "user_input_fields": config.user_input_fields or None,
            "external_execution": config.external_execution,
            "external_execution_silent": config.external_execution_silent,
            "show_result": config.show_result,
            "stop_after_tool_call": config.stop_after_tool_call,
            "cache_results": config.cache_results,
            "cache_dir": config.cache_dir,
            "cache_ttl": config.cache_ttl,
        }
        # Drop None-valued flags so Agno applies its own defaults. Boolean
        # False is KEPT (it is a meaningful explicit value, not "unset").
        flags = {k: v for k, v in flags.items() if v is not None}
        return agno_tool(**flags)(raw_callable)
```

### MODIFY `src/yaml_agno/tools/schema.py` — `CustomToolConfig` widened

Replace the shipped minimal `CustomToolConfig` (lines 50-62) with the widened
version below. `path` is KEPT (shipped convention); `tool_hooks` / `pre_hook`
/ `post_hook` are OMITTED (`extra="forbid"` rejects them until slice D).

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
        ..., min_length=1, max_length=400,
        description="Dotted-path callable (e.g. 'my_pkg.tools.fetch').",
    )

    # --- @tool identity overrides (SPEC_11 §3.1) ---
    name: str | None = Field(
        default=None, max_length=200,
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
    external_execution_silent: bool = Field(
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
        default=None, ge=1,
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
```

### MODIFY `src/yaml_agno/factories/agent_factory.py`

```python
"""AgentFactory — builds a native ``agno.Agent`` from an ``AgentConfig``.

Slice #1 (SPEC_01) mapped the 4 identity fields. Slice C (SPEC_11) adds
optional tools wiring: when ``resolver`` is provided and ``cfg.tools`` is
non-empty, ``ToolFactory(resolver).build(cfg.tools)`` resolves the opaque
dicts into the mixed list ``agno.Agent(tools=...)`` accepts (Option B —
AgentConfig.tools stays opaque; validation happens inside the factory).

Contract:
    - Construction stays pure assignment + factory dispatch. No network, no
      LLM instantiation, no provider resolution. ``MCPResolver`` returns
      UNCONNECTED instances; ``agno.Agent`` auto-connects at run time.
    - When ``resolver is None`` (the default), behavior is UNCHANGED from
      slice #1: ``tools=[]`` is forwarded and existing callers/tests are
      untouched (zero breaking tests).

@ai-directive: SSOT is specs/SPEC_01_AGENT_FACTORY.md (identity) +
specs/SPEC_11_TOOLS_AND_MCP.md (tools wiring). Discrepancies resolve in their
favor. This module consumes SPEC_02 (AgentConfig) read-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agno.agent import Agent

from yaml_agno.models.config.agent_config import AgentConfig
from yaml_agno.tools.tool_factory import ToolFactory

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver

__all__ = ["AgentFactory"]


class AgentFactory:
    """Builds ``agno.Agent`` instances from validated ``AgentConfig`` objects.

    Scope (identity + model + optional tools):

        +--------------------------+--------------------------+-----------+
        | AgentConfig field        | agno.Agent kwarg         | Mapping   |
        +--------------------------+--------------------------+-----------+
        | name: str                | name                     | direct    |
        | instructions: str | None | instructions             | direct    |
        | description: str | None  | description              | direct    |
        | model: str               | model                    | passthru  |
        | tools: list[dict]        | tools                    | factory*  |
        +--------------------------+--------------------------+-----------+
        | knowledge, memory, ...   | (not forwarded)          | deferred  |
        | tags, metadata           | (not forwarded)          | deferred  |
        +--------------------------+--------------------------+-----------+

        * tools is resolved ONLY when ``resolver`` is passed to ``build()``.
          Otherwise tools stays ``[]`` (slice #1 behavior, zero broken tests).

    Deferred slots are accepted silently and resolved by their owner SPECs +
    the DependencyManager. This class exposes a static ``build()`` method; it
    holds no state and is not instantiated.
    """

    @staticmethod
    def build(
        cfg: AgentConfig,
        resolver: AgnoResolver | None = None,
    ) -> Agent:
        """Build a native ``agno.Agent`` from an ``AgentConfig``.

        Maps the 4 identity/behavior fields directly. When ``resolver`` is
        provided AND ``cfg.tools`` is non-empty, resolves the opaque tools
        dicts into the mixed list ``agno.Agent(tools=...)`` accepts via
        ``ToolFactory`` (Option B). When ``resolver is None``, tools stays
        empty — preserving slice #1 behavior and all existing tests.

        Args:
            cfg: A validated ``AgentConfig`` (SPEC_02). Its ``model`` field is
                a ``provider:id`` string forwarded verbatim to Agno. Its
                ``tools`` field is an opaque ``list[dict]`` resolved here when
                a resolver is supplied.
            resolver: Optional ``AgnoResolver`` for allowlisted dotted-path
                resolution of custom tools / toolkit classes / MCP
                ``header_provider``. When ``None`` (default), tools are
                skipped — callers that do not need tools pass nothing.

        Returns:
            A constructed ``agno.Agent``. Per ``agno/agent/agent.py:504``,
            construction is pure assignment — no network call, no LLM
            instantiation, no provider resolution occurs until ``run()`` or
            ``arun()`` is invoked. MCP tools are UNCONNECTED at this point;
            Agent auto-connects them during ``aget_tools`` (A2).

        Raises:
            (none directly) Any exception raised by ``agno.Agent.__init__`` or
                ``ToolFactory.build()`` (``UnknownBuiltinError``,
                ``SecurityError``, ``ValidationError``) propagates unchanged.
        """
        tools: list[Any] = []
        if cfg.tools and resolver is not None:
            factory = ToolFactory(resolver)
            tools = factory.build(cfg.tools)
        return Agent(
            name=cfg.name,
            instructions=cfg.instructions,
            description=cfg.description,
            model=cfg.model,
            tools=tools or None,
            # tool_call_limit is DEFER to slice D (TASK_011): AgentConfig has
            # no tool_call_limit field today; requires SPEC_02 evolution.
        )
```

### MODIFY `src/yaml_agno/tools/__init__.py`

Add `ToolFactory` to the imports and `__all__`:

```python
from yaml_agno.tools.tool_factory import ToolFactory
```

Add `"ToolFactory"` to the `__all__` list (alphabetical position, after
`"ToolEntry"`).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (schema) | `CustomToolConfig` accepts all `@tool` flags; `extra="forbid"` rejects `tool_hooks`; HITL validator raises on 2+ True | `tests/unit/tools/test_schema.py` — assert valid configs parse, invalid HITL combos raise `ValidationError`, unknown fields rejected. STRICT TDD: write failing test first. |
| Unit (factory) | `build([])` → `[]`; each `kind` dispatches to correct resolver; raw dict + pre-parsed `ToolEntry` both accepted; mixed list order preserved | `tests/unit/tools/test_tool_factory.py` — mock `CustomToolLoader` / `BUILTIN_REGISTRY` / `MCPResolver`, assert dispatch + return types. STRICT TDD. |
| Unit (factory wrap) | `_wrap_tool` applies `requires_confirmation`; drops `None` flags; returns `Function` (not callable) | `tests/unit/tools/test_tool_factory.py` — real `@tool` on a stub callable, assert `Function` attributes + that `None` flags do not reach `agno_tool`. |
| Unit (integration) | `AgentFactory.build(cfg_with_tools, resolver)` → `Agent.tools` non-empty; `build(cfg)` without resolver → `tools=[]` (existing tests unchanged) | `tests/unit/factories/test_agent_factory.py` — ADD tools-forwarding scenario; existing scenarios run unmodified (resolver defaults None). |

## TDD (Strict TDD Mode active)

1. **RED**: write `test_custom_tool_config_hitl_validator_rejects_two_flags`
   in `test_schema.py` — expect `ValidationError`. Run → fails (shipped
   schema has no validator).
2. **GREEN**: add the `model_validator` to `CustomToolConfig`. Run → passes.
3. **RED**: write `test_tool_factory_dispatches_builtin` /
   `test_tool_factory_wraps_function` / `test_tool_factory_empty_list` in
   `test_tool_factory.py`. Run → fails (`ToolFactory` does not exist).
4. **GREEN**: create `tool_factory.py` with `build` + `_wrap_tool`. Run → passes.
5. **RED**: write `test_agent_factory_forwards_tools_when_resolver` in
   `test_agent_factory.py`. Run → fails (shipped build ignores tools).
6. **GREEN**: modify `agent_factory.py` (`resolver` param + `ToolFactory`
   call). Run → passes. Re-run the FULL existing `test_agent_factory.py` →
   all green (resolver defaults None).
7. Run full suite → all green.

## Verification

- `AgentFactory.build(cfg_with_tools, resolver)` produces an `Agent` whose
  `.tools` contains resolved Agno objects (not `[]`).
- `kind: function` + `requires_confirmation: true` produces a `Function`
  with the flag applied.
- `CustomToolConfig` with 2+ HITL flags `True` raises `ValidationError` at
  schema time (before wrap).
- `AgentFactory.build(cfg)` without `resolver` returns `Agent` with `tools=[]`
  (zero existing tests broken).
- `ToolFactory.build([])` returns `[]` (empty-state safe).
- Mixed list (builtin + function + mcp) builds with no `await` (sync path).

## Rollback

1. Revert `agent_factory.py` to `build(cfg)` without `resolver` (1 file, no
   dependents — `team_factory` / `workflow_factory` are not yet shipped).
2. Delete `tool_factory.py` (new file, no dependents).
3. Revert `CustomToolConfig` to `{kind, path}` in `schema.py`.
4. Revert `__init__.py` re-export.
5. Slice A+B tests do not depend on slice C — rollback does not break them.
6. `openspec/specs/` is not modified in slice C (only delta specs in the
   change folder) — file rollback does not touch published specs.

## Open Questions

- [ ] `tool_call_limit` ownership: defer to slice D (default) vs add to
      `AgentConfig` now. **Assumption for slice C: DEFER.**
- [ ] None blocking. All other decisions are baked in (A1-A5).
