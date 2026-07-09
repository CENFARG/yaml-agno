---
change: team-factory
spec: SPEC_01
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/team-factory/proposal.md (engram #1956)
  - spec: openspec/changes/team-factory/specs/team-factory/spec.md (BDD SSOT for behavior, 8 reqs / 11 scenarios)
  - design: openspec/changes/team-factory/design.md (literal code, 6 ADRs, 3 files)
  - shipped_pattern: src/yaml_agno/factories/agent_factory.py (AgentFactory.build @staticmethod — style template)
  - consumed_contract: src/yaml_agno/models/config/team_config.py (SPEC_02, TeamConfig + TeamMemberConfig)
strict_tdd: true
test_command: "python -m pytest"
---

# Tasks: TeamFactory — SPEC_01 slice #3 (TeamConfig + agents dict → agno.Team)

> **SSOT normativo**: `openspec/changes/team-factory/specs/team-factory/spec.md`
> (8 Requirements, 11 Scenarios). Toda discrepancia se resuelve a favor de la
> spec. El `design.md` provee el código **literal** del factory (byte-for-byte).
>
> **Strict TDD ACTIVO** (`sdd-init/doc.reca` engram #531: `strict_tdd: true`,
> test runner `python -m pytest`). El task de comportamiento (Phase 2) sigue
> RED → GREEN. Los tasks de wiring (scaffolding, re-export) no requieren RED
> pero sí verificación.
>
> **VERIFICADO empíricamente (orchestrator)**:
> `Team(members=[Agent], mode=TeamMode.coordinate, name='t', instructions='x')`
> construye → `type: Team | mode: TeamMode.coordinate | members: 1 |
> instructions: x`. Los 4 kwargs funcionan. `cfg.mode` ya es enum `TeamMode`
> (sin envolver). `instructions=None` pasa sin error.
>
> **Prerequisito satisfecho**: `tests/unit/factories/` ya existe (creado en
> el slice #1 `agent-factory-basic`). No se vuelve a crear el namespace.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~80-110 (3 files: ~45 factory + ~5 init re-export delta + ~40-60 tests) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (el slice cabe holgado en el budget de 400 líneas) |
| Delivery strategy | ask-on-risk (default; decide el orquestador — sin cachear en esta fase) |
| Chain strategy | size-exception (single PR; no se necesita cadena) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | TeamFactory completo: RED tests + GREEN factory + re-export + verification | PR 1 (único) | base = feature/team-factory branch; `tests/unit/factories/` ya existe; incluye `factories/__init__.py` delta (agregar `TeamFactory` al re-export existente) |

> Un único PR slice con start claro (RED test Phase 2), finish claro (GREEN
> Phase 3 + verification Phase 4), scope autónomo y rollback (`git revert`).
> Rollback: borrar `team_factory.py`, revertir `__init__.py`, borrar test.

## Phase 1: Baseline & Scaffolding (Foundation)

> Satisface: precondition para todos los Requirements (namespace de tests ya
> existe desde slice #1; solo se confirma el punto de partida).

- [x] 1.1 Verificar árbol limpio y HEAD en la branch del slice (`git status` limpio). Bloqueante: si hay cambios sin commitear, abortar.
- [x] 1.2 Confirmar que `src/yaml_agno/factories/__init__.py` YA existe con `AgentFactory` re-exported (1 símbolo). Confirmar que `src/yaml_agno/factories/team_factory.py` NO existe.
- [x] 1.3 Confirmar que `tests/unit/factories/` existe (con `test_agent_factory.py` del slice #1) y que `tests/unit/factories/test_team_factory.py` NO existe. NO crear `__init__.py` (ya existe del slice #1).
- [x] 1.4 (Sin commit en esta fase — no hay archivos creados/modificados aún.)

## Phase 2: RED — Tests de TeamFactory (TDD estricto)

> Satisface: TODOS los Requirements de la spec. Cubre los 11 escenarios de la
> spec. Test falla con `ImportError` (módulo no existe aún).

- [x] 2.1 **RED**: Crear `tests/unit/factories/test_team_factory.py` con `import pytest`, `from agno.agent import Agent`, `from agno.team.team import Team`, `from agno.team.mode import TeamMode`, `from yaml_agno.factories import TeamFactory`, `from yaml_agno.models.config.team_config import TeamConfig`, `from yaml_agno.models.config.team_member_config import TeamMemberConfig` (o el path real del schema SPEC_02 — confirmar import path antes de escribir). Marker a nivel módulo/clase: `@pytest.mark.unit`. El test falla con `ImportError` (`TeamFactory` aún no se re-exporta). Verificar RED ejecutando `python -m pytest tests/unit/factories/test_team_factory.py -m unit` → ImportError. Commit: `test: add RED tests for TeamFactory`.
- [ ] 2.2 Tests a cubrir (dentro de 2.1), mapeados a escenarios spec — **usa instancias reales `agno.Agent` construidas inline con `model="openai:gpt-4o"` (no hay network al construir)**:
  - **GREEN golden 2-member**: `TeamConfig(name="t", mode=TeamMode.coordinate, members=[{member:"m1",agent:"a1"},{member:"m2",agent:"a2"}])` + `agents={"a1":agentA,"a2":agentB}` → `isinstance(result, Team)` + `result.members == [agentA, agentB]` + `result.mode is TeamMode.coordinate` + `result.name == "t"`. (Scenario "Golden path — equipo de 2 miembros resueltos")
  - **GREEN golden instructions**: cfg con `instructions="You orchestrate invoices."` → `result.instructions == "You orchestrate invoices."`. (Scenario "Golden path con instructions pasadas por completo")
  - **GREEN member order**: `members=[{agent:"z"},{agent:"a"},{agent:"m"}]` con 3 agents → `result.members == [agents["z"], agents["a"], agents["m"]]`. (Scenario "Orden de miembros preservado")
  - **RED missing agent**: `cfg.members=[{member:"x",agent:"no_existe"}]`, `agents={}` → `pytest.raises(ValueError, match="no_existe")`. Verificar que `Team` nunca se instancia (raise ocurre antes del constructor). (Scenario "RED — referencia de agente inexistente")
  - **GREEN mode passthrough**: `cfg.mode=TeamMode.route` → `result.mode is TeamMode.route` (misma instancia, sin conversión). (Scenario "Passthrough de mode")
  - **GREEN instructions None**: `cfg.instructions=None` → `result.instructions is None`. (Scenario "Instructions None no rompe")
  - **GREEN no model**: cfg sin campo model (no existe) → `result.model is None`. (Scenario "Sin model — Team se construye igual")
  - **GREEN workflows opaco**: `cfg.workflows=[{"workflow":"x","steps":[...]}]` → `isinstance(result, Team)` sin error, y `result` no recibe ningún kwarg derivado de workflows. (Scenario "Workflows presentes, sin error")
  - **GREEN 4 modos**: un sub-test por cada `TeamMode` (`coordinate` 1+ miembro, `route` ≥2, `broadcast` ≥2, `tasks` 1+) → `result.mode is <modo>`. (Scenarios "coordinate/route/broadcast/tasks construyen")
  - **GREEN schema delegación**: intentar `TeamConfig(name="t", mode=TeamMode.route, members=[único])` → Pydantic `ValueError`/`ValidationError` ANTES de `build()` (factory nunca invocada). (Scenario "Modo route con 1 miembro — error viene del schema")
  - **GREEN import raíz**: `from yaml_agno.factories import TeamFactory` + `callable(TeamFactory.build)`. (Contract smoke)
  - **GREEN colección marker**: `python -m pytest -m unit tests/unit/factories/` selecciona y pasa todos (agent + team) offline.

## Phase 3: GREEN — TeamFactory (implementación mínima, código literal del design)

> Satisface: Requirements "TeamFactory construye agno.Team válido", "Resolución
> de miembros por nombre", "Mapeo directo de TeamMode", "Identidad y
> comportamiento pasados", "NO resolución de model", "Slot opaco workflows
> ignorado", "Sin re-validación", "Los 4 modos construyen", "Re-export".
> Código **literal** del `design.md` §"Class-by-Class Model".

- [x] 3.1 **GREEN**: Crear `src/yaml_agno/factories/team_factory.py` con `TeamFactory.build(cfg, agents) -> Team` staticmethod. Código byte-for-byte del `design.md`: imports `from agno.agent import Agent`, `from agno.team.team import Team`, `from yaml_agno.models.config.team_config import TeamConfig`; loop `for member in cfg.members:` con `if agent_name not in agents: raise ValueError(f"Agent not found: {agent_name!r}. Check the 'agents:' section of your YAML.")`; `resolved_members.append(agents[agent_name])`; `return Team(members=resolved_members, mode=cfg.mode, name=cfg.name, instructions=cfg.instructions)`. **MUST NOT** envolver `cfg.mode` en `TeamMode()` (passthrough). **MUST NOT** pasar `model=`. **MUST NOT** procesar `workflows`/`description`/`tags`/`metadata`.
- [x] 3.2 **GREEN**: Modificar `src/yaml_agno/factories/__init__.py` para agregar `from yaml_agno.factories.team_factory import TeamFactory` y extender `__all__` a `["AgentFactory", "TeamFactory"]`. Código literal del `design.md`. El re-export de `AgentFactory` queda intacto. Verificar smoke: `python -c "from yaml_agno.factories import TeamFactory; print(TeamFactory)"`.
- [x] 3.3 Verificar GREEN: `python -m pytest tests/unit/factories/ -m unit` → todos verde (agent + team). Commit: `feat: add TeamFactory (member resolution by name, 4-kwarg Team construction, opaque slots deferred)`.

## Phase 4: Verification (no implementation)

> Satisface: Requirement "Tests con marker @pytest.mark.unit" + `design.md`
> §Verification Strategy.

- [x] 4.1 Ejecutar `python -m pytest -m unit tests/unit/factories/test_team_factory.py` → todos verde. Reportar conteo.
- [x] 4.2 Ejecutar `python -m pytest -m unit tests/unit/factories/` → verde integral (agent_factory + team_factory; el re-export no rompe `AgentFactory`).
- [x] 4.3 Ejecutar `ruff check src/yaml_agno/factories tests/unit/factories` — limpio (line-length 120, import sort). Corregir si findings.
- [x] 4.4 Ejecutar `mypy src/yaml_agno/factories` — limpio. **Caveat**: Agno stubs con `ignore_missing_imports=true` → import path erróneo NO falla type-check; el contrato REAL es el runtime import del test.
- [x] 4.5 Smoke runtime: `python -c "from yaml_agno.factories import TeamFactory; print(TeamFactory)"` funciona sin error.
- [x] 4.6 Runtime smoke de construcción: `python -c "from agno.agent import Agent; from agno.team.team import Team; from agno.team.mode import TeamMode; a=Agent(name='x', model='openai:gpt-4o'); t=Team(members=[a], mode=TeamMode.coordinate, name='t', instructions='x'); print(type(t).__name__, t.name, t.mode, len(t.members), t.instructions)"` → imprime `Team t TeamMode.coordinate 1 x`.
- [x] 4.7 Confirmar `git diff openspec/changes/team-factory/specs/` vacío — la spec NO se mutó durante implementación.
- [x] 4.8 Confirmar `git diff src/yaml_agno/models/ specs/ openspec/specs/` vacío — SPEC_02 (TeamConfig) + specs read-only intocados (este slice solo añade factory + tests).
- [x] 4.9 Commit final si hay fixes de lint/type: `style: ruff/mypy compliance for team-factory`. NO committear si 4.1-4.8 ya verde.

## Phase 5: Commit Granular (conventional, per fase)

- [x] 5.1 Confirmar que los commits granulares siguen conventional format: `test:` (2.1 RED), `feat:` (3.3 GREEN), `style:` (4.9 si aplica). El histórico de commits = el avance TDD. (Phase 1 no commitea — solo verificación.)
- [x] 5.2 NO commitear este tasks.md (el apply sub-agent actualiza los checkboxes `[x]` conforme avanza). El commit final lo decide el orquestador según delivery_strategy.

## TDD Compliance Matrix (trazabilidad spec → tasks)

| Spec Requirement | RED task | GREEN task | Scenarios cubiertos |
|------------------|----------|------------|---------------------|
| TeamFactory construye un agno.Team válido | 2.1, 2.2 | 3.1, 3.2 | Golden 2-member (isinstance + mode + name), Golden instructions |
| Resolución de miembros por nombre | 2.1, 2.2 | 3.1 | Golden 2-member (members==[a1,a2]), Member order preservado |
| Referencia de agente faltante — error claro | 2.1, 2.2 | 3.1 | RED missing agent (ValueError match "no_existe") |
| Mapeo directo de TeamMode | 2.1, 2.2 | 3.1 | Mode passthrough (`is` misma instancia) |
| Identidad y comportamiento pasados por completo | 2.1, 2.2 | 3.1 | Golden instructions (str completa), Instructions None (==None) |
| NO resolución de model | 2.1, 2.2 | 3.1 | No model (result.model is None) |
| Slot opaco `workflows` ignorado sin error | 2.1, 2.2 | 3.1 | Workflows opaco (isinstance sin error) |
| Sin re-validación de invariantes de TeamConfig | 2.1, 2.2 | 3.1 | Schema delegación (route+1miembro → ValidationError pre-build) |
| Los 4 modos construyen correctamente | 2.1, 2.2 | 3.1 | coordinate, route (≥2), broadcast (≥2), tasks |
| Re-export desde factories/__init__.py | 2.1, 2.2 | 3.2 | Import raíz (`from yaml_agno.factories import TeamFactory`) |
| Tests con marker @pytest.mark.unit | 2.1 | — | Colección `-m unit` |
| SSOT no mutado (SPEC_02, specs) | — (invariante diff review) | — | 4.7, 4.8 (spec + SPEC_02 + specs/ vacíos en diff) |

## Implementation Order (razón)

Secuencia estrictamente dependiente y lineal (no hay paralelismo — el change es
un slice cohesivo de ~80-110 líneas, 3 archivos):

1. **Phase 1** (baseline): confirma el punto de partida — `factories/__init__.py`
   ya re-exporta `AgentFactory`, `tests/unit/factories/` ya existe del slice #1,
   `team_factory.py` y `test_team_factory.py` NO existen. Sin commits.
2. **Phase 2** (RED): escribe TODOS los tests primero en
   `test_team_factory.py`. Falla con `ImportError` porque `TeamFactory` no se
   re-exporta. Usa `agno.Agent` reales con `model="openai:gpt-4o"` (construcción
   sin network). Commit `test:`.
3. **Phase 3** (GREEN): crea `team_factory.py` con el código literal del design
   (loop + ValueError + 4 kwargs) y actualiza `__init__.py` (delta de 1 import +
   1 item en `__all__`). Tests pasan. Commit `feat:`.
4. **Phase 4** (verification): pytest/ruff/mypy + runtime smoke de construcción
   (Team con Agent inline) + invariantes de diff (spec y SPEC_02 no mutados).
5. **Phase 5** (commits): el histórico conventional emerge de las fases
   previas.

Cada Phase commitea de forma independiente (salvo Phase 1 que solo verifica).
Un único PR (no chained) cubre Phase 2+3+4 — el change entero cabe en el budget
de 400 líneas.
