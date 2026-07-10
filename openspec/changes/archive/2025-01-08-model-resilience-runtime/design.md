---
change: model-resilience-runtime
spec: SPEC_14
status: designed
artifact_store: hybrid
depends_on:
  - openspec/specs/model-config-schema
  - openspec/specs/provider-factory-adapter
slice: "SPEC_14 #4 (DOMAIN-only)"
---

# Design: model-resilience-runtime (SPEC_14 slice #4 — DOMAIN)

## Technical Approach

Three additive, standalone modules under `src/yaml_agno/models/` close the
resilience DOMAIN layer: each is a pure function or static-method class with
injectable dependencies, no async, no network. They COMPOSE the already-shipped
slices — `ModelExpandedSpec` / `FallbackConfig` / `parse_model_spec` /
`ProviderResolver` (slice #2) and `ProviderFactory.build` (slice #3) — into the
three primitives the runtime (SPEC_09) and step-retry (SPEC_05) will consume.

- `fallback_chain.py` assembles Agno Model **instances** (not specs) via
  `ProviderFactory.build`, primary at index 0, truncated to
  `max_fallback_hops`.
- `cache_key.py` derives a deterministic sha256 hex digest over the spec + the
  caller-supplied message/tool/response-model hashes. It is a dedup/observability
  KEY (SPEC_09 traces), not a cache store.
- `fallback_classifier.py` is a thin `isinstance` adapter over
  `agno.exceptions` (Agno already classifies via
  `ModelProviderError.classify`); it never reimplements status/pattern logic.

The slice is bounded by the explicit DEFER list (proposal Out-of-Scope):
`call_with_fallback`, `CircuitBreaker`, `RetryPolicy`, `compute_delay`,
`dispatch_fallback_callback`, `probe_models_health` are NOT touched here.

## Architecture Decisions

### A1 — DOMAIN-only slice; runtime/breaker/retry deferred

**Choice**: Ship ONLY `build_fallback_chain`, `CacheKeyBuilder`,
`FallbackErrorClassifier`. DEFER `call_with_fallback` + `CircuitBreaker` to
SPEC_09 and step-level `RetryPolicy` to SPEC_05.

**Alternatives considered**:
- Ship a minimal `call_with_fallback` here → rejected: it needs
  `CircuitBreaker.allow_request()`/`guard()` which does not exist yet.
- Ship model-level `RetryPolicy` → rejected: decision #6 (DECISIONES.md) says
  retry is step-level; model-level retry is Agno-native (forwarded via slice #2
  fields `retries`, `delay_between_retries`, etc.).

**Rationale**: Keeps the slice pure, async-free, and independently testable.
SPEC_09 and SPEC_05 get well-typed primitives to build on without coupling to
half-built runtime internals. ~305 changed lines, well under the 400-line
review budget — single PR viable.

### A2 — FallbackErrorClassifier is a THIN ADAPTER over Agno

**Choice**: Use `isinstance` against Agno's exception hierarchy
(`ModelRateLimitError`, `ContextWindowExceededError`, `ModelProviderError`),
delegating the ambiguous case to `ModelProviderError.classify(exc)`.

**Alternatives considered**:
- Reimplement 429/529 status-code + `CONTEXT_WINDOW_PATTERNS` inspection →
  rejected: Agno already does this in `agno/exceptions.py`; duplicating it
  creates drift.
- Switch on `exc.status_code` / `exc.message` strings → rejected: couples to
  Agno internals that are private to those exception classes.

**Rationale**: yaml-agno already imports `agno.*` throughout; the coupling is
consistent with the codebase. The classifier stays under 45 LOC and gains
Agno's classification improvements for free.

### A3 — build_fallback_chain returns Model INSTANCES, not specs

**Choice**: `build_fallback_chain(...) -> list[Any]` where each element is an
Agno Model instance built via `factory.build(spec)`.

**Alternatives considered**:
- Return `list[ModelExpandedSpec]` (SPEC_14 §12.2 draft) → rejected: with
  `ProviderFactory` shipped, the runtime (SPEC_09) needs invokable Models, not
  specs it would have to re-instantiate.
- Return `list[Model]` (Agno type) → rejected: `Model` is resolved dynamically
  via `resolve_class`; annotating with it couples mypy to an opaque import. `Any`
  matches `ProviderFactory.build`'s return contract.

**Rationale**: One construction site (`ProviderFactory.build`), instances ready
for invocation, type-checker stays decoupled. Deviation from SPEC_14 §12.2 is
documented in the proposal.

### A4 — CacheKeyBuilder builds a DEDUP KEY, not a cache layer

**Choice**: `CacheKeyBuilder.build` returns a sha256 hex digest. It does NOT
store, retrieve, or invalidate. Message/tool/response-model content is hashed
by the caller; the builder only concatenates the caller-supplied hashes with the
spec dump.

**Alternatives considered**:
- Builder serializes messages/tools itself → rejected: forces the domain layer
  to know Agno message/tool schemas (scope creep, R4).
- Add a `CacheManager` (get/set) → rejected: SPEC_14 §5.4 says yaml-agno does
  NOT add a cache layer; Agno `cache_response` is native.
- Drop `check_compatibility` dynamic-context warning → rejected (SPEC_15
  territory, not here).

**Rationale**: Pure, fast, dependency-free. The key serves observability/dedup
needs (SPEC_09 traces) without committing yaml-agno to owning cache semantics.

### A5 — Reject `{"alias": name}` refs with explicit NotImplementedError

**Choice**: When a `fallback_models` entry is a dict whose ONLY key is
`"alias"`, raise `NotImplementedError` naming TASK_013.

**Alternatives considered**:
- Skip silently → rejected: hides an unsupported shape from the user.
- Resolve via a stub registry → rejected: `ModelsConfig.definitions` (TASK_013)
  is unshipped; inventing a half-registry would be throwaway.

**Rationale**: A loud, explicit error is safer than silent data loss and points
the user at the future work item.

## Data Flow

```
  ModelExpandedSpec (slice #2)            ProviderFactory (slice #3)
       │  .fallback.fallback_models            │  .build(spec) -> Model
       │  .fallback.max_fallback_hops          │
       ▼                                       │
  build_fallback_chain ────────── parse_model_spec + ProviderResolver
       │  (per entry: str | dict)             │
       │   ├── {"alias": ...} ──► NotImplementedError (A5)
       │   └── str / {provider,id} ──► factory.build ──► Model
       ▼
  list[Any] = [primary_model, *fallback_models][:max_fallback_hops]


  ModelProviderError / ModelRateLimitError / ContextWindowExceededError
       │
       ▼
  FallbackErrorClassifier.classify(exc)
       ├── isinstance ModelRateLimitError ─────────► "rate_limit"
       ├── isinstance ContextWindowExceededError ──► "context_overflow"
       ├── isinstance ModelProviderError ──► delegate ModelProviderError.classify(exc)
       └── else ───────────────────────────────────► "error"
       │
       ▼  (consumed by SPEC_09 runtime to pick on_rate_limit/on_context_overflow/on_error)


  ModelExpandedSpec + caller hashes
       │  spec.model_dump(exclude_none=True)  +  messages_hash  +  tool_defs_hash  +  response_model_hash
       ▼
  CacheKeyBuilder.build  ──► json.dumps(sort_keys=True, separators=(",",":")) ──► sha256 hexdigest
       │
       ▼
  "64-char dedup key"  (SPEC_09 trace identity — NOT a cache store)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/models/fallback_chain.py` | Create | `build_fallback_chain(primary, factory) -> list[Any]`. Parses `fallback_models` via `parse_model_spec` + `ProviderResolver`, builds each via `factory.build`, primary at index 0, truncates to `max_fallback_hops`. Rejects `{"alias": ...}` with `NotImplementedError`. |
| `src/yaml_agno/models/cache_key.py` | Create | `CacheKeyBuilder.build(spec, *, messages_hash, tool_defs_hash="", response_model_hash="") -> str`. Deterministic sha256 hex digest over a stable serialization of the spec + caller hashes. |
| `src/yaml_agno/models/fallback_classifier.py` | Create | `FallbackErrorClassifier.classify(exc) -> Literal["rate_limit","context_overflow","error"]`. Thin `isinstance` adapter over `agno.exceptions`; delegates ambiguous `ModelProviderError` to Agno's `classify`. |
| `src/yaml_agno/models/__init__.py` | Modify | Re-export `build_fallback_chain`, `CacheKeyBuilder`, `FallbackErrorClassifier`. |
| `tests/unit/models/test_fallback_chain.py` | Create | Strict TDD: empty chain, N-model chain, `max_fallback_hops` truncation, `{"alias":...}` rejection. |
| `tests/unit/models/test_cache_key.py` | Create | Strict TDD: determinism, temperature sensitivity, messages_hash sensitivity. |
| `tests/unit/models/test_fallback_classifier.py` | Create | Strict TDD: 4 branches with real Agno exceptions + mock subclasses for delegación. |
| `src/yaml_agno/models/model_spec.py` | Untouched | READ for `FallbackConfig`, `parse_model_spec`, `ProviderResolver`, `ModelExpandedSpec`. |
| `src/yaml_agno/di/provider_factory.py` | Untouched | READ for `ProviderFactory.build(spec) -> Any`. |

## Interfaces / Contracts

### `src/yaml_agno/models/fallback_chain.py`

```python
"""build_fallback_chain — ensambla la cadena de fallback Agno (SPEC_14 #4 DOMAIN).

COMPOSE los slices #2 y #3: parsea cada entrada de
``FallbackConfig.fallback_models`` vía :func:`parse_model_spec`, canonicaliza
el provider vía :class:`ProviderResolver`, y construye cada instancia Agno Model
vía ``factory.build(spec)``. La primaria va en el índice 0; la lista se
trunca a ``max_fallback_hops``.

Devuelve INSTANCIAS (no specs) — ver ADR A3. El tipo es ``list[Any]`` para no
acoplar el type-checker al tipo ``Model`` de Agno (resuelto dinámicamente vía
``resolve_class``).

@ai-directive: NO reimplementes parse_model_spec / ProviderResolver — delega.
    NO construyas instancias directamente — usa factory.build. NO resuelvas
    ``{"alias": name}`` refs (TASK_013 unshipped) — REJECT con NotImplementedError.
"""

from __future__ import annotations

from typing import Any

from yaml_agno.di.provider_factory import ProviderFactory
from yaml_agno.models.model_spec import (
    ModelExpandedSpec,
    ProviderResolver,
    parse_model_spec,
)

__all__ = ["build_fallback_chain"]


def build_fallback_chain(
    primary: ModelExpandedSpec,
    factory: ProviderFactory,
    *,
    resolver: ProviderResolver | None = None,
) -> list[Any]:
    """Assemble the ordered fallback chain as Agno Model instances.

    Pipeline:
      1. Build the primary model via ``factory.build(primary)`` → index 0.
      2. If ``primary.fallback is None``, return ``[primary_model]``.
      3. Otherwise iterate ``primary.fallback.fallback_models``; for each entry:
         - dict with a single ``"alias"`` key → raise ``NotImplementedError``
           (definitions registry = TASK_013, unshipped; A5).
         - ``str | dict`` → :func:`parse_model_spec` →
           :meth:`ProviderResolver.resolve` (canonicalize alias) →
           ``factory.build(spec)`` → Model instance.
      4. Truncate the resulting list to ``primary.fallback.max_fallback_hops``
         (inclusive of the primary).

    Args:
        primary: The primary model spec. When ``primary.fallback`` is set, its
            ``fallback_models`` and ``max_fallback_hops`` drive the chain.
        factory: ProviderFactory (slice #3) — builds each Agno Model instance.
        resolver: Optional ProviderResolver for alias canonicalization. Defaults
            to ``ProviderResolver()``; injectable for testing.

    Returns:
        Ordered list of Agno Model instances, primary first. Length is
        ``min(1 + len(fallback_models), max_fallback_hops)`` when a fallback
        config exists, else ``[primary_model]`` (length 1).

    Raises:
        NotImplementedError: If a ``fallback_models`` entry is a dict whose only
            key is ``"alias"`` (definitions registry unshipped; A5).
        KeyError: Propagated from ``factory.build`` on unknown provider.
        ValueError: Propagated from ``parse_model_spec`` / ``ProviderResolver``
            on malformed input or unsupported provider.

    Example:
        >>> primary = ModelExpandedSpec(
        ...     provider="openai", id="gpt-4o",
        ...     fallback=FallbackConfig(fallback_models=["anthropic:claude-3-5-sonnet"]),
        ... )
        >>> chain = build_fallback_chain(primary, factory)
        >>> len(chain)
        2
    """
    active_resolver = resolver if resolver is not None else ProviderResolver()
    primary_model = factory.build(primary)

    if primary.fallback is None:
        return [primary_model]

    chain: list[Any] = [primary_model]
    for entry in primary.fallback.fallback_models:
        if isinstance(entry, dict) and set(entry.keys()) == {"alias"}:
            raise NotImplementedError(
                "Alias-by-name fallback refs ({'alias': ...}) require a "
                "definitions registry (TASK_013, unshipped). Use inline "
                "'provider:id' strings or {provider, id} dicts instead."
            )
        parsed = parse_model_spec(entry)
        resolved = active_resolver.resolve(parsed)
        chain.append(factory.build(resolved))

    max_hops = primary.fallback.max_fallback_hops
    # +1 because max_fallback_hops counts hops AFTER the primary (index 0),
    # not total chain length. (Off-by-one corrected during apply.)
    return chain[: max_hops + 1]
```

### `src/yaml_agno/models/cache_key.py`

```python
"""CacheKeyBuilder — clave sha256 determinista (SPEC_14 #4 DOMAIN).

Deriva una clave de 64 chars (hex sha256) sobre la identidad del spec + los
hashes que el caller provee. Es una CLAVE de dedup/observabilidad (trazas
SPEC_09), NO un cache store — Agno ``cache_response`` es nativo y yaml-agno NO
agrega capa de cache (SPEC_14 §5.4, ADR A4).

El builder NO serializa messages/tools/response_model: el caller (runtime
SPEC_09) los hashea y los pasa como strings. Esto evita scope-creep de
serialización de esquemas Agno en el dominio (R4).

@ai-directive: NO agregues get/set/invalidate — no es un CacheManager. NO
    serialices mensajes/tools — el caller los hashea. Usa SIEMPRE
    sort_keys=True + separators compactos para estabilidad cross-plataforma.
"""

from __future__ import annotations

import hashlib
import json

from yaml_agno.models.model_spec import ModelExpandedSpec

__all__ = ["CacheKeyBuilder"]

# Prefijo corto y estable para distinguir esta clave de otros hashes en trazas.
# NO cambia entre versiones: alterarlo rompe la determinismo cross-versión.
_PREFIX = "ya:ck:v1:"


class CacheKeyBuilder:
    """Build a deterministic sha256 hex digest for a model invocation.

    Stateless. The digest is over a stable JSON serialization of:
      - ``spec.model_dump(exclude_none=True)`` (provider, id, temperature, ...)
      - the caller-supplied ``messages_hash``, ``tool_defs_hash``,
        ``response_model_hash``.

    Serialization is ``json.dumps(..., sort_keys=True, separators=(",", ":"))``
    so key ordering and whitespace never affect the digest.

    Example:
        >>> key_a = CacheKeyBuilder.build(spec, messages_hash="abc")
        >>> key_b = CacheKeyBuilder.build(spec, messages_hash="abc")
        >>> key_a == key_b
        True
    """

    @staticmethod
    def build(
        spec: ModelExpandedSpec,
        *,
        messages_hash: str,
        tool_defs_hash: str = "",
        response_model_hash: str = "",
    ) -> str:
        """Return a 64-char sha256 hex digest identifying this invocation.

        Args:
            spec: The model spec — provider, id, and generation params feed the
                digest (``None`` fields excluded so optional unset values do not
                change the key).
            messages_hash: Caller-supplied hash of the serialized messages. The
                caller is responsible for stable ordering (e.g. sort by role).
            tool_defs_hash: Caller-supplied hash of the tool definitions. Empty
                string when no tools are bound.
            response_model_hash: Caller-supplied hash of the response model
                schema. Empty string for free-form completions.

        Returns:
            A string of the form ``"ya:ck:v1:<64 hex chars>"``. Deterministic:
            identical inputs always produce identical output.
        """
        payload = {
            "spec": spec.model_dump(exclude_none=True),
            "messages_hash": messages_hash,
            "tool_defs_hash": tool_defs_hash,
            "response_model_hash": response_model_hash,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{_PREFIX}{digest}"
```

### `src/yaml_agno/models/fallback_classifier.py`

```python
"""FallbackErrorClassifier — adaptador delgado sobre agno.exceptions (SPEC_14 #4).

Agno YA clasifica excepciones de modelo en ``agno/exceptions.py``:
``ModelProviderError.classify(error)`` es un classmethod que inspecciona
status_code (429/529 → ModelRateLimitError) y message patterns
(``CONTEXT_WINDOW_PATTERNS`` → ContextWindowExceededError). Este módulo NO
reimplementa esa lógica — es un adaptador ``isinstance`` que mapea la
jerarquía Agno al enum de routing que ``FallbackConfig`` define
(``on_rate_limit | on_context_overflow | on_error``).

@ai-directive: NO reimplementes status_code/patterns — delega a
    ModelProviderError.classify. NO uses los nombres del draft SPEC_14
    (``RateLimitError``, ``ContextOverflowError``) — NO existen en agno.exceptions.
"""

from __future__ import annotations

from typing import Literal

from agno.exceptions import (
    ContextWindowExceededError,
    ModelProviderError,
    ModelRateLimitError,
)

__all__ = ["FallbackErrorClassifier"]

# Tipo de retorno público. Mapea 1:1 a los routing enums de FallbackConfig
# (on_rate_limit / on_context_overflow / on_error).
ErrorCategory = Literal["rate_limit", "context_overflow", "error"]


class FallbackErrorClassifier:
    """Map an Agno model exception to a routing category.

    Thin adapter (ADR A2): the classification logic lives in Agno. This class
    only selects the right branch by ``isinstance`` and, for the ambiguous
    ``ModelProviderError`` case, delegates to ``ModelProviderError.classify``.

    Example:
        >>> try:
        ...     invoke_model()
        ... except Exception as exc:
        ...     cat = FallbackErrorClassifier.classify(exc)
        ...     # cat in {"rate_limit", "context_overflow", "error"}
    """

    @staticmethod
    def classify(exc: Exception) -> ErrorCategory:
        """Classify ``exc`` into one of three routing categories.

        Order matters: check the most specific subclasses first.
          1. ``ModelRateLimitError`` → ``"rate_limit"``.
          2. ``ContextWindowExceededError`` → ``"context_overflow"``.
          3. ``ModelProviderError`` (generic) → delegate to
             ``ModelProviderError.classify(exc)`` and map its result. If the
             Agno classmethod returns a subclass of one of the two above, map
             accordingly; otherwise fall back to ``"error"``. If delegation
             itself raises, treat as ``"error"`` (defensive — never let the
             classifier crash the runtime).
          4. Anything else → ``"error"``.

        Args:
            exc: The exception raised by an Agno Model invocation.

        Returns:
            One of ``"rate_limit"``, ``"context_overflow"``, ``"error"``.
        """
        if isinstance(exc, ModelRateLimitError):
            return "rate_limit"
        if isinstance(exc, ContextWindowExceededError):
            return "context_overflow"
        if isinstance(exc, ModelProviderError):
            try:
                classified = ModelProviderError.classify(exc)
            except Exception:
                # Delegación Agno lanzó — no dejes que el clasificador rompa
                # el runtime. Trata como error genérico.
                return "error"
            if isinstance(classified, ModelRateLimitError):
                return "rate_limit"
            if isinstance(classified, ContextWindowExceededError):
                return "context_overflow"
            return "error"
        return "error"
```

### `src/yaml_agno/models/__init__.py` (diff)

Append to the existing re-exports:

```python
from yaml_agno.models.cache_key import CacheKeyBuilder
from yaml_agno.models.fallback_chain import build_fallback_chain
from yaml_agno.models.fallback_classifier import FallbackErrorClassifier

__all__ = [
    # ... existing entries ...
    "CacheKeyBuilder",
    "FallbackErrorClassifier",
    "build_fallback_chain",
]
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `build_fallback_chain` | Stub `ProviderFactory` (returns tagged dicts) + real `parse_model_spec`/`ProviderResolver`. RED: `[primary_model]` when `fallback is None`. GREEN: 2-model chain from one str ref. GREEN: truncation at `max_fallback_hops`. RED: `NotImplementedError` on `{"alias": ...}`. |
| Unit | `CacheKeyBuilder.build` | Pure determinism: same inputs → same digest; differs on `temperature`; differs on `messages_hash`; stable across dict re-ordering (sort_keys). |
| Unit | `FallbackErrorClassifier.classify` | Use REAL Agno exceptions (`ModelRateLimitError(...)`, `ContextWindowExceededError(...)`, generic `ModelProviderError`) for the 3 isinstance branches + a plain `RuntimeError` for the else branch. Mock subclass for the `ModelProviderError.classify` delegation path. |
| Integration | none | No network in slice #4 — all components are pure. Integration wiring lands in SPEC_09. |
| E2E | none | Runtime path is SPEC_09 territory. |

### TDD Discipline (strict)

Per slice #4's strict TDD mode, each module follows RED-GREEN-REFACTOR:

1. **RED** — write one failing test per behavior (e.g. empty chain, truncation,
   alias rejection). Run `python -m pytest tests/unit/models/test_<mod>.py` →
   fails (module or symbol missing).
2. **GREEN** — implement the minimum to pass (the literal code above).
3. **REFACTOR** — extract constants (`_PREFIX`, `ErrorCategory`), tighten
   docstrings; tests stay green.

Test fixtures mirror the shipped patterns in
`tests/unit/di/test_provider_factory.py` (stub factories, `@dataclass` doubles)
and `tests/unit/models/test_model_spec.py` (pure Pydantic, `@pytest.mark.unit`).

## Verification (pre-apply assumptions to confirm)

The exploration (obs #1936) verified the Agno exception names by reading
`agno/exceptions.py` source directly. These were NOT re-verifiable at design
time (no venv/agno install in this sandbox). At apply time, the first test in
`test_fallback_classifier.py` MUST confirm:

```bash
python -c "from agno.exceptions import ModelRateLimitError, ContextWindowExceededError, ModelProviderError; print('ok')"
python -c "from agno.exceptions import ModelProviderError; print(hasattr(ModelProviderError, 'classify'))"
```

If either fails, STOP apply and update the import contract before proceeding
(risk R1/R5). The `mypy` config already sets
`ignore_missing_imports = true` for `agno.*`, so type-checking will not block.

## Migration / Rollback

No migration required. The three modules are additive and standalone — no
existing module imports them until SPEC_09 lands. The only file touching an
existing surface is `models/__init__.py` (three re-exports added under the
`[tool.ruff.lint.per-file-ignores]` F401 exemption for `__init__.py`).

**Rollback**: `git revert` of the slice #4 commit/PR, or
`git switch -c revert/model-resilience-runtime` + delete the 3 new files +
revert the `models/__init__.py` diff. No schema change, no `AgentConfig.model`
change, no data migration. Specs `model-config-schema` and
`provider-factory-adapter` stay intact. Estimated rollback: under 5 minutes.

## Open Questions

- [ ] Confirm `ModelProviderError.classify` return type at apply time (design
      assumes it returns an exception instance; the classifier defensively
      `isinstance`-checks the result). If it returns a string/enum instead, the
      mapping branch needs a 1-line adjustment — covered by the R5 mitigation.
- [ ] Confirm whether `messages_hash` should include session id (SPEC_09
      decision) — slice #4 just passes the caller's hash through, so this is a
      caller concern, not a blocker here.
