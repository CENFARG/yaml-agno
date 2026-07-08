---
change: agent-config-schema
spec: SPEC_02
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/agent-config-schema/proposal.md (engram #1877)
  - spec: openspec/changes/agent-config-schema/specs/agent-config-schema/spec.md (engram #1878)
  - design: openspec/changes/agent-config-schema/design.md (engram #1879)
strict_tdd: true
test_command: "python -m pytest"
---

# Tasks: Domain Model — YAML Configuration Schemas (Pydantic V2)

> **SSOT normativo**: `specs/SPEC_02_DOMAIN_MODEL.md` (read-only). Este checklist
> es el HOW operativo; toda discrepancia se resuelve a favor de SPEC_02 y del
> `design.md` (obs 1879) que contiene el código Pydantic V2 fiel y verificado.
>
> **Strict TDD ACTIVO** (`openspec/config.yaml` → `apply.tdd: true`). Este cambio
> **TIENE behavioral RED real** (los validadores rechazan input inválido). Cada
> task de comportamiento sigue RED → GREEN → REFACTOR. Los tasks de wiring
> (scaffolding, package markers, re-export) no requieren RED pero sí verificación.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1000-1300 (12 files: ~600-800 schemas + ~400-500 tests) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (value objects: DIReference + scaffolding) → PR 2 (AgentConfig + TeamConfig) → PR 3 (WorkflowConfig + StepConfig + wiring) |
| Delivery strategy | ask-on-risk (default; sin cachear en esta fase — decide el orquestador) |
| Chain strategy | pending (decisión del usuario: stacked-to-main | feature-branch-chain | size-exception) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Scaffolding dirs + DIReference value object (frozen, tokens, resolve) | PR 1 | base = feature/tracker branch; incluye `tests/unit/value_objects/` + package markers |
| 2 | AgentConfig (13 fields + 9 opaque slots + 2 validators) + TeamConfig + TeamMemberConfig (4 validators) | PR 2 | base = PR 1 branch; cubre 5 scenarios RED + golden paths |
| 3 | StepConfig (16 fields + type-specific validator) + WorkflowConfig (steps_integrity) + `models/__init__.py` re-export + enums runtime import test | PR 3 | base = PR 2 branch; cierra el contrato público de `yaml_agno.models` |

> Cada PR slice tiene: start claro (RED test), finish claro (GREEN + lint/type),
> scope autónomo y rollback (`git revert`). Para `feature-branch-chain`, PR #1
> base = tracker; PR #2 base = PR #1; PR #3 base = PR #2. Si GitHub muestra
> cambios de slices previos en un child diff, retarget/rebase antes de review.

## Phase 1: Baseline & Scaffolding (Foundation)

- [x] 1.1 Verificar árbol limpio y HEAD en la rama feature del change (`git status` limpio, rama correcta). Bloqueante: si hay cambios sin commitear, abortar.
- [x] 1.2 Crear `src/yaml_agno/models/config/__init__.py` (package marker vacío con docstring de 1 línea).
- [x] 1.3 Crear `src/yaml_agno/models/value_objects/__init__.py` (package marker vacío con docstring de 1 línea).
- [x] 1.4 Crear `tests/unit/__init__.py`, `tests/unit/models/__init__.py`, `tests/unit/value_objects/__init__.py` (package markers). Verificar que `tests/unit/` no existía previamente.
- [x] 1.5 Confirmar que `src/yaml_agno/models/__init__.py` existe vacío (heredado del bootstrap) — NO modificar aún (se hace en Phase 5). Commit: `chore: scaffold models/{config,value_objects} + tests/unit/`.

## Phase 2: DIReference Value Object (TDD estricto)

> Satisface: Requirement "Validador de formato de template de DIReference" + "Inmutabilidad de DIReference" + Requirement "Seis clases Pydantic V2" (parte frozen=True).

- [x] 2.1 **RED**: `tests/unit/value_objects/test_di_reference.py` — escribir tests que fallen (ImportError: módulo aún no existe). Cubrir: golden single/multi token, `tokens` extraction, `resolve` basic + literal + missing-key (KeyError), invalid format no-token, invalid format uppercase, frozen immutability. Marker `@pytest.mark.unit`. Commit: `test: add RED tests for DIReference value object`.
- [x] 2.2 **GREEN**: Crear `src/yaml_agno/models/value_objects/di_reference.py` con `DIReference(frozen=True)` + `validate_format` + `tokens` property + `resolve()` self-contained. Código literal del `design.md` §4. Verificar: `python -m pytest tests/unit/value_objects/ -m unit` verde. Commit: `feat: add DIReference value object (frozen, tokens, resolve)`.

## Phase 3: AgentConfig Schema (TDD estricto)

> Satisface: Requirements "Seis clases" + "Nueve slots opacos" + "Ausencia de user_id" + "Validador de caracteres de name" + "Validador de formato de model".

- [x] 3.1 **RED**: `tests/unit/models/test_agent_config.py` — tests failing. Cubrir escenarios spec: GREEN instanciación mínima, GREEN 9 opaque slots aceptan dicts, RED invalid model format (no-slash / empty provider / empty model_id), RED invalid name characters, RED extra field forbidden, RED user_id ausente (no en `model_fields`). Marker `@pytest.mark.unit`. Commit: `test: add RED tests for AgentConfig`.
- [x] 3.2 **GREEN**: Crear `src/yaml_agno/models/config/agent_config.py` con `AgentConfig(extra="forbid")`, 13 fields + 9 opaque slots + type aliases PEP 695 + 2 field_validators (`validate_name_characters`, `validate_model_format`). Código literal del `design.md` §1. Verificar tests verde. Commit: `feat: add AgentConfig schema (13 fields + 9 opaque slots + 2 validators)`.

## Phase 4: TeamConfig + TeamMemberConfig (TDD estricto)

> Satisface: Requirements "Enums TeamMode importados" + "Validador de members únicos" + "Validador de requisitos por mode".

- [x] 4.1 **RED**: `tests/unit/models/test_team_config.py` — tests failing. Cubrir: golden coordinate default, mode from string `"route"`, RED invalid mode `"coroutine"`, RED duplicate members, RED route con 1 member, RED broadcast con 1 member, golden coordinate con 1 member OK, RED extra field forbidden. Marker `@pytest.mark.unit`. Commit: `test: add RED tests for TeamConfig + TeamMemberConfig`.
- [x] 4.2 **GREEN**: Crear `src/yaml_agno/models/config/team_config.py` con import `from agno.team.mode import TeamMode` + `TeamMemberConfig` (sin extra=forbid, per SPEC_02) + `TeamConfig(extra="forbid")` + 2 validators (`validate_members_unique` field_validator, `validate_mode_requirements` model_validator after). Código literal del `design.md` §2. Verificar tests verde. Commit: `feat: add TeamConfig + TeamMemberConfig (TeamMode imported + 2 validators)`.

## Phase 5: StepConfig + WorkflowConfig (TDD estricto)

> Satisface: Requirements "Validador de campos type-specific" + "Validador de integridad de step-ids" + "Alias finally para finally_". Es el validador más complejo del change.

- [x] 5.1 **RED**: `tests/unit/models/test_workflow_config.py` — tests failing. Cubrir: golden workflow creation, golden `type="Parallel"` → `StepType.PARALLEL`, RED invalid step type, RED duplicate step ids, RED dangling if_true, RED dangling if_false, RED dangling cases value, EDGE cases key collision with step_id OK, RED nested steps on invalid type, RED condition fields on non-Condition, RED router fields on non-Router, RED loop fields on non-Loop, EDGE `finally` alias from YAML dict, EDGE `finally_` from Python kwarg, RED max_iterations=0. Marker `@pytest.mark.unit`. Commit: `test: add RED tests for WorkflowConfig + StepConfig`.
- [x] 5.2 **GREEN**: Crear `src/yaml_agno/models/config/workflow_config.py` con import `from agno.workflow.types import StepType` + `StepConfig(extra="forbid", populate_by_name=True)` 16 fields + `finally_` alias + `validate_type_specific_fields` (4 categorías) + `WorkflowConfig(extra="forbid")` + `validate_steps_integrity` (camina `cases.values()` no keys). Código literal del `design.md` §3. Verificar tests verde. Commit: `feat: add StepConfig + WorkflowConfig (type-specific + steps_integrity validators)`.

## Phase 6: Wiring & Runtime Import Contract

> Satisface: Requirements "Enums importados runtime" + "Re-export de las 6 clases". No es RED puro (wiring), pero el enum import test SÍ puede fallar si Agno se desinstala.

- [x] 6.1 **RED**: Crear `tests/unit/test_enums_import.py` — tests que validan `from agno.team.mode import TeamMode` (4 miembros lowercase) y `from agno.workflow.types import StepType` (8 miembros Capitalized) en runtime (NO mypy). Marker `@pytest.mark.unit`. Este es el contrato real contra Agno 2.6.22. Commit: `test: add runtime enum import contract (Agno 2.6.22)`.
- [x] 6.2 **GREEN**: Modificar `src/yaml_agno/models/__init__.py` (estaba vacío) para re-exportar las 6 clases + `__all__`. Código literal del `design.md` §5. Verificar smoke test: `python -c "from yaml_agno.models import AgentConfig, TeamConfig, TeamMemberConfig, WorkflowConfig, StepConfig, DIReference"`. Commit: `feat: re-export 6 public classes from yaml_agno.models`.

## Phase 7: Verification (no implementation)

> Satisface: Requirement "Tests unitarios con marker @pytest.mark.unit" + design.md §Verification Strategy.

- [x] 7.1 Ejecutar `python -m pytest -m unit` — todos los tests del change seleccionados y verde. Reportar conteo.
- [x] 7.2 Ejecutar `ruff check .` — limpio (line-length, import sort). Corregir si findings.
- [x] 7.3 Ejecutar `mypy src/yaml_agno` — limpio. **Caveat**: Agno stubs con `ignore_missing_imports=true` → import path erróneo NO falla type-check; el contrato REAL es el runtime test 6.1.
- [x] 7.4 Confirmar `git diff openspec/changes/agent-config-schema/specs/` vacío — no se mutó la spec durante implementación.
- [x] 7.5 Commit final si hay fixes de lint/type: `style: ruff/mypy compliance for agent-config-schema`. NO committear si 7.1-7.4 ya verde (los commits granulares de cada fase son el histórico).

## Phase 8: Closure (orchestrator handoff)

- [ ] 8.1 NO commitear este tasks.md (el apply sub-agent actualiza los checkboxes `[x]` conforme avanza). El commit granular final lo decide el orquestador según delivery_strategy + chain_strategy resueltas.

## TDD Compliance Matrix (trazabilidad spec → tasks)

| Spec Requirement | RED task | GREEN task | Scenarios cubiertos |
|------------------|----------|------------|---------------------|
| Seis clases + model_config (extra/frozen) | 2.1, 3.1, 5.1 | 2.2, 3.2, 5.2 | GREEN instanciación, RED extra forbidden |
| 9 slots opacos | 3.1 | 3.2 | GREEN slots aceptan dicts, RED slot inválido |
| Enums importados Agno | 6.1 | 6.2 | GREEN import runtime, GREEN mode→enum |
| user_id ausente | 3.1 | 3.2 | RED user_id rechazado |
| Validador name | 3.1 | 3.2 | GREEN válido, RED ilegal |
| Validador model format | 3.1 | 3.2 | GREEN provider/id, RED no-slash, RED vacíos |
| Members únicos | 4.1 | 4.2 | GREEN únicos, RED duplicados |
| Mode min-members | 4.1 | 4.2 | GREEN route 2+, RED route 1, RED broadcast 1 |
| Step type-specific fields | 5.1 | 5.2 | GREEN correctos, RED cross-type (4 categorías) |
| Step-ids integrity (cases.values) | 5.1 | 5.2 | GREEN refs válidas, RED dup ids, RED dangling, EDGE cases keys |
| Alias finally | 5.1 | 5.2 | GREEN YAML key + Python kwarg |
| DIReference format + frozen | 2.1 | 2.2 | GREEN token, RED no-token, RED uppercase, RED mutate |
| Re-export 6 clases | 6.1 | 6.2 | GREEN import raíz |
| Marker @pytest.mark.unit | 2.1-6.1 | — | GREEN colección `-m unit` |
| Exclusión factories/persistencia/API | — (invariante diff review) | — | RED inspección diff |

## Implementation Order (razón)

Secuencia estrictamente dependiente: Phase 1 (scaffolding sin código) → Phase 2
(DIReference, sin dependencias) → Phase 3 (AgentConfig, standalone) → Phase 4
(TeamConfig importa TeamMode de Agno) → Phase 5 (WorkflowConfig/StepConfig
importa StepType + es el más complejo) → Phase 6 (wiring cierra el contrato
público) → Phase 7 (verification gates). Cada Phase commitea de forma
independiente; los PR slices del forecast mapean 1:1 a grupos de phases
(PR 1 = Phase 1+2; PR 2 = Phase 3+4; PR 3 = Phase 5+6+7).
