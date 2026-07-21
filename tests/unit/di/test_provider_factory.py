"""Unit tests for ProviderFactory (SPEC_14 slice #3).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Uses InMemoryDependencyAdapter
(core-cenf double) + @dataclass stubs for Agno Model subclasses so
dataclasses.fields() introspection works the same as on real Agno Models.

Covers:
  - api_key resolved from injected SecretResolver (no os.environ).
  - Local providers (api_key_env=None) skip the SecretResolver entirely.
  - _compose_kwargs forwards temperature to a class that declares it.
  - _compose_kwargs drops top_k (and thinking) on a class that lacks them.
  - Unknown provider raises KeyError.
  - Factory delegates to resolver.resolve_class (no importlib duplication).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from core_infrastructure.dependency import InMemoryDependencyAdapter

import yaml_agno
from yaml_agno.di.agno_resolver import AgnoResolver
from yaml_agno.di.provider_capabilities import PROVIDER_REGISTRY
from yaml_agno.di.provider_factory import ProviderFactory
from yaml_agno.models.model_spec import ModelExpandedSpec

# ---------------------------------------------------------------------------
# @dataclass stubs mirroring the real Agno Model surface — these let
# dataclasses.fields() return the same kind of field-name set the real
# OpenAIChat / Ollama expose. The factory's _compose_kwargs filters against
# this set, so the stubs must match the real divergence (OpenAIChat has no
# top_k; Ollama is local, api_key_env=None).
# ---------------------------------------------------------------------------


@dataclass
class StubOpenAIChat:
    """Stub for agno.models.openai.OpenAIChat — has temperature, NO top_k/thinking."""

    id: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    seed: int | None = None
    retries: int | None = None
    reasoning_effort: str | None = None
    api_key: str | None = None
    stop: list[str] | None = field(default_factory=list)


@dataclass
class StubOllama:
    """Stub for agno.models.ollama.Ollama — local provider, accepts temperature."""

    id: str = ""
    temperature: float | None = None
    top_k: int | None = None


# Seed mapping: (module_path, class_name) -> stub class. Uses the REAL
# PROVIDER_REGISTRY entries so the factory's lookup hits a seeded key.
_MAPPING: dict[tuple[str, str], type] = {
    (
        PROVIDER_REGISTRY["openai"].module_path,
        PROVIDER_REGISTRY["openai"].class_name,
    ): StubOpenAIChat,
    (
        PROVIDER_REGISTRY["ollama"].module_path,
        PROVIDER_REGISTRY["ollama"].class_name,
    ): StubOllama,
}


def _build_factory(
    secret_resolver: Callable[[str], str | None] = lambda env: None,
) -> ProviderFactory:
    """Build a ProviderFactory backed by the in-memory adapter + stubs."""
    adapter = InMemoryDependencyAdapter(mapping=_MAPPING)
    resolver = AgnoResolver(adapter)
    return ProviderFactory(resolver, secret_resolver)


# ---------------------------------------------------------------------------
# api_key resolution scenarios
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_injects_api_key_when_entry_has_env() -> None:
    """Cloud provider (openai) gets api_key from the injected SecretResolver.

    The factory MUST NOT touch os.environ — the SecretResolver is the only
    secret-access path. We assert the constructed instance received the key.
    """
    factory = _build_factory(secret_resolver=lambda env: "sk-test")
    spec = ModelExpandedSpec(provider="openai", id="gpt-4o")
    result = factory.build(spec)
    assert isinstance(result, StubOpenAIChat)
    assert result.api_key == "sk-test"


@pytest.mark.unit
def test_build_local_provider_skips_secret_resolver() -> None:
    """Local provider (ollama, api_key_env=None) MUST NOT consult the resolver.

    We inject a resolver that raises AssertionError if called — proving the
    factory never reaches it for a local provider.
    """

    def _explode(env: str) -> str | None:
        raise AssertionError(f"SecretResolver must not be called for local provider, got env={env!r}")

    factory = _build_factory(secret_resolver=_explode)
    spec = ModelExpandedSpec(provider="ollama", id="llama3")
    result = factory.build(spec)
    assert isinstance(result, StubOllama)
    # No api_key kwarg was forwarded — StubOllama does not declare it.
    assert not hasattr(result, "api_key") or getattr(result, "api_key", None) is None


# ---------------------------------------------------------------------------
# _compose_kwargs dynamic filtering scenarios
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compose_kwargs_forwards_temperature_to_openai() -> None:
    """temperature is declared on StubOpenAIChat → forwarded to the constructor."""
    factory = _build_factory()
    spec = ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=0.5)
    result = factory.build(spec)
    assert isinstance(result, StubOpenAIChat)
    assert result.temperature == 0.5


@pytest.mark.unit
def test_compose_kwargs_drops_top_k_on_openai() -> None:
    """top_k is NOT declared on StubOpenAIChat → silently dropped (no TypeError)."""
    factory = _build_factory()
    spec = ModelExpandedSpec(provider="openai", id="gpt-4o", top_k=40)
    # If top_k were forwarded, StubOpenAIChat.__init__ would raise TypeError.
    result = factory.build(spec)
    assert isinstance(result, StubOpenAIChat)


@pytest.mark.unit
def test_compose_kwargs_drops_thinking_on_openai() -> None:
    """thinking is excluded from forwarding (type mismatch with Claude Dict).

    Open Item #1: ModelExpandedSpec.thinking is bool but Claude.thinking is
    Dict[str, Any]. We exclude thinking from _compose_kwargs universally so the
    bool never reaches a constructor expecting a dict. Users wanting thinking
    configure it via provider_kwargs (future slice).
    """
    factory = _build_factory()
    # Bypass Pydantic provider validation by constructing then mutating is not
    # needed — thinking is a valid field on the spec for any provider.
    spec = ModelExpandedSpec(provider="openai", id="gpt-4o", thinking=True)
    # If thinking were forwarded AND the class lacked it, StubOpenAIChat would
    # raise TypeError. StubOpenAIChat lacks thinking, so this proves exclusion.
    result = factory.build(spec)
    assert isinstance(result, StubOpenAIChat)


# ---------------------------------------------------------------------------
# Unknown provider + delegation scenarios
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_unknown_provider_raises_keyerror() -> None:
    """An unknown provider id MUST raise KeyError before any class resolution."""
    factory = _build_factory()
    # Construct bypassing Pydantic provider validation (which would also reject).
    spec = ModelExpandedSpec.model_construct(provider="no_existe", id="x")
    with pytest.raises(KeyError, match="no_existe"):
        factory.build(spec)


@pytest.mark.unit
def test_factory_does_not_duplicate_importlib() -> None:
    """The factory source delegates to resolver.resolve_class — no importlib dup.

    Source introspection: provider_factory.py contains
    ``self._resolver.resolve_class(`` and does NOT contain
    ``importlib.import_module``. This is the COMPOSE contract (design A1).
    """
    factory_src = Path(yaml_agno.__file__).parent / "di" / "provider_factory.py"
    text = factory_src.read_text(encoding="utf-8")
    assert "self._resolver.resolve_class(" in text, "factory must delegate to resolver.resolve_class"
    assert "importlib.import_module" not in text, "factory must NOT duplicate importlib"


# ---------------------------------------------------------------------------
# Integration: REAL ImportlibDependencyAdapter + real agno OpenAIChat.
# Mirrors test_resolve_model_integration_real_openai_chat_is_model_instance.
# Tagged @pytest.mark.unit (OpenAIChat defers HTTP client; no network at build).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_integration_real_openai_chat_is_model_instance() -> None:
    """End-to-end: real ImportlibDependencyAdapter + seeded allowlist + agno.

    Constructs ProviderFactory with the REAL ImportlibDependencyAdapter (not the
    in-memory double), seeds dependency.allowlist_paths=AGNO_ALLOWLIST_PREFIXES,
    and builds from a ModelExpandedSpec with temperature/top_k/retries. Asserts
    the result is a genuine agno Model instance, id/temperature/retries are set,
    and top_k was dropped (OpenAIChat does not declare it).
    """
    from agno.models.base import Model
    from agno.models.openai import OpenAIChat
    from core_infrastructure.config.adapters.in_memory_config_adapter import (
        InMemoryConfigAdapter,
    )
    from core_infrastructure.dependency import ImportlibDependencyAdapter
    from core_infrastructure.errors.adapters import CapturingErrorAdapter
    from core_infrastructure.logger.adapters import InMemoryLoggerAdapter
    from core_infrastructure.observability.adapters import NoopObservabilityAdapter

    from yaml_agno.di.registries import AGNO_ALLOWLIST_PREFIXES

    cfg = InMemoryConfigAdapter()
    cfg.set_value("dependency.allowlist_paths", AGNO_ALLOWLIST_PREFIXES)
    logger = InMemoryLoggerAdapter()
    obs = NoopObservabilityAdapter()
    errors = CapturingErrorAdapter(cfg, logger, obs)
    adapter = ImportlibDependencyAdapter(cfg, logger, errors)
    resolver = AgnoResolver(adapter)
    factory = ProviderFactory(resolver, secret_resolver=lambda env: None)

    spec = ModelExpandedSpec(
        provider="openai", id="gpt-4o", temperature=0.7, top_k=5, retries=3
    )
    result = factory.build(spec)
    assert isinstance(result, Model)
    assert isinstance(result, OpenAIChat)
    assert result.id == "gpt-4o"
    assert result.temperature == 0.7
    assert result.retries == 3
    # top_k was filtered out — OpenAIChat does not declare it.
    assert not hasattr(result, "top_k")
