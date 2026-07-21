"""Unit tests for ``yaml_agno.models.model_spec`` — SPEC_14 slice #2.

Covers the 5 Pydantic schemas: ModelStringSpec (string override + format +
provider validation + alias acceptance), ModelExpandedSpec (generation params
ranges, Agno-native retry boundary, fallback nesting), FallbackConfig
(routing enums + scalars), the ModelSpec union (str + dict branches), and
ProviderResolver (alias canonicalization). Pure Pydantic, mock-free.

Tagged ``@pytest.mark.unit``. No network.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yaml_agno.models.model_spec import (
    FallbackConfig,
    ModelExpandedSpec,
    ModelSpec,
    ModelStringSpec,
    ProviderResolver,
    parse_model_spec,
)

# ---------------------------------------------------------------------------
# ModelStringSpec
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_model_string_spec_from_bare_string() -> None:
    """Golden: ``ModelStringSpec.model_validate('openai:gpt-4o')`` parses."""
    spec = ModelStringSpec.model_validate("openai:gpt-4o")
    assert spec.provider == "openai"
    assert spec.id == "gpt-4o"


@pytest.mark.unit
def test_model_string_spec_rejects_unknown_provider() -> None:
    """RED: a well-formed but unknown provider fails fast.

    The provider half must match the format regex (``[A-Za-z0-9_]+``) so the
    error is "Unknown provider", not "Invalid format". We use ``banana``
    (valid format, not in SUPPORTED_PROVIDERS).
    """
    with pytest.raises(ValueError, match="Unknown provider"):
        ModelStringSpec.model_validate("banana:gpt-4o")


@pytest.mark.unit
def test_model_string_spec_rejects_bad_format() -> None:
    """RED: a string without a ':' or with empty halves is invalid format."""
    with pytest.raises(ValueError, match="Invalid model string"):
        ModelStringSpec.model_validate("no-colon")
    with pytest.raises(ValueError, match="Invalid model string"):
        ModelStringSpec.model_validate("openai:")  # empty id half


@pytest.mark.unit
def test_model_string_spec_accepts_openai_alias_as_written() -> None:
    """``openai`` is a known alias key in SUPPORTED_PROVIDERS (slice 1), so it
    is accepted at parse time. Canonicalization is deferred to ProviderResolver."""
    spec = ModelStringSpec.model_validate("openai:gpt-4o")
    assert spec.provider == "openai"  # alias NOT expanded here


# ---------------------------------------------------------------------------
# ModelSpec union — the load-bearing override test (tasks risk)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_model_spec_union_resolves_from_string_and_dict() -> None:
    """``parse_model_spec`` dispatches by input type: str -> ModelStringSpec,
    dict -> ModelExpandedSpec.

    Pydantic V2 cannot auto-discriminate a bare ``str`` from a ``dict`` for the
    ``ModelSpec`` union (both satisfy the ``{provider, id}`` shape), so
    :func:`parse_model_spec` is the canonical entry point. If it breaks, the
    union is unusable.
    """
    from_str = parse_model_spec("openai:gpt-4o")
    from_dict = parse_model_spec({"provider": "openai", "id": "gpt-4o"})
    assert isinstance(from_str, ModelStringSpec)
    assert isinstance(from_dict, ModelExpandedSpec)


@pytest.mark.unit
def test_parse_model_spec_passthrough_already_parsed() -> None:
    """parse_model_spec returns an already-parsed spec unchanged."""
    spec = ModelStringSpec.model_validate("openai:gpt-4o")
    assert parse_model_spec(spec) is spec


@pytest.mark.unit
def test_parse_model_spec_rejects_unsupported_type() -> None:
    """parse_model_spec raises TypeError on an unsupported input type."""
    with pytest.raises(TypeError, match="Unsupported model spec input type"):
        parse_model_spec(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ModelExpandedSpec
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_model_expanded_spec_golden() -> None:
    """Golden: full expanded form with generation params + retry."""
    spec = ModelExpandedSpec(
        provider="anthropic",
        id="claude-3-5-sonnet",
        temperature=0.7,
        max_tokens=4096,
        cache_response=True,
        retries=3,
    )
    assert spec.provider == "anthropic"
    assert spec.temperature == 0.7
    assert spec.retries == 3


@pytest.mark.unit
def test_model_expanded_spec_rejects_temperature_out_of_range() -> None:
    """RED: temperature must be in [0.0, 2.0]."""
    with pytest.raises(ValidationError):
        ModelExpandedSpec(provider="anthropic", id="x", temperature=2.5)


@pytest.mark.unit
def test_model_expanded_spec_rejects_top_p_out_of_range() -> None:
    """RED: top_p must be in [0.0, 1.0]."""
    with pytest.raises(ValidationError):
        ModelExpandedSpec(provider="anthropic", id="x", top_p=1.5)


@pytest.mark.unit
def test_model_expanded_spec_rejects_retries_above_cap() -> None:
    """RED: retries must be <= 10 (Agno native cap mirrored)."""
    with pytest.raises(ValidationError):
        ModelExpandedSpec(provider="anthropic", id="x", retries=11)


@pytest.mark.unit
def test_model_expanded_spec_rejects_unknown_provider() -> None:
    """RED: provider must be in SUPPORTED_PROVIDERS (SSOT validator)."""
    with pytest.raises(ValidationError, match="Unknown provider"):
        ModelExpandedSpec(provider="banana", id="x")


@pytest.mark.unit
def test_model_expanded_spec_rejects_extra_field() -> None:
    """RED: extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        ModelExpandedSpec(provider="anthropic", id="x", not_a_field=True)


@pytest.mark.unit
def test_model_expanded_spec_retry_fields_are_agno_native_names() -> None:
    """Retry boundary (audit TOP 3 #2): only Agno-native retry fields exist.

    NO yaml-agno-only ``retry_delay`` / ``wait_on_rate_limit`` / ``retry_jitter``.
    """
    spec = ModelExpandedSpec(
        provider="openai",
        id="gpt-4o",
        retries=2,
        delay_between_retries=1.5,
        exponential_backoff=True,
        retry_with_guidance=True,
        retry_with_guidance_limit=1,
    )
    assert spec.retries == 2
    assert spec.delay_between_retries == 1.5
    # The forbidden fields are NOT in the model.
    forbidden = {"retry_delay", "wait_on_rate_limit", "retry_jitter"}
    assert not (forbidden & set(ModelExpandedSpec.model_fields))


# ---------------------------------------------------------------------------
# FallbackConfig
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fallback_config_golden() -> None:
    """Golden: fallback chain with routing enums."""
    cfg = FallbackConfig(
        fallback_models=["openai_responses:gpt-4o"],
        on_rate_limit="route_fallback",
        on_error="retry_then_fallback",
        max_fallback_hops=3,
    )
    assert cfg.fallback_models == ["openai_responses:gpt-4o"]
    assert cfg.on_rate_limit == "route_fallback"
    assert cfg.max_fallback_hops == 3
    assert cfg.propagate_session is True  # default


@pytest.mark.unit
def test_fallback_config_rejects_invalid_enum() -> None:
    """RED: routing strategy must be one of the Literal values."""
    with pytest.raises(ValidationError):
        FallbackConfig(fallback_models=["openai:gpt-4o"], on_rate_limit="banana")  # type: ignore[arg-type]


@pytest.mark.unit
def test_fallback_config_rejects_hops_below_one() -> None:
    """RED: max_fallback_hops must be >= 1."""
    with pytest.raises(ValidationError):
        FallbackConfig(fallback_models=["openai:gpt-4o"], max_fallback_hops=0)


@pytest.mark.unit
def test_fallback_config_rejects_empty_models() -> None:
    """RED: fallback_models must have at least one entry."""
    with pytest.raises(ValidationError):
        FallbackConfig(fallback_models=[])


@pytest.mark.unit
def test_model_expanded_spec_nests_fallback_config() -> None:
    """ModelExpandedSpec.fallback accepts a FallbackConfig (forward ref works)."""
    spec = ModelExpandedSpec(
        provider="openai",
        id="gpt-4o",
        fallback=FallbackConfig(fallback_models=["anthropic:claude-3-5-sonnet"]),
    )
    assert spec.fallback is not None
    assert spec.fallback.fallback_models == ["anthropic:claude-3-5-sonnet"]


# ---------------------------------------------------------------------------
# ProviderResolver
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_provider_resolver_canonicalizes_openai_alias() -> None:
    """``openai`` -> ``openai_chat`` on a ModelStringSpec."""
    spec = ModelStringSpec.model_validate("openai:gpt-4o")
    resolved = ProviderResolver().resolve(spec)
    assert resolved.provider == "openai_chat"


@pytest.mark.unit
def test_provider_resolver_leaves_canonical_unchanged() -> None:
    """A canonical provider (no alias) is returned unchanged."""
    spec = ModelExpandedSpec(provider="anthropic", id="claude-3-5-sonnet")
    resolved = ProviderResolver().resolve(spec)
    assert resolved.provider == "anthropic"
    assert resolved is spec  # unchanged, same instance


@pytest.mark.unit
def test_provider_resolver_rejects_unsupported_alias_target() -> None:
    """A stale alias pointing outside SUPPORTED_PROVIDERS raises."""
    spec = ModelStringSpec.model_validate("openai:gpt-4o")
    resolver = ProviderResolver(aliases={"openai": "banana"})  # stale alias
    with pytest.raises(ValueError, match="not in SUPPORTED_PROVIDERS"):
        resolver.resolve(spec)


@pytest.mark.unit
def test_provider_resolver_rejects_unsupported_type() -> None:
    """resolve() raises TypeError on an unsupported spec type."""
    with pytest.raises(TypeError, match="Unsupported spec type"):
        ProviderResolver().resolve("not-a-spec")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AgentConfig regression guard (slice 2 MUST NOT touch AgentConfig.model)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_agent_config_model_still_str_not_union() -> None:
    """Invariant (ADR A1): AgentConfig.model stays the str alias in slice #2.

    The ModelSpec union is NOT wired into AgentConfig in this slice; it ships
    standalone. This guards against an accidental widening that would break
    ~14 existing tests + the factory passthru. We assert the field annotation
    is NOT the new union (it remains the ModelReference str alias).
    """
    from yaml_agno.models.config.agent_config import AgentConfig

    field = AgentConfig.model_fields["model"]
    # The annotation must remain the str alias (ModelReference), NOT the union.
    assert field.annotation is not ModelSpec
    assert field.annotation is not None
    # ModelReference is a PEP 695 alias of str; confirm via repr rather than `is str`.
    assert "str" in repr(field.annotation).lower() or field.annotation.__name__ in {"ModelReference", "str"}
