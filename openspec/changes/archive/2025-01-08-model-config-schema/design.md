---
change: model-config-schema
slice: SPEC_14 #2
artifact: design
status: ready-for-tasks
loc_budget: ~450
depends_on:
  - src/yaml_agno/di/registries.py          # PROVIDER_ALIASES (shipped slice 1)
  - src/yaml_agno/di/provider_capabilities.py # SUPPORTED_PROVIDERS (shipped slice 1)
consumed_by:
  - src/yaml_agno/models/config/agent_config.py # future slice (union swap)
  - src/yaml_agno/factories/agent_factory.py     # future slice (cfg.model passthru)
---

# Design: model-config-schema (SPEC_14 slice #2)

## Technical Approach

Add the Pydantic V2 schema layer that turns a YAML model reference into a
validated, provider-normalized, Agno-ready spec — WITHOUT touching the shipped
`AgentConfig.model: str` field. All new code lives in ONE new file
`src/yaml_agno/models/model_spec.py`, consuming slice-1 registries
(`SUPPORTED_PROVIDERS`, `PROVIDER_ALIASES`) as the single source of truth.

The slice ships five public types:
`ModelStringSpec`, `ModelExpandedSpec`, `FallbackConfig`, `ProviderResolver`,
and the `ModelSpec` union alias. They are pure data + a pure resolver; no
Agno instantiation, no network, no DI injection. Runtime fallback execution
(`build_fallback_chain`, `call_with_fallback`, Circuit Breaker) is deferred to
slice #4 per the archived proposal. `FallbackConfig` ships here only because
`ModelExpandedSpec.fallback` needs a concrete type (avoids forward refs).

## Architecture Decisions

### A1 — SEPARATE new file, do NOT BREAK `AgentConfig`

| Option | Tradeoff | Decision |
|---|---|---|
| BREAK: swap `AgentConfig.model: str` → `ModelSpec` union now | Coordinated evolution of `AgentConfig` (SPEC_02) + `AgentFactory.build` (SPEC_01) + ~14 tests asserting `cfg.model == "openai:gpt-4o"` | rejected |
| SEPARATE: ship schemas in `model_spec.py`, leave `AgentConfig.model: str` untouched | Zero blast radius; union swap is a later slice with its own test churn | **chosen** |

**Rationale**: `AgentConfig` is shipped (SPEC_02) and `AgentFactory.build`
does `model=cfg.model` verbatim into `agno.Agent(model=...)` (agent_factory.py:82),
relying on Agno's native string parsing. Changing the type mid-chain forces a
coordinated three-file evolution and ~14 test edits before any of slice #2's
value lands. The SEPARATE approach lets the schema layer be built, tested, and
proven in isolation; the union swap becomes a focused migration slice with its
own review.

### A2 — `field_validator` against `SUPPORTED_PROVIDERS`, NOT a hardcoded `Literal`

| Option | Tradeoff | Decision |
|---|---|---|
| `provider: Literal["anthropic", "openai", ...]` (26 entries, SPEC_14 §3.4:221-228) | Static typing, but second SSOT that drifts when providers added | rejected |
| `provider: str` + `@field_validator` checking membership in `SUPPORTED_PROVIDERS` frozenset | Runtime-only validation, one SSOT (PROVIDER_REGISTRY → SUPPORTED_PROVIDERS) | **chosen** |

**Rationale**: Slice 1 already derives `SUPPORTED_PROVIDERS: Final[frozenset[str]]`
from `PROVIDER_REGISTRY.keys()` (provider_capabilities.py:284). Hardcoding a
26-entry `Literal` recreates a second enumeration that silently drifts the next
time a provider is added. The `field_validator` keeps one source of truth; the
error message names the offending provider and points at the catalog.

### A3 — Retry fields map 1:1 to Agno native `Model` fields

**Choice**: yaml-agno user-facing retry names forward directly to Agno base
`Model` constructor params: `retries`, `delay_between_retries`,
`exponential_backoff`, `retry_with_guidance`, `retry_with_guidance_limit`.

**Rejected**: introducing `retry_delay` / `wait_on_rate_limit` / `retry_jitter`
(yaml-agno-only names with no Agno target).

**Rationale**: This slice is an audit boundary — every field we expose MUST have
a native Agno sink (verified SPEC_05:210 + SPEC_14 iter-4 notes 551-554, 824-825).
Inventing fields without a sink produces silent no-ops the moment the factory
hands the dict to Agno. `retry_delay` → use `delay_between_retries`;
`wait_on_rate_limit` and `retry_jitter` are out of scope entirely.

### A4 — `ModelSpec` union discrimination by Python type, no discriminator field

**Choice**: `ModelSpec = ModelStringSpec | ModelExpandedSpec`. Pydantic V2
discriminates by input shape: `str` → `ModelStringSpec`, `dict` → `ModelExpandedSpec`.

**Rejected**: adding a `kind: Literal["string","expanded"]` discriminator field.

**Rationale**: The two shapes are already unambiguous at the YAML layer — a
model is either `"openai:gpt-4o"` (scalar) or `{provider:..., id:...}` (mapping).
A synthetic discriminator adds user-facing noise to every YAML file for zero
ambiguity resolution. Pydantic V2 handles `str | BaseModel` unions natively in
left-to-right order.

### A5 — `ProviderResolver` is a plain class, not a Pydantic model

**Choice**: `ProviderResolver` is a stateless class with a `resolve()` method.

**Rejected**: making it a `BaseModel` with the spec as a field and a
`model_validator`.

**Rationale**: A resolver is behavior, not data. Pydantic `BaseModel` is for
validated payloads. Keeping `ProviderResolver` as a plain class also keeps the
schema models pure data (a model_validator that calls alias logic would couple
data and resolution and complicate unit testing).

### A6 — `FallbackConfig` ships schema only; runtime stays in slice #4

**Choice**: `FallbackConfig` defines `fallback_models: list[str | dict]` with a
length cap and a `strategy` field. No `build_fallback_chain`, no Circuit Breaker.

**Rationale**: archived proposal.md:92-93 puts all fallback runtime in slice #4.
But `ModelExpandedSpec.fallback: FallbackConfig | None` needs a concrete class
to avoid a Pydantic forward reference. Definition order is `FallbackConfig`
BEFORE `ModelExpandedSpec`.

## Data Flow

```
YAML (agent.model: "openai:gpt-4o"  OR  {provider: openai, id: gpt-4o, ...})
        │
        ▼
   ModelSpec  (str | dict union, validated by Pydantic)
        │             format check: "provider:id"
        │             provider check: in SUPPORTED_PROVIDERS (frozenset)
        ▼
   ProviderResolver.resolve(model_spec)
        │   1. apply PROVIDER_ALIASES  ("openai" -> "openai_chat")
        │   2. confirm canonical id in SUPPORTED_PROVIDERS
        │   3. return ModelStringSpec | ModelExpandedSpec (canonical provider)
        ▼
   (future slice) AgentFactory → agno.Model(...)
```

This slice owns the boxed region only. Everything below the second box is a
later slice.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/models/model_spec.py` | Create | 5 public types: `ModelStringSpec`, `ModelExpandedSpec`, `FallbackConfig`, `ProviderResolver`, `ModelSpec` union. ~400 LOC pure Pydantic V2 + Google docstrings. |
| `src/yaml_agno/models/__init__.py` | Modify | Re-export the 5 new symbols so `from yaml_agno.models import ModelSpec` works (matches existing AgentConfig/TeamConfig re-export convention). |
| `openspec/changes/model-config-schema/design.md` | Create | This document. |

File count: **3** (1 create source, 1 modify `__init__`, 1 design doc). No tests
in this artifact — tests are specified in the Testing Strategy section and will
be created in the `sdd-tasks` / `sdd-apply` phase.

## Interfaces / Contracts — LITERAL Pydantic V2 code

The block below is the exact source to be written to
`src/yaml_agno/models/model_spec.py`. It compiles against the shipped slice-1
imports and matches `agent_config.py` style
(`ConfigDict(extra="forbid")`, `field_validator`, Google docstrings, type hints,
`@ai-directive`).

```python
"""Model specification schemas + provider resolver (SPEC_14 slice #2).

Pure-data Pydantic V2 schemas that turn a YAML model reference into a validated,
provider-normalized, Agno-ready spec. Consumes the slice-1 provider catalog
(``SUPPORTED_PROVIDERS``, ``PROVIDER_ALIASES``) as the single source of truth.

This module does NOT instantiate Agno models and does NOT touch
``AgentConfig.model`` (which stays ``str``). The union swap
(``AgentConfig.model: ModelSpec``) is a later, focused migration slice.

@ai-directive: do NOT import Agno here. Schemas only + a pure resolver.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from yaml_agno.di.provider_capabilities import SUPPORTED_PROVIDERS
from yaml_agno.di.registries import PROVIDER_ALIASES

# Regex shared by ModelStringSpec format validation. "provider:id" with both
# halves non-empty; ":" alone is invalid (AgentConfig.validate_model_format
# invariants mirrored here for slice-2 standalone use).
_PROVIDER_ID_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_]+:[A-Za-z0-9_.\-]+$")


class ModelStringSpec(BaseModel):
    """Model reference in compact string form ``"provider:id"``.

    The scalar variant of the ``ModelSpec`` union. Provider half is validated
    against ``SUPPORTED_PROVIDERS`` (frozenset derived from PROVIDER_REGISTRY,
    slice 1) so an unknown provider fails fast at parse time. Alias expansion
    (``"openai"`` -> ``"openai_chat"``) is performed later by
    :class:`ProviderResolver`, NOT by this validator — the spec keeps the
    user-written provider so error messages reference what the user typed.

    Attributes:
        provider: Provider half (e.g. ``"openai"``, ``"anthropic"``). Validated
            against ``SUPPORTED_PROVIDERS``.
        id: Model identifier (e.g. ``"gpt-4o"``).

    Example:
        >>> spec = ModelStringSpec.model_validate("openai:gpt-4o")
        >>> spec.provider, spec.id
        ('openai', 'gpt-4o')
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1, description="Provider id; must be in SUPPORTED_PROVIDERS.")
    id: str = Field(..., min_length=1, description="Model identifier (e.g. 'gpt-4o').")

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):  # pragma: no cover - schema hook
        # Allows ``ModelStringSpec`` to be validated from a bare JSON string.
        return schema

    # Enable ``ModelStringSpec.model_validate("openai:gpt-4o")``: Pydantic V2
    # otherwise expects a dict. We accept a bare string by parsing it here.
    @classmethod
    def model_validate(cls, obj, *args, **kwargs):  # type: ignore[override]
        """Accept either a ``"provider:id"`` string or a dict payload."""
        if isinstance(obj, str):
            return cls._from_string(obj)
        return super().model_validate(obj, *args, **kwargs)

    @classmethod
    def _from_string(cls, value: str) -> "ModelStringSpec":
        """Parse and validate a ``"provider:id"`` string.

        Args:
            value: Bare model string, e.g. ``"openai:gpt-4o"``.

        Returns:
            A validated :class:`ModelStringSpec`.

        Raises:
            ValueError: If the format is wrong or the provider is unknown.
        """
        if not _PROVIDER_ID_RE.match(value):
            raise ValueError(
                f"Invalid model string: {value!r}. Expected 'provider:id' "
                f"(e.g. 'openai:gpt-4o')."
            )
        provider, _, model_id = value.partition(":")
        # NOTE: alias resolution is deferred to ProviderResolver; here we only
        # confirm the provider is a known key or alias target.
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unknown provider: {provider!r}. Supported providers: "
                f"{sorted(SUPPORTED_PROVIDERS)}."
            )
        return cls(provider=provider, id=model_id)


class FallbackConfig(BaseModel):
    """Declarative fallback chain for a model.

    Schema only in this slice. Runtime ``build_fallback_chain`` /
    ``call_with_fallback`` and Circuit Breaker integration ship in slice #4.
    Listed here as a concrete type so :class:`ModelExpandedSpec.fallback` does
    not need a forward reference.

    Attributes:
        fallback_models: Ordered list of fallback model references. Each entry
            is a ``"provider:id"`` string OR a provider:id mapping (the same
            shapes accepted by :data:`ModelSpec`). The first entry is tried
            first after the primary model.
        on_rate_limit / on_context_overflow / on_error: Per-error-class routing
            strategy (Literal ``retry_only | route_fallback |
            retry_then_fallback | fail``). Reserved for slice #4 runtime — the
            value is validated here, not acted on.
        fallback_callback: Optional dotted callable ref invoked on fallback
            (resolved by slice #3 ProviderFactory).
        max_fallback_hops: Max sequential fallback attempts (>= 1, default 3).
        propagate_session: Whether the session carries across fallback hops
            (default True).

    Example:
        >>> FallbackConfig(fallback_models=["anthropic:claude-3-5-sonnet"])
    """

    model_config = ConfigDict(extra="forbid")

    fallback_models: list[Union[str, dict[str, Any]]] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Ordered fallback model references (str 'provider:id' or dict).",
    )
    on_rate_limit: Literal["retry_only", "route_fallback", "retry_then_fallback", "fail"] = Field(
        "route_fallback",
        description="Routing strategy on rate-limit errors. Reserved for slice #4.",
    )
    on_context_overflow: Literal["retry_only", "route_fallback", "retry_then_fallback", "fail"] = Field(
        "route_fallback",
        description="Routing strategy on context-overflow errors. Reserved for slice #4.",
    )
    on_error: Literal["retry_only", "route_fallback", "retry_then_fallback", "fail"] = Field(
        "retry_then_fallback",
        description="Routing strategy on generic errors. Reserved for slice #4.",
    )
    fallback_callback: str | None = Field(
        None,
        description="Optional dotted callable ref invoked on fallback (resolved slice #3).",
    )
    max_fallback_hops: int = Field(3, ge=1, description="Max sequential fallback attempts (>= 1).")
    propagate_session: bool = Field(True, description="Whether the session carries across fallback hops.")


class ModelExpandedSpec(BaseModel):
    """Model reference in expanded mapping form.

    The dict variant of the ``ModelSpec`` union. Mirrors the fields the Agno
    base ``Model`` constructor accepts (verified SPEC_05:210 + SPEC_14 iter-4
    notes 551-554, 824-825). Retry fields map 1:1 to Agno native names; no
    yaml-agno-only retry names are exposed (see ADR A3).

    Attributes:
        provider: Provider id; validated against ``SUPPORTED_PROVIDERS``.
        id: Model identifier (e.g. ``"gpt-4o"``).
        name: Optional display name forwarded to Agno ``Model.name``.
        model_type: Optional Agno model type tag.
        supports_native_structured_outputs: Agno base flag.
        supports_json_schema_outputs: Agno base flag.
        cache_response: Enable Agno prompt caching (Agno base ``cache_response``).
        cache_ttl: Cache time-to-live in seconds (Agno ``cache_ttl``).
        cache_dir: Optional cache directory (Agno ``cache_dir``).
        retries: Number of retries on transient failure (Agno ``retries``).
        delay_between_retries: Seconds between retries (Agno
            ``delay_between_retries``). NOT ``retry_delay``.
        exponential_backoff: Use exponential backoff (Agno
            ``exponential_backoff``).
        retry_with_guidance: Retry with guidance prompt (Agno
            ``retry_with_guidance``).
        retry_with_guidance_limit: Max guidance retries (Agno
            ``retry_with_guidance_limit``).
        fallback: Optional :class:`FallbackConfig`. Schema only this slice.

    Example:
        >>> ModelExpandedSpec(provider="openai", id="gpt-4o", retries=3)
    """

    model_config = ConfigDict(extra="forbid")

    # --- Identity (2 required fields) ---
    provider: str = Field(..., min_length=1, description="Provider id; must be in SUPPORTED_PROVIDERS.")
    id: str = Field(..., min_length=1, description="Model identifier (e.g. 'gpt-4o').")

    # --- Agno base Model passthrough (optional, 3 fields) ---
    name: str | None = Field(None, description="Display name forwarded to Agno Model.name.")
    model_type: str | None = Field(None, description="Agno model_type tag.")

    # --- Structured outputs (2 fields) ---
    supports_native_structured_outputs: bool | None = Field(
        None, description="Agno base flag for native structured outputs."
    )
    supports_json_schema_outputs: bool | None = Field(
        None, description="Agno base flag for JSON-schema outputs."
    )

    # --- Generation params (SPEC_14 §4.1; provider-specific, forwarded as kwargs) ---
    temperature: float | None = Field(None, ge=0.0, le=2.0, description="Sampling temperature (0.0-2.0).")
    max_tokens: int | None = Field(None, ge=1, description="Max tokens to generate (>= 1).")
    top_p: float | None = Field(None, ge=0.0, le=1.0, description="Nucleus sampling probability (0.0-1.0).")
    top_k: int | None = Field(None, ge=0, description="Top-k sampling (>= 0).")
    stop_sequences: list[str] | None = Field(None, description="Stop sequences.")
    seed: int | None = Field(None, description="Deterministic sampling seed.")

    # --- Reasoning (provider-specific; SPEC_14 §3.4) ---
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = Field(
        None, description="Reasoning effort level (provider-specific)."
    )
    thinking: bool | None = Field(None, description="Enable extended thinking (provider-specific).")

    # --- Caching (3 fields) ---
    cache_response: bool | None = Field(None, description="Enable Agno prompt caching.")
    cache_ttl: int | None = Field(None, ge=0, description="Cache TTL in seconds.")
    cache_dir: str | None = Field(None, description="Optional cache directory.")

    # --- Retry (Agno native names; ADR A3) ---
    retries: int | None = Field(None, ge=0, description="Number of retries (Agno retries).")
    delay_between_retries: float | None = Field(
        None, ge=0.0, description="Seconds between retries (Agno delay_between_retries)."
    )
    exponential_backoff: bool | None = Field(
        None, description="Use exponential backoff (Agno exponential_backoff)."
    )
    retry_with_guidance: bool | None = Field(
        None, description="Retry with guidance prompt (Agno retry_with_guidance)."
    )
    retry_with_guidance_limit: int | None = Field(
        None, ge=0, description="Max guidance retries (Agno retry_with_guidance_limit)."
    )

    # --- Fallback (schema only; runtime slice #4) ---
    fallback: FallbackConfig | None = Field(
        None, description="Fallback chain. Schema only; runtime in slice #4."
    )

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        """Confirm ``provider`` is a known key in ``SUPPORTED_PROVIDERS``.

        Alias expansion (``"openai"`` -> ``"openai_chat"``) is deferred to
        :class:`ProviderResolver` so the spec retains what the user wrote.
        """
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unknown provider: {v!r}. Supported providers: "
                f"{sorted(SUPPORTED_PROVIDERS)}."
            )
        return v


# Union exported to consumers (future AgentConfig.model swap). Pydantic V2
# discriminates by input shape: str -> ModelStringSpec, dict -> ModelExpandedSpec.
ModelSpec = Union[ModelStringSpec, ModelExpandedSpec]


class ProviderResolver:
    """Normalize a :data:`ModelSpec` by applying provider aliases.

    Stateless resolver. Applies ``PROVIDER_ALIASES`` (slice 1) to the provider
    half of a :class:`ModelStringSpec` or :class:`ModelExpandedSpec`, then
    confirms the canonical id is in ``SUPPORTED_PROVIDERS``. Does NOT import
    Agno or instantiate models — that is the factory's job.

    Aliases handled:
        - ``"openai"`` -> ``"openai_chat"`` (legacy -> canonical SPEC_14).

    Attributes:
        aliases: Mapping applied to the provider half. Defaults to the slice-1
            ``PROVIDER_ALIASES`` constant; injectable for testing.

    Example:
        >>> spec = ModelStringSpec.model_validate("openai:gpt-4o")
        >>> ProviderResolver().resolve(spec).provider
        'openai_chat'
    """

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        """Initialize the resolver.

        Args:
            aliases: Optional override for ``PROVIDER_ALIASES``. Mainly for
                unit tests; production callers leave this ``None``.
        """
        self.aliases = aliases if aliases is not None else dict(PROVIDER_ALIASES)

    def resolve(self, spec: ModelSpec) -> ModelSpec:
        """Return a copy of ``spec`` with its provider canonicalized.

        Args:
            spec: A :class:`ModelStringSpec` or :class:`ModelExpandedSpec`.

        Returns:
            A new spec of the same type with ``provider`` set to the canonical
            id (alias applied if one existed). If the provider was already
            canonical, the input is returned unchanged.

        Raises:
            ValueError: If the canonicalized provider is not in
                ``SUPPORTED_PROVIDERS`` (indicates a stale alias map).
        """
        if isinstance(spec, ModelStringSpec):
            canonical = self._canonical_provider(spec.provider)
            if canonical == spec.provider:
                return spec
            return spec.model_copy(update={"provider": canonical})
        if isinstance(spec, ModelExpandedSpec):
            canonical = self._canonical_provider(spec.provider)
            if canonical == spec.provider:
                return spec
            return spec.model_copy(update={"provider": canonical})
        # Defensive: ModelSpec is a closed union, but guard anyway.
        raise TypeError(f"Unsupported spec type for resolution: {type(spec).__name__}")

    def _canonical_provider(self, provider: str) -> str:
        """Apply the alias map once and confirm membership.

        Args:
            provider: Provider half as written by the user.

        Returns:
            Canonical provider id.

        Raises:
            ValueError: If the resolved id is not in ``SUPPORTED_PROVIDERS``.
        """
        canonical = self.aliases.get(provider, provider)
        if canonical not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Resolved provider {canonical!r} (from {provider!r}) is not in "
                f"SUPPORTED_PROVIDERS. Check PROVIDER_ALIASES / PROVIDER_REGISTRY."
            )
        return canonical


__all__ = [
    "FallbackConfig",
    "ModelExpandedSpec",
    "ModelSpec",
    "ModelStringSpec",
    "ProviderResolver",
]
```

### `src/yaml_agno/models/__init__.py` — modification (diff)

Append to the existing import block and `__all__`:

```python
# added imports
from yaml_agno.models.model_spec import (
    FallbackConfig,
    ModelExpandedSpec,
    ModelSpec,
    ModelStringSpec,
    ProviderResolver,
)

# __all__ gains 5 entries (alphabetical, matching existing convention):
#   "FallbackConfig", "ModelExpandedSpec", "ModelSpec",
#   "ModelStringSpec", "ProviderResolver"
```

The public-API docstring at the top of `__init__.py` is extended with one line:

```python
#   from yaml_agno.models import ModelSpec, ModelStringSpec, ModelExpandedSpec
#   from yaml_agno.models import FallbackConfig, ProviderResolver
```

## Testing Strategy

All tests are pure-Pydantic — no mocks, no Agno import, no network. Test file
target: `tests/unit/models/test_model_spec.py` (created in `sdd-tasks`).

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `ModelStringSpec` accepts `"openai:gpt-4o"`, splits provider/id | `model_validate("openai:gpt-4o")` → assert fields |
| Unit | `ModelStringSpec` rejects bad format (`"gpt-4o"`, `":gpt"`, `"openai:"`) | `pytest.raises(ValidationError)` |
| Unit | `ModelStringSpec` rejects unknown provider (`"nope:x"`) | `pytest.raises(ValidationError)`; assert message names provider |
| Unit | `ModelExpandedSpec` accepts minimal `{provider, id}` and full field set | Construct + assert passthrough |
| Unit | `ModelExpandedSpec` rejects unknown provider | `pytest.raises(ValidationError)` |
| Unit | `ModelExpandedSpec.extra="forbid"` rejects unknown key (`temperature` is fine, `bogus` is not — note: `temperature` is NOT modelled here, so it must be rejected) | `pytest.raises(ValidationError)` on `{"provider":"openai","id":"x","bogus":1}` |
| Unit | `ModelExpandedSpec.fallback` accepts a `FallbackConfig` and rejects empty `fallback_models` | Construct nested; `min_length=1` enforcement |
| Unit | `FallbackConfig.strategy` validator rejects `"weird"` | `pytest.raises(ValidationError)` |
| Unit | `FallbackConfig` accepts mixed `["anthropic:claude", {"provider":"groq","id":"x"}]` | Assert length preserved (no deep validation this slice) |
| Unit | `ProviderResolver.resolve` maps `"openai"` → `"openai_chat"` for string spec | Assert `.provider == "openai_chat"` |
| Unit | `ProviderResolver.resolve` maps `"openai"` → `"openai_chat"` for expanded spec | Same, on `ModelExpandedSpec` |
| Unit | `ProviderResolver.resolve` no-op when provider already canonical (`"anthropic"`) | Assert identity (`is` or equal unchanged) |
| Unit | `ProviderResolver` injectable aliases via ctor | Pass custom `{"foo":"bar"}`, assert applied |
| Unit | `ProviderResolver.resolve` raises `TypeError` on foreign type | `pytest.raises(TypeError)` |

### TDD Approach (strict mode active)

Strict TDD mode is enabled for this project. The apply phase MUST:

1. Write the failing test file FIRST (`tests/unit/models/test_model_spec.py`)
   covering every row above.
2. Run the suite → confirm red.
3. Implement `src/yaml_agno/models/model_spec.py` exactly as in the Contracts
   block above.
4. Run the suite → confirm green.
5. Refactor only if needed; re-run.

No Standard Mode fallback. Test runner: project default (`pytest`).

## Verification

- `python -c "from yaml_agno.models import ModelSpec, ProviderResolver"` succeeds.
- `pytest tests/unit/models/test_model_spec.py` is green.
- `mypy src/yaml_agno/models/model_spec.py` (if configured) passes.
- The shipped `agent_config.py`, `test_agent_config.py`, and
  `test_agent_factory.py` remain UNCHANGED and green — proving zero blast
  radius (ADR A1).
- `models/__init__.py` re-exports resolve without circular import (the new
  module imports only from `yaml_agno.di.*`, never from `yaml_agno.models.*`).

## Rollback

Single-file rollback: delete `src/yaml_agno/models/model_spec.py` and revert
the 5-line addition to `src/yaml_agno/models/__init__.py`. No other shipped
file is touched, so no coordinated rollback is required. Because
`AgentConfig.model` stays `str` (ADR A1), reverting this slice leaves the
system in the exact pre-slice state — no consumer depended on the new schemas.

## Open Questions

- None blocking. The union swap (`AgentConfig.model: ModelSpec`) and factory
  integration are explicitly deferred and tracked as a future slice.
