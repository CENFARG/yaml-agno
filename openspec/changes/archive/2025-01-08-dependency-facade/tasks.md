---
change: dependency-facade
spec: SPEC_01
artifact: tasks
status: applied
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/dependency-facade/proposal.md (engram #1943)
  - spec: openspec/changes/dependency-facade/specs/dependency-facade/spec.md (engram #1946)
  - design: openspec/changes/dependency-facade/design.md (engram #1947)
strict_tdd: true
test_command: "python -m pytest"
---

# Tasks: Dependency Facade + ValueResolver

> **SSOT normativo**: `openspec/changes/dependency-facade/specs/dependency-facade/spec.md`
> (9 reqs RFC 2119 + 15 escenarios). El `design.md` (obs 1947) contiene el código
> literal verificado contra core-cenf v0.1.0. Cualquier discrepancia se resuelve a
> favor del design (2 correcciones NOTIFICADAS abajo; sobreescriben la proposal).
>
> **Strict TDD ACTIVO** (`openspec/config.yaml` → `apply.tdd: true` + sdd-init #1241).
> Este cambio TIENE behavioral RED real en `agno_resolver.py`, `value_resolver.py` y
> el wiring `build_agno_resolver`. Cada task de comportamiento sigue
> RED → GREEN → REFACTOR. Los tasks de datos (`registries.py`) y wiring estático
> (scaffolding, package markers, re-export) no requieren RED pero sí verificación.
>
> **2 correcciones del design vs proposal (bake-in, OVERRIDE a obs 1943)**:
> 1. `ClassificationAdapter(config, logger, observability)` exige **3 args** — el
>    3ro es `observability: ObservabilityManager`. Default: `NoopObservabilityAdapter()`.
>    Grafo correcto: **Config → Logger → Observability → Errors → Dependency**.
> 2. `ImportlibDependencyAdapter.resolve_class(module, class)` **IGNORA el registry**;
>    sólo aplica allowlist prefix-match + `importlib.import_module`. Por ende
>    `resolve_model`/`build_db` hacen lookup en `MODEL_REGISTRY`/`STORAGE_REGISTRY`
>    para obtener `(module_path, class_name)` y LUEGO llaman
>    `adapter.resolve_class(module_path, class_name)` (que valida allowlist + cachea).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines (post-hoc) | ~1066 insertions, 9 files (src + tests + spec/design/tasks) |
| Original forecast | ~150-180 — **materially understated** (see note below) |
| 400-line budget risk | High (actual exceeded budget; facade-slice wiring boilerplate) |
| Chained PRs recommended | No (single PR acceptable con size-exception) |
| Suggested split | Single PR (todos los archivos nuevos bajo `di/` salvo `__init__.py` ya vacío) |
| Delivery strategy | ask-on-risk (default; sin cachear — decide el orquestador) |
| Chain strategy | size-exception (single PR, excedido el budget 400) |

> **Forecast correction (W3, post-hoc)**: el forecast original (~150-180 líneas)
> fue materialmente understated. El tamaño real (~1066 insertions, 9 files) refleja
> el boilerplate de wiring de core-cenf (imports de 6 managers, 3 test files con
> doubles, docstrings largos). Lección: forecasts para facade-slices que cablean
> múltiples managers de core-cenf DEBEN contabilizar el wiring boilerplate, no sólo
> la lógica de dominio. El single PR se mantuvo porque el slice es atómico y todos
> los archivos son nuevos (sin conflicto); se grabó `size:exception`.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High (excedido; size-exception grabado)

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Todo el slice: registries DATA + AgnoResolver + ValueResolver + build_agno_resolver + re-export + 3 test files | PR 1 (single) | base = feature branch del change; commit granular por phase; rollback = revert `di/` a `__init__.py` vacío |

> Single PR justificado: ~150-180 líneas (muy por debajo del budget 400), todos los
> archivos son nuevos bajo `di/` (sin conflicto), y el slice es atómico — las 4
> abstracciones se validan juntas en el smoke test. No hay razón para fragmentar.

## Phase 1: Baseline & Scaffolding (Foundation)

> No TDD aquí: package markers y verificación de árbol limpio. Sin comportamiento.

- [x] 1.1 Verificar árbol limpio y HEAD en la rama feature del change (`git status` limpio). Bloqueante: si hay cambios sin commitear, abortar.
- [x] 1.2 Confirmar que `src/yaml_agno/di/` existe y `src/yaml_agno/di/__init__.py` está vacío (heredado del bootstrap). NO modificar aún (se hace en Phase 6).
- [x] 1.3 Crear `tests/unit/di/__init__.py` (package marker vacío con docstring de 1 línea `"""Unit tests for yaml_agno.di package."""`). Verificar que `tests/unit/di/` no existía previamente.
- [x] 1.4 Commit: `chore: scaffold tests/unit/di package marker`.

## Phase 2: Registries (DATA, no behavioral RED)

> Satisface (parcial): Requirement "register de namespaces Agno" — `MODEL_REGISTRY`
> y `STORAGE_REGISTRY` son la fuente declarativa que `AgnoResolver.register()` y
> `resolve_model`/`build_db` consultan.

- [x] 2.1 **DATA**: Crear `src/yaml_agno/di/registries.py` con `MODEL_REGISTRY`, `STORAGE_REGISTRY`, `WORKFLOW_REGISTRY` (tuples `(module_path, class_name, [packages])`), `AGNO_ALLOWLIST_PREFIXES` (5 prefijos) + `__all__`. Código LITERAL del `design.md` §registries.py. NOTA: es DATA pura — no hay RED posible (dicts no son comportamiento), pero se valida import.
- [x] 2.2 **VERIFY**: `python -c "from yaml_agno.di.registries import MODEL_REGISTRY, STORAGE_REGISTRY, WORKFLOW_REGISTRY, AGNO_ALLOWLIST_PREFIXES; assert isinstance(MODEL_REGISTRY, dict) and isinstance(STORAGE_REGISTRY, dict)"` — confirma imports + tipos dict. Commit: `feat: add Agno declarative registries (MODEL/STORAGE/WORKFLOW + allowlist)`.

## Phase 3: AgnoResolver — RED tests

> Satisface: Reqs "AgnoResolver envuelve el motor", "resolve_model con sintaxis
> provider:id", "build_db con semántica conn_str", "resolve_class validada por
> allowlist", "register idempotencia". Cubre 8 escenarios.

- [x] 3.1 **RED**: Crear `tests/unit/di/test_agno_resolver.py` con `InMemoryDependencyAdapter` (double oficial core-cenf) + stubs `OpenAIChat`/`InMemoryDb`/`PostgresDb`. Tests que fallan (módulo `agno_resolver.py` aún no existe → ImportError):
  - `test_resolve_model_openai_returns_openaichat_class` (golden path, scenario "golden path openai:gpt-4o").
  - `test_resolve_model_unknown_provider_raises_keyerror` (scenario "provider desconocido").
  - `test_build_db_memory_no_conn_str` (scenario "memory sin conn_str" — `cls()` sin args).
  - `test_build_db_postgres_with_conn_str` (scenario "postgres con conn_str" — `cls(conn_str)`).
  - `test_build_db_postgres_without_conn_str_raises_validation_error` (scenario "postgres sin conn_str rechazado").
  - `test_build_db_unknown_storage_raises_keyerror` (scenario "storage desconocido").
  - `test_resolve_class_allowlisted_permitted` (scenario "path allowlisted permitido").
  - `test_resolve_class_non_allowlisted_rejected` (scenario "path no allowlisted rechazado" — `resolve_class("os","system")` lanza).
  - `test_register_idempotent` (scenario "idempotencia de register" — 2 calls no duplican).
  - Marker `@pytest.mark.unit` en todos. Commit: `test: add RED tests for AgnoResolver (8 scenarios)`.

## Phase 4: AgnoResolver — GREEN (literal del design)

- [x] 4.1 **GREEN**: Crear `src/yaml_agno/di/agno_resolver.py` con `AgnoResolver` (4 métodos: `resolve_model`, `build_db`, `resolve_workflow_primitive`, `resolve_class`) + `_NO_CONN_STR_PROVIDERS = frozenset({"memory","sqlite"})`. Código LITERAL del `design.md` §agno_resolver.py. `build_db` valida `provider in _NO_CONN_STR` → `cls()` else `cls(conn_str)`; si falta conn_str para no-memory/sqlite → `ValidationError`.
- [x] 4.2 **VERIFY**: `python -m pytest tests/unit/di/test_agno_resolver.py -m unit` verde. Si REFACTOR: limpiar duplicados en branches de `build_db`. Commit: `feat: add AgnoResolver facade over ImportlibDependencyAdapter`.

## Phase 5: build_agno_resolver — RED tests (wiring del grafo)

> Satisface: Req "build_agno_resolver instancia managers en orden del grafo". Cubre
> scenario "bootstrap sin excepción con doubles in-memory".

- [x] 5.1 **RED**: Crear `tests/unit/di/test_build_agno_resolver.py`. Tests que fallan (`build_agno_resolver` aún no exportado):
  - `test_build_with_injected_adapter_skips_wiring` — pasa `adapter=InMemoryDependencyAdapter(...)` directo, retorna `AgnoResolver` sin construir managers.
  - `test_build_empty_allowlist_raises_validation_error` — `InMemoryConfigAdapter()` SIN `dependency.allowlist_paths` sembrado → `ValidationError`.
  - `test_build_full_wiring_with_inmemory_doubles` — `InMemoryConfigAdapter` + `set_value("dependency.allowlist_paths", AGNO_ALLOWLIST_PREFIXES)` + `InMemoryLoggerAdapter` + `CapturingErrorAdapter` + `NoopObservabilityAdapter()` → retorna `AgnoResolver` funcional sin excepción.
  - `test_build_graph_order_config_logger_observability_errors_dependency` — valida que `ClassificationAdapter` se construye con 3 args `(config, logger, observability)` (corrige proposal que omitía el 3ro).
  - Marker `@pytest.mark.unit`. Commit: `test: add RED tests for build_agno_resolver wiring`.

## Phase 6: build_agno_resolver — GREEN + re-export

- [x] 6.1 **GREEN**: Implementar `build_agno_resolver(config=None, *, logger=None, errors=None, observability=None, adapter=None)` en `src/yaml_agno/di/agno_resolver.py`. Código LITERAL del `design.md`. Early-return si `adapter is not None`; sino grafo **Config → Logger → Observability (`NoopObservabilityAdapter()` default) → Errors (`ClassificationAdapter(config, logger, observability)` — 3 args) → Dependency → AgnoResolver**. Guard: allowlist vacío → `ValidationError`.
- [x] 6.2 **GREEN re-export**: Modificar `src/yaml_agno/di/__init__.py` (estaba vacío) para re-exportar `AgnoResolver`, `build_agno_resolver`, `ValueResolver` (placeholder import, se completa Phase 8), `MODEL_REGISTRY`, `STORAGE_REGISTRY`, `WORKFLOW_REGISTRY`, `AGNO_ALLOWLIST_PREFIXES` + `__all__`. Código LITERAL del `design.md` §__init__.py.
- [x] 6.3 **VERIFY**: `python -m pytest tests/unit/di/test_build_agno_resolver.py -m unit` verde. Commit: `feat: add build_agno_resolver factory (graph-order wiring) + di package re-export`.

## Phase 7: ValueResolver — RED tests

> Satisface: Req "ValueResolver produce dict para DIReference.resolve" + "ValueResolver
> y AgnoResolver son abstracciones distintas". Cubre 4 escenarios env/db/api/file.

- [x] 7.1 **RED**: Crear `tests/unit/di/test_value_resolver.py`. Tests que fallan (`value_resolver.py` aún no existe):
  - `test_resolve_env_single_token` — `DIReference(template="${env.api_key}")` + `InMemoryConfigAdapter(initial_data={"api_key":"sk-x"})` → `{"env.api_key": "sk-x"}` (scenario "env provider resuelve").
  - `test_resolve_env_feeds_direference_resolve_e2e` — `DIReference(template="key=${env.api_key}")` → `ValueResolver.resolve(ref)` → `ref.resolve(dict)` == `"key=sk-x"` (scenario "DIReference integration end-to-end").
  - `test_resolve_db_raises_not_implemented` — token `db.user_db.name` → `NotImplementedError` (scenario "db provider").
  - `test_resolve_api_raises_not_implemented` — token `api.foo.bar` → `NotImplementedError` (scenario "api y file diferidos").
  - `test_resolve_file_raises_not_implemented` — token `file.path.x` → `NotImplementedError`.
  - `test_value_resolver_independent_of_agno_resolver` — `ValueResolver(cfg)` funciona sin `AgnoResolver` (scenario "separación de concerns").
  - Marker `@pytest.mark.unit`. Commit: `test: add RED tests for ValueResolver (env + NotImplementedError)`.

## Phase 8: ValueResolver — GREEN (literal del design)

- [x] 8.1 **GREEN**: Crear `src/yaml_agno/di/value_resolver.py` con `ValueResolver(config)` + `resolve(reference)` (itera `reference.tokens`, arma dict `"provider.key" -> value`) + `_resolve_provider(provider, key)` (branch `env` → `config.get_string(key)`; else `NotImplementedError` diferido a SPEC_23). `_SUPPORTED_PROVIDERS = frozenset({"env"})`. Código LITERAL del `design.md` §value_resolver.py.
- [x] 8.2 **VERIFY**: `python -m pytest tests/unit/di/test_value_resolver.py -m unit` verde. Commit: `feat: add ValueResolver (env.* MVP, db/api/file deferred to SPEC_23)`.

## Phase 9: Verification (no implementation)

> Satisface: Reqs transversales "Tests unitarios con marker @pytest.mark.unit" +
> design.md §Verification.

- [x] 9.1 Ejecutar `python -m pytest -m unit` — todos los tests del change seleccionados y verde. Reportar conteo total.
- [x] 9.2 Ejecutar `ruff check src/yaml_agno/di/` — limpio (line-length, import sort). Corregir si findings.
- [x] 9.3 Ejecutar `ruff format --check src/yaml_agno/di/` — formato consistente.
- [x] 9.4 Ejecutar `mypy src/yaml_agno/di/` — strict sin errores. Caveat: `ignore_missing_imports=true` para core-cenf y agno stubs.
- [x] 9.5 Smoke import manual: `python -c "from yaml_agno.di import build_agno_resolver, AgnoResolver, ValueResolver, MODEL_REGISTRY, STORAGE_REGISTRY, AGNO_ALLOWLIST_PREFIXES; print('OK')"`.
- [x] 9.6 Confirmar `git diff openspec/changes/dependency-facade/specs/ openspec/changes/dependency-facade/design.md openspec/changes/dependency-facade/proposal.md` vacío — no se mutaron spec/design/proposal durante implementación.
- [x] 9.7 Commit final si hay fixes de lint/type: `style: ruff/mypy compliance for dependency-facade`. NO committear si 9.1-9.6 ya verde (los commits granulares de cada fase son el histórico).

## Phase 10: Closure (orchestrator handoff)

- [x] 10.1 NO commitear este tasks.md (el apply sub-agent actualiza los checkboxes `[x]` conforme avanza). El commit granular final lo decide el orquestador según `delivery_strategy` + `chain_strategy` resueltas (aquí: single PR, `size-exception`).

## TDD Compliance Matrix (trazabilidad spec → tasks)

| Spec Requirement | RED task | GREEN task | Scenarios cubiertos |
|------------------|----------|------------|---------------------|
| AgnoResolver envuelve el motor importado | 3.1 | 4.1 | resolve_class delega y cachea |
| build_agno_resolver instancia managers en orden del grafo | 5.1 | 6.1, 6.2 | bootstrap sin excepción, idempotencia register |
| resolve_model con sintaxis provider:id | 3.1 | 4.1 | golden path openai, provider desconocido |
| build_db con semántica de connection-string | 3.1 | 4.1 | memory sin conn_str, postgres con/sin conn_str, storage desconocido |
| resolve_class validada por allowlist en strict mode | 3.1 | 4.1 | path allowlisted permitido, path no allowlisted rechazado |
| register de namespaces Agno en bootstrap | 3.1 (data en 2.1) | 4.1 | registro de model namespace |
| ValueResolver produce dict para DIReference.resolve | 7.1 | 8.1 | env provider resuelve, db/api/file NotImplementedError |
| ValueResolver y AgnoResolver son abstracciones distintas | 7.1 | 8.1 | separación de concerns, DIReference e2e |
| Tests unitarios con marker @pytest.mark.unit | 3.1, 5.1, 7.1 | — | colección `-m unit` verde |
| NO reimplementar importlib/allowlist/cache | — (invariante diff review) | — | inspección: `agno_resolver.py` sólo delega al adapter |

## Implementation Order (razón)

Secuencia estrictamente dependiente:

1. **Phase 1 (scaffolding)** — package markers sin código; no bloquea comportamiento.
2. **Phase 2 (registries DATA)** — los catálogos son la fuente que `AgnoResolver`
   consulta; deben existir antes de cualquier GREEN del resolver. No hay RED
   posible (dicts), pero se valida import.
3. **Phases 3-4 (AgnoResolver RED→GREEN)** — la fachada principal; depende de
   `registries.py` (Phase 2) y del `ImportlibDependencyAdapter` importado. 8
   escenarios.
4. **Phases 5-6 (build_agno_resolver RED→GREEN + re-export)** — la fábrica
   ensambla los managers core-cenf en orden del grafo; depende de `AgnoResolver`
   (Phase 4) existir para retornarlo. El re-export del `__init__.py` cierra aquí el
   contrato público parcial (ValueResolver se añade en Phase 8).
5. **Phases 7-8 (ValueResolver RED→GREEN)** — independiente de `AgnoResolver`
   (req explícito de "abstracciones distintas"); podría paralelizarse con Phases
   3-6 en另一个 thread, pero se deja secuencial para TDD estricto unificado.
6. **Phase 9 (verification)** — gates de pytest/ruff/mypy/smoke; corre después de
   todo el código.
7. **Phase 10 (closure)** — handoff al orquestador para el commit final según
   delivery strategy.

Cada Phase commitea de forma independiente (conventional commits). El single PR
del forecast agrupa todas las phases — el diff total (~150-180 líneas) cabe
holgadamente en el budget de 400.
