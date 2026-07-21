"""Unit tests for build_fallback_chain (SPEC_14 slice #4 — DOMAIN).

RED-GREEN strict TDD. Tagged ``@pytest.mark.unit``. Uses a stub
``ProviderFactory`` (records the canonical provider it received and returns a
tagged dict — no network, no Agno class resolution) + the real
``parse_model_spec`` / ``ProviderResolver``.

Covers (Req 1, Req 2, Req 3, Req 8):
  - Golden chain: primary at index 0, fallback after.
  - No fallback config -> single-entry list (primary only).
  - Truncation at ``max_fallback_hops`` (Open Item #1 resolution).
  - ``{"alias": name}`` rejection -> ``NotImplementedError``.
  - str ref canonicalizes provider alias before factory.build.
  - dict ref ``{provider, id}`` expands without aliasing.
  - Invariant: no CircuitBreaker/RetryPolicy/call_with_fallback symbols in the
    three new modules (Req 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from yaml_agno.models.fallback_chain import build_fallback_chain
from yaml_agno.models.model_spec import (
    FallbackConfig,
    ModelExpandedSpec,
    ProviderResolver,
)

# ---------------------------------------------------------------------------
# Stub ProviderFactory — records the canonical provider and returns a tagged
# dict. Lets us assert which provider the factory received (alias resolution)
# without standing up Agno class resolution + secrets.
# ---------------------------------------------------------------------------


@dataclass
class _StubFactory:
    """Stand-in for ProviderFactory.build that records calls and tags output.

    Each ``build(spec)`` returns ``{"provider": spec.provider, "id": spec.id}``
    so tests can assert ordering and alias canonicalization by inspecting the
    tagged dicts. ``calls`` records every spec received, in order.
    """

    calls: list[ModelExpandedSpec] = field(default_factory=list)

    def build(self, spec: ModelExpandedSpec) -> dict[str, str]:
        """Mirror ProviderFactory.build's signature; return a tagged dict."""
        self.calls.append(spec)
        return {"provider": spec.provider, "id": spec.id}


def _factory() -> _StubFactory:
    return _StubFactory()


def _primary(
    fallback: FallbackConfig | None = None,
    *,
    provider: str = "anthropic",
    model_id: str = "claude-sonnet-4-5",
) -> ModelExpandedSpec:
    """Build a primary ModelExpandedSpec, optionally with a fallback config."""
    return ModelExpandedSpec(provider=provider, id=model_id, fallback=fallback)


# ---------------------------------------------------------------------------
# Req 1 — ordered chain, primary at index 0; no-fallback returns primary only
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_golden_chain_primary_first_then_fallback() -> None:
    """Golden: ``[primary, fallback]`` — primary at index 0.

    Spec scenario: cadena dorada — primario + un fallback.
    """
    factory = _factory()
    primary = _primary(
        FallbackConfig(fallback_models=["openai:gpt-4o"], max_fallback_hops=3)
    )
    chain = build_fallback_chain(primary, factory)
    assert len(chain) == 2
    assert chain[0] == {"provider": "anthropic", "id": "claude-sonnet-4-5"}
    assert chain[1] == {"provider": "openai_chat", "id": "gpt-4o"}


@pytest.mark.unit
def test_no_fallback_config_returns_single_entry_list() -> None:
    """When ``primary.fallback is None``, the chain is just ``[primary]``.

    Spec scenario: sin fallback devuelve sólo el primario.
    """
    factory = _factory()
    primary = _primary(fallback=None)
    chain = build_fallback_chain(primary, factory)
    assert len(chain) == 1
    assert chain[0] == {"provider": "anthropic", "id": "claude-sonnet-4-5"}
    # The factory was invoked exactly once (for the primary).
    assert len(factory.calls) == 1


# ---------------------------------------------------------------------------
# Req 1 (truncation) — Open Item #1 resolution: max_fallback_hops + 1 entries
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_truncation_at_max_fallback_hops_plus_one() -> None:
    """``max_fallback_hops=2`` with 4 fallbacks -> 3 entries (primary + 2 hops).

    Open Item #1 (tasks.md) CRITICAL CORRECTION: the field
    ``max_fallback_hops`` means "max number of FALLBACK hops" (hops AFTER the
    primary), NOT total chain length. So ``max_fallback_hops=2`` yields a chain
    of ``2 + 1 = 3`` entries: the primary plus up to 2 fallbacks. The design
    literal ``chain[:max_fallback_hops]`` is an OFF-BY-ONE BUG — the correct
    slice is ``chain[:max_fallback_hops + 1]``.

    Spec scenario: truncado a max_fallback_hops.
    """
    factory = _factory()
    primary = _primary(
        FallbackConfig(
            fallback_models=[
                "openai:gpt-4o",
                "google:gemini-2.5-pro",
                "mistral:mistral-large-latest",
                "deepseek:deepseek-chat",
            ],
            max_fallback_hops=2,
        )
    )
    chain = build_fallback_chain(primary, factory)
    # primary (index 0) + 2 fallback hops = 3 entries; the 3rd and 4th
    # fallbacks are discarded.
    assert len(chain) == 3
    assert chain[0] == {"provider": "anthropic", "id": "claude-sonnet-4-5"}
    assert chain[1] == {"provider": "openai_chat", "id": "gpt-4o"}
    assert chain[2] == {"provider": "google", "id": "gemini-2.5-pro"}


@pytest.mark.unit
def test_truncation_unchanged_when_fewer_fallbacks_than_hops() -> None:
    """Triangulation: when fallbacks <= max_fallback_hops, no truncation.

    With 1 fallback and ``max_fallback_hops=3``, the chain has 2 entries
    (primary + 1 fallback) — the hop budget is not padded.
    """
    factory = _factory()
    primary = _primary(
        FallbackConfig(fallback_models=["openai:gpt-4o"], max_fallback_hops=3)
    )
    chain = build_fallback_chain(primary, factory)
    assert len(chain) == 2


# ---------------------------------------------------------------------------
# Req 2 — str ref canonicalizes alias; dict ref expands without aliasing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_str_ref_canonicalizes_provider_alias_before_factory_build() -> None:
    """A ``"openai:gpt-4o"`` str ref is canonicalized to ``"openai_chat"``.

    Spec scenario: ref string se parsea y canonicaliza. The factory MUST receive
    a ModelExpandedSpec whose provider is the canonical id (alias resolved by
    ProviderResolver), not the raw alias the user wrote.
    """
    factory = _factory()
    primary = _primary(
        FallbackConfig(fallback_models=["openai:gpt-4o"], max_fallback_hops=3)
    )
    build_fallback_chain(primary, factory)
    # factory.calls[0] is the primary; calls[1] is the fallback spec.
    assert len(factory.calls) == 2
    assert factory.calls[1].provider == "openai_chat"
    assert factory.calls[1].id == "gpt-4o"


@pytest.mark.unit
def test_dict_ref_expands_without_aliasing() -> None:
    """A ``{"provider": "google", "id": "gemini-2.5-pro"}`` dict ref is parsed
    and forwarded with the provider unchanged (no alias applies to "google").

    Spec scenario: ref dict expandido se parsea sin alias.
    """
    factory = _factory()
    primary = _primary(
        FallbackConfig(
            fallback_models=[{"provider": "google", "id": "gemini-2.5-pro"}],
            max_fallback_hops=3,
        )
    )
    chain = build_fallback_chain(primary, factory)
    assert factory.calls[1].provider == "google"
    assert factory.calls[1].id == "gemini-2.5-pro"
    assert chain[1] == {"provider": "google", "id": "gemini-2.5-pro"}


# ---------------------------------------------------------------------------
# Req 3 — reject {"alias": name} with NotImplementedError
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_alias_ref_rejected_with_not_implemented_error() -> None:
    """A ``{"alias": "fb-openai"}`` ref raises ``NotImplementedError``.

    Spec scenario: alias-ref rechazado con NotImplementedError. The definitions
    registry (TASK_013) is unshipped, so resolving alias-by-name would require a
    half-built registry. A loud error points the user at the future work item.
    """
    factory = _factory()
    primary = _primary(
        FallbackConfig(fallback_models=[{"alias": "fb-openai"}], max_fallback_hops=3)
    )
    with pytest.raises(NotImplementedError, match="definitions registry"):
        build_fallback_chain(primary, factory)


# ---------------------------------------------------------------------------
# Injectable resolver (design contract — default ProviderResolver() when None)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_custom_resolver_is_used_when_injected() -> None:
    """An injected ``ProviderResolver`` overrides the default.

    Triangulation for the ``resolver`` kwarg: we inject a resolver whose alias
    map canonicalizes ``openai`` to ``openai_responses`` (instead of the default
    ``openai_chat``) and confirm the factory received the custom canonical id.
    """
    factory = _factory()
    primary = _primary(
        FallbackConfig(fallback_models=["openai:gpt-4o"], max_fallback_hops=3)
    )
    custom = ProviderResolver(aliases={"openai": "openai_responses"})
    build_fallback_chain(primary, factory, resolver=custom)
    assert factory.calls[1].provider == "openai_responses"


# ---------------------------------------------------------------------------
# Req 8 — invariant: no CircuitBreaker / RetryPolicy / call_with_fallback
# ---------------------------------------------------------------------------


_FORBIDDEN_SYMBOLS = (
    "CircuitBreaker",
    "call_with_fallback",
    "RetryPolicy",
    "compute_delay",
    "dispatch_fallback_callback",
    "probe_models_health",
)


@pytest.mark.unit
@pytest.mark.parametrize("module_name", ["fallback_chain", "cache_key", "fallback_classifier"])
@pytest.mark.parametrize("symbol", _FORBIDDEN_SYMBOLS)
def test_no_deferred_symbols_in_resilience_modules(module_name: str, symbol: str) -> None:
    """No deferred SPEC_05/SPEC_09 symbol appears in the three new modules.

    Spec scenario: no-circuit-breaker invariant (Req 8). The slice #4 DOMAIN
    layer must NOT introduce runtime/breaker/retry symbols — those are SPEC_05
    (RetryPolicy, step-level) and SPEC_09 (CircuitBreaker + runtime executor).

    We read the module source directly (not its namespace) so that even a
    comment or string mentioning the symbol is caught — the invariant is about
    the delivered source, not just importable names. NOTE: the spec labels the
    invariant's own forbidden words as "the spec references them" — but the
    invariant targets the PRODUCTION modules, not this test file, so this test
    is a valid guard over the delivered source.
    """
    import importlib
    from pathlib import Path

    module = importlib.import_module(f"yaml_agno.models.{module_name}")
    module_file = Path(module.__file__).resolve()
    source = module_file.read_text(encoding="utf-8")
    assert symbol not in source, (
        f"Forbidden symbol {symbol!r} found in {module_name}.py — "
        f"slice #4 must not introduce SPEC_05/SPEC_09 runtime components."
    )
