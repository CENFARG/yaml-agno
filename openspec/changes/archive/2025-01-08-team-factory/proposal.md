---
change: team-factory
spec: SPEC_01
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/agent-config-schema
  - openspec/specs/agent-factory-basic
---

# Proposal: TeamFactory (SPEC_01 slice #3)

## Intent

SPEC_01 cadena de factories: falta el slice #3, que construye un `agno.Team`
desde un `TeamConfig` (SPEC_02) y un dict de agentes ya construidos. Sin este
slice, los teams declarados en YAML no pueden materializarse en runtime.
Completa la trilogía `AgentFactory` → `TeamFactory` → `WorkflowFactory`.

## Why now

El `TeamConfig` ya está shippeado (`src/yaml_agno/models/config/team_config.py`)
con sus validadores (uniqueness de members, min-counts por mode). El
`AgentFactory.build()` ya provee el patrón a replicar (static method, mapeo
directo, sin side-effects). Este slice es trivial (~40 líneas) y cierra la
capa de composición de agentes antes del slice #4 (workflow-factory, el más
complejo).

## Scope

### In Scope

- `TeamFactory.build(cfg: TeamConfig, agents: dict[str, Agent]) -> agno.Team`
  método estático (matchea el patrón de `AgentFactory.build`).
- Resolución de members: para cada `TeamMemberConfig`, lookup de
  `cfg.agent` (nombre) en el dict `agents` → el `agno.Agent` ya construido.
  `ValueError("Agent not found: <name>")` en miss.
- Construcción: `agno.Team(members=[resolved], mode=TeamMode(cfg.mode),
  name=cfg.name, instructions=cfg.instructions)`.
- Re-export `TeamFactory` desde `src/yaml_agno/factories/__init__.py`.
- Tests unitarios en `tests/unit/factories/test_team_factory.py` con
  `@pytest.mark.unit`: construcción, mapeo de members, error de agente
  faltante, sin red ni LLM.

### Out of Scope

- Resolución de `model`: `TeamConfig` no tiene campo `model` top-level (Agno
  resuelve el model del team leader internamente si se pasa al `run()`). Nada
  que hacer aquí.
- Forwarding del slot `workflows`: queda opaco (`list[dict[str, Any]]`); su
  resolución es del `WorkflowFactory` (slice #4) y SPEC_01 §4.
- Resolución de slots avanzados de `Team()` (caching keys, callable factories,
  reasoning, followups, etc. — ~100 kwargs): deferred a SPEC_05.
- Tags y metadata del `TeamConfig`: no se forwardean en este slice.
- Re-validación de mode/members: ya la hace `TeamConfig` (SPEC_02).

## Capabilities

### New Capabilities

- `team-factory`: construcción de `agno.Team` desde `TeamConfig` + dict de
  agentes pre-construidos; resolución de member-refs por nombre.

### Modified Capabilities

None.

## Approach

Réplica directa del patrón `AgentFactory`:

1. `from agno.team.team import Team`; `from agno.team.mode import TeamMode`
   (import directo, NO `resolve_team_symbols()` — ese método es pseudo-código
   inventado de SPEC_01 §2, ignorarlo).
2. Loop sobre `cfg.members`: `agents[m.agent]` por cada `TeamMemberConfig`.
   Si KeyError → `raise ValueError(f"Agent not found: {m.agent}")`.
3. `Team(members=[...], mode=TeamMode(cfg.mode), name=cfg.name,
   instructions=cfg.instructions)`. `cfg.mode` ya es `TeamMode` (Pydantic lo
   coerce en el schema), pero `TeamMode(cfg.mode)` es idempotente y explícito.

Firma estática: `TeamFactory` no se instancia. Matchea `AgentFactory.build()`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/factories/team_factory.py` | New | `TeamFactory.build()` estático. |
| `src/yaml_agno/factories/__init__.py` | Modified | Re-export `TeamFactory`. |
| `tests/unit/factories/test_team_factory.py` | New | BDD scenarios, offline. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Member-ref mismatch (nombre en YAML no existe en dict de agents) | Med | `ValueError` explícito con el nombre ofensor; tests cubren el caso. |
| `Team()` rechaza members como objetos `Agent` ya construidos | Baja | Verificado `team.py:437-439`: `members: Union[List[Union[Agent, "Team"]], ...]`. Acepta instancias `Agent`. |
| Orden de resolución: agents deben construirse antes que el team | Baja | Contrato del caller (el orquestador runtime). Documentado en docstring. |
| `mode=None` si alguien construye `TeamConfig` sin default | Baja | `TeamConfig.mode` tiene `default=TeamMode.coordinate`. |

## Rollback Plan

Eliminar `src/yaml_agno/factories/team_factory.py`, revertir el re-export en
`factories/__init__.py`, borrar `tests/unit/factories/test_team_factory.py`.
No hay migración ni estado persistente; el rollback es un `git revert` del
commit del slice.

## Dependencies

- `openspec/specs/agent-config-schema` (SPEC_02): provee `TeamConfig`,
  `TeamMemberConfig`. Shippeado.
- `openspec/specs/agent-factory-basic`: provee el patrón `AgentFactory.build()`
  y los agentes que alimentan el dict `agents`. Shippeado.
- Agno 2.6.22: `agno.team.team.Team`, `agno.team.mode.TeamMode`.

## Success Criteria

- [ ] `TeamFactory.build(cfg, agents)` retorna `isinstance(result, agno.Team)`.
- [ ] Los miembros del `Team` resultante son los `Agent` resueltos por nombre.
- [ ] Agente faltante en el dict lanza `ValueError` con el nombre ofensor.
- [ ] Tests corren offline (`-m unit`), sin LLM ni red.
- [ ] `from yaml_agno.factories import TeamFactory` funciona.
