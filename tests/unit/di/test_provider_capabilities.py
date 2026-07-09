"""RED tests for the PROVIDER_REGISTRY capability catalog.

Covers SPEC_14 slice #1 scenarios on ``yaml_agno.di.provider_capabilities``:
  - PROVIDER_REGISTRY has an entry for every MODEL_REGISTRY key (same key set).
  - Each entry has module_path, class_name, packages, api_key_env, capabilities.
  - ProviderCapabilities is a frozen dataclass with the 6 declared fields.
  - Local providers (ollama, llamacpp, lm_studio, vllm) have api_key_env=None.
  - SUPPORTED_PROVIDERS / LOCAL_PROVIDERS are frozensets derived from the
    registry (single source of truth).

Tagged ``@pytest.mark.unit``. No network. Pure DATA assertions.
"""

from __future__ import annotations

import dataclasses

import pytest

from yaml_agno.di.provider_capabilities import (
    LOCAL_PROVIDERS,
    PROVIDER_REGISTRY,
    SUPPORTED_PROVIDERS,
    ProviderCapabilities,
    ProviderRegistryEntry,
)
from yaml_agno.di.registries import MODEL_REGISTRY

_EXPECTED_LOCAL: frozenset[str] = frozenset({"ollama", "llamacpp", "lm_studio", "vllm"})


# ---------------------------------------------------------------------------
# Scenario: cada provider del catálogo tiene entrada completa
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_provider_registry_shape_for_all_keys() -> None:
    """Every PROVIDER_REGISTRY entry has all required fields, non-empty where
    required.

    Required fields per ProviderRegistryEntry:
        - module_path: non-empty str, mirrors MODEL_REGISTRY.
        - class_name: non-empty str, mirrors MODEL_REGISTRY.
        - packages: tuple, non-empty for non-local providers (locals MAY be
          empty, but in this catalog all locals declare a package too).
        - api_key_env: None for locals, non-empty str otherwise.
        - capabilities: a ProviderCapabilities instance with 6 declared fields.
    """
    assert set(PROVIDER_REGISTRY) == set(MODEL_REGISTRY), (
        "PROVIDER_REGISTRY and MODEL_REGISTRY MUST share the same key set"
    )
    for provider_id, entry in PROVIDER_REGISTRY.items():
        assert isinstance(entry, ProviderRegistryEntry), f"{provider_id}: not a ProviderRegistryEntry"
        # module_path / class_name mirror MODEL_REGISTRY (single source of truth).
        model_module, model_class, _ = MODEL_REGISTRY[provider_id]
        assert entry.module_path == model_module, f"{provider_id}: module_path drift"
        assert entry.class_name == model_class, f"{provider_id}: class_name drift"
        assert isinstance(entry.module_path, str) and entry.module_path
        assert isinstance(entry.class_name, str) and entry.class_name
        # packages is a non-empty tuple.
        assert isinstance(entry.packages, tuple)
        assert len(entry.packages) >= 1, f"{provider_id}: packages empty"
        assert all(isinstance(p, str) and p for p in entry.packages)
        # api_key_env: None for locals, non-empty str otherwise.
        if provider_id in _EXPECTED_LOCAL:
            assert entry.api_key_env is None, f"{provider_id}: local must have api_key_env=None"
        else:
            assert isinstance(entry.api_key_env, str) and entry.api_key_env, (
                f"{provider_id}: non-local must have non-empty api_key_env"
            )
        # capabilities is a well-formed ProviderCapabilities.
        assert isinstance(entry.capabilities, ProviderCapabilities)


# ---------------------------------------------------------------------------
# Scenario: ProviderCapabilities es un struct bien formado (6 campos declarados)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_provider_capabilities_has_six_declared_fields() -> None:
    """ProviderCapabilities exposes exactly the 6 declared capability fields.

    Fields (per design A4): multimodal (tuple), structured_output (tuple),
    tool_use (Literal), streaming (bool), caching (bool), reasoning (bool).
    """
    expected_fields = {
        "multimodal",
        "structured_output",
        "tool_use",
        "streaming",
        "caching",
        "reasoning",
    }
    actual_fields = {f.name for f in dataclasses.fields(ProviderCapabilities)}
    assert actual_fields == expected_fields, (
        f"ProviderCapabilities fields mismatch: {actual_fields ^ expected_fields}"
    )
    # Every entry's capability booleans are STRICTLY bool (not None, not int).
    for provider_id, entry in PROVIDER_REGISTRY.items():
        caps = entry.capabilities
        assert isinstance(caps.streaming, bool), f"{provider_id}.streaming not bool"
        assert isinstance(caps.caching, bool), f"{provider_id}.caching not bool"
        assert isinstance(caps.reasoning, bool), f"{provider_id}.reasoning not bool"
        assert caps.tool_use in ("native", "partial", "none"), f"{provider_id}.tool_use invalid"
        assert isinstance(caps.multimodal, tuple), f"{provider_id}.multimodal not tuple"
        assert isinstance(caps.structured_output, tuple), f"{provider_id}.structured_output not tuple"


# ---------------------------------------------------------------------------
# Scenario: provider local no requiere API key + provider cloud declara env var
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_local_providers_have_null_api_key_env() -> None:
    """Local providers (ollama, llamacpp, lm_studio, vllm) have api_key_env=None."""
    for local_id in _EXPECTED_LOCAL:
        assert PROVIDER_REGISTRY[local_id].api_key_env is None, (
            f"{local_id}: local provider must not require an API key"
        )


@pytest.mark.unit
def test_cloud_provider_declares_env_var() -> None:
    """A cloud provider (anthropic) declares its API key env var name."""
    assert PROVIDER_REGISTRY["anthropic"].api_key_env == "ANTHROPIC_API_KEY"


# ---------------------------------------------------------------------------
# Requirement: PROVIDER_REGISTRY entry is immutable (frozen dataclass)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_provider_registry_entry_is_frozen() -> None:
    """ProviderRegistryEntry is a frozen dataclass — attribute assignment raises.

    Immutability is required because these are Final module constants shared
    across the process; nothing should mutate them at runtime.
    """
    entry = PROVIDER_REGISTRY["anthropic"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.api_key_env = "HACKED"  # type: ignore[misc]


@pytest.mark.unit
def test_provider_capabilities_is_frozen() -> None:
    """ProviderCapabilities is frozen — capability cells cannot be mutated."""
    caps = PROVIDER_REGISTRY["anthropic"].capabilities
    with pytest.raises(dataclasses.FrozenInstanceError):
        caps.streaming = False  # type: ignore[misc]


@pytest.mark.unit
def test_provider_registry_entry_has_slots() -> None:
    """ProviderRegistryEntry uses slots — no __dict__ attribute (lean instances)."""
    entry = PROVIDER_REGISTRY["anthropic"]
    assert not hasattr(entry, "__dict__"), "ProviderRegistryEntry should use slots"


# ---------------------------------------------------------------------------
# Requirement: SUPPORTED_PROVIDERS + LOCAL_PROVIDERS derived from the registry
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_supported_providers_and_local_providers_derived() -> None:
    """SUPPORTED_PROVIDERS and LOCAL_PROVIDERS are frozensets derived from the
    registry; LOCAL_PROVIDERS is a subset of SUPPORTED_PROVIDERS and equals the
    4 known local ids.
    """
    assert isinstance(SUPPORTED_PROVIDERS, frozenset)
    assert isinstance(LOCAL_PROVIDERS, frozenset)
    # SUPPORTED_PROVIDERS is the registry key set (single source of truth).
    assert frozenset(PROVIDER_REGISTRY) == SUPPORTED_PROVIDERS
    # LOCAL_PROVIDERS is the subset with api_key_env is None.
    assert _EXPECTED_LOCAL == LOCAL_PROVIDERS
    assert LOCAL_PROVIDERS <= SUPPORTED_PROVIDERS


# ---------------------------------------------------------------------------
# Optional-dep aware: declared Agno class IS importable when its dep is present.
# Uses pytest.importorskip so a missing optional dep skips (never fails) the
# suite — the catalog is DATA, importability is only asserted when the SDK the
# entry points at is actually installed.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_openai_chat_class_importable_when_dep_present() -> None:
    """When ``openai`` is installed, MODEL_REGISTRY['openai_chat'] resolves.

    Triangulation: confirms the (module_path, class_name) declared in the
    catalog is a real, importable Agno class — not just well-formed data.
    Skips cleanly if openai is absent (optional dep).
    """
    import importlib

    pytest.importorskip("openai")
    module_path, class_name, _ = MODEL_REGISTRY["openai_chat"]
    mod = importlib.import_module(module_path)
    assert hasattr(mod, class_name), f"{module_path} does not export {class_name}"
