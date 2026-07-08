---
change: agent-factory-basic
spec: SPEC_01
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/agent-config-schema  # SPEC_02 (shipped, branch feature/agent-factory-basic)
---

# Proposal: AgentFactory — primer slice de fábrica (AgentConfig → agno.Agent)

> **Cambio #1 de los 4 slices de SPEC_01** (cadena factories). Primer slice
> cohesivo y TDD-eable: prueba `AgentConfig → agno.Agent` end-to-end con
> **construcción real de Agno, sin LLM**. Desbloquea TeamFactory (#3) y
> WorkflowFactory (#4).

## Intent

SPEC_01 define AgentFactory+TeamFactory+WorkflowFactory+DependencyManager pero
no hay NINGÚN factory implementado. Este cambio entrega el **primer vertical
slice runnable**: dado un `AgentConfig` (SPEC_02, ya shipped), construir un
`agno.Agent` válido con los campos de identidad mapeados. Éxito: `pytest`
verde con `isinstance(agent, agno.Agent)` + asserts de mapeo de atributos, **sin
network calls** (verificado: `Agent(model=...)` solo asigna, no hace I/O).

## Scope

### In Scope
- `AgentFactory.build(cfg: AgentConfig) -> agno.Agent` (método estático o clase simple).
- Mapeo de **campos de identidad**: `name`, `instructions`, `description`, `model`.
- `model` pasado **directo** (string `provider:id`); Agno lo resuelve nativamente.
- Test de construcción (smoke, sin `.run()`).
- `tests/unit/factories/` namespace nuevo.

### Out of Scope (explícito — cambios posteriores)
- **DependencyManager** (change #2): sin importlib/lru_cache/entry_points/allowlist.
- **TeamFactory** (#3) y **WorkflowFactory** (#4).
- **Resolución de los 9 slots opacos** (`tools`, `knowledge`, `memory`, `session`,
  `reasoning`, `skills`, `human_review`, `culture`, `persistence`): pasan
  **UNRESOLVED** — NO se envían a `Agent(...)` en este cambio. El agent se
  construye con éxito pero sin tools/knowledge/etc. hasta que los owner SPECs
  aterricen. La firma de `build()` NO los acepta aún.
- **`.run()` / `.arun()`**: fuera (requiere red/LLM).
- **SPEC_14** (model resilience / fallback): no se necesita aquí.
- **Lazy import vía importlib**: cambio #2. Import directo de `agno` es aceptable.

## Capabilities

### New Capabilities
- `agent-factory-basic`: construye `agno.Agent` desde `AgentConfig` mapeando
  identidad + modelo, sin resolución de dependencias ni side-effects en red.

### Modified Capabilities
- *None*. `agent-config-schema` (SPEC_02) no cambia — se consume read-only.

## Approach

**Mapeo mínimo y directo.** La firma de `Agent.__init__`
(`agno/agent/agent.py:384-503`, keyword-only, ~120 params) acepta los 4 campos
como kwargs nativos con defaults `None`. No hay traducción de nombres.

| AgentConfig (SPEC_02)        | `agno.Agent(...)` kwarg | Notas                                  |
|------------------------------|-------------------------|----------------------------------------|
| `name: str`                  | `name`                  | directo                                |
| `instructions: str \| None`  | `instructions`          | directo (Agent acepta `str\|list\|Callable`) |
| `description: str \| None`   | `description`           | directo                                |
| `model: str` (`provider:id`) | `model`                 | **passthrough**; Agno parsea nativamente |
| 9 slots opacos + `tags` + `metadata` | *(no mapeados)*   | deferred — owner SPECs                 |

**Sin side-effects en construcción** (verificado): `self.model = model`
(agent.py:504) es asignación pura. No se instancia cliente HTTP hasta
`run()`/`arun()`.

**TDD por construcción, no por run():** tests assert `isinstance(agent,
agno.Agent)` + igualdad `agent.name == cfg.name`, etc. Modelo real (p.ej.
`"openai:gpt-4o"`) — no mock, no network.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/factories/agent_factory.py` | New | `AgentFactory.build(cfg) -> agno.Agent`. |
| `src/yaml_agno/factories/__init__.py` | Modified | Re-export `AgentFactory` (hoy vacío). |
| `tests/unit/factories/__init__.py` | New | Namespace vacío. |
| `tests/unit/factories/test_agent_factory.py` | New | Tests de construcción + mapeo. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `Agent()` side-effects no detectados en construct (telemetría, imports pesados). | Baja | Verificado agent.py:504-517: solo asignaciones. Telemetry flag existe pero es flag, no call. Test lo cazará si regresa. |
| Mismatch de nombres AgentConfig ↔ Agent param (p.ej. `instructions` vs `system_message`). | Baja | Verificado: `instructions` existe (line 456), es el campo correcto. |
| `instructions=None` rompe construcción. | Baja | Default Agent es `None` (line 456) — OK. |
| Agno import lento / transitive deps pesadas en tests. | Media | Aceptar costo; inherente al framework. |
| Slots opacos "olvidados" parecen bug a reviewer. | Media | Documentado explícitamente en docstring + este proposal. |

## Rollback Plan

**Net-new** (todos archivos nuevos salvo `factories/__init__.py` que pasa de
vacío a re-export). `git revert` del commit restaura `factories/__init__.py`
vacío. Sin mutación de SPEC_02 ni otros módulos.

## Dependencies

- **SPEC_02 / `agent-config-schema`** (shipped, branch actual): provee
  `AgentConfig`. Consumo read-only.
- `agno==2.6.22` (pinneado en pyproject).
- **NO** depende de SPEC_14 ni de DependencyManager.

## Success Criteria

- [ ] `AgentFactory.build(AgentConfig(...))` retorna `isinstance(_, agno.Agent)`.
- [ ] `agent.name == cfg.name`, `agent.model == cfg.model`,
      `agent.description == cfg.description`, `agent.instructions == cfg.instructions`.
- [ ] `pytest tests/unit/factories/` verde, **sin** network/LLM.
- [ ] `ruff check` + `mypy` limpios en archivos nuevos.
- [ ] Los 9 slots opacos NO se envían a `Agent(...)` (build no los acepta aún).
- [ ] `git diff src/yaml_agno/models/ specs/` vacío (SPEC_02 intocado).
