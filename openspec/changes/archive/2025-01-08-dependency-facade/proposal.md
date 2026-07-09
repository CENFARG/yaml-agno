---
change: dependency-facade
spec: SPEC_01
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/agent-config-schema        # SPEC_02 (shipped, read-only)
  - openspec/specs/agent-factory-basic         # SPEC_01 slice #1 (shipped)
  - core_infrastructure.dependency             # ImportlibDependencyAdapter + In-memory test double
  - core_infrastructure.config                  # ConfigManager Protocol + PydanticConfigAdapter
  - core_infrastructure.logger                  # LoggerManager Protocol + StructlogAdapter
  - core_infrastructure.errors                  # ErrorHandlingManager Protocol + ClassificationAdapter
---

# Proposal: Dependency Facade + `${provider.key}` ValueResolver

## Intent

SPEC_01 §1.3 originalmente planeaba construir un `DependencyManager` *from scratch*
(~200 líneas de importlib + allowlist + cache). El análisis empírico (obs 1936)
demostró que `core-cenf-py` **ya distribuye** ese motor: `ImportlibDependencyAdapter`
cubre lazy-class-load + allowlist prefix-match + cache + `invalidate_cache()`.
Reimplementarlo sería frankenstein.

Este slice colapsa a dos abstracciones **separadas** que core-cenf no provee:
(1) una **facades fina de dominio Agno** que envuelve el adapter importado y
expone `resolve_model` / `build_db` / `resolve_workflow_primitive` / `resolve_class`;
(2) un **ValueResolver** que traduce la sintaxis propia `${provider.key}` (validada
por `DIReference`, SPEC_02 ya entregado) al diccionario `resolved_values` que
`DIReference.resolve()` consume. Ambas son responsabilidades de dominio Agno,
no transversales.

## Scope

### In Scope

- `di/registries.py` — `MODEL_REGISTRY`, `STORAGE_REGISTRY`, `WORKFLOW_REGISTRY`,
  `AGNO_ALLOWLIST_PREFIXES` como **datos declarativos** (tuples `(module_path, class_name)`).
- `di/agno_resolver.py` — fachada delgada: holds an `ImportlibDependencyAdapter`,
  `register()` los namespaces Agno en bootstrap, expone los 4 métodos de dominio.
  `build_db` especial-casa `memory`/`sqlite` (sin `connection_string`) vs
  `postgres`/`redis` (lo requiere).
- `di/value_resolver.py` — resuelve `${provider.key}` consultando providers;
  MVP `env.*` vía `ConfigManager.get_string()`. Produce `dict[str, Any]` para
  `DIReference.resolve()`.
- `di/__init__.py` — re-export de la API pública (`AgnoResolver`, `ValueResolver`,
  factoría de bootstrap).
- `tests/unit/di/test_agno_resolver.py`, `tests/unit/di/test_value_resolver.py` —
  usan `InMemoryDependencyAdapter` + `CapturingErrorAdapter` + `InMemoryLoggerAdapter`
  (doubles oficiales de core-cenf), sin red ni filesystem real.

### Out of Scope

- Reimplementar importlib / allowlist / cache (IMPORTADO de core-cenf).
- `team-factory` (slice #3) y `workflow-factory` (slice #4).
- Backends completos del ValueResolver: `db.*`, `api.*`, `file.*` diferidos a SPEC_23.
  El MVP implementa **solo `env.*`**; el resto lanza `NotImplementedError` explícito.
- Compilación CEL de `evaluator`/`selector`/`end_condition` ( concerns del slice #4).

## Capabilities

### New Capabilities

- `dependency-facade`: fachada de dominio Agno sobre el motor de carga de clases
  de core-cenf, con registros declarativos de providers y `build_db` con
  semántica de connection-string.

### Modified Capabilities

- `agent-config-schema`: el ValueResolver produce el `resolved_values` que
  `DIReference.resolve()` (SPEC_02, ya entregado) consume — sin cambiar la firma
  de `DIReference`, solo habilitando su uso en runtime.

## Approach

### Wiring verificado de los 3 managers de core-cenf

core-cenf expone **Protocols** (`config/ports.py`, `logger/ports.py`,
`errors/ports.py`) + **adaptadores concretos**:
- Config: `core_infrastructure.config.adapters.PydanticConfigAdapter` (YAML + env `CENF_`),
  `InMemoryConfigAdapter` (tests).
- Logger: `core_infrastructure.logger.adapters.StructlogAdapter` (prod),
  `InMemoryLoggerAdapter` (tests).
- Errors: `core_infrastructure.errors.adapters.ClassificationAdapter` (prod),
  `CapturingErrorAdapter` (tests).
- Dependency: `ImportlibDependencyAdapter` (prod), `InMemoryDependencyAdapter` (tests).

NO existe un factory/`build_core()` único — `BootstrapOrchestrator` es un
orquestador de *runtime* (async lifecycle), no un ensamblador. Por ende
yaml-agno provee una **fábrica propia** `build_agno_resolver()` en `di/__init__.py`
que: (a) instancia los 3 managers (inyectando el ConfigManager ya construido en
logger y errors, según el grafo `Config → Logger → Errors → Dependency` de
`bootstrap.py`); (b) instancia `ImportlibDependencyAdapter(config, logger, errors)`;
(c) `register()` los 4 namespaces Agno. yaml-agno **no** duplica `BootstrapOrchestrator`
— este slice trabaja con managers ya inicializados (síncrono); el lifecycle async
es responsabilidad del host que arranca yaml-agno.

### Configuración del allowlist

El allowlist se lee del ConfigManager vía `get_section("dependency")["allowlist_paths"]`
(prefix-match, verificado en `importlib_dependency_adapter.py:58-61, 70-88`).
`build_agno_resolver()` inyecta los prefijos Agno en la configuración antes de
construir el adapter: `["agno.models.", "agno.db.", "agno.workflow.", "agno.team.",
"agno.agent"]`. En strict mode (default), `resolve_class("os", "...")` queda bloqueado.

### `build_db` — semántica especial

`InMemoryDb()` y `SqliteDb()` (cuando es in-memory) NO toman `connection_string`;
`PostgresDb`/`RedisDb` lo requieren. `build_db` valida esto antes de delegar
`resolve_class` + instanciación.

### ValueResolver — contrato con `DIReference`

`DIReference.resolve(resolved_values: dict[str, Any]) -> str` (verificado en
`di_reference.py:66-88`) espera un dict plano `"provider.key" -> value`. El
ValueResolver itera `ref.tokens` (lista de `(provider, key)`), resuelve cada uno
contra el provider correspondiente, y arma ese dict. MVP: `env.<key>` →
`ConfigManager.get_string(key)`. Otros providers lanzan `NotImplementedError`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/di/__init__.py` | Modified | Re-exporta `AgnoResolver`, `ValueResolver`, `build_agno_resolver()` (hoy está vacío). |
| `src/yaml_agno/di/registries.py` | New | Registros Agno como datos. |
| `src/yaml_agno/di/agno_resolver.py` | New | Fachada sobre `ImportlibDependencyAdapter`. |
| `src/yaml_agno/di/value_resolver.py` | New | Resolución `${provider.key}` MVP `env.*`. |
| `tests/unit/di/` | New | Tests unitarios con doubles oficiales de core-cenf. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Orden de inicialización de los 3 managers (Config → Logger → Errors → Dependency) mal aplicado | Medium | `build_agno_resolver()` codifica el orden del grafo documentado en `bootstrap.py:10-12`; test verifica que el adapter se construye sin excepción. |
| Allowlist vacío → `resolve_class` siempre rechaza en strict mode | Medium | `build_agno_resolver()` siembra los prefijos Agno *antes* de construir el adapter; test GREEN con `agno.models.openai.OpenAIChat`. |
| `PydanticConfigAdapter` requiere path YAML real para producción | Low | En runtime yaml-agno el host lo provee; en tests se usa `InMemoryConfigAdapter`. El slice no acopla a un path fijo. |
| ValueResolver MVP `env-only` deja escenarios de SPEC sin cubrir | High (aceptado) | `db/api/file` explícitamente fuera de scope, diferidos a SPEC_23. Se documenta como `NotImplementedError` ruidoso, no silencioso. |
| `di/__init__.py` puede chocar con exports futuros de slices #3/#4 | Low | Solo se exportan los símbolos de este slice; slices posteriores añaden los suyos. |

## Rollback Plan

Todos los archivos son nuevos bajo `di/` (salvo `__init__.py` que está vacío hoy).
Revertir restaura `di/__init__.py` a su contenido vacío y elimina los 3 módulos
+ sus tests. No hay mutación de SPEC_02 (`DIReference` ya entregado) ni de
agent-factory-basic. Sin migraciones de datos ni estado persistente.

## Dependencies

- `core_infrastructure.dependency` — `ImportlibDependencyAdapter`, `InMemoryDependencyAdapter`,
  `DependencyManager` Protocol, `RegistryEntry`.
- `core_infrastructure.config` — `ConfigManager` Protocol + `PydanticConfigAdapter`
  / `InMemoryConfigAdapter`.
- `core_infrastructure.logger` — `LoggerManager` Protocol + `StructlogAdapter` /
  `InMemoryLoggerAdapter`.
- `core_infrastructure.errors` — `ErrorHandlingManager` Protocol + `ClassificationAdapter`
  / `CapturingErrorAdapter`.
- SPEC_02 (`DIReference`, entregado) — el ValueResolver produce el dict que su
  `.resolve()` consume.

No depende de SPEC_14 ni de slices #3/#4.

## Success Criteria

- [ ] `AgnoResolver.resolve_model("openai")` retorna `agno.models.openai.OpenAIChat`
      vía `ImportlibDependencyAdapter`, sin importar `os` u otros módulos no allowlisted.
- [ ] `build_db("memory")` instancia `InMemoryDb()` sin `connection_string`;
      `build_db("postgres", conn_str=...)` requiere `conn_str` o lanza.
- [ ] `ValueResolver.resolve(DIReference(template="${env.api_key}"))` retorna
      `{"env.api_key": <valor>}` consumible por `DIReference.resolve()`.
- [ ] Todos los tests usan doubles oficiales de core-cenf (sin red, sin YAML real).
- [ ] Ningún módulo nuevo reimplementa importlib / allowlist / cache.
