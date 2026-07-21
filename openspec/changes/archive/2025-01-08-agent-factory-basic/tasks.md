---
change: agent-factory-basic
spec: agent-factory-basic
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/agent-factory-basic/proposal.md
  - spec: openspec/changes/agent-factory-basic/specs/agent-factory-basic/spec.md
  - design: openspec/changes/agent-factory-basic/design.md
strict_tdd: true
test_command: "python -m pytest"
---

# Tasks: AgentFactory — primer slice (AgentConfig → agno.Agent)

> **SSOT normativo**: `openspec/changes/agent-factory-basic/specs/agent-factory-basic/spec.md`
> (spec CORREGIDA — refleja el comportamiento verificado de Agno). Toda
> discrepancia se resuelve a favor de la spec. El `design.md` provee el código
> literal del factory.
>
> **Strict TDD ACTIVO** (`openspec/config.yaml` → `apply.tdd: true`). El task
> de comportamiento (Phase 2) sigue RED → GREEN. Los tasks de wiring
> (scaffolding, re-export) no requieren RED pero sí verificación.
>
> **CRITICAL — modelo resuelto**: `Agent(model="openai:gpt-4o").model` es una
> instancia de `agno.models.base.Model` (NO el string). El factory NO cambia
> (passthrough del string es correcto); solo los asserts del test reflejan la
> resolución: `isinstance(result.model, Model)` + `result.model.id`. Import:
> `from agno.models.base import Model`. NO agregar `partition()` ni traducción.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~80-120 (4 files: ~25 factory + ~5 init re-export + ~1 test marker + ~70-90 tests) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (todo el change cabe holgado en el budget de 400 líneas) |
| Delivery strategy | ask-on-risk (default; decide el orquestador — sin cachear en esta fase) |
| Chain strategy | size-exception (single PR; no se necesita cadena) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | AgentFactory completo: scaffolding + RED tests + GREEN factory + verification | PR 1 (único) | base = feature/agent-factory-basic branch; incluye `factories/__init__.py` re-export + `tests/unit/factories/` namespace |

> Un único PR slice con start claro (RED test Phase 2), finish claro (GREEN
> Phase 3 + verification Phase 4), scope autónomo y rollback (`git revert`).

## Phase 1: Baseline & Scaffolding (Foundation)

> Satisface: precondition para todos los Requirements (namespace de tests +
> confirmación de `factories/__init__.py` vacío).

- [x] 1.1 Verificar árbol limpio y HEAD en `feature/agent-factory-basic` (`git status` limpio). Bloqueante: si hay cambios sin commitear, abortar.
- [x] 1.2 Confirmar que `src/yaml_agno/factories/__init__.py` existe vacío (1 línea del bootstrap) — NO modificar aún (se hace en Phase 3). Confirmar que `src/yaml_agno/factories/agent_factory.py` NO existe.
- [x] 1.3 Crear `tests/unit/factories/__init__.py` (package marker vacío o con docstring de 1 línea). Confirmar que `tests/unit/factories/` no existía previamente.
- [x] 1.4 Commit: `chore: scaffold tests/unit/factories/ namespace`.

## Phase 2: RED — Tests de AgentFactory (TDD estricto)

> Satisface: TODOS los Requirements de la spec excepto el wiring puro. Cubre los
> 13 escenarios de la spec. Test falla con ImportError (módulo no existe).

- [x] 2.1 **RED**: Crear `tests/unit/factories/test_agent_factory.py` con `import pytest`, `from agno.agent import Agent`, `from agno.models.base import Model`, `from yaml_agno.factories import AgentFactory`, `from yaml_agno.models.config.agent_config import AgentConfig`. Marker a nivel módulo/clase: `@pytest.mark.unit`. El test falla con `ImportError` (AgentFactory aún no se re-exporta). Verificar RED ejecutando `python -m pytest tests/unit/factories/ -m unit` → ImportError. Commit: `test: add RED tests for AgentFactory`.
- [x] 2.2 Tests a cubrir (dentro de 2.1), mapeados a escenarios spec:
  - **GREEN minimal**: `AgentConfig(name="agent-01", model="openai:gpt-4o")` → `isinstance(result, Agent)`. (Scenario "Instancia válida retornada desde config mínima")
  - **GREEN 4 campos**: config con name+model+instructions+description → `result.name`, `result.instructions`, `result.description` iguales a cfg; `result.model` es instancia de `Model`. (Scenario "El retorno mapea los cuatro campos de identidad")
  - **GREEN name+model minimal**: `result.name == "my-agent"` + `result.model.id == "gpt-4o"`. (Scenario "Config mínima mapea name y model")
  - **GREEN identidad completa**: los 4 campos coinciden sin transformación. (Scenario "Identidad completa mapea los cuatro campos")
  - **GREEN model resuelto a Model**: `isinstance(result.model, Model)` + `result.model.id == "gpt-4o"` + `result.model.provider == "OpenAI"`. (Scenario "`agent.model` es una instancia de `Model` resuelta por Agno")
  - **GREEN slots opacos tolerados**: config con `memory={"driver":"sqlite"}`, `tools=[{"name":"t"}]` → `isinstance(result, Agent)` sin error. (Scenario "Slots opacos presentes no rompen la construcción")
  - **EDGE todos los opacos**: config con 9 slots + tags + metadata poblados → factory ignora los 11 campos, retorna Agent válido. (Scenario "Todos los slots opacos poblados simultáneamente")
  - **GREEN no side-effects**: spy/mock sobre `Agent.run` y `Agent.arun` → ni run ni arun llamados tras `build()`. (Scenario "`build()` no invoca `run()` ni `arun()`")
  - **GREEN idempotencia**: dos configs idénticos → `agent_a is not agent_b`, `agent_a.name == agent_b.name`, `type(agent_a.model) is type(agent_b.model)`, `agent_a.model.id == agent_b.model.id`. (Scenario "Dos llamadas producen agents equivalentes")
  - **GREEN instructions=None**: `AgentConfig(name="x", model="openai:gpt-4o", instructions=None)` → Agent válido + `result.instructions is None`. (Scenario "Config con `instructions=None`")
  - **RED delegación validación**: `AgentConfig(name="", model="bad")` → Pydantic `ValidationError` ANTES de `build()` (factory nunca se alcanza). (Scenario "La fábrica delega validación a SPEC_02")
  - **GREEN import raíz**: `from yaml_agno.factories import AgentFactory` + `callable(AgentFactory.build)`. (Scenario "Import desde el paquete raíz")
  - **GREEN colección marker**: `python -m pytest -m unit tests/unit/factories/` selecciona y pasa todos los tests offline. (Scenario "Colección de tests con marker unit")

## Phase 3: GREEN — AgentFactory (implementación mínima)

> Satisface: Requirements "fábrica construye agno.Agent", "Mapeo directo",
> "Passthrough de model", "Slots opacos ignorados", "instructions=None válido",
> "Re-export desde factories/__init__.py". Código literal del `design.md`.

- [x] 3.1 **GREEN**: Crear `src/yaml_agno/factories/agent_factory.py` con `AgentFactory.build(cfg) -> Agent` staticmethod, 4-field mapping (`name`, `instructions`, `description`, `model`), model passthrough directo (SIN `partition()`), slots opacos ignorados. Código literal del `design.md` §"Class-by-Class Model". Imports: `from agno.agent import Agent` + `from yaml_agno.models.config.agent_config import AgentConfig`.
- [x] 3.2 **GREEN**: Modificar `src/yaml_agno/factories/__init__.py` (vacío) para re-exportar `AgentFactory` + `__all__`. Código literal del `design.md`. Verificar smoke: `python -c "from yaml_agno.factories import AgentFactory; print(AgentFactory)"`.
- [x] 3.3 Verificar GREEN: `python -m pytest tests/unit/factories/ -m unit` → todos verde. Commit: `feat: add AgentFactory (4-field map, model passthrough, opaque slots ignored)`.

## Phase 4: Verification (no implementation)

> Satisface: Requirement "Tests unitarios con marker @pytest.mark.unit" +
> `design.md` §Verification Strategy.

- [x] 4.1 Ejecutar `python -m pytest -m unit` — todos los tests del change seleccionados y verde. Reportar conteo.
- [x] 4.2 Ejecutar `ruff check .` — limpio (line-length 120, import sort). Corregir si findings.
- [x] 4.3 Ejecutar `mypy src/yaml_agno` — limpio. **Caveat**: Agno stubs con `ignore_missing_imports=true` → import path erróneo NO falla type-check; el contrato REAL es el runtime import del test.
- [x] 4.4 Smoke runtime: `python -c "from yaml_agno.factories import AgentFactory; print(AgentFactory)"` funciona sin error.
- [x] 4.5 Confirmar `git diff openspec/changes/agent-factory-basic/specs/` vacío — la spec NO se mutó durante implementación.
- [x] 4.6 Confirmar `git diff src/yaml_agno/models/ specs/` vacío — SPEC_02 (AgentConfig) + specs read-only intocados.
- [x] 4.7 Commit final si hay fixes de lint/type: `style: ruff/mypy compliance for agent-factory-basic`. NO committear si 4.1-4.6 ya verde.

## Phase 5: Commit Granular (conventional, per fase)

- [x] 5.1 Confirmar que los commits granulares siguen conventional format: `chore:` (1.4 scaffolding), `test:` (2.1 RED), `feat:` (3.3 GREEN), `style:` (4.7 si aplica). El histórico de commits = el avance TDD.
- [x] 5.2 NO commitear este tasks.md (el apply sub-agent actualiza los checkboxes `[x]` conforme avanza). El commit final lo decide el orquestador según delivery_strategy.

## TDD Compliance Matrix (trazabilidad spec → tasks)

| Spec Requirement | RED task | GREEN task | Scenarios cubiertos |
|------------------|----------|------------|---------------------|
| Fábrica construye agno.Agent real | 2.1, 2.2 | 3.1, 3.2 | GREEN instancia válida, GREEN no I/O |
| Mapeo directo sin traducción de nombres | 2.1, 2.2 | 3.1 | GREEN 4 campos, GREEN minimal, GREEN identidad completa |
| Passthrough de model (`:` nativo) | 2.1, 2.2 | 3.1 | GREEN model resuelto a `Model` (id/provider) |
| Slots opacos + tags + metadata ignorados | 2.1, 2.2 | 3.1 | GREEN tolerados, EDGE los 11 poblados |
| Ausencia de side-effects/red | 2.1, 2.2 | 3.1 | GREEN no run/arun |
| Idempotencia de build() | 2.1, 2.2 | 3.1 | GREEN dos agents equivalentes (mismo tipo Model + mismo id) |
| instructions=None válido | 2.1, 2.2 | 3.1 | GREEN config minimal con None |
| Validación delegada a SPEC_02 | 2.1, 2.2 | 3.1 | RED ValidationError antes de build |
| Re-export desde factories/__init__.py | 2.1, 2.2 | 3.2 | GREEN import raíz |
| Tests con marker @pytest.mark.unit | 2.1 | — | GREEN colección `-m unit` |
| Exclusión DependencyManager/run/arun | — (invariante diff review) | — | 4.5, 4.6 (spec + SPEC_02 no mutados) |

## Implementation Order (razón)

Secuencia estrictamente dependiente y lineal (no hay paralelismo — el change es
un slice cohesivo de ~80-120 líneas):

1. **Phase 1** (scaffolding): crea el namespace `tests/unit/factories/` y
   confirma el punto de partida (`factories/__init__.py` vacío). Sin código
   de comportamiento — wiring puro.
2. **Phase 2** (RED): escribe TODOS los tests primero. Falla con `ImportError`
   porque `AgentFactory` no se re-exporta. Los asserts usan `isinstance(Model)`
   + `.id` según el comportamiento verificado de Agno.
3. **Phase 3** (GREEN): implementa el factory con el código literal del design
   (4 kwargs, passthrough). Tests pasan. Commit granular `feat:`.
4. **Phase 4** (verification): pytest/ruff/mypy + invariantes de diff (spec y
   SPEC_02 no mutados).
5. **Phase 5** (commits): el histórico conventional emerge de las fases
   previas.

Cada Phase commitea de forma independiente. Un único PR (no chained) cubre
Phase 1+2+3+4 — el change entero cabe en el budget de 400 líneas.
