---
change: circuit-breaker-foundation
spec: SPEC_09
status: proposed
artifact_store: hybrid
depends_on: []
slice: "A (SPEC_09 §4.1)"
---

# Proposal: CircuitBreaker Foundation (SPEC_09 Slice A)

## Intent

Espec_09 define CircuitBreaker como pieza fundacional de resiliencia, pero hoy
no existe implementación en `yaml-agno`. Sin él, no hay protección contra
cascading failures y SPEC_05 `ResilientExecutor` (slice C) queda bloqueado.

Este slice entrega el **state machine puro**: cero dependencias externas,
cero clasificación de errores (núcleo de core-cenf), cero retry (SPEC_05).
Es la única pieza totalmente autocontenida del plan de 3 slices y desbloquea
todo lo demás.

## Scope

### In Scope

- `src/yaml_agno/resilience/circuit_breaker.py` (nuevo):
  - `CircuitState(str, Enum)`: `CLOSED`, `OPEN`, `HALF_OPEN`.
  - `CircuitBreaker` con constructor por defecto
    (`failure_threshold=50.0`, `recovery_timeout=30.0`, `min_requests=10`,
    `half_open_max_calls=3`) y métodos `record_success`, `record_failure`,
    `_should_trip` (rate-based con `min_requests`), `allow_request`,
    `execute` (async), `get_state_metrics`.
  - `CircuitBreakerOpenError` (excepción levantada por `execute` y
    `ResilientExecutor` cuando el breaker está OPEN).
- `tests/` (unit): transiciones CLOSED→OPEN (rate-based), OPEN→HALF_OPEN
  tras `recovery_timeout`, HALF_OPEN probe (éxito cierra, fallo reabre),
  `allow_request` por estado, `execute` async (éxito/fallo/open).
- `src/yaml_agno/resilience/__init__.py` (paquete nuevo).

### Out of Scope

- **Telemetry / instrumentación** (slice B: `telemetry/metrics.py`,
  `telemetry/tracing.py`).
- **ResilientExecutor** (slice C: composición con SPEC_05 `RetryPolicy`;
  bloqueado por reconciliación `should_retry()` vs `is_retryable()`).
- **Clasificación de errores**: permanece en core-cenf
  `ErrorHandlingManager.classify()`. Sin `type(e).__name__`, sin
  `ErrorCategory` local.
- **Retry**: propiedad de SPEC_05 `RetryPolicy`.

## Capabilities

### New Capabilities

- `circuit-breaker`: state machine puro CLOSED/OPEN/HALF_OPEN con
  trip rate-based (`min_requests` + `failure_threshold`), probe en
  HALF_OPEN y métricas de estado.

### Modified Capabilities

None (greenfield; no modifica specs existentes).

## Approach

Implementación directa del contrato SPEC_09 §4.1 (lines 343-485). El breaker
es un objeto sin I/O ni dependencias: sólo `time.time()`, contadores y
transiciones. `execute()` es async (`asyncio`) y delega la decisión de
admisión a `allow_request()`; en fallo registra y re-raisea (sin tragar
excepciones, sin clasificar). TDD estricto: cada transición arranca con
test RED.

**Decisión de diseño (bake-in)**: `CircuitBreakerOpenError` se define en este
módulo (SPEC_09 la referencia pero no la declara — gap a cerrar en sdd-spec).

## Affected Areas

| Area | Impact | Descripción |
|------|--------|-------------|
| `src/yaml_agno/resilience/circuit_breaker.py` | New | State machine + error. |
| `src/yaml_agno/resilience/__init__.py` | New | Paquete. |
| `tests/.../test_circuit_breaker.py` | New | Cobertura 100% del estado. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `CircuitBreakerOpenError` sin definición formal en SPEC_09. | Mediana | sdd-spec la declara explícitamente; meanwhile se asume `class CircuitBreakerOpenError(Exception)`. |
| Drift entre defaults del spec y tests (umbrales). | Baja | Tests parametrizan sobre los defaults del spec. |
| `time.time()` acoplado impide tests deterministas. | Mediana | Inyectar `time_fn` en constructor (default `time.time`); no rompe contrato. |
| Confusión con retry (alcance). | Baja | Out-of-scope explícito; ResilientExecutor es slice C. |

## Rollback Plan

Al ser fichero nuevo sin consumidores (ResilientExecutor aún no existe),
el rollback es `git revert` del commit + borrado de
`src/yaml_agno/resilience/`. Sin migración, sin datos, sin dependientes.

## Dependencies

Ninguna (cero imports de core-cenf, Agno, ni otros módulos yaml-agno).

## Success Criteria

- [ ] `CircuitBreaker` cubre 100% (transiciones, rate-based, HALF_OPEN probe).
- [ ] `CircuitBreakerOpenError` levantada cuando `allow_request()` es False.
- [ ] Cero dependencias externas (sólo stdlib `time`, `enum`, `typing`).
- [ ] `ruff` + `mypy` limpios; `pytest` verde.
- [ ] Slice C (ResilientExecutor) desbloqueado conceptualmente.
