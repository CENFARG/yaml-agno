---
change: agent-config-schema
spec: SPEC_02
artifact: proposal
status: proposed
artifact_store: hybrid
---

# Proposal: Domain Model — YAML Configuration Schemas (Pydantic V2)

## Intent

Llenar el namespace vacío `src/yaml_agno/models/` con el **único modelo de datos propio** de yaml-agno: los 6 schemas Pydantic V2 que validan la forma del YAML antes de pasar a los factories (SPEC_01). Sin estos schemas no existe SSOT contra el cual validar entradas de usuario ni contra el cual los factories puedan construir objetos Agno.

## Scope

### In Scope

- 6 clases Pydantic V2 en `src/yaml_agno/models/config/` (AgentConfig, TeamConfig, TeamMemberConfig, WorkflowConfig, StepConfig) y `src/yaml_agno/models/value_objects/` (DIReference).
- `model_config = ConfigDict(extra="forbid")` en los 5 *Config; `frozen=True` en DIReference.
- Enums `TeamMode` y `StepType` **importados de Agno** (nunca redefinidos).
- Validadores: `name` chars, `model` formato `provider/id`, members únicos, mode min-members, campos type-specific de step, integridad de step-ids (walks `if_true`/`if_false`/`cases.values()`), formato `${provider.key}` de DIReference.
- 9 slots opacos `dict[str,Any]|None` en AgentConfig (`tools` es `list[ToolConfig]`).
- `src/yaml_agno/models/__init__.py` re-exportando las 5 clases públicas + DIReference.
- Tests unitarios en `tests/unit/{models,value_objects}/` con marker `@pytest.mark.unit` (RED→GREEN).
- Sin `user_id` en ningún *Config (composite, runtime-only, SPEC_04).

### Out of Scope

- **Factories** *Config→Agno (SPEC_01, change #3). Esto incluye el rename `function`→`executor` — aquí solo se define el campo `function`, no se traduce.
- Persistencia (SPEC_03), API (SPEC_06), schemas dueños de slots opacos (SPEC_03/04/10/11/28/29/30/31) — referenciados, no validados aquí.
- Carga de YAML, construcción de objetos Agno, comportamiento runtime.

## Capabilities

### New Capabilities

- `agent-config-schema`: schemas Pydantic V2 para `agent:`/`team:`/`workflow:` YAML roots + value object DIReference. SSOT de la forma del YAML.

### Modified Capabilities

- None. (Cambio verde-field; el paquete `package-skeleton` ya archivado no se modifica.)

## Approach

Mecanismo Pydantic V2: `ConfigDict(extra="forbid")` garantiza reject de campos desconocidos; cada feature de Agno se **expone como slot nombrado** (`tools`, `memory`, ...) en vez de colarse por `extra="allow"`. Los enums se importan directamente de `agno.team.mode`/`agno.workflow.types` (verificados en 2.6.22), así yaml-agno hereda cambios de Agno sin tocar código. Los slots opacos son `dict[str,Any]|None` — su validación interna es responsabilidad del SPEC dueño (DRY/SSOT).

**Clarificación de paths** (flag de la exploración): `src/yaml_agno/models/config/` (schemas, NUEVO) y `src/yaml_agno/config/` (loader SPEC_23, existente) son **paths distintos, sin colisión**, ambos válidos per DECISIONES §4bis.

**Verificación adversarial** (obs 1866 + exploración): cada slot opaco de AgentConfig tiene contraparte nativa en `agno/agent/agent.py:384-503` (model/name/instructions/tools/knowledge/memory/skills/reasoning/metadata/culture/persistence). `human_review` es correcto que esté solo a nivel Workflow/Step (no es param de Agent).

## Affected Areas

| Area | Impact | Descripción |
|------|--------|-------------|
| `src/yaml_agno/models/config/agent_config.py` | New | AgentConfig + 9 slots opacos + 2 field_validators |
| `src/yaml_agno/models/config/team_config.py` | New | TeamConfig + TeamMemberConfig + validators members/mode |
| `src/yaml_agno/models/config/workflow_config.py` | New | WorkflowConfig + StepConfig + validators type-specific/integrity |
| `src/yaml_agno/models/value_objects/di_reference.py` | New | DIReference frozen + tokens + resolve |
| `src/yaml_agno/models/__init__.py` | Modified | re-export de las 5 + DIReference |
| `tests/unit/models/test_{agent,team,workflow}_config.py` | New | RED-GREEN por TDD |
| `tests/unit/value_objects/test_di_reference.py` | New | tokens/resolve/format |

## Risks

| Riesgo | Likelihood | Mitigación |
|--------|-----------|------------|
| `validate_type_specific_fields` cruza 4 categorías step-type (Parallel/Steps/Condition, Condition-only, Router-only, Loop-only) — validador de mayor complejidad | Med | Cobertura de tests type×field exhaustiva (todas las combinaciones ilegales) |
| `validate_steps_integrity` camina `cases.values()` (no keys) — edge case dict[str,str] | Bajo | Test explícito con cases cuyas keys colisionen con step-ids |
| `finally_` con `alias="finally"` (keyword Python) — riesgo de populate silencioso roto | Med | Verificar `populate_by_name=True` o que el alias YAML funcione; test ambos |
| Agno mypy stubs con `ignore_missing_imports=true` — import path erróneo no falla en type-check | Med | BDD/runtime import test es verificación real (no confiar en mypy) |
| Enums importados de Agno pueden cambiar entre versiones | Bajo | Pin Agno==2.6.22; import test verde es el contrato |

## Rollback Plan

Todo el cambio vive en archivos nuevos bajo `models/{config,value_objects}/`. Rollback = `git revert` del PR + restaurar `models/__init__.py` a su estado vacío. Sin migración, sin mutación de datos, sin dependientes (factories todavía no existen). El paquete `yaml_agno` sigue instalable.

## Dependencies

- **Change #1 (bootstrap)** — DONE/archived. Provee `src/yaml_agno/`, `models/__init__.py` vacío, pyproject con marker `unit`, deps `pydantic>=2`, `agno==2.6.22`.
- **Agno v2.6.22** — enums `agno.team.mode.TeamMode` (4 members), `agno.workflow.types.StepType` (8 members), verificados.
- **SPEC_02** — read-only source of truth; no se edita.

## Success Criteria

- [ ] 6 clases definidas per SPEC_02 con `model_config` correcto (5× `extra="forbid"`, 1× `frozen=True`).
- [ ] Slots opacos de AgentConfig verificados contra `agent.py:384-503` (citar verificación en código/tests).
- [ ] Enums importados de Agno (no redefinidos); runtime import test verde.
- [ ] `user_id` ausente de todos los *Config.
- [ ] `extra="forbid"` rechaza campos desconocidos (test explícito).
- [ ] Todos los validadores con cobertura RED→GREEN (name, model, members, mode, type-specific, step-id integrity, DI format).
- [ ] `ruff check .` limpio, `mypy src/yaml_agno` limpio, `python -m pytest` verde (marker unit).
- [ ] `models/__init__.py` re-exporta las 6 clases.
- [ ] Ningún SPEC editado, ningún factory escrito, ningún objeto Agno construido.
