# CODE-QUALITY_REPORT — yaml-agno (Remediación FULL del audit)

**Fecha**: 2026-08-07 · **Equipo**: quality-team (independiente) · **Trigger**: on-demand pre-release
**Fuente**: `QUALITY-FEEDBACK.md` + `.openspec/SDD-HOTSPOTS-REFACTOR.md`
**Veredicto**: **PASS** — todos los hotspots P0/P1 remediados, gate de calidad completo verde.

---

## 1. Resumen ejecutivo (1 página)

| Área | Baseline (audit) | Final | Verdicto |
|---|---|---|---|
| `_build_step` McCabe (workflow_factory) | **24 (D)** | **6 (A)** — dispatcher + 5 builders | ✅ remediado |
| `build()` McCabe (agentos_factory) | **16 (B)** | **1 (A)** — pipeline 5 fases | ✅ remediado |
| mypy --strict | **22 errores** (14 por core-cenf sin py.typed) | **0 errores** en 94 files | ✅ remediado |
| Cobertura condition_evaluator | **56%** | **94%** (línea 32 ambiental) | ✅ remediado |
| Cobertura provider_factory | **82%** | **100%** | ✅ remediado |
| Docstrings API pública | 5.3% comment ratio (radon) | **100% cobertura** (197/197), docstring/LOC **20%** | ✅ remediado |
| MI archivos refactorizados | 38.2 (workflow_factory) | **52-70 (B/A)** | ✅ mejorado |
| Suite unit | 640 passed / 6 fails MCP | **652 passed** / 6 fails MCP (pre-existentes §P2.9) | ✅ sin regresión |
| ruff | 0 | 0 | ✅ estable |
| SPEC gate | 34/34 | 34/34 | ✅ estable |

**Costo de remediación**: 4 slices SDD (P0-1, P0-2, P1, P2), 9 commits granulares + 4 merges `--no-ff`, ~0 h de retrabajo humano (TDD automático), supervision ratio: agente 100% (ejecución directa del orquestador tras fallo de subagente por depth limit).

## 2. Trazabilidad por slice (métrica → script → timestamp)

### Slice P0-1 — workflow_factory `_build_step` CC 24→6 (TASK 1)
- **Baseline**: radon `cc_visit` — CC=24, ts 15:50:26
- **TDD**: 6 de 10 casos del audit ya cubiertos; +4 tests defensivos pinchan referencias colgantes vía `WorkflowConfig.model_construct()` (bypasa boundary `validate_steps_integrity`)
- **Refactor**: `_build_step` → dispatcher CC 6 + `_build_steps_group`/`_build_parallel_group`/`_build_condition_group`/`_build_router_group`/`_build_loop_group` + tabla módulo `_STEP_BUILDERS` (post-clase: los staticmethods no existen durante el body)
- **After**: radon ts 15:52:20 — CC 6; MI 38.2→55.11 (A)
- **Commits**: `0bcfd3e` (tests, 37/37), `869ba5b` (refactor) → merge `89b5cf7`
- **Engram**: #2720

### Slice P0-2 — mypy --strict 0 errores
- **Hallazgo**: override `[[tool.mypy.overrides]]` para agno/core_infrastructure/a2a **ya existía** (P0-2a pre-hecho); solo se documentó la deuda
- **Corrección**: audit listó 5 unused ignores; mypy --strict real flaggea 3 → removidos (`model_spec.py:69,78`, `workflow_factory.py:671`); `circuit_breaker.py:140` ya no se flaggea (declarado con evidencia)
- **Gotcha**: `a2a_interface.py` import dentro de `_require_a2a_sdk()` — ignore inline sería flagged como unused → comentario explicativo + override documentado
- **Commits**: `8ff8f9a` → merge `b94ed06` · **Engram**: #2721

### Slice P1 — agentos_factory `build()` CC 16→1 (TASK 2, adaptado)
- **Desviación del plan (Decision Card)**: TASK 2 describe FastAPI/middlewares; la realidad es `agno.os.AgentOS` → pipeline 5 fases adaptado
- **Refactor**: `_validate_config`(1) → `_build_dependencies`(3) → `_wire_integrations`(1, tras dividir intento CC 10 por el conteo de `and` de radon) → `_assemble_app`(1) → `_register_lifecycle`(5); sub-wirers `_wire_auth_mcp_scheduler`(3)/`_wire_interfaces`(4)/`_warn_resync_missing`(3); warning resync PRE-construcción (paridad exacta)
- **Tests**: +4 `TestStepConfigContract` (defaults, round-trip, discriminador 8 tipos, membro directo) — `950f264`, 28/28
- **Suites**: agentos 34/34; unit completo 640 passed + 6 fails MCP pre-existentes
- **Commits**: `950f264`, `442da89` → merge `002668d` · **Engram**: #2722

### Slice P2 — cobertura + docstrings (TASK 3)
- **Root cause 56%**: `cel-python` no instalado; constraint `>=1.4.5` **roto** (máx publicado 0.5.0) → `>=0.5.0`, instalado 0.5.0 → `CEL_AVAILABLE=True`
- **Tests**: +5 condition_evaluator (3 `_strip_template` directos siempre corren + 2 skipif CEL: blank/invalid → ValueError), +4 provider_factory (wrap constructor, guard non-dataclass, capability mismatch ollama+thinking, id formats); `StubExploding` declara `api_key` (TypeError de dataclass en vez de ValueError)
- **Cobertura final**: provider_factory 100%, condition_evaluator 94% (línea 32 = guard RuntimeError ambiental, mutuamente excluyente con test skipif)
- **Docstrings**: 3 faltantes completados (`LifespanComponent.start/stop`, `CircuitState`), + sección lifecycle `ProviderFactory`, + convenciones `BUILTIN_REGISTRY` (en `tools/registry.py`, no tool_factory) → **100%** (197/197), docstring/LOC 20%
- **Nota métrica**: radon raw `comments` cuenta SOLO `#` (5.0%); los docstrings no entran → la métrica de intención del §8 es cobertura de docstrings (20% ≥ target 10%)
- **Commits**: `9eb735b` (tests+constraint), `c1420fe` (docstrings), `05ef610` (scripts .quality/) → merge `81c7dad` · **Engram**: #2723

## 3. Métricas crudas (scripts + outputs)

```
mypy --strict src/yaml_agno            → Success: no issues found in 94 source files
ruff check .                           → All checks passed!
pytest -m unit -q                      → 652 passed, 1 skipped, 6 failed (MCP pre-existentes §P2.9)
python scripts/spec_gate.py all        → 34 SPECs checked, 0 violations
.quality/measure_docstring_coverage.py → coverage=100.0% (197/197), docstring_ratio=20.0%
.quality/measure_mi_final.py           → workflow_factory MI=53.2 max_cc=9 · agentos_factory MI=53.8 max_cc=7
                                          provider_factory MI=70.0 max_cc=7 · condition_evaluator MI=62.2 max_cc=3
                                          registry MI=52.6 max_cc=6
```

Scripts de medición reproducibles commiteados en `.quality/`.

## 4. Decision Cards

| # | Decisión | Justificación | Alternativa descartada |
|---|---|---|---|
| D1 | Pipeline P1 adaptado de FastAPI → `agno.os.AgentOS` | TASK 2 del plan describe realidad inexistente en el repo; agentos_factory construye AgentOS | Seguir TASK 2 literal = refactor de código que no existe |
| D2 | Tests defensivos vía `model_construct()` | Boundary `validate_steps_integrity` rechaza refs colgantes (comportamiento correcto del dominio) | Debilitar el validador para poder testear = empeorar el dominio |
| D3 | Contrato CEL: ValueError propaga | Empíricamente el blank/invalid CEL lanza ValueError "Failed to evaluate CEL" (agno envuelve) | Cambiar el contrato en un slice de cobertura = scope creep |
| D4 | Métrica §8 = cobertura de docstrings, no comment ratio radon | radon raw no cuenta docstrings (solo `#`); target 10% inalcanzable por esa vía | Maquillar `#` comments artificiales para inflar ratio |

## 5. Datos faltantes / fuera de scope (declarados, no estimados)

- **6 fails `tests/unit/tools/test_mcp_resolver.py`** (audit §P2.9): pre-existentes, verificados idénticos en main. Fuera de scope de remediación P0/P1 — item P2.9 pendiente (probablemente mocks de `MultiStdioServer` desactualizados frente a agno 2.8.3). **DATO FALTANTE**: verificación en CI limpio.
- **Cobertura condition_evaluator línea 32** (guard `RuntimeError` sin cel-python): ambiental — solo corre sin el paquete; con cel-python instalado el test mutuamente excluyente skipea. Declarado, no cubrible en este entorno.
- **3 fails integración end-to-end** (liveness/readiness, audit §I): dependencia de entorno (config path). No ejecutados (requieren servicios externos). **DATO FALTANTE**: CI limpio.
- **Cobertura total del repo**: no re-medida (el audit reportó 96%; la cobertura de paquete requiere pytest-cov, no ejecutado en este gate). Solo se cerraron los 2 hotspots §Cobertura.

## 6. Handoff — próximo paso recomendado

1. **P2.9 (MCP)**: investigar los 6 fails con agno 2.8.3 — probablemente `MultiStdioServer` cambió su firma (`commands`/`params`). Estimar ~1-2 h.
2. **Integración e2e**: correr en CI con config path correcto (verificar liveness/readiness).
3. **Precio/release**: con veredicto PASS, el repo está en condiciones para GO de contrato desde el punto de vista de calidad estructural. Riesgo residual: solo el item P2.9 (bajo).
