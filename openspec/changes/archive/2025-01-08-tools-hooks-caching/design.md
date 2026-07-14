---
change: tools-hooks-caching
spec: SPEC_11
status: designed
artifact_store: hybrid
slice: D (final)
depends_on:
  - openspec/specs/tool-factory-wiring
  - openspec/specs/tools-slice-a-schema-resolver
  - openspec/specs/agent-config-schema
ai-directive: SSOT for HOW (literal code). specs/SPEC_11_TOOLS_AND_MCP.md §3.1
  (hook flags), §5.4 (tool_call_limit), §8.1 (hooks), §10.3 (allowlist). Shipped
  slice-C code resolves naming/disposition: CustomToolConfig.path (NOT module),
  CustomToolLoader._resolve_dotted (reuse, NOT a new hooks.py), _wrap_tool flags
  dict + None-drop (extend, do NOT rewrite).
---

# Design: Tools Hooks + Caching + tool_call_limit (SPEC_11 Slice D — final)

## Technical Approach

Slice D closes SPEC_11 with **four small, mostly-orthogonal changes** that
share one property: they are all **thin forwarding / data extension**, never
new execution logic. The anti-Frankenstein principle from the exploration
(obs-2095) governs every decision: Agno already owns hooks, per-call caching,
and tool execution; yaml-agno only **declares** them in YAML and **forwards**
them at construction time.

The four changes:

1. **Hooks NOW** (A1 + A2): widen `CustomToolConfig` with three dotted-path
   string fields (`pre_hook`, `post_hook`, `tool_hooks`) and resolve them in
   `_wrap_tool` by reusing the EXISTING `CustomToolLoader._resolve_dotted`
   (the same path used for `path` itself and MCP `header_provider`). The
   resolved callables are forwarded to `@tool(pre_hook=..., post_hook=...,
   tool_hooks=[...])`, which sets them on the returned `Function`. No new
   module, no new resolver class, no `hooks.py` frankenstein.

2. **Caching DONE** (A3): per-call caching (`cache_results` / `cache_dir` /
   `cache_ttl`) already shipped in slice C (schema.py:124-137 + tool_factory
   flags dict). This design asserts that invariant and adds **zero new code**
   for it. Cross-run callable caching (`cache_callables` /
   `callable_tools_cache_key`, SPEC_11 §8.3 / §10.4) is explicitly DEFERRED
   (post-MVP) — tools are cheap to build except MCP, which auto-connects at
   run time anyway.

3. **Concurrency NEVER** (A4): yaml-agno only **builds** tool objects; it does
   not **execute** them. Agno's `Agent.run()` / `arun()` owns tool execution,
   sync/async dispatch, and `asyncio.TaskGroup` parallelism (STRAT003 applies
   to **bootstrap** pre-resolution, not tool execution). Slice D adds NO
   executor, NO `run_tools_concurrently`, NO new module. This is a permanent
   NEVER, not a defer.

4. **Registry SEPARATED** (A5): expanding `BUILTIN_REGISTRY` from 5 to 120+
   adapters is pure DATA (each entry is a `ToolkitAdapter` dataclass; the
   `build()` / `_filter_kwargs()` logic is generic). It is a separate change
   with its own PR boundary because the diff size exceeds the 400-line budget.
   Slice D touches zero registry lines.

5. **`tool_call_limit` NOW** (A6): one field on `AgentConfig`
   (`tool_call_limit: int | None = Field(default=None, ge=1)`) + one line in
   `AgentFactory.build()` to forward it to `Agent(tool_call_limit=...)`. This
   unblocks SPEC_01's agent-level tool-call budget without touching the tools
   layer at all.

Net surface: **3 files modified, 0 files created**. The change is small,
additive, and each modification is independent (the four concerns touch
disjoint code regions), so any subset can be reviewed in isolation.

## Architecture Decisions

### A1: Hooks via dotted-path strings + `_resolve_dotted` reuse (NO `hooks.py`)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| New `src/yaml_agno/tools/hooks.py` with `HookResolver` (SPEC_11 TASK_005 as written) | Duplicates the `is_module_allowed` + `AgnoResolver.resolve_class` chain already in `CustomToolLoader._resolve_dotted`; new module, new class, new tests for identical behavior | Rejected — frankenstein |
| Resolve hooks inside `CustomToolLoader.load_callable` (eager, at import time) | Couples hook resolution to the raw-callable import; if a hook module is misconfigured, the whole tool fails before `@tool` is applied, obscuring the error site | Rejected |
| **Dotted-path strings on `CustomToolConfig` + resolve in `_wrap_tool` via `self._loader._resolve_dotted`** | Reuses the EXACT same allowlist + resolver path as `path` and `header_provider`; one resolution mechanism, one security boundary, one set of tests | **Chosen** |

**Rationale**: SPEC_11 §10.3 (line 854) is explicit — hooks use the SAME
import allowlist as custom tools and MCP `header_provider`. The shipped
`CustomToolLoader._resolve_dotted` (custom_loader.py:127-148) already
implements: (a) `"." in dotted_path` structural check, (b) `is_module_allowed`
allowlist guard with `SecurityError`, (c) `resolver.resolve_class(module,
name)`. Reusing it gives three properties for free: consistent error
messages, one security boundary to audit, and zero new code paths.

The hook fields are **plain `str`** (not a `ToolHookRef` pydantic model as
SPEC_11 §3.3 sketches). Reasons: (a) the shipped `path` field is `str`, (b)
the shipped `header_provider` field is `str`, (c) a single-field BaseModel
adds validation surface with no additional constraint, (d) `str` is what
`_resolve_dotted` consumes. Consistency with shipped convention wins over the
spec sketch; the spec resolves in favor of shipped code per the ai-directive.

**Rejected alternative — set hooks on `Function` post-decoration**: the
orchestrator has verified (Agno 2.6.22) that `@tool(pre_hook=callable)(func)`
sets `pre_hook` on the returned `Function`. Forwarding via the decorator is
cleaner than mutating the `Function` after construction and keeps a single
code path for all `@tool` flags.

### A2: Hooks forwarded in the `_wrap_tool` flags dict (extend, do NOT rewrite)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Build a separate `hooks` dict and pass it alongside `flags` | Bifurcates the flag-forwarding path; two places where `None`-dropping must happen | Rejected |
| **Resolve hooks then add `pre_hook` / `post_hook` / `tool_hooks` keys to the SAME `flags` dict, before the None-drop comprehension** | One flag-forwarding path; the existing `{k: v for k, v in flags.items() if v is not None}` already drops unset hooks; `tool_hooks=[]` is dropped (falsy after `or None` normalization), `tool_hooks=[callable]` is kept | **Chosen** |

**Rationale**: slice C's `_wrap_tool` (tool_factory.py:159-177) already
centralizes all `@tool` flag forwarding through one `flags` dict + one
None-drop comprehension. Hooks are just three more keys in that same dict.
The only new logic is **resolution**: each hook string must be resolved to a
callable BEFORE insertion, because `@tool` expects a `Callable`, not a string.
That resolution is a 3-line loop over `self._loader._resolve_dotted`.

The `tool_hooks` list needs special handling: an empty list must be normalized
to `None` so the None-drop removes it (Agno's default is `[]`, but forwarding
`[]` explicitly is harmless; we normalize to `None` for consistency with the
other list field `user_input_fields`, which already does `or None` at
tool_factory.py:164).

### A3: Caching is DONE — invariant assertion, zero new code

| Concern | Status in slice D | Action |
|---------|-------------------|--------|
| Per-call `cache_results` / `cache_dir` / `cache_ttl` | **SHIPPED** (slice C: schema.py:124-137, tool_factory.py:170-172) | None — invariant |
| Cross-run `cache_callables` / `callable_tools_cache_key` (SPEC_11 §8.3, §10.4) | DEFERRED (post-MVP) | None — documented as deferred |
| `BuiltinToolConfig` caching | **WORKS** via `extra="allow"` → `init_args` → toolkit constructor | None — invariant |

**Rationale**: the exploration (obs-2095 §b) confirms per-call caching is
fully shipped and exercised. Cross-run callable caching caches the BUILT tool
object across runs; it is low-value for MVP because tool construction is cheap
(except MCP, which auto-connects at run time regardless). DEFER is the right
call: it avoids a yaml-agno-side LRU cache that would duplicate Agno's own
caching layer.

### A4: Concurrency is NEVER — Agno owns tool execution

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `src/yaml_agno/tools/executor.py` with `run_tools_concurrently` (SPEC_11 TASK_012 as written) | Reimplements Agno's internal `Agent.run()` execution loop; duplicates sync/async dispatch, retry, and `TaskGroup` semantics; breaks when Agno changes its run loop | Rejected — frankenstein, NEVER |
| **No executor. `ToolFactory.build()` stays synchronous; returns a mixed list; Agent executes.** | Correct layering: yaml-agno DECLARES + BUILDS, Agno EXECUTES. STRAT003 (`asyncio.TaskGroup`) applies to **bootstrap** pre-resolution (TECH004, TECH010), not tool execution. | **Chosen (permanent)** |

**Rationale**: verified (obs-2018, obs-2095 §c): `ToolFactory.build()` is
synchronous and returns UNCONNECTED / UNDECORATED-FOR-EXECUTION objects.
`agno.Agent` owns the entire execution path: `aget_tools()` auto-connects
`MCPTools`, the run loop decides sync/async, and parallel tool calls use
Agno's internal `TaskGroup`. A yaml-agno executor would be a transparent
wrapper around `Agent.run()` adding zero value and coupling yaml-agno to
Agno's internal execution API (which is not a stable public surface).

### A5: Registry expansion (120+) is a SEPARATE change

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Fold the 120+ adapter expansion into slice D | Diff exceeds 400-line budget (each adapter is ~5-10 lines + alias_map); couples unrelated DATA expansion with hook/caching logic; unreviewable | Rejected |
| **Separate change (`tools-registry-expansion`), batched PRs by category** | Each category (database, search, web-scrape, etc.) is an independent PR; slice D stays small and reviewable; registry logic is GENERIC (inspect.signature) so no new logic — only DATA | **Chosen** |

**Rationale**: the 5 shipped adapters (registry.py) prove the pattern works.
Expanding to 120+ is mechanical (each entry is a `ToolkitAdapter` dataclass)
but voluminous. Mixing it into slice D would make the change unreviewable and
trigger the 400-line budget guard. Slice D touches zero registry lines; the
expansion gets its own change with its own proposal + tasks.

### A6: `tool_call_limit` NOW — 1 field + 1 forwarding line

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Defer to a future SPEC_02 evolution (as slice-C design A5 suggested) | Leaves SPEC_11 §5.4 unimplemented; blocks agents that need a tool-call budget | Rejected |
| Put `tool_call_limit` on a `ToolSetConfig` (SPEC_11 §1 sketch, line 61) | Requires introducing `ToolSetConfig` (does not exist in shipped code); couples a per-run agent property to the tools layer | Rejected |
| **Add `tool_call_limit: int \| None = Field(default=None, ge=1)` to `AgentConfig` + forward in `AgentFactory.build()`** | Matches shipped reality (AgentConfig is the aggregate; no `ToolSetConfig` exists); SPEC_02 owner is AgentConfig; 1 field + 1 kwarg; Agno's `Agent(tool_call_limit=N)` accepts it directly | **Chosen** |

**Rationale**: SPEC_11 §5.4 (line 339-349) defines the semantics — a per-run
cap on total tool calls, applied across the whole run. The shipped
`AgentConfig` (agent_config.py) is the YAML aggregate that names agent-level
slots; `tool_call_limit` is agent-level (not per-tool), so it belongs there.
The field uses `ge=1` (matches the task contract); NO `le=100` upper bound
despite SPEC_11 §1 line 61 sketching one — Agno itself imposes no upper bound,
and an artificial cap would reject valid long-running agent configs. The
disposition comment in agent_factory.py:108-109 is resolved by this ADR.

## Data Flow

```
YAML agent.tools[i] (dict, kind: function)     YAML agent.tool_call_limit (int|None)
        │                                                     │
        ▼                                                     ▼
CustomToolConfig (widened: +pre_hook +post_hook +tool_hooks)  AgentConfig.tool_call_limit (NEW field)
        │                                                     │
        │  _ENTRY_ADAPTER.validate_python                     │
        ▼                                                     │
ToolFactory.build()                                           │
        │                                                     │
        │  isinstance(entry, CustomToolConfig)                │
        ▼                                                     │
loader.load_callable(entry)  → raw_callable                   │
        │                                                     │
        ▼                                                     │
_wrap_tool(raw_callable, entry)                               │
        │                                                     │
        │  NEW: resolve hooks via self._loader._resolve_dotted│
        │    pre_hook_str  → pre_hook_callable  (or None)     │
        │    post_hook_str → post_hook_callable (or None)     │
        │    tool_hooks_strs → [callables...]   (or [])       │
        │                                                     │
        │  flags = { ...existing...,                          │
        │           "pre_hook": pre_hook_callable,            │
        │           "post_hook": post_hook_callable,          │
        │           "tool_hooks": tool_hooks_list or None }   │
        │  flags = {k:v for k,v in flags.items() if v is None}│
        ▼                                                     │
agno_tool(**flags)(raw_callable)  →  Function                 │
        │  (pre_hook/post_hook/tool_hooks set on Function)    │
        │                                                     │
        ▼                                                     │
list[Any] (mixed)                                             │
        │                                                     │
        ▼                                                     ▼
AgentFactory.build(cfg, resolver)
        │
        ▼
Agent(tools=mixed_list or None, tool_call_limit=cfg.tool_call_limit)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/tools/schema.py` | Modify | Add `pre_hook`, `post_hook`, `tool_hooks` fields to `CustomToolConfig`. Update the class docstring NOTE (remove the "intentionally absent" sentence — hooks now exist). `extra="forbid"` STAYS. |
| `src/yaml_agno/tools/tool_factory.py` | Modify | In `_wrap_tool`: resolve hook refs via `self._loader._resolve_dotted`, add `pre_hook` / `post_hook` / `tool_hooks` to the `flags` dict before the None-drop. Update module + class docstrings (remove "Slice D adds hooks" sentence). |
| `src/yaml_agno/models/config/agent_config.py` | Modify | Add `tool_call_limit: int \| None = Field(default=None, ge=1)` to `AgentConfig`. Update the field-count comment. |
| `src/yaml_agno/factories/agent_factory.py` | Modify | Forward `cfg.tool_call_limit` to `Agent(tool_call_limit=...)`. Remove the "DEFER to slice D" comment. Update the scope table. |

**Net: 4 files modified, 0 files created.** No new modules, no new tests
files (extend the existing `test_schema.py`, `test_tool_factory.py`,
`test_agent_factory.py`).

## Interfaces / Contracts

### MODIFY `src/yaml_agno/tools/schema.py` — `CustomToolConfig` hook fields

Add three fields to the shipped `CustomToolConfig` (insert after the caching
block at schema.py:137, before the `@model_validator`). Also update the class
docstring: the NOTE that says hooks are "INTENTIONALLY ABSENT (DEFER to slice
D, TASK_005)" is REMOVED — hooks now exist.

```python
class CustomToolConfig(BaseModel):
    """A custom ``@tool`` function declared as a dotted-path callable reference.

    ``path`` is resolved via ``CustomToolLoader.load_callable`` (allowlisted
    importlib, slice A) and returned RAW. ``ToolFactory._wrap_tool`` applies
    ``@tool(**flags)`` from the remaining fields (SPEC_11 §3.1, slice C),
    including hook resolution (slice D).

    The HITL mutual-exclusivity constraint (SPEC_11 §3.1: at most one of
    ``requires_confirmation`` / ``requires_user_input`` /
    ``external_execution`` may be ``True``) is enforced at the schema
    boundary via a ``model_validator(mode="after")`` — fail-early, fail-loud,
    before ``@tool`` is applied.

    Hook fields (``pre_hook`` / ``post_hook`` / ``tool_hooks``, slice D) are
    dotted-path strings resolved through the SAME allowlist + resolver as
    ``path`` (SPEC_11 §10.3). Resolution happens in ``_wrap_tool``, NOT at
    schema time, so a misconfigured hook module fails with a clear
    ``SecurityError`` at the wrap site.
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
    strict: bool | None = Field(
        default=None,
        description="Enable strict parameter checking (Agno @tool strict flag).",
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

    # --- @tool caching flags (per-call; cross-run LRU is DEFERRED post-MVP) ---
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

    # --- @tool hooks (SPEC_11 §3.1, §8.1, §10.3 — slice D) ---
    # Dotted-path strings resolved via CustomToolLoader._resolve_dotted (the
    # SAME allowlisted path used for `path` and MCP `header_provider`). Agno's
    # `@tool` accepts the resolved Callables and sets them on the Function.
    pre_hook: str | None = Field(
        default=None,
        min_length=1,
        max_length=400,
        description="Dotted-path to a Callable invoked before tool execution "
        "(e.g. 'myapp.hooks.audit_pre'). Resolved in _wrap_tool.",
    )
    post_hook: str | None = Field(
        default=None,
        min_length=1,
        max_length=400,
        description="Dotted-path to a Callable invoked after tool execution "
        "(e.g. 'myapp.hooks.audit_post'). Resolved in _wrap_tool.",
    )
    tool_hooks: list[str] = Field(
        default_factory=list,
        description="Dotted-path Callables chained around tool execution "
        "(e.g. ['myapp.hooks.audit_log', 'myapp.hooks.rate_limit']). Each "
        "entry is resolved via _resolve_dotted in _wrap_tool.",
    )

    @model_validator(mode="after")
    def _validate_hitl_mutual_exclusivity(self) -> CustomToolConfig:
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

### MODIFY `src/yaml_agno/tools/tool_factory.py` — `_wrap_tool` hook resolution

Update the module docstring (remove the "Slice D adds hooks, cross-run
caching, concurrency, and tool_call_limit forwarding — do NOT add them here"
sentence at tool_factory.py:18 — slice D IS this change) and the `ToolFactory`
class docstring (remove the "Slice C scope" paragraph at tool_factory.py:62-65).
Then extend `_wrap_tool` with hook resolution.

The literal `_wrap_tool` after slice D:

```python
    def _wrap_tool(self, raw_callable: Any, config: CustomToolConfig) -> Any:
        """Apply ``@tool(**flags)`` from ``CustomToolConfig`` to a raw callable.

        The ``CustomToolLoader`` returns the RAW callable by design (A4,
        SPEC_11 §9.5); this method is the single place where the ``@tool``
        decorator is applied. Flags set to ``None`` are DROPPED so Agno uses
        its own defaults (matches SPEC_11 §3.1: ``show_result`` default
        ``None``, ``name``/``description`` default to function name/docstring).

        Hook fields (``pre_hook`` / ``post_hook`` / ``tool_hooks``, slice D)
        are dotted-path strings RESOLVED HERE via
        ``self._loader._resolve_dotted`` — the same allowlisted path used for
        ``config.path`` itself and MCP ``header_provider`` (SPEC_11 §10.3).
        The resolved ``Callable`` objects are forwarded to ``@tool``, which
        sets them on the returned ``Function`` (verified Agno 2.6.22).

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

        Raises:
            SecurityError: If a hook dotted-path references a non-allowlisted
                module (propagated from ``_resolve_dotted``).
            ValueError: If a hook dotted-path has no ``module.name`` structure
                (propagated from ``_resolve_dotted``).
        """
        # --- Slice D: resolve hook dotted-paths to Callables (A1, A2) ---
        # Reuses CustomToolLoader._resolve_dotted (the SAME allowlisted path
        # as `config.path` and MCP `header_provider`). No separate hooks.py.
        pre_hook_callable = (
            self._loader._resolve_dotted(config.pre_hook)
            if config.pre_hook is not None
            else None
        )
        post_hook_callable = (
            self._loader._resolve_dotted(config.post_hook)
            if config.post_hook is not None
            else None
        )
        tool_hooks_callables = [
            self._loader._resolve_dotted(hook_ref) for hook_ref in config.tool_hooks
        ]

        flags = {
            "name": config.name,
            "description": config.description,
            "requires_confirmation": config.requires_confirmation,
            "requires_user_input": config.requires_user_input,
            "user_input_fields": config.user_input_fields or None,
            "external_execution": config.external_execution,
            "external_execution_silent": config.external_execution_silent,
            "strict": config.strict,
            "show_result": config.show_result,
            "stop_after_tool_call": config.stop_after_tool_call,
            "cache_results": config.cache_results,
            "cache_dir": config.cache_dir,
            "cache_ttl": config.cache_ttl,
            "pre_hook": pre_hook_callable,
            "post_hook": post_hook_callable,
            "tool_hooks": tool_hooks_callables or None,
        }
        # Drop None-valued flags so Agno applies its own defaults. Boolean
        # False is KEPT (it is a meaningful explicit value, not "unset"). An
        # empty tool_hooks list is normalized to None above so it is dropped
        # here (Agno default is []).
        flags = {k: v for k, v in flags.items() if v is not None}
        return agno_tool(**flags)(raw_callable)
```

**Key load-bearing snippet** (the hook resolution block, lines that are
genuinely new in slice D):

```python
        pre_hook_callable = (
            self._loader._resolve_dotted(config.pre_hook)
            if config.pre_hook is not None
            else None
        )
        post_hook_callable = (
            self._loader._resolve_dotted(config.post_hook)
            if config.post_hook is not None
            else None
        )
        tool_hooks_callables = [
            self._loader._resolve_dotted(hook_ref) for hook_ref in config.tool_hooks
        ]
```

followed by the three new keys in the `flags` dict:

```python
            "pre_hook": pre_hook_callable,
            "post_hook": post_hook_callable,
            "tool_hooks": tool_hooks_callables or None,
```

The `strict` flag (already shipped in `_wrap_tool` at tool_factory.py:167 but
absent from the slice-C design's literal block) is preserved here — it is a
shipped-field invariant, not a slice-D addition.

### MODIFY `src/yaml_agno/models/config/agent_config.py` — `tool_call_limit` field

Add the field in the Behavior section (after `description`, before the
"Delegated sub-systems" block). Update the field-count comment at line 66-67.

```python
    # --- Behavior (2 fields) ---
    instructions: Instructions | None = Field(None, max_length=50000, description="System prompt.")
    description: str | None = Field(None, description="Human-readable description.")
    # tool_call_limit (slice D, SPEC_11 §5.4): per-run cap on total tool
    # calls across the whole run. Agent-level, NOT per-tool. ge=1 matches
    # Agno's own lower bound; NO upper bound (Agnone imposes none; an
    # artificial le=100 would reject valid long-running agent configs).
    tool_call_limit: int | None = Field(
        default=None,
        ge=1,
        description="Max tool calls per run (Agent-level). None = no limit. See SPEC_11 §5.4.",
    )
```

And update the trailing comment at agent_config.py:66-67:

```python
    # Total: 14 named fields (2 identity + 3 behavior + 9 opaque + 2 org) + model_config.
    # `user_id` is INTENTIONALLY ABSENT (composite, runtime-only, SPEC_04).
```

(The count goes from 13 to 14; behavior section goes from 2 to 3 fields.)

### MODIFY `src/yaml_agno/factories/agent_factory.py` — `tool_call_limit` forwarding

Update the scope table in the class docstring (add a `tool_call_limit` row)
and add the kwarg to the `Agent(...)` constructor call. Remove the
"tool_call_limit is DEFER to slice D" comment at agent_factory.py:108-109.

The literal `build()` return block after slice D:

```python
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
            tool_call_limit=cfg.tool_call_limit,
        )
```

Updated scope table (in the class docstring):

```
        +--------------------------+--------------------------+-----------+
        | AgentConfig field        | agno.Agent kwarg         | Mapping   |
        +--------------------------+--------------------------+-----------+
        | name: str                | name                     | direct    |
        | instructions: str | None | instructions             | direct    |
        | description: str | None  | description              | direct    |
        | model: str               | model                    | passthru  |
        | tools: list[dict]        | tools                    | factory*  |
        | tool_call_limit: int|None| tool_call_limit          | direct    |
        +--------------------------+--------------------------+-----------+
        | knowledge, memory, ...   | (not forwarded)          | deferred  |
        | tags, metadata           | (not forwarded)          | deferred  |
        +--------------------------+--------------------------+-----------+
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (schema) | `CustomToolConfig` accepts `pre_hook` / `post_hook` / `tool_hooks`; `extra="forbid"` still rejects unknown fields; existing HITL validator still fires | `tests/unit/tools/test_schema.py` — ADD a parse-success test for a config with all three hook fields; ADD a parse-success test for `tool_hooks` as a list of strings. STRICT TDD: write failing test first (shipped schema rejects the fields via `extra="forbid"`). |
| Unit (schema) | `tool_call_limit` accepts valid ints (`1`, `5`, `1000`); rejects `0`, `-1`, non-int | `tests/unit/models/test_agent_config.py` — ADD field-validation tests. `ge=1` boundary: `1` ok, `0` raises. |
| Unit (factory) | `_wrap_tool` resolves `pre_hook` dotted-path via `_resolve_dotted` and forwards to `@tool`; the returned `Function` has `pre_hook` set | `tests/unit/tools/test_tool_factory.py` — ADD a test using `_CallableResolver` (already in the file) that asserts `_resolve_dotted` is called AND the `Function.pre_hook` attribute matches the stub. |
| Unit (factory) | `_wrap_tool` resolves `tool_hooks` list; empty list → not forwarded (None-dropped); non-empty → forwarded as a list of Callables | `tests/unit/tools/test_tool_factory.py` — ADD a test with `tool_hooks=['agno.tools.stub.h1', 'agno.tools.stub.h2']`; assert `Function.tool_hooks` length. |
| Unit (factory) | `_wrap_tool` raises `SecurityError` when a hook dotted-path is not allowlisted | `tests/unit/tools/test_tool_factory.py` — ADD a test with `pre_hook='evil_pkg.hooks.spy'`; expect `SecurityError`. |
| Unit (agent_factory) | `AgentFactory.build(cfg_with_tool_call_limit)` → `Agent.tool_call_limit == N`; `build(cfg_without)` → `Agent.tool_call_limit is None` | `tests/unit/factories/test_agent_factory.py` — ADD two scenarios. Existing scenarios unchanged (`tool_call_limit` defaults to `None`). |

## TDD (Strict TDD Mode active)

1. **RED** (schema hooks): write
   `test_custom_tool_config_accepts_hook_fields` in `test_schema.py` —
   parse a config with `pre_hook`, `post_hook`, `tool_hooks`. Run → FAILS
   (shipped schema has `extra="forbid"`, rejects the fields).
2. **GREEN**: add the three fields to `CustomToolConfig`. Run → passes.
3. **RED** (factory hooks): write
   `test_wrap_tool_resolves_pre_hook` in `test_tool_factory.py` — assert
   `_resolve_dotted` is called and `Function.pre_hook` is the stub. Run →
   FAILS (shipped `_wrap_tool` does not resolve hooks).
4. **GREEN**: add the hook-resolution block to `_wrap_tool`. Run → passes.
5. **RED** (factory hooks security): write
   `test_wrap_tool_rejects_non_allowlisted_hook` — expect `SecurityError`.
   Run → passes immediately IF step 4 is correct (the security guard lives
   in `_resolve_dotted`, already tested). If it fails, the wiring is wrong.
6. **RED** (agent_config): write
   `test_agent_config_accepts_tool_call_limit` and
   `test_agent_config_rejects_zero_tool_call_limit`. Run → FAILS (shipped
   `AgentConfig` has `extra="forbid"`, rejects the field).
7. **GREEN**: add `tool_call_limit` to `AgentConfig`. Run → passes.
8. **RED** (agent_factory): write
   `test_agent_factory_forwards_tool_call_limit`. Run → FAILS (shipped
   `build()` does not forward `tool_call_limit`).
9. **GREEN**: add `tool_call_limit=cfg.tool_call_limit` to the `Agent(...)`
   call. Run → passes. Re-run the FULL existing `test_agent_factory.py` →
   all green (`tool_call_limit` defaults to `None`).
10. Run full suite → all green.

## Verification

- `CustomToolConfig(pre_hook="myapp.hooks.audit_pre", path="...",
  kind="function")` parses without error (schema accepts the field).
- `CustomToolConfig(pre_hook="x")` with an unknown extra field still raises
  `ValidationError` (`extra="forbid"` preserved).
- `ToolFactory._wrap_tool` with a `pre_hook` produces a `Function` whose
  `.pre_hook` attribute is the resolved callable (verified via attribute
  read on the returned object, not via `@tool` internals).
- `ToolFactory._wrap_tool` with `tool_hooks=[]` produces a `Function`
  unchanged from the no-hooks path (empty list is dropped, not forwarded).
- `ToolFactory._wrap_tool` with a non-allowlisted `pre_hook` raises
  `SecurityError` (reuses the existing guard).
- `AgentConfig(tool_call_limit=5, ...)` parses; `AgentConfig(tool_call_limit=0)`
  raises `ValidationError` (`ge=1`).
- `AgentFactory.build(cfg_with_tool_call_limit)` produces an `Agent` whose
  `.tool_call_limit == 5`.
- `AgentFactory.build(cfg_without_tool_call_limit)` produces an `Agent`
  whose `.tool_call_limit is None` (default preserved).
- Per-call caching (`cache_results` / `cache_dir` / `cache_ttl`) still
  forwards correctly (slice-C invariant — the flags dict still contains
  them after the slice-D edits).
- Full existing test suite passes with no modifications to existing tests
  (all new fields default to `None` / `[]` / `False`).

## Rollback

Slice D's four modifications are independent and can be rolled back in any
order. Full rollback:

1. **Revert `agent_factory.py`**: remove the `tool_call_limit=cfg.tool_call_limit`
   line from the `Agent(...)` call. Restore the "DEFER to slice D" comment.
   (1 line removed, 2 lines restored.)
2. **Revert `agent_config.py`**: remove the `tool_call_limit` field. Restore
   the field-count comment to "13 named fields (2 identity + 2 behavior + ...)".
3. **Revert `tool_factory.py` `_wrap_tool`**: remove the hook-resolution
   block (the three `pre_hook_callable` / `post_hook_callable` /
   `tool_hooks_callables` assignments) and the three keys from the `flags`
   dict. Restore the module + class docstrings to slice-C wording.
4. **Revert `schema.py` `CustomToolConfig`**: remove the `pre_hook` /
   `post_hook` / `tool_hooks` fields. Restore the class-docstring NOTE
   ("INTENTIONALLY ABSENT (DEFER to slice D, TASK_005)").
5. Each revert is independently safe — no cross-file runtime dependency
   exists between the four changes (hooks live in the tools layer;
   `tool_call_limit` lives in the agent layer; they share no code path).
6. Slice A/B/C tests do not depend on slice D — rollback does not break them.
7. `openspec/specs/` is not modified by slice D (only this delta design in
   the change folder) — spec rollback is a file deletion, not an edit.

## Open Questions

- [ ] None blocking. All five decisions (A1-A6) are baked in from the
      exploration (obs-2095) + the orchestrator's baked-in decisions.
- [ ] Allowlist extension: hook modules (e.g. `myapp.hooks.`) MUST be added
      to the bootstrap allowlist for users to declare their own hooks. This
      is a **bootstrap-config concern** (SPEC_11 §10.3), NOT a slice-D code
      change — the allowlist is populated at startup, not in schema/factory
      code. The `_resolve_dotted` security guard reads the allowlist as-is.
      Documented as a deployment step, not a code change.
- [ ] Cross-run callable caching (`cache_callables` /
      `callable_tools_cache_key`): DEFERRED post-MVP (A3). Revisit when
      profiling shows tool-construction cost matters.
