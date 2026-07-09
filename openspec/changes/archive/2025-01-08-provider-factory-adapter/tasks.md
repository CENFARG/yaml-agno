---
change: provider-factory-adapter
spec: openspec/changes/provider-factory-adapter/specs/provider-factory-adapter/spec.md
artifact: tasks
status: applied
artifact_store: hybrid
depends_on:
  - openspec/changes/provider-factory-adapter/proposal.md
  - openspec/changes/provider-factory-adapter/specs/provider-factory-adapter/spec.md
  - openspec/changes/provider-factory-adapter/design.md
  - engram://doc.reca/sdd/provider-factory-adapter/proposal (obs 1988)
  - engram://doc.reca/sdd/provider-factory-adapter/spec (obs 1987)
  - engram://doc.reca/sdd/provider-factory-adapter/design (obs 1989)
strict_tdd: true
test_command: python -m pytest -m unit
linters: [ruff, mypy --strict]
path_decision: src/yaml_agno/di/ (NOT src/yaml_agno/models/) — ProviderFactory COMPOSES around AgnoResolver which lives in di/
---

# Tasks: provider-factory-adapter (SPEC_14 slice #3)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~250-300 (4 new src files ~180 LOC + tests ~100-120 LOC + __init__ patch) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR (additive, 5 files, one bounded slice) |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

**Rationale**: 4 new src modules + 4 new test files + 1 `__init__.py` patch. All literal code is in design.md (copy-faithful GREEN). Below the 400-line threshold. No existing module consumes the new code (invariant Req 9), so blast radius is zero and a single PR is reviewable in one pass.

## TDD Compliance Matrix (9 reqs → 14 scenarios → RED → GREEN)

| # | Requirement | Scenario(s) | RED test(s) | GREEN module |
|---|-------------|-------------|-------------|--------------|
| R1 | ProviderFactory.build constructs Model | golden OpenAIChat+temperature; unknown provider KeyError | 2.1, 2.7 | provider_factory.py |
| R2 | COMPOSE delegates to resolve_class | factory no importlib dup | 2.8 | provider_factory.py |
| R3 | _compose_kwargs dynamic filter | temperature forwarded; top_k filtered | 2.5, 2.6 | provider_factory.py |
| R4 | api_key via injected sync SecretResolver | api_key resolved; local provider skips | 2.3, 2.4 | provider_factory.py |
| R5 | ConfigSecretResolver default | reads config; returns None if missing | 1.1, 1.2 | secret_resolver.py |
| R6 | AgnoModelAdapter caches by alias | build twice same instance; invalidate clears | 3.1, 3.2 | agno_model_adapter.py |
| R7 | ModelCapabilitiesValidator pure-data | reasoning rejected (mistral); reasoning accepted (openai) | 4.1, 4.2 | capabilities_validator.py |
| R8 | Retry fields Agno-native 1:1 | (implicit via _compose_kwargs forwarding) | 2.5, 2.6 | provider_factory.py |
| R9 | AgentConfig.model UNCHANGED | AgentConfig unchanged (invariant) | 5.4 | (no mutation — assertion only) |

## Implementation Order

```
Phase 1 (baseline) → Phase 2 (RED, all tests fail) → Phase 3 (GREEN per module) → Phase 4 (verify) → Phase 5 (commit)
```

GREEN order follows the dependency graph: `secret_resolver` (no deps) → `capabilities_validator` (imports ProviderCapabilities + ModelExpandedSpec) → `provider_factory` (imports resolver + SecretResolver + PROVIDER_REGISTRY + ModelExpandedSpec) → `agno_model_adapter` (no deps) → `__init__` re-exports.

## Phase 1: Baseline & Scaffolding

- [x] 1.1 Confirm `src/yaml_agno/di/` exists (it does — agno_resolver.py, registries.py, provider_capabilities.py, value_resolver.py, __init__.py already shipped in slices 1-2). No new dir needed.
- [x] 1.2 Confirm `AgnoResolver.resolve_class(module_path, class_name)` is public (agno_resolver.py:184-199) — the escape hatch the factory delegates to. Read-only check.
- [x] 1.3 Confirm `tests/unit/di/` exists with `__init__.py` and the `@pytest.mark.unit` marker is registered in pyproject.toml (markers.unit). Read-only check.
- [x] 1.4 Create empty test files to anchor Phase 2: `tests/unit/di/test_secret_resolver.py`, `test_provider_factory.py`, `test_agno_model_adapter.py`, `test_capabilities_validator.py`.

## Phase 2: RED — Failing Tests (Strict TDD)

All tests tagged `@pytest.mark.unit`. Doubles: `InMemoryDependencyAdapter` + stub `@dataclass` stand-ins for Agno Models (NO network at construct time — Agno builds HTTP client lazily).

### `tests/unit/di/test_secret_resolver.py`

- [x] 2.1 RED `test_config_secret_resolver_reads_secrets_namespace` — InMemoryConfigAdapter double with `secrets.openai_api_key = "sk-cfg"`; `ConfigSecretResolver(config)("OPENAI_API_KEY")` returns `"sk-cfg"`. Covers Scenario: ConfigSecretResolver reads config.
- [x] 2.2 RED `test_config_secret_resolver_returns_none_when_key_missing` — ConfigManager without the key; `ConfigSecretResolver(config)("OPENAI_API_KEY")` returns `None`. Covers Scenario: ConfigSecretResolver devuelve None.

### `tests/unit/di/test_provider_factory.py`

- [x] 2.3 RED `test_build_injects_api_key_when_entry_has_env` — SecretResolver double `lambda env: "sk-test"`; `ModelExpandedSpec(provider="openai", id="gpt-4o")`; assert instance built with `api_key="sk-test"` AND factory did not touch `os.environ`. Covers Scenario: api_key resuelto desde SecretResolver.
- [x] 2.4 RED `test_build_local_provider_skips_secret_resolver` — ollama provider (`api_key_env=None`); SecretResolver double that `raise AssertionError` if called; assert instance built with no `api_key` kwarg. Covers Scenario: provider local no requiere api_key.
- [x] 2.5 RED `test_compose_kwargs_forwards_temperature_to_openai` — `ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=0.5)`; real OpenAIChat (no network at construct); assert `result.temperature == 0.5`. Covers Scenario: temperature se reenvía a OpenAIChat.
- [x] 2.6 RED `test_compose_kwargs_drops_top_k_on_openai` — `ModelExpandedSpec(provider="openai", id="gpt-4o", top_k=40)`; assert NO TypeError AND instance built (top_k silently dropped). Covers Scenario: top_k NO se reenvía a OpenAIChat.
- [x] 2.7 RED `test_build_unknown_provider_raises_keyerror` — `ModelExpandedSpec(provider="no_existe", id="x")` (constructed bypassing validation); assert `factory.build(spec)` raises `KeyError`. Covers Scenario: build rechaza provider desconocido.
- [x] 2.8 RED `test_factory_does_not_duplicate_importlib` — source introspection: `provider_factory.py` contains `self._resolver.resolve_class(` and does NOT contain `importlib.import_module`. Covers Scenario: el factory no duplica importlib.

### `tests/unit/di/test_agno_model_adapter.py`

- [x] 3.1 RED `test_get_or_build_caches_instance` — two calls same alias `"openai:gpt-4o"`; builder double invoked once; both results `is`-identical. Covers Scenario: build dos veces devuelve la misma instancia.
- [x] 3.2 RED `test_invalidate_selective_and_full` — seed cache; `invalidate("openai:gpt-4o")` drops one entry (assert `__contains__` False); `invalidate(None)` clears all (assert `__len__` 0). Covers Scenario: invalidate limpia el cache.

### `tests/unit/di/test_capabilities_validator.py`

- [x] 4.1 RED `test_validate_reasoning_intent_rejected_on_non_reasoning_provider` — mistral (`capabilities.reasoning == False`) + `reasoning_effort="high"`; assert error list non-empty mentioning `reasoning_effort`. Covers Scenario: reasoning_effort rechazado en provider non-reasoning.
- [x] 4.2 RED `test_validate_reasoning_intent_accepted_on_reasoning_provider` — openai (`capabilities.reasoning == True`) + `reasoning_effort="high"`; assert error list empty. Covers Scenario: reasoning_effort aceptado en provider reasoning.

## Phase 3: GREEN — Implementation (Literal from design.md)

Copy-faithful from design.md §"Interfaces / Contracts — LITERAL CODE". Do NOT paraphrase signatures.

- [x] 5.1 GREEN `src/yaml_agno/di/secret_resolver.py` — `SecretResolver` Protocol (`@runtime_checkable`, `__call__(env_name) -> str | None`) + `ConfigSecretResolver(config)` reading `config.get_string(f"secrets.{env_name.lower()}", default_value=None)`. NO `os.environ`. Makes 2.1, 2.2 GREEN.
- [x] 5.2 GREEN `src/yaml_agno/di/capabilities_validator.py` — `ModelCapabilitiesValidator.validate(spec, capabilities) -> list[str]` staticmethod; `_check_reasoning` + `_check_caching` private staticmethods. Pure-data, no Agno import. Makes 4.1, 4.2 GREEN.
- [x] 5.3 GREEN `src/yaml_agno/di/provider_factory.py` — `ProviderFactory(resolver, secret_resolver, *, validate_capabilities=False)` + `build(spec) -> Any` + `_compose_kwargs(spec, cls)` + `ModelConstructionError`. Pipeline: registry lookup → `resolve_class` → `_compose_kwargs` → conditional api_key → optional caps check → `cls(id=spec.id, **kwargs)`. Makes 2.3-2.8 GREEN.
- [x] 5.4 GREEN `src/yaml_agno/di/agno_model_adapter.py` — `AgnoModelAdapter` with `get_or_build(alias, builder)`, `invalidate(alias=None)`, `__len__`, `__contains__`. Makes 3.1, 3.2 GREEN.
- [x] 5.5 GREEN `src/yaml_agno/di/__init__.py` (Modify) — append 5 imports + 6 `__all__` entries (`AgnoModelAdapter`, `ConfigSecretResolver`, `ModelCapabilitiesValidator`, `ModelConstructionError`, `ProviderFactory`, `SecretResolver`). Keep existing entries unchanged.

## Phase 4: Verification

- [x] 6.1 Run `python -m pytest -m unit` — all RED tests now GREEN; no regressions in slices 1-2 tests.
- [x] 6.2 Run `python -m pytest tests/unit/di/test_agno_resolver.py` — slices 1-2 still GREEN (factory did NOT touch AgnoResolver).
- [x] 6.3 Run `ruff check src/yaml_agno/di/ tests/unit/di/` — clean.
- [x] 6.4 Run `mypy --strict src/yaml_agno/di/` — clean (ConfigSecretResolver satisfies SecretResolver Protocol structurally).
- [x] 6.5 Smoke import check: `python -c "from yaml_agno.di import ProviderFactory, AgnoModelAdapter, SecretResolver, ConfigSecretResolver, ModelCapabilitiesValidator, ModelConstructionError"` succeeds.
- [x] 6.6 Integration test: real `ImportlibDependencyAdapter` + seeded allowlist + real `agno.models.openai.OpenAIChat`; `factory.build(ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=0.7, top_k=5, retries=3))` → assert `isinstance(result, Model)`, `id == "gpt-4o"`, `temperature == 0.7`, `retries == 3`, NO `top_k` attr set. Tag `@pytest.mark.integration` (or keep unit if no network — OpenAIChat defers HTTP client). Mirrors `test_resolve_model_integration_real_openai_chat_is_model_instance`.
- [x] 6.7 Invariant check: `git diff src/yaml_agno/agent_config.py` (or wherever AgentConfig lives) shows NO changes — `AgentConfig.model` type untouched. Covers Req 9.
- [x] 6.8 Invariant check: spec.md and design.md NOT mutated during apply (`git diff openspec/` empty for spec/design files).

## Phase 5: Commit (Granular Work Units)

One commit per GREEN module + final verification commit. Conventional commits only, no AI attribution.

- [x] 7.1 `feat(di): add SecretResolver protocol and ConfigSecretResolver default` — secret_resolver.py + test_secret_resolver.py GREEN.
- [x] 7.2 `feat(di): add ModelCapabilitiesValidator pure-data config-time checks` — capabilities_validator.py + test_capabilities_validator.py GREEN.
- [x] 7.3 `feat(di): add ProviderFactory composing AgnoResolver with kwargs filter` — provider_factory.py + test_provider_factory.py GREEN.
- [x] 7.4 `feat(di): add AgnoModelAdapter alias-keyed instance cache` — agno_model_adapter.py + test_agno_model_adapter.py GREEN.
- [x] 7.5 `feat(di): re-export slice #3 symbols from di package` — __init__.py patch.
- [x] 7.6 `test(di): add real OpenAIChat integration build via factory` — integration test 6.6.
- [x] 7.7 (only if lint/type drift found) `style(di): apply ruff/mypy fixes for slice #3 modules`.

## Open Items (carry into apply)

- [x] **`thinking` type mismatch** (spec.thinking is `bool`, Claude.thinking is `Dict[str, Any]`): design recommends excluding `thinking` from `_compose_kwargs` universal forwarding. DECISION NEEDED in apply: either (a) add `thinking` to the `excluded` set and document `provider_kwargs` as future escape hatch, or (b) forward and let Claude constructor reject at runtime. Recommend (a) — add `"thinking"` to the `excluded` set in `_compose_kwargs` with a comment referencing this Open Item.
- [x] **`stop_sequences` (Claude) vs `stop` (OpenAI)** naming mismatch: filtering by name drops `stop_sequences` on OpenAI silently. Acceptable for slice #3 (no rename layer). Document in module docstring; per-provider rename deferred.
- [x] **capabilities validator hard-error vs warning**: `validate_capabilities` defaults `False`. Bootstrap wiring (SPEC_02 evolution) decides. No action in slice #3.
