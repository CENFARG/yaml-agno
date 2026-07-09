"""RED tests for the expanded provider catalog (MODEL_REGISTRY + PROVIDER_ALIASES).

Covers SPEC_14 slice #1 scenarios on ``yaml_agno.di.registries``:
  - MODEL_REGISTRY exposes the full 26-key catalog (+ mistral_gateway alias-row).
  - mistral maps to ``MistralChat`` (bug fix; was ``Mistral``).
  - vertex maps to the ``agno.models.vertexai.claude`` submodule (bug fix).
  - openai is a back-compat alias of openai_chat (direct key + alias map).
  - every module_path is covered by AGNO_ALLOWLIST_PREFIXES (prefix-match guard).
  - the static registries module imports even when optional deps are absent.

Tagged ``@pytest.mark.unit``. No network. Pure DATA assertions.
"""

from __future__ import annotations

import pytest

from yaml_agno.di.registries import (
    AGNO_ALLOWLIST_PREFIXES,
    MODEL_REGISTRY,
    PROVIDER_ALIASES,
)

# ---------------------------------------------------------------------------
# The 26 canonical provider_ids from SPEC_14 §2.2 (the catalog contract).
# ``openai`` is listed here as a back-compat alias-row. ``mistral_gateway`` is
# an additional gateway alias-row declared by the design (same class as
# ``mistral``); it is NOT in the SPEC_14 §2.2 list of 26, so tests treat the 26
# as the required subset and allow the extra gateway row.
# ---------------------------------------------------------------------------

_SPEC_26_PROVIDERS: frozenset[str] = frozenset(
    {
        "anthropic",
        "openai",
        "openai_chat",
        "openai_responses",
        "google",
        "mistral",
        "deepseek",
        "cohere",
        "perplexity",
        "xai",
        "meta",
        "dashscope",
        "vercel",
        "ollama",
        "llamacpp",
        "lm_studio",
        "vllm",
        "bedrock",
        "azure",
        "vertex",
        "openrouter",
        "together",
        "groq",
        "fireworks",
        "langdb",
        "nebius",
    }
)


# ---------------------------------------------------------------------------
# Scenario: las 26 claves del catálogo están presentes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_model_registry_has_exactly_26_spec_keys() -> None:
    """MODEL_REGISTRY contains every SPEC_14 §2.2 provider_id (superset allowed).

    The 26 SPEC keys MUST all be present. The design adds ``mistral_gateway``
    as an extra gateway alias-row pointing at the same MistralChat class, so the
    total length is 27 (26 spec + mistral_gateway).
    """
    registry_keys = set(MODEL_REGISTRY)
    missing = _SPEC_26_PROVIDERS - registry_keys
    assert not missing, f"MODEL_REGISTRY missing SPEC_14 providers: {sorted(missing)}"
    # mistral_gateway is the one design-declared extra beyond the SPEC 26.
    assert "mistral_gateway" in registry_keys
    assert len(MODEL_REGISTRY) == 27


# ---------------------------------------------------------------------------
# Scenario: la clase Mistral (sin Chat) NO existe en el mapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mistral_maps_to_mistral_chat() -> None:
    """MODEL_REGISTRY['mistral'] class_name is 'MistralChat' (NOT 'Mistral').

    Bug fix: Agno 2.6.22 exports ``MistralChat`` from ``agno.models.mistral``;
    the shipped 'Mistral' class_name would raise AttributeError at runtime.
    """
    _module_path, class_name, _packages = MODEL_REGISTRY["mistral"]
    assert class_name == "MistralChat"
    assert class_name != "Mistral"


# ---------------------------------------------------------------------------
# Scenario: el module_path incluye el submodule claude
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertex_module_path_includes_claude_submodule() -> None:
    """MODEL_REGISTRY['vertex'] module_path is 'agno.models.vertexai.claude'.

    Bug fix: ``agno/models/vertexai/__init__.py`` is EMPTY in Agno 2.6.22, so
    importing the parent package and getattr-ing 'Claude' would fail. The class
    lives in the ``claude`` submodule.
    """
    module_path, _class_name, _packages = MODEL_REGISTRY["vertex"]
    assert module_path == "agno.models.vertexai.claude"
    assert module_path != "agno.models.vertexai"


# ---------------------------------------------------------------------------
# Scenario: openai alias resuelve idéntico a openai_chat
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_openai_is_alias_of_openai_chat() -> None:
    """MODEL_REGISTRY['openai'] tuple equals MODEL_REGISTRY['openai_chat'].

    Back-compat: configs using ``resolve_model("openai:gpt-4o")`` must resolve
    identically to the canonical ``openai_chat`` id. ``openai_responses`` is a
    DISTINCT entry (OpenAIResponses, not OpenAIChat).
    """
    assert "openai" in MODEL_REGISTRY
    assert "openai_chat" in MODEL_REGISTRY
    assert "openai_responses" in MODEL_REGISTRY
    # openai and openai_chat point at the SAME class.
    assert MODEL_REGISTRY["openai"] == MODEL_REGISTRY["openai_chat"]
    # openai_responses is a DIFFERENT class (OpenAIResponses, not OpenAIChat).
    assert MODEL_REGISTRY["openai_responses"] != MODEL_REGISTRY["openai_chat"]
    assert MODEL_REGISTRY["openai_responses"][1] == "OpenAIResponses"
    # PROVIDER_ALIASES makes the back-compat explicit data.
    assert PROVIDER_ALIASES["openai"] == "openai_chat"
    # The alias target MUST be a real key in MODEL_REGISTRY.
    assert PROVIDER_ALIASES["openai"] in MODEL_REGISTRY


# ---------------------------------------------------------------------------
# Invariant: every module_path is allowlisted (prefix-match guard).
# Locks the invariant for all 20 new entries + the 2 bug fixes.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_module_paths_under_allowlist() -> None:
    """Every MODEL_REGISTRY module_path starts with an allowed prefix.

    ImportlibDependencyAdapter._is_allowlisted does prefix-match against
    AGNO_ALLOWLIST_PREFIXES. A module_path outside the allowlist would be
    rejected in strict mode at resolve_class time.
    """
    bad: list[str] = []
    for _provider, (module_path, _class, _pkgs) in MODEL_REGISTRY.items():
        if not any(module_path.startswith(prefix) for prefix in AGNO_ALLOWLIST_PREFIXES):
            bad.append(module_path)
    assert not bad, f"module_paths outside AGNO_ALLOWLIST_PREFIXES: {bad}"


@pytest.mark.unit
def test_provider_aliases_targets_all_exist_in_registry() -> None:
    """Every PROVIDER_ALIASES value MUST be a real MODEL_REGISTRY key.

    Prevents a dangling alias that would KeyError at resolution time.
    """
    dangling = {alias: target for alias, target in PROVIDER_ALIASES.items() if target not in MODEL_REGISTRY}
    assert not dangling, f"PROVIDER_ALIASES targets missing from MODEL_REGISTRY: {dangling}"


# ---------------------------------------------------------------------------
# Scenario: graceful skip — registries module imports with optional deps absent.
# The catalog is STATIC DATA; importing yaml_agno.di.registries MUST NOT require
# any optional provider SDK (mistralai, anthropic, groq, ...). Only resolve_model
# propagates ImportError when the dep is missing.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_registries_module_imports_without_optional_deps() -> None:
    """Importing the registries module never raises even if deps are absent.

    The catalog is declarative DATA — no importlib of provider SDKs happens at
    module load. Optional deps (mistralai, anthropic, ...) are only touched by
    resolve_model at call time.
    """
    import importlib

    # Re-importing must not raise regardless of which optional deps are present.
    mod = importlib.import_module("yaml_agno.di.registries")
    assert hasattr(mod, "MODEL_REGISTRY")
    assert hasattr(mod, "PROVIDER_ALIASES")
    # mistral entry is present even though mistralai is NOT installed in this env.
    assert "mistral" in mod.MODEL_REGISTRY


@pytest.mark.unit
def test_openai_alias_lockstep_in_sync() -> None:
    """Lock-step guard: the openai back-compat alias MUST stay identical to openai_chat.

    The ``openai`` shorthand is represented in THREE places (coherence audit obs
    #1978): a direct ``MODEL_REGISTRY`` key, a direct ``PROVIDER_REGISTRY`` key,
    AND the ``PROVIDER_ALIASES`` map. If a future edit changes one without the
    others, raw ``MODEL_REGISTRY["openai"]`` lookups and alias-aware resolution
    silently diverge. This test enforces their equality so drift fails loudly.
    """
    from yaml_agno.di.provider_capabilities import PROVIDER_REGISTRY
    from yaml_agno.di.registries import MODEL_REGISTRY, PROVIDER_ALIASES

    # 1. Alias map points openai -> openai_chat (the canonical id).
    assert PROVIDER_ALIASES.get("openai") == "openai_chat"

    # 2. The direct MODEL_REGISTRY key equals the canonical openai_chat tuple.
    assert MODEL_REGISTRY["openai"] == MODEL_REGISTRY["openai_chat"]

    # 3. The direct PROVIDER_REGISTRY entry equals the canonical one too.
    assert PROVIDER_REGISTRY["openai"] == PROVIDER_REGISTRY["openai_chat"]
