# Design: memory-identity-leaf

> Technical design for the **LEAF slice** of SPEC_04 (Memory Architecture):
> `resolve_user_id()` + `MemoryConfig` Pydantic V2 schema. This slice breaks
> the mutual SPEC_04 <-> SPEC_06 dependency cycle by shipping the resolver and
> the typed memory schema **with no callers wired yet**. SPEC_06
> (`TenantContextMiddleware`) is deferred.

## Technical Approach

Two additive, self-contained modules plus one re-export. Nothing imports them
yet (the `AgentConfig.memory` slot stays `dict[str, Any] | None` — Option B
opaque — until a later coordinated change):

1. `src/yaml_agno/memory/user_identity.py` — the **single** `user_id` resolver
   for all of yaml-agno (HTTP + non-HTTP). Returns the composite
   `"{tenant_id}:{principal_id}"`, never `None`, never a bare principal, never
   Agno's shared `"default"` bucket. Verified literal from SPEC_04 §1.4
   (lines 166-259).
2. `src/yaml_agno/models/config/memory_config.py` — a pure-Pydantic V2 typed
   replacement for the opaque `memory: dict[str, Any] | None` slot. NO Agno
   imports (memory is 100% Agno-native; we only configure Agno's constructor
   flags). Mirrors the standalone-schema precedent set by
   `src/yaml_agno/models/model_spec.py` (SPEC_14): `ConfigDict(extra="forbid")`,
   Google docstrings, `__all__`, separate file.
3. `src/yaml_agno/memory/__init__.py` — re-export `resolve_user_id` and
   `UserIdentityResolutionError` so callers `from yaml_agno.memory import
   resolve_user_id`.

The approach is deliberately the smallest slice that unblocks SPEC_03
(persistence), SPEC_06 (tenant middleware) and SPEC_15 (context compression):
the resolver and the schema are the contract those SPECs depend on, and they
carry no upstream coupling themselves.

## Architecture Decisions

### Decision: `resolve_user_id()` is self-contained (no Agno import)

- **Choice**: `resolve_user_id(memory_cfg, principal_id, tenant_id, context)`
  takes `memory_cfg: Any` and reads `system_user_id` via `getattr`. It does not
  import `MemoryConfig`, Agno, or anything else.
- **Alternatives considered**:
  - Type `memory_cfg: MemoryConfig` — couples the resolver to the schema
    module, and forces tests to build a full `MemoryConfig` just to exercise
    the resolver. The resolver only needs `system_user_id`.
  - Pass `system_user_id` as a separate scalar — loses the symmetry with the
    YAML `memory:` block and forces every caller to extract the field.
- **Rationale**: `Any` + `getattr` keeps the resolver pure-Python, trivially
  unit-testable with a one-field stub object or `types.SimpleNamespace`, and
  lets `MemoryConfig` evolve without a resolver change. This is the literal
  signature in SPEC_04 §1.4 (lines 183-186).

### Decision: `MemoryConfig` is pure Pydantic V2, no Agno imports

- **Choice**: `MemoryConfig` mirrors the Agno `Agent` constructor flags
  (`enable_agentic_memory`, `update_memory_on_run`, `add_memories_to_context`,
  `num_history_runs`, `num_history_messages`) plus `system_user_id` and the
  nested `session` / `working` / `learning` / `retention` blocks. It imports
  only `pydantic` and the stdlib.
- **Alternatives considered**:
  - Re-export Agno's own memory config dataclasses — Agno has no such typed
    config; the flags are loose `Agent.__init__` kwargs. There is nothing to
    re-export.
  - Import Agno to validate field names at parse time — couples the schema to
    a pinned Agno version and breaks the "configure, don't wrap" rule
    (decision #4: memory is 100% Agno-native).
- **Rationale**: Pure Pydantic matches the `model_spec.py` precedent
  (standalone additive slice, `ConfigDict(extra="forbid")`, `__all__`) and keeps
  the schema importable even if Agno is absent (useful for docs generation and
  editor autocomplete in YAML authoring).

### Decision: Option B opaque — `AgentConfig.memory` left as `dict[str, Any] | None`

- **Choice**: This slice does NOT touch `AgentConfig.memory`
  (`src/yaml_agno/models/config/agent_config.py:63`). The typed `MemoryConfig`
  ships as a standalone schema that nothing wires yet.
- **Alternatives considered**:
  - Option A (swap the slot to `memory: MemoryConfig | None` now) — breaks
    every existing config fixture and forces a coordinated `AgentConfig`
    validation change; out of scope for a leaf whose job is to break a cycle.
  - Ship a `parse_memory_config()` helper like `parse_model_spec()` — premature
    until the wiring slice decides dispatch rules.
- **Rationale**: the leaf's contract is "the resolver and the schema exist and
  are tested". Wiring is a separate, reviewable change with its own blast
  radius. The proposal explicitly defers `AgentConfig` slot replacement.

### Decision: DEFER SPEC_06 wiring

- **Choice**: `TenantContextMiddleware` (the HTTP caller of `resolve_user_id`)
  is NOT built here. The middleware will `from yaml_agno.memory import
  resolve_user_id` when SPEC_06 lands.
- **Alternatives considered**: ship a minimal middleware stub now — violates
  the slice boundary and re-introduces the SPEC_04 <-> SPEC_06 cycle this leaf
  exists to break.
- **Rationale**: the cycle is broken precisely because the resolver has no
  caller in this slice; SPEC_06 can depend on a shipped, tested symbol instead
  of a spec paragraph.

## Components & Data Flow

```
                 resolve_user_id(memory_cfg, principal_id, tenant_id, context)
                 ─────────────────────────────────────────────────────────────
                 1. tenant_id missing?        -> raise UserIdentityResolutionError
                 2. principal_id present?     -> resolved_principal = principal_id
                 3. else memory_cfg.system_user_id:
                      "{" in it?              -> template.format(**context)
                                                (missing context/key -> raise)
                      else                    -> literal string
                 4. neither resolves?         -> raise UserIdentityResolutionError
                 5. return f"{tenant_id}:{resolved_principal}"
```

Caller topology (future, NOT in this slice):

- HTTP path: `TenantContextMiddleware` (SPEC_06) extracts `tenant_id` from
  JWT/header and `principal_id` from the authenticated user, then calls
  `resolve_user_id(memory_cfg, principal_id, tenant_id, request_context)`.
- Autonomous / workflow path: the runner passes `tenant_id` from the
  agent/workflow YAML `tenant_id` field, `principal_id=None`, and a `context`
  dict carrying `agent_id` / `workflow_id` for template expansion.

Integration points:

- `MemoryConfig.system_user_id` is the field `resolve_user_id` reads via
  `getattr(memory_cfg, "system_user_id", None)`. The two modules share this
  field name as their only contract; everything else is independent.
- No filesystem, no DB, no network. Both modules are pure functions / pure
  data classes.

## Literal Code

The three files below are the literal source to be written by `sdd-apply`.
They are copied verbatim from SPEC_04 §1.4 (lines 166-259) for
`user_identity.py`, and derived field-for-field from SPEC_04 §1.3 (lines
86-153) for `memory_config.py`, matching the `model_spec.py` standalone-schema
pattern.

### `src/yaml_agno/memory/user_identity.py`

```python
"""User identity resolution for yaml-agno (SPEC_04 leaf).

THE single ``user_id`` resolver for ALL of yaml-agno (HTTP + non-HTTP). Returns
the composite ``"{tenant_id}:{principal_id}"`` — never a bare principal, never
``None``. ``TenantContextMiddleware`` (SPEC_06) calls this instead of building
the composite inline.

Verified against Agno v2.6.18: ``MemoryManager`` coerces ``user_id=None`` to the
literal string ``"default"`` in every method (``agno/memory/manager.py:177,191,
205,239``), causing cross-talk between anonymous runs. This module exists to
make that fall-through impossible.
"""

from typing import Any


class UserIdentityResolutionError(RuntimeError):
    """Raised when user_id cannot be resolved and Agno's 'default' is disallowed."""


def resolve_user_id(memory_cfg: Any,
                    principal_id: str | None,
                    tenant_id: str | None,
                    context: dict | None = None) -> str:
    """Resolve the effective Agno user_id as the composite "{tenant_id}:{principal_id}".

    This is THE single resolver used everywhere in yaml-agno (HTTP requests via
    TenantContextMiddleware, and autonomous/workflow runs). The composite format
    lives ONLY here; callers MUST NOT build ``f"{tenant}:{user}"`` inline.

    Selection of the principal:
      1. ``principal_id`` (the human user id, when a human is present).
      2. ``memory_cfg.system_user_id``, after expanding derivation templates such
         as ``"workflow:{workflow_id}"`` or ``"agent:{agent_id}"`` against
         ``context``.
      3. Nothing else — there is NO silent fallback to Agno's ``"default"``.

    Args:
        memory_cfg: YAML ``memory:`` block (SPEC_02 *Config). Carries
            ``system_user_id`` (a literal string or a ``{placeholder}`` template)
            used as the principal when no human is present.
        principal_id: Human user id when the run has one; ``None`` otherwise
            (the ``system_user_id`` is then used as the principal).
        tenant_id: Tenant id. For HTTP requests it comes from the JWT/header
            (TenantContextMiddleware, SPEC_06); for autonomous/workflow runs it
            comes from the agent/workflow YAML ``tenant_id`` field.
        context: Optional dict used to expand templates (``workflow_id``,
            ``agent_id``, etc.).

    Returns:
        The composite ``"{tenant_id}:{principal_id}"`` string (never ``None``,
        never a bare principal).

    Raises:
        UserIdentityResolutionError: if ``tenant_id`` is missing, or if neither a
            human principal nor a ``system_user_id`` resolves. The caller MUST
            surface this at config-build/run time rather than passing
            ``user_id=None`` to Agno.
    """
    if not tenant_id:
        raise UserIdentityResolutionError(
            "tenant_id is required to build the composite user_id "
            "'{tenant_id}:{principal_id}'. For HTTP requests it comes from the "
            "TenantContextMiddleware (SPEC_06); for autonomous runs set the "
            "agent/workflow YAML 'tenant_id' field. Refusing to build a "
            "tenant-less user_id (would break tenant isolation)."
        )

    if principal_id:
        resolved_principal = principal_id
    else:
        template = getattr(memory_cfg, "system_user_id", None)
        if not template:
            raise UserIdentityResolutionError(
                "No principal resolves (no human user and no "
                "memory.system_user_id). Refusing to fall through to Agno's "
                "shared 'default' memory bucket; set memory.system_user_id or "
                "pass an explicit principal_id."
            )
        if "{" in template and "}" in template:
            if context is None:
                raise UserIdentityResolutionError(
                    f"system_user_id template {template!r} needs a context dict "
                    f"(workflow_id/agent_id/...) to expand."
                )
            try:
                resolved_principal = template.format(**context)
            except KeyError as exc:
                raise UserIdentityResolutionError(
                    f"system_user_id template {template!r} references missing "
                    f"key {exc}. Provide it in the run context."
                ) from exc
        else:
            resolved_principal = template

    return f"{tenant_id}:{resolved_principal}"


__all__ = ["UserIdentityResolutionError", "resolve_user_id"]
```

### `src/yaml_agno/models/config/memory_config.py`

```python
"""Memory configuration schema (SPEC_04 leaf).

A pure-Pydantic V2 typed replacement for the opaque
``AgentConfig.memory: dict[str, Any] | None`` slot. Maps the Agno ``Agent``
constructor memory flags + ``system_user_id`` + the nested
session/working/learning/retention blocks declared in SPEC_04 §1.3.

This module is a STANDALONE additive slice: nothing imports it yet, and it
imports nothing from Agno (memory is 100% Agno-native; yaml-agno only
configures it). Wiring ``AgentConfig.memory`` to :class:`MemoryConfig` is a
later coordinated change (Option B opaque until then). Pattern follows
SPEC_14 ``model_spec.py``: ``ConfigDict(extra="forbid")``, separate file,
Google docstrings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionMemoryConfig(BaseModel):
    """Agno session DB configuration (SPEC_04 §1.3 ``memory.session``).

    Attributes:
        storage_type: Agno session storage backend.
        max_messages: Agno native cap on recalled history messages.
    """

    model_config = ConfigDict(extra="forbid")

    storage_type: Literal["sqlite", "postgres", "memory"] = Field(
        ...,
        description="Agno session storage backend (sqlite|postgres|memory).",
    )
    max_messages: int = Field(
        ...,
        ge=0,
        description="Agno native cap on recalled history messages.",
    )


class WorkingMemoryConfig(BaseModel):
    """Working-context configuration (SPEC_04 §1.3 ``memory.working``).

    Attributes:
        max_context_tokens: Max tokens admitted into the working context window.
        compression_threshold: Token count at which SPEC_15 compression triggers.
        include_tool_calls: Whether tool-call transcripts are kept in working memory.
    """

    model_config = ConfigDict(extra="forbid")

    max_context_tokens: int = Field(..., ge=1, description="Max tokens in the working context window.")
    compression_threshold: int = Field(
        ..., ge=0, description="Token count at which SPEC_15 compression triggers."
    )
    include_tool_calls: bool = Field(..., description="Keep tool-call transcripts in working memory.")


class LearnedKnowledgeScopeConfig(BaseModel):
    """Scope for the ``learned_knowledge`` Agno store (SPEC_04 §1.5).

    Attributes:
        scope: Top-level namespace for learned knowledge. MUST be set explicitly
            (NOT inherited; see SPEC_04 §1.5 gotcha).
    """

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(..., min_length=1, description="Namespace for learned_knowledge (set explicitly).")


class EntityMemoryScopeConfig(BaseModel):
    """Scope for the ``entity_memory`` Agno store (SPEC_04 §1.5).

    Attributes:
        scope: Namespace for entity memory. Inherits the top-level learning scope
            when omitted; set explicitly to override.
    """

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(..., min_length=1, description="Namespace for entity_memory (inherits when omitted at runtime).")


class LearningMemoryConfig(BaseModel):
    """Long-term learning configuration (SPEC_04 §1.3 ``memory.learning``).

    Maps to the Agno ``LearningMachine`` (rich, 6 stores) when ``enabled`` is
    true, and to the ``MemoryManager`` / ``UserMemory`` simple path otherwise.

    Attributes:
        enabled: Turn on the Agno ``LearningMachine`` (cross-session learning).
        recall_on_start: Inject recalled learnings when a session starts.
        save_on_decision: Persist decisions through Agno native memory.
        save_on_discovery: Persist discoveries through Agno native memory.
        save_on_bugfix: Persist bug fixes through Agno native memory.
        scope: Top-level namespace inherited by ``entity_memory``.
        learned_knowledge: Explicit ``learned_knowledge`` namespace (NOT inherited).
        entity_memory: ``entity_memory`` namespace (inherits ``scope`` when omitted).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Turn on Agno LearningMachine (cross-session learning).")
    recall_on_start: bool = Field(..., description="Inject recalled learnings when a session starts.")
    save_on_decision: bool = Field(..., description="Persist decisions through Agno native memory.")
    save_on_discovery: bool = Field(..., description="Persist discoveries through Agno native memory.")
    save_on_bugfix: bool = Field(..., description="Persist bug fixes through Agno native memory.")
    scope: str = Field(..., min_length=1, description="Top-level namespace, inherited by entity_memory.")
    learned_knowledge: LearnedKnowledgeScopeConfig = Field(
        ..., description="learned_knowledge namespace (MUST be set explicitly; see §1.5)."
    )
    entity_memory: EntityMemoryScopeConfig = Field(
        ..., description="entity_memory namespace (inherits top-level scope when omitted)."
    )


class RetentionMaxAgeConfig(BaseModel):
    """Retention TTLs per store (SPEC_04 §1.3 ``memory.retention.max_age_days``).

    Attributes:
        sessions: Session messages TTL in days (example default 30).
        user_memory: UserMemory/UserMemo TTL in days (example default 180).
        learned_knowledge: learned_knowledge namespace TTL in days (example default 365).
    """

    model_config = ConfigDict(extra="forbid")

    sessions: int = Field(..., ge=0, description="Session messages TTL in days.")
    user_memory: int = Field(..., ge=0, description="UserMemory/UserMemo TTL in days.")
    learned_knowledge: int = Field(..., ge=0, description="learned_knowledge namespace TTL in days.")


class RetentionConfig(BaseModel):
    """Retention configuration (SPEC_04 §1.3 ``memory.retention``).

    Post-MVP configurable job; Agno has no native retention. WARNING (SPEC_04
    §3.4): do NOT use ``MemoryManager.clear()`` / ``db.clear_memories()`` in the
    purge job — they are global nukes with NO user/tenant filter.

    Attributes:
        enabled: Whether the retention purge job is active (post-MVP; non-blocking).
        max_age_days: Per-store TTLs.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Enable the retention purge job (post-MVP).")
    max_age_days: RetentionMaxAgeConfig = Field(..., description="Per-store TTLs.")


class MemoryConfig(BaseModel):
    """Typed replacement for the opaque ``memory: dict[str, Any] | None`` slot.

    Mirrors the Agno ``Agent`` constructor memory flags plus ``system_user_id``
    and the nested session/working/learning/retention blocks declared in
    SPEC_04 §1.3. Pure Pydantic V2 — no Agno imports.

    Attributes:
        enable_agentic_memory: Agno agentic memory on/off.
        update_memory_on_run: Persist learnings after each run.
        add_memories_to_context: Inject recalled memories into the prompt.
        num_history_runs: Agno-managed history window (runs).
        num_history_messages: Agno-managed history window (messages).
        system_user_id: Principal part of the composite user_id used when there
            is no human user. Literal string OR a ``{placeholder}`` template
            resolved by :func:`yaml_agno.memory.resolve_user_id` against the
            run ``context``. The tenant_id is prefixed at resolve time.
        session: Agno session DB configuration.
        working: Working-context configuration.
        learning: Long-term learning configuration.
        retention: Retention purge configuration (post-MVP).

    Example:
        >>> MemoryConfig(
        ...     enable_agentic_memory=True,
        ...     update_memory_on_run=True,
        ...     add_memories_to_context=True,
        ...     num_history_runs=5,
        ...     num_history_messages=50,
        ...     system_user_id="agent:my_agent",
        ... )
    """

    model_config = ConfigDict(extra="forbid")

    # --- Agno Agent constructor memory flags (5 fields) ---
    enable_agentic_memory: bool = Field(..., description="Agno agentic memory on/off.")
    update_memory_on_run: bool = Field(..., description="Persist learnings after each run.")
    add_memories_to_context: bool = Field(..., description="Inject recalled memories into the prompt.")
    num_history_runs: int = Field(..., ge=0, description="Agno-managed history window (runs).")
    num_history_messages: int = Field(..., ge=0, description="Agno-managed history window (messages).")

    # --- User identity (1 field) ---
    system_user_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Principal part of the composite user_id (tenant prefixed at resolve "
            "time by resolve_user_id). Literal string OR a {placeholder} template."
        ),
    )

    # --- Nested blocks (4 fields) ---
    session: SessionMemoryConfig | None = Field(None, description="Agno session DB configuration.")
    working: WorkingMemoryConfig | None = Field(None, description="Working-context configuration.")
    learning: LearningMemoryConfig | None = Field(None, description="Long-term learning configuration.")
    retention: RetentionConfig | None = Field(None, description="Retention purge configuration (post-MVP).")


__all__ = [
    "EntityMemoryScopeConfig",
    "LearnedKnowledgeScopeConfig",
    "LearningMemoryConfig",
    "MemoryConfig",
    "RetentionConfig",
    "RetentionMaxAgeConfig",
    "SessionMemoryConfig",
    "WorkingMemoryConfig",
]
```

### `src/yaml_agno/memory/__init__.py`

```python
"""Memory subsystem (SPEC_04 leaf).

Re-exports the single user_id resolver so callers can
``from yaml_agno.memory import resolve_user_id``.
"""

from yaml_agno.memory.user_identity import UserIdentityResolutionError, resolve_user_id

__all__ = ["UserIdentityResolutionError", "resolve_user_id"]
```

## File Changes

| File | Change | Type |
| --- | --- | --- |
| `src/yaml_agno/memory/user_identity.py` | NEW — `UserIdentityResolutionError` + `resolve_user_id()`. Literal from SPEC_04 §1.4 (lines 166-259). | additive |
| `src/yaml_agno/models/config/memory_config.py` | NEW — `MemoryConfig` + 7 nested sub-schemas. Fields from SPEC_04 §1.3 (lines 86-153), pattern from `model_spec.py`. | additive |
| `src/yaml_agno/memory/__init__.py` | EDITED — currently empty; gains the two re-exports. | additive |

**Out of scope (explicitly NOT touched):**

- `src/yaml_agno/models/config/agent_config.py:63` — the
  `memory: dict[str, Any] | None` slot stays opaque (Option B).
- `TenantContextMiddleware` — deferred to SPEC_06.
- `ContextCompressor` — deferred to SPEC_15.
- PII / secret sanitization — deferred to SPEC_16.
- Retention purge job — post-MVP.

## Testing Strategy

Two unit-test modules, co-located with the source per repo convention:

- `tests/yaml_agno/memory/test_user_identity.py`
- `tests/yaml_agno/models/config/test_memory_config.py`

`resolve_user_id` coverage = the 5 RED cases from SPEC_04 TASK_005 (lines
728-787):

1. **Happy human** — `principal_id` set, `tenant_id` set -> returns
   `"{tenant_id}:{principal_id}"`.
2. **System principal literal** — `principal_id=None`,
   `memory_cfg.system_user_id="agent:facturacion"` -> returns
   `"acme:agent:facturacion"`.
3. **System principal template** — `system_user_id="workflow:{workflow_id}"`,
   `context={"workflow_id": "wf-42"}` -> returns `"acme:workflow:wf-42"`.
4. **Missing tenant** — `tenant_id=None` -> raises
   `UserIdentityResolutionError`.
5. **Missing principal** — `principal_id=None`, no `system_user_id` -> raises
   `UserIdentityResolutionError`.

Plus two template-edge cases implied by the literal code:

6. **Template without context** — `system_user_id="workflow:{workflow_id}"`,
   `context=None` -> raises.
7. **Template with missing key** — `context={"agent_id": "a"}` but template
   references `{workflow_id}` -> raises `UserIdentityResolutionError`
   (chained from `KeyError`).

`MemoryConfig` coverage:

- Parse the SPEC_04 §1.3 YAML example end-to-end (all nested blocks).
- `extra="forbid"` rejects unknown keys.
- Required-flag omission fails fast (`enable_agentic_memory` etc. are
  required, no defaults — they are behavioral knobs, not cosmetic).
- `system_user_id` empty string rejected (`min_length=1`).
- `num_history_runs` / `num_history_messages` reject negatives (`ge=0`).
- Nested `session.storage_type` rejects values outside the
  `sqlite|postgres|memory` literal.
- Top-level `MemoryConfig` parses with only the 6 required scalar fields
  (`session` / `working` / `learning` / `retention` optional -> `None`).

## TDD

Strict TDD (repo mode). For each file pair:

1. **RED** — write the failing test module first, run `pytest <path>`, confirm
   it fails on `ImportError` (module does not exist yet).
2. **GREEN** — write the literal source above, run `pytest <path>`, confirm
   all tests pass.
3. **REFACTOR** — none expected; the code is literal from SPEC_04 and should
   not be reshaped. If a test reveals a SPEC gap, stop and surface it rather
   than editing the literal.

Order: `user_identity.py` first (no deps), then `memory_config.py` (no deps),
then `memory/__init__.py` (depends on `user_identity`).

## Verification

After implementation:

- `pytest tests/yaml_agno/memory/test_user_identity.py
  tests/yaml_agno/models/config/test_memory_config.py -v` — all green.
- `ruff check src/yaml_agno/memory/ src/yaml_agno/models/config/memory_config.py` — clean.
- `mypy src/yaml_agno/memory/ src/yaml_agno/models/config/memory_config.py` — clean.
- `python -c "from yaml_agno.memory import resolve_user_id, UserIdentityResolutionError; from yaml_agno.models.config.memory_config import MemoryConfig; print('ok')"` — imports resolve.
- Confirm `AgentConfig.memory` is STILL `dict[str, Any] | None`
  (`grep -n "memory:" src/yaml_agno/models/config/agent_config.py`) — Option B
  untouched.

## Rollback

All three changes are additive (two new files, one empty -> re-export). Rollback
is mechanical:

1. `git rm src/yaml_agno/memory/user_identity.py`
2. `git rm src/yaml_agno/models/config/memory_config.py`
3. Revert `src/yaml_agno/memory/__init__.py` to its empty prior content.
4. `git rm` the two test modules.

No downstream caller depends on these symbols (Option B opaque; SPEC_06
deferred), so removal cannot break anything else. No DB migrations, no config
file format changes, no published API.

## Open Items / Assumptions

- **Assumption**: `MemoryConfig` scalar flags are required (no defaults). The
  SPEC_04 §1.3 example shows explicit values for every flag; if a later wiring
  slice wants defaults, that is a separate, reviewable change.
- **Assumption**: `session` / `working` / `learning` / `retention` are optional
  (`... | None = None`). The SPEC_04 example shows all four populated, but a
  minimal memory config (just the 6 scalars) should parse — these blocks are
  independently meaningful (e.g. `retention.enabled=false` is post-MVP).
- **Assumption**: `resolve_user_id` reads `system_user_id` via `getattr(...,
  None)` so a `types.SimpleNamespace(system_user_id="x")` is a valid
  `memory_cfg` for tests; production callers pass a `MemoryConfig`.
- **Risk**: if a future Agno version renames the `Agent` memory constructor
  flags, `MemoryConfig` field names will drift from the kwargs the wiring slice
  forwards. Mitigation: the wiring slice's tests assert the field-name ->
  kwarg-name mapping against the pinned Agno version.
- **Risk**: `learning.scope` / `learned_knowledge.scope` / `entity_memory.scope`
  are free strings with no format validation in this slice; SPEC_04 §1.5
  namespace semantics are enforced later by the learning-machine wiring.
