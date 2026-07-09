---
change: provider-catalog-expansion
spec: openspec/changes/provider-catalog-expansion/specs/provider-catalog-expansion/spec.md
design: openspec/changes/provider-catalog-expansion/design.md
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on:
  - openspec/changes/provider-catalog-expansion/proposal.md
  - openspec/changes/provider-catalog-expansion/specs/provider-catalog-expansion/spec.md
  - openspec/changes/provider-catalog-expansion/design.md
  - engram://sdd/provider-catalog-expansion/proposal (obs 1971)
  - engram://sdd/provider-catalog-expansion/spec (obs 1972)
  - engram://sdd/provider-catalog-expansion/design (obs 1973)
strict_tdd: true
test_command: python -m pytest -m unit
---

# Tasks: Provider Catalog Expansion

> SPEC_14 slice #1 — pure DATA. Expande `MODEL_REGISTRY` 6→26, fija 2 bugs
> (`mistral`→MistralChat, `vertex`→submodule `claude`), preserva alias back-compat
> `openai`, e introduce `provider_capabilities.py` con la matriz declarativa.
> **TDD estricto: RED → GREEN por cada behavior.** Slice ~150-200 LOC.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-200 (registries.py +20 rows +alias, provider_capabilities.py new ~90, agno_resolver.py alias edit ~2, 2 test fixes, new tests ~80) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR (slice completa cabe holgada bajo budget) |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Catálogo 26 + capabilities + alias-aware resolver (slice #1 entera) | PR único | base = rama actual; commits atómicos separan data/resolver/tests |

## Phase 1: Baseline & Safety Net

- [x] 1.1 `git status` limpio, registrar HEAD actual como rollback point. **Req: Rollback Plan.**
- [x] 1.2 Verificar que `src/yaml_agno/di/registries.py` (6 entradas), `src/yaml_agno/di/agno_resolver.py` y `tests/unit/di/test_agno_resolver.py` existen y son el estado verde shipped. Confirmar `resolve_model` hace `if provider not in self._models` (línea 119) — NO alias-aware.
- [x] 1.3 Safety net: `python -m pytest tests/unit/di/ -m unit` verde (baseline N passing). Sin RED pre-existente. Anotar N. **TDD: Safety Net antes de tocar shipped code.**

## Phase 2: RED — tests primero (TDD estricto)

- [x] 2.1 Crear `tests/unit/di/test_provider_catalog.py` con test RED `test_model_registry_has_exactly_26_keys`: `set(MODEL_REGISTRY) == {las 26 claves del spec}`. **Req: resolve_model con sintaxis provider:id — Scenario: las 26 claves del catálogo están presentes.**
- [x] 2.2 RED `test_mistral_maps_to_mistral_chat`: `MODEL_REGISTRY["mistral"][1] == "MistralChat"` (falla hoy, shipped es `"Mistral"`). **Req: mapping de mistral apunta a MistralChat — Scenario: la clase Mistral NO existe en el mapping.**
- [x] 2.3 RED `test_vertex_module_path_includes_claude_submodule`: `MODEL_REGISTRY["vertex"][0] == "agno.models.vertexai.claude"` (falla hoy, no existe la key). **Req: mapping de vertex usa el submodule claude — Scenario: module_path incluye submodule claude.**
- [x] 2.4 RED `test_openai_is_alias_of_openai_chat`: `MODEL_REGISTRY["openai"] == MODEL_REGISTRY["openai_chat"]` Y existe `MODEL_REGISTRY["openai_responses"]` distinto. **Req: openai es alias de back-compat — Scenario: openai alias resuelve idéntico a openai_chat.**
- [x] 2.5 RED `test_supported_providers_and_local_providers_derived` (en `test_provider_capabilities.py`): `SUPPORTED_PROVIDERS` y `LOCAL_PROVIDERS` son `frozenset`, `LOCAL_PROVIDERS ⊆ SUPPORTED_PROVIDERS`, locales = `{ollama, llamacpp, lm_studio, vllm}`. **Req: PROVIDER_REGISTRY enriquecido.**
- [x] 2.6 RED `test_provider_registry_shape_for_all_keys` (en `test_provider_capabilities.py`): cada una de las 26 entradas tiene `agno_module`, `agno_class`, `packages` (list no vacía salvo locales), `api_key_env` (None para locales, str no vacío resto), `capabilities` (instancia de `ProviderCapabilities` con los 6 bools estrictos). **Req: PROVIDER_REGISTRY enriquecido — Scenario: cada provider del catálogo tiene entrada completa + ProviderCapabilities bien formado.**
- [x] 2.7 RED `test_local_providers_have_null_api_key_env` (en `test_provider_capabilities.py`): `PROVIDER_REGISTRY["ollama"].api_key_env is None`; `PROVIDER_REGISTRY["anthropic"].api_key_env == "ANTHROPIC_API_KEY"`. **Req: providers locales sin API key — Scenario: provider local no requiere API key + provider cloud declara env var.**
- [x] 2.8 RED `test_resolve_model_openai_alias_still_works` (en `test_agno_resolver.py`): con el InMemoryDependencyAdapter doblado (mapping key `("agno.models.openai", "OpenAIChat")`), `resolve_model("openai:gpt-4o")` retorna `OpenAIChat(id="gpt-4o")`. Tras el refactor del alias, `"openai"` deja de ser key directa → este test valida que `resolve_model` resuelva el alias. **Req: openai alias — Scenario: resolve_model("openai:gpt-4o") sigue funcionando.**
- [x] 2.9 Actualizar las **2** líneas shipped que rompen con el alias refactor: `tests/unit/di/test_agno_resolver.py:81` y `:207-208` (`MODEL_REGISTRY["openai"]` → `MODEL_REGISTRY[PROVIDER_ALIASES["openai"]]` i.e. `MODEL_REGISTRY["openai_chat"]`). Mantienen comportamiento actual vía alias. **Req: openai alias back-compat (no romper shipped).**
- [x] 2.10 RED `test_optional_dep_provider_graceful_skip` (en `test_provider_catalog.py`, con `pytest.importorskip`): el módulo `yaml_agno.di.registries` SIEMPRE se importa (DATA estática) sin importar deps; para providers con dep ausente, solo `resolve_model` propaga `ImportError`. **Req: toda entrada importable cuando su dependencia está instalada — Scenario: graceful skip.**
- [x] 2.11 Ejecutar `python -m pytest tests/unit/di/ -m unit` → confirmar RED colectivo (tests nuevos fallan, baseline sigue verde). **GATE TDD: no GREEN antes de producir código.**

## Phase 3: GREEN — implementación mínima

- [x] 3.1 Expandir `src/yaml_agno/di/registries.py` `MODEL_REGISTRY` a las **26** claves del spec (incluye `openai_chat`+`openai_responses` separados + las 24 nuevas). Fijar `mistral`→`"MistralChat"` y agregar `vertex`→`("agno.models.vertexai.claude", "Claude", [...])`. Añadir `PROVIDER_ALIASES: Final[dict[str, str]] = {"openai": "openai_chat"}`. **Reqs: 26 keys + mistral + vertex + openai alias.**
- [x] 3.2 Editar `src/yaml_agno/di/agno_resolver.py` `resolve_model`: insertar `provider = PROVIDER_ALIASES.get(provider, provider)` ANTES de `if provider not in self._models` (línea 119). Importar `PROVIDER_ALIASES` desde `registries`. **Req: openai alias — resolve_model alias-aware.**
- [x] 3.3 Crear `src/yaml_agno/di/provider_capabilities.py` con `@dataclass(frozen=True, slots=True) ProviderCapabilities` (6 bools: `multimodal, structured, tool_use, streaming, caching, reasoning`) y `ProviderRegistryEntry` (`agno_module, agno_class, packages, api_key_env, capabilities`). Construir `PROVIDER_REGISTRY: Final[dict[str, ProviderRegistryEntry]]` con las 26 entradas (locales con `api_key_env=None`). Derivar `SUPPORTED_PROVIDERS: Final[frozenset[str]]` y `LOCAL_PROVIDERS: Final[frozenset[str]] = frozenset({"ollama","llamacpp","lm_studio","vllm"})`. **Reqs: PROVIDER_REGISTRY enriquecido + providers locales sin API key.**
- [x] 3.4 Ejecutar `python -m pytest tests/unit/di/ -m unit` → todos los RED de Phase 2 pasan a GREEN; baseline (1.3) sigue verde. **GATE TDD: GREEN confirmado por ejecución.**

## Phase 4: Verification (escenario a escenario)

- [x] 4.1 `python -m pytest -m unit` verde total (baseline N + tests nuevos). **Scenario coverage: 12/12 spec scenarios.**
- [x] 4.2 `ruff check .` sin findings (incluye `provider_capabilities.py` nuevo + imports en `agno_resolver.py`). **Lint.**
- [x] 4.3 `mypy src/yaml_agno` sin errores (`Final`, dataclasses frozen/slots, uniones `str | None`). **Types.**
- [x] 4.4 Smoke import: `python -c "from yaml_agno.di.registries import MODEL_REGISTRY, PROVIDER_ALIASES; from yaml_agno.di.provider_capabilities import PROVIDER_REGISTRY; assert len(MODEL_REGISTRY)==26"`. **Import sin crash.**
- [x] 4.5 Runtime back-compat: `python -c "from yaml_agno.di.agno_resolver import AgnoResolver; from yaml_agno.di.importlib_dependency_adapter import ImportlibDependencyAdapter; r=AgnoResolver(ImportlibDependencyAdapter()); m=r.resolve_model('openai:gpt-4o'); print(type(m).__name__, m.id)"` → `OpenAIChat gpt-4o`. Si `mistralai` instalado, también `resolve_model("mistral:mistral-large-latest")` → instancia de `MistralChat`. **Reqs: openai alias + mistral — Scenarios runtime.**
- [x] 4.6 `git diff --name-only openspec/changes/provider-catalog-expansion/specs/ openspec/changes/provider-catalog-expansion/design.md` → vacío (spec/design NO mutados). **Protección de artifacts.**
- [x] 4.7 `git diff --name-only openspec/specs/` → vacío (progenitor `dependency-facade/spec.md` intocado). **No tocar SPECs base.**

## Phase 5: Commit granular (conventional commits)

- [x] 5.1 Commits atómicos en orden: `fix: map mistral to MistralChat and vertex to claude submodule` (subset 3.1 bugs) → `feat: expand MODEL_REGISTRY to 26 providers with openai alias` (resto 3.1) → `refactor: make AgnoResolver.resolve_model alias-aware` (3.2 + 2.9 test fixes) → `feat: add provider_capabilities registry with declared capability matrix` (3.3) → `test: add provider catalog TDD coverage` (2.x tests nuevos). **No commitear specs/ ni openspec/specs/.**

## TDD Compliance Matrix

| Spec Requirement | RED Task | GREEN Task | Scenario cubierto |
|------------------|----------|------------|-------------------|
| resolve_model con sintaxis provider:id (26 keys) | 2.1 | 3.1 | las 26 claves presentes + provider desconocido rechazado |
| mapping mistral → MistralChat | 2.2 | 3.1 | resolve_model mistral instancia MistralChat + clase no es "Mistral" |
| mapping vertex → submodule claude | 2.3 | 3.1 | module_path incluye submodule claude + resolve_model vertex → Claude provider VertexAI |
| openai alias back-compat | 2.4, 2.8, 2.9 | 3.1, 3.2 | openai == openai_chat + resolve_model("openai:gpt-4o") sigue funcionando |
| PROVIDER_REGISTRY enriquecido | 2.5, 2.6 | 3.3 | cada provider con entrada completa + capabilities bien formado |
| providers locales sin API key | 2.7 | 3.3 | ollama None + anthropic "ANTHROPIC_API_KEY" |
| toda entrada importable (graceful skip) | 2.10 | 3.1, 3.3 | módulo importa sin crash + resolve_model propaga ImportError |

## Implementation Order

1. **Phase 1** (baseline + safety net) — pre-requisito de TDD honesto.
2. **Phase 2** (RED completo) — todos los tests fallando primero; triangulación cubre los 12 scenarios.
3. **Phase 3** (GREEN en 3 pasos): primero los bugs de `registries.py` (3.1), luego el resolver alias-aware (3.2, necesario para que 2.8 y 2.9 pasen), finalmente el módulo nuevo (3.3).
4. **Phase 4** (verification) — ejecuta contra los 12 scenarios del spec.
5. **Phase 5** (commits granulares) — cada commit deja el árbol verde.

**Dependencia crítica**: el paso 3.2 (alias-aware resolver) DEBE ir antes de/o con 3.1 — sin él, `resolve_model("openai:gpt-4o")` KeyErrors tras quitar `openai` como key directa. Tests 2.8 y 2.9 son la red que atrapa esto.

## Open Items

- **`mistral_gateway`**: NO se agrega como key propia (design §8: alias-of-mistral-via-gateway es dispatch de slice #2). Spec §2.2 lo lista en SUPPORTED_PROVIDERS pero este slice lo omite — revisar que el Literal `SUPPORTED_PROVIDERS` (frozenset derivado, no Literal aquí) no choque. Sin blocker para apply.
- **vertex `api_key_env`**: design usa `GOOGLE_APPLICATION_CREDENTIALS` (gcloud default) vs SPEC_14 vago "GCP service account JSON". Se sigue el design. No blocker.
- **Capabilities provenance**: "declarado, no verificado en runtime" — contrato del docstring (design §4). Slice #4 puede añadir verificación si se requiere.
