---
change: model-resilience-runtime
spec: SPEC_14
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/model-config-schema
  - openspec/specs/provider-factory-adapter
slice: "SPEC_14 #4 (DOMAIN-only)"
---

# Proposal: model-resilience-runtime (SPEC_14 slice #4 — DOMAIN)

## Intent (Por qué, ahora)

El slice #4 CIERRA la capa de dominio de resiliencia: hasta hoy
`FallbackConfig` (slice #2) y `ProviderFactory.build` (slice #3) existen
pero NO se componen — no hay forma de ensamblar la cadena de fallback
declarada, ni de derivar una clave determinista para trazas/dedup
(SPEC_09), ni de clasificar una excepción Agno en uno de los tres enums
de routing (`on_rate_limit | on_context_overflow | on_error`) que el
schema YA define. Sin estos tres componentes puros, el runtime
`call_with_fallback` (SPEC_09) no tiene de qué nutrirse.

Éxito = tres funciones puras / métodos estáticos, injectables, sin
async, sin red, cubiertas por strict TDD (RED-GREEN-REFACTOR), listas
para que SPEC_09 las consuma sin tocar su interior.

## Scope

### In Scope (DOMAIN — slice #4)

- `build_fallback_chain(primary, factory) -> list[Any]` — ensambla la
  cadena de Model INSTANCES (vía `ProviderFactory.build`), primaria en
  índice 0, truncada a `max_fallback_hops`. Re-exporte en
  `models/__init__.py`.
- `CacheKeyBuilder.build(...) -> str` — sha256 hex determinista sobre
  identidad + parámetros del spec + hash de mensajes serializado de
  forma estable. Es una CLAVE de dedup/observabilidad, NO un
  cache store.
- `FallbackErrorClassifier.classify(exc) -> Literal[...]` — adaptador
  DELGADO sobre `agno.exceptions` (ModelRateLimitError,
  ContextWindowExceededError, ModelProviderError). NO reimplementa
  status/pattern.
- 3 test files en `tests/unit/models/` (strict TDD, estilo
  `test_model_spec.py` / `test_provider_factory.py`).
- `models/__init__.py` re-export.

### Out of Scope (DEFER — explícito)

| Componente DEFERRED | Owner | Razón |
|---|---|---|
| `call_with_fallback` runtime executor | SPEC_09 | necesita `CircuitBreaker.allow_request()`/`guard()` |
| CircuitBreaker (estados, min_requests) | SPEC_09 | rate-based breaker no shipped |
| `RetryPolicy` (step-level, `classify()`/backoff/jitter) | SPEC_05 | retry es step-level, NO model-level (ADR A3 / DECISIONES.md #6) |
| `compute_delay` (fallback-probe) | SPEC_09 | sólo consumido dentro de `call_with_fallback` |
| `dispatch_fallback_callback` (async) | SPEC_09+ | necesita `CallableRegistry` (SPEC_11/15) |
| `probe_models_health` (TaskGroup) | SPEC_09 | runtime probing |
| Referencias `{"alias": name}` en `fallback_models` | TASK_013 | definitions registry unshipped — REJECT con `NotImplementedError` en slice #4 |
| RetryPolicy a nivel de MODELO | NUNCA | Agno `Model.*` nativo lo maneja (slice #2/3 forwardea esos fields) |
| CacheManager / cache layer | NUNCA | Agno `cache_response` nativo — yaml-agno NO agrega capa de cache |
| Re-implementar lógica de status_code/patterns | NUNCA | Agno ya expone `ModelProviderError.classify()` — adaptador, no reinvención |

## Capabilities

> Relevamiento de `openspec/specs/`: NO existe capability
> `model-resilience-runtime`. Las dos dependencias
> (`model-config-schema`, `provider-factory-adapter`) están archivadas.
> Esta propuesta crea UNA capability nueva.

### New Capabilities

- `model-resilience-runtime`: ensamblaje de la cadena de fallback
  (DOMINIO puro), clave de cache determinista para dedup/trazas, y
  clasificador de excepciones Agno → routing enum. Sin runtime, sin
  breaker, sin retry step-level — sólo los componentes que SPEC_09/SPEC_05
  consumirán.

### Modified Capabilities

- Ninguna. Ni `model-config-schema` ni `provider-factory-adapter`
  cambian sus requirements: slice #4 LEE sus tipos exportados
  (`FallbackConfig`, `ModelExpandedSpec`, `parse_model_spec`,
  `ProviderResolver`, `ProviderFactory.build`) pero no los modifica.

## Approach

Tres módulos Python nuevos bajo `src/yaml_agno/models/`, cada uno
autocontenido y testeable de forma aislada.

### A. `fallback_chain.py` — `build_fallback_chain`

```
def build_fallback_chain(
    primary: ModelExpandedSpec,
    factory: ProviderFactory,
    *,
    resolver: ProviderResolver | None = None,
) -> list[Any]:  # Model instances
```

Pipeline: `[primary, *primary.fallback.fallback_models]` → para cada
entrada `str | dict`, `parse_model_spec` → `ProviderResolver.resolve`
(canonicaliza alias) → `factory.build(spec)`. Truncar a
`primary.fallback.max_fallback_hops`. Si `primary.fallback is None`,
retornar `[factory.build(primary)]`. **Rechazar** entrada
`dict` con clave única `"alias"` con `NotImplementedError` (definitions
registry = TASK_013).

**Deviation documentada**: SPEC_14 §12.2 mostraba `list[ModelExpandedSpec]`;
con `ProviderFactory` shipped (slice #3) el dominio entrega INSTANCIAS
— el runtime SPEC_09 las necesita para invocar. Devuelve `list[Any]`
para no acoplar el type-checker al tipo `Model` de Agno (dinámico vía
`resolve_class`).

### B. `cache_key.py` — `CacheKeyBuilder`

```
class CacheKeyBuilder:
    @staticmethod
    def build(
        spec: ModelExpandedSpec,
        *,
        messages_hash: str,
        tool_defs_hash: str = "",
        response_model_hash: str = "",
    ) -> str:  # hex sha256, 64 chars
```

Determinista: serializa `spec.model_dump(exclude_none=True)` (incluye
`provider`, `id`, `temperature`, `top_p`, ...) + los hashes del caller
con `json.dumps(sort_keys=True, separators=(",", ":"))`, luego
`hashlib.sha256(...).hexdigest()`. El hashing de
messages/tools/response_model NO es responsabilidad de este builder —
el caller (runtime SPEC_09) los provee; el builder sólo los concatena de
forma estable. Esto evita scope-creep de serialización de
mensajes/herramientas (R4).

### C. `fallback_classifier.py` — `FallbackErrorClassifier`

```
class FallbackErrorClassifier:
    @staticmethod
    def classify(
        exc: Exception,
    ) -> Literal["rate_limit", "context_overflow", "error"]: ...
```

Adaptador DELGADO sobre `agno.exceptions` (nombres verificados, obs #1936):

```python
from agno.exceptions import (
    ContextWindowExceededError,
    ModelProviderError,
    ModelRateLimitError,
)
```

1. `isinstance(exc, ModelRateLimitError)` → `"rate_limit"`
2. `isinstance(exc, ContextWindowExceededError)` → `"context_overflow"`
3. `isinstance(exc, ModelProviderError)` → delegar a
   `ModelProviderError.classify(exc)` (classmethod Agno) y mapear
   resultado → enum
4. else → `"error"`

**NO reimplementar** status 429/529 ni `CONTEXT_WINDOW_PATTERNS` — Agno
ya lo hace. Los nombres del draft SPEC_14 (`RateLimitError`,
`ContextOverflowError`) NO existen en `agno/exceptions.py` y NO se usan.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/models/fallback_chain.py` | New | `build_fallback_chain` + `NotImplementedError` para `{"alias": ...}` |
| `src/yaml_agno/models/cache_key.py` | New | `CacheKeyBuilder.build` (sha256 determinista) |
| `src/yaml_agno/models/fallback_classifier.py` | New | `FallbackErrorClassifier.classify` (adaptador Agno) |
| `src/yaml_agno/models/__init__.py` | Modified | Re-export de los 3 símbolos nuevos |
| `tests/unit/models/test_fallback_chain.py` | New | Strict TDD: RED-GREEN por componente |
| `tests/unit/models/test_cache_key.py` | New | Determinismo + diferenciación por input |
| `tests/unit/models/test_fallback_classifier.py` | New | Mapeo por tipo + delegación a `ModelProviderError.classify` |
| `src/yaml_agno/models/model_spec.py` | Untouched | Se LEE `FallbackConfig`, `parse_model_spec`, `ProviderResolver`, `ModelExpandedSpec` — no se modifica |
| `src/yaml_agno/di/provider_factory.py` | Untouched | Se LEE `ProviderFactory.build` (signature en `provider_factory.py:104`) — no se modifica |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| R1 — Agno renombra excepciones en `agno.exceptions` | Low (estable desde 2.6.x) | Import directo (yaml-agno YA importa `agno.*` en todos lados); cobertura de test sobre los 4 branches |
| R2 — `build_fallback_chain` return type ambiguo (`list[Any]` vs `list[Model]`) | Low | Documentado en este proposal; `Any` evita acoplar mypy al tipo Agno dinámico; SPEC_09 usa duck-typing |
| R3 — `{"alias": name}` refs rompen la cadena | Med | Slice #4 REJECT con `NotImplementedError` explícito (no skip silencioso); mensaje nombra TASK_013 |
| R4 — CacheKeyBuilder scope-creep (serializar messages/tools) | Med | Builder sólo acepta hashes del caller; NO serializa messages/tools/response_model — queda en el runtime |
| R5 — `ModelProviderError.classify()` cambia signature | Low (classmethod estable) | Test con mock subclass cubre el path de delegación; fallback a `isinstance` branch si raise |
| R6 — Review workload | Low | Forecast: ~155 src LOC + ~150 test LOC ≈ 305 líneas changed. Bajo budget 400. Single PR viable |

## Rollback Plan

Los tres módulos son aditivos y standalone — ningún módulo existente los
importa todavía. Rollback = `git revert` del commit/PR del slice #4 (o
`git switch -c revert/model-resilience-runtime` + borrar los 3 archivos
+ revertir el diff de `models/__init__.py`). No hay migración de datos,
no hay cambio de schema, no hay cambio en `AgentConfig.model`. Las
specs `model-config-schema` y `provider-factory-adapter` quedan
intactas. Tiempo de rollback estimado: < 5 min.

## Dependencies

- **Hard**: `openspec/specs/model-config-schema` (shipped, slice #2) —
  provee `FallbackConfig`, `ModelExpandedSpec`, `parse_model_spec`,
  `ProviderResolver`. Verificado en `src/yaml_agno/models/model_spec.py`
  (FallbackConfig en línea 109, parse_model_spec línea 259,
  ProviderResolver línea 289).
- **Hard**: `openspec/specs/provider-factory-adapter` (shipped, slice #3)
  — provee `ProviderFactory.build(spec) -> Any` (Instancia Agno Model).
  Verificado en `src/yaml_agno/di/provider_factory.py:104-162`.
- **Soft (runtime only)**: `agno.exceptions` (ModelRateLimitError,
  ContextWindowExceededError, ModelProviderError) — nombres verificados
  obs #1936. Agno v2.6.18 lockeado en `openspec/config.yaml`.

## Success Criteria

- [ ] `build_fallback_chain` devuelve `[primary_model, *fallback_models]`
      truncada a `max_fallback_hops`; `[primary_model]` cuando
      `primary.fallback is None`; `NotImplementedError` para
      `{"alias": name}`.
- [ ] `CacheKeyBuilder.build` es determinista (mismos inputs → mismo
      digest); difiere al cambiar `temperature`; difiere al cambiar
      `messages_hash`.
- [ ] `FallbackErrorClassifier.classify` mapea las 4 branches
      (`rate_limit`, `context_overflow`, delegación a
      `ModelProviderError.classify`, `error`) — sin reimplementar
      status/patterns.
- [ ] `from yaml_agno.models import build_fallback_chain, CacheKeyBuilder, FallbackErrorClassifier` funciona.
- [ ] `python -m pytest tests/unit/models/` verde al 100% de coverage
      sobre los 3 módulos nuevos.
- [ ] Ningún módulo existente fuera de `models/` se modifica (diff vacío
      salvo `models/__init__.py` y los 3 archivos nuevos).
- [ ] Slice respeta frontera SPEC_05/SPEC_09: cero referencias a
      `RetryPolicy`, `CircuitBreaker`, `call_with_fallback`,
      `compute_delay`, `dispatch_fallback_callback`, `probe_models_health`.
