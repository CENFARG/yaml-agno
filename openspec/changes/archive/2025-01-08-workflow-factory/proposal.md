---
change: workflow-factory
spec: SPEC_01
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/agent-config-schema   # WorkflowConfig + StepConfig (shipped, read-only)
  - openspec/specs/agent-factory-basic   # AgentFactory.build -> agno.Agent (shipped)
  - openspec/specs/team-factory          # TeamFactory.build -> agno.Team (shipped)
  - agno.workflow.cel                    # is_cel_expression + evaluate_cel_* (reused, NOT vendored)
---

# Proposal: WorkflowFactory — traductor StepConfig -> agno.Workflow

## Intent

SPEC_01 §4 define `WorkflowFactory` como el traductor que convierte un
`WorkflowConfig` (16 campos por `StepConfig`, ya shipped y validado por Pydantic)
en un `agno.workflow.Workflow` ejecutable. Es el slice #4 de SPEC_01 y el **más
duro** del set: debe resolver referencias de agentes/equipos ya construidos,
decidir por cada string del YAML si es CEL o callable, y armar correctamente los
7 primitivas de Agno (`Step`, `Parallel`, `Condition`, `Router`, `Loop`,
ensambladas en `Workflow`).

La exploración (obs 1962) y el slice-plan v2 (obs 1942) demostraron dos hechos
que cambian la forma del slice respecto al pseudo-código de SPEC_01:

1. **Agno ya distribuye integración CEL** (`cel-python`, expuesto en
   `agno.workflow.cel`). REUSARLA — no instalar otra lib ni reescribir bindings.
2. **El pseudo-código de SPEC_01 tiene 9 bugs** contra la API real de Agno v2.6
   (`add_step` no existe, `Parallel(steps=)` es variádico, `Step(function=)` es
   `executor=`, los nombres de campos nativos difieren, `InMemoryDb()` sin
   conexión, etc.). El factory los corrige.

**Éxito**: dado un `WorkflowConfig` válido + los dicts `agents`/`teams`/`callables`,
`WorkflowFactory.build(...)` retorna un `agno.Workflow` con `isinstance(workflow,
agno.Workflow)` cuyos `workflow.steps` contienen exactamente las primitivas
nativas correspondientes a cada `StepConfig`, con callables resueltos y CEL
delegado a Agno.

## Scope

### In Scope
- `WorkflowFactory.build(cfg, agents, teams, callables=None) -> agno.Workflow`
  en `src/yaml_agno/factories/workflow_factory.py` (NEW).
- Dispatch por `cfg.type` a 7 builders de primitiva (`_build_step`,
  `_build_parallel`, `_build_condition`, `_build_router`, `_build_loop`).
- **Resolución híbrida de strings** para `condition`/`expression`/`end_condition`/
  `function`: si `is_cel_expression(s)` → pasar el string crudo a Agno (Agno lo
  compila perezosamente); si es identificador simple → resolver del registry
  `callables` (o `agents`/`teams` para `function`); si ninguno → `raise`.
- **Resolución recursiva** de steps anidados (`steps` de Parallel/Condition,
  `choices` de Router, body de Loop).
- **`execute`/`finally_`: validate-and-warn** — `logger.warning(...)` cuando
  `cfg.execute is False` o `cfg.finally_ is True`, pero el step **se construye
  igual** (semántica diferida a SPEC_05).
- Corrección de los 9 bugs de pseudo-código SPEC_01 (ver Approach).
- Ensamblado final: `Workflow(name=cfg.name, steps=[built_steps])` (no `add_step`).
- Tests unitarios BDD en `tests/unit/factories/test_workflow_factory.py` (NEW).

### Out of Scope
- Semántica real de `execute=False` / `finally_=True` (DEFERIDO a SPEC_05 — solo
  se loguea).
- `human_review` (slot opaco — DEFERIDO a SPEC_29).
- Persistencia/`db`/`session_state` del Workflow (runtime, SPEC_06).
- `Step.workflow` (workflow anidado como executor) — se acepta el campo en
  `StepConfig` pero el builder inicial lanza `NotImplementedError` si se usa
  (slice futuro).
- Reimplementación de CEL, validación de expresiones CEL en tiempo de build, o
  parsers YAML adicionales.

## Capabilities

### New Capabilities
- `workflow-factory`: traduce `WorkflowConfig` (shipped) + instancias ya
  construidas (`agents`/`teams`/`callables`) en un `agno.Workflow` nativo.
  Cubre: dispatch por `StepType`, 7 primitivas, resolución híbrida
  CEL/registry, ensamblado por constructor, validate-and-warn.

### Modified Capabilities
- None. `agent-config-schema` (`WorkflowConfig`/`StepConfig`) ya está shipped y
  **no se toca** — el factory lo consume como entrada read-only.

## Approach

### 1. Resolución híbrida de strings (la decisión central)

Una función privada `_resolve_callable(s, registries) -> Callable | str`:

```python
from agno.workflow.cel import is_cel_expression

def _resolve_callable(s, callables, *, kind):
    if is_cel_expression(s):          # Agno compila perezosamente
        return s                       # -> se pasa como str al constructor
    ident = s                          # no es CEL -> identificador de registry
    if ident in callables:
        return callables[ident]        # callable nativo
    raise WorkflowFactoryError(
        f"{kind} '{ident}' no es CEL ni está en el registry 'callables'")
```

Esto **alinea el heurístico con el detector nativo de Agno** (`is_cel_expression`,
cel.py:87-96): identificador sin puntos → callable; puntos/operadores → CEL. El
regex original de SPEC_01 (`^[a-zA-Z_][a-zA-Z0-9_.]*$`) se descarta porque
clasificaría mal expresiones CEL con dotted-access (`session_state.retry_count`).

### 2. Matriz de 7 primitivas (verificada contra source Agno v2.6)

| `cfg.type` | Builder | Salida Agno |
|---|---|---|
| `Step` (agent) | `_build_step` | `Step(name=cfg.step, agent=agents[cfg.agent])` |
| `Step` (team) | `_build_step` | `Step(name=cfg.step, team=teams[cfg.team])` |
| `Step` (function) | `_build_step` | `Step(name=cfg.step, executor=callables[ref])` |
| `Parallel` | `_build_parallel` | `Parallel(*built_steps, name=cfg.step)` (variadic) |
| `Condition` | `_build_condition` | `Condition(name=cfg.step, evaluator=<resolved>, steps=[...], else_steps=[...])` |
| `Router` | `_build_router` | `Router(name=cfg.step, selector=<resolved>, choices=[...])` |
| `Loop` | `_build_loop` | `Loop(name=cfg.step, steps=[...], max_iterations=cfg.max_iterations, end_condition=<resolved>)` |
| (ensamblado) | `build` | `Workflow(name=cfg.name, steps=[built_steps])` |

`Steps` se mapea a `Parallel` (Agno no expone constructor público separado) o se
rechaza con error claro — a definir en spec.

### 3. Corrección de los 9 bugs del pseudo-código SPEC_01

| # | Bug SPEC_01 | Corrección |
|---|---|---|
| 1 | `workflow.add_step(step)` | `Workflow(name=, steps=[...])` (no existe `add_step`) |
| 2 | `Parallel(steps=[...])` | `Parallel(*steps, name=)` (variadic posicional) |
| 3 | `Step(function=...)` | `Step(executor=...)` |
| 4 | `Condition(condition=, if_true=, if_false=)` | `Condition(evaluator=, steps=, else_steps=)` |
| 5 | `Router(expression=, cases=)` | `Router(selector=, choices=)` |
| 6 | `Loop(end_condition=input)` | `end_condition: Callable[[List[StepOutput]], bool]` |
| 7 | `Router.choices` como dict | `choices` = lista de Step; cada `.name` = key de `cases` |
| 8 | `InMemoryDb(conn=...)` | `InMemoryDb()` (sin arg de conexión) — aplica a build_db |
| 9 | campo `execute` en `Step` | no existe en Agno; se maneja via validate-and-warn |

### 4. validate-and-warn para `execute`/`finally_`

Antes de construir cada step:

```python
if cfg.execute is False:
    logger.warning("Step '%s' tiene execute=False; SPEC_05 aún no implementa "
                   "la semántica — se construye normalmente.", cfg.step)
if cfg.finally_:
    logger.warning("Step '%s' tiene finally=True; SPEC_05 aún no implementa "
                   "cleanup post-workflow — se construye normalmente.", cfg.step)
```

El step **se construye igual**. Esto preserva el contrato de `build()` (siempre
retorna un Workflow completo) mientras deja rastro audible para SPEC_05.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/factories/workflow_factory.py` | New | `WorkflowFactory.build` + 5 builders privados + `_resolve_callable` |
| `src/yaml_agno/factories/__init__.py` | Modified | re-export `WorkflowFactory` |
| `src/yaml_agno/errors.py` (o equivalente) | Modified | `WorkflowFactoryError` si no existe ya |
| `tests/unit/factories/test_workflow_factory.py` | New | BDD scenarios: golden-path step, parallel, condition, router, loop, CEL dispatch, registry miss, validate-and-warn, recursive nesting |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `Router.selector` debe retornar **nombre de step** (string), no un valor arbitrario — el mapeo `cases` → `choices` debe setear `.name` en cada choice igual a su key | High | Cobertura explícita en spec + test BDD que afirma `choice.name == cases_key`. Verified en router.py:503-553. |
| `Loop.end_condition` recibe `List[StepOutput]`, no `StepInput` — contexto CEL distinto (`current_iteration`, `max_iterations`, `all_success`, `last_step_content`, `step_outputs`) | Med | Reusar `evaluate_cel_loop_end_condition` de Agno (cel.py:116-133) — NO envolver el string en un lambda que reciba StepInput. Test BDD específico. |
| `CEL_AVAILABLE=False` en runtime si `cel-python` no instalado — Agno lanza `RuntimeError` al evaluar, no al construir | Med | En build, si el string pasa `is_cel_expression`, se pasa crudo; el RuntimeError aparece en `.run()`, no en `build()`. Documentar en spec. Opcional: `validate_cel_expression` en build con warn-only. |
| Steps con `type=Steps` — Agno no expone constructor público claro | Med | Spec debe decidir: mapear a `Parallel` o rechazar con error. Recomendación inicial: rechazar (yaml-agno usa `Parallel`). |
| `function` (yaml-agno) podría apuntar a un agent/team ya construido, no solo a un callable puro — ambigüedad de registry | Baja | `function` se resuelve **solo** contra `callables`; `agent`/`team` son campos separados en `StepConfig`. El schema ya fuerza esta separación. |
| Compatibilidad futura SPEC_05 (execute/finally reales) — el warn-and-build puede crear contrato frágil | Baja | El test afirma que el step **se construye**; SPEC_05 añadirá el wrap, no cambiará la firma de `build`. |

## Rollback Plan

Este slice **solo añade** un módulo nuevo + su test. No muta `WorkflowConfig`
(shipped) ni factories existentes. Rollback:

1. `git revert` del commit del slice en rama `feature/workflow-factory`.
2. Eliminar `src/yaml_agno/factories/workflow_factory.py` y
   `tests/unit/factories/test_workflow_factory.py`.
3. Quitar el re-export de `src/yaml_agno/factories/__init__.py`.
4. Los slices shipped (agent/team/dependency/config) **no se ven afectados** —
   no hay dependencia inversa.

No hay migraciones de datos ni cambios en YAML público.

## Dependencies

- `openspec/specs/agent-config-schema` — `WorkflowConfig`/`StepConfig` (shipped,
  read-only). **Requerido** en build-time.
- `openspec/specs/agent-factory-basic` — provee `agents: dict[str, Agent]`.
- `openspec/specs/team-factory` — provee `teams: dict[str, Team]`.
- `agno.workflow.cel` — `is_cel_expression`, `evaluate_cel_*` (reusado, no
  vendored). Requiere extra `cel-python` (PyPI: `cel-python`, ya declarado en
  `agno/libs/agno/agno/pyproject.toml:106`).
- `callables: dict[str, Callable]` — **suministrado por el caller** (runtime
  concerns, SPEC_06). El factory no carga callables por su cuenta.

## Success Criteria

- [ ] `WorkflowFactory.build(cfg, agents, teams, callables)` retorna
      `isinstance(agno.Workflow)` para los 7 tipos de `StepConfig`.
- [ ] Para `cfg.condition`/`expression`/`end_condition` CEL: el string pasa
      crudo al constructor Agno (no se compila en build).
- [ ] Para identificador simple en registry: se pasa el callable resuelto.
- [ ] Registry miss lanza `WorkflowFactoryError` con mensaje accionable.
- [ ] `execute=False` / `finally_=True` producen `logger.warning` Y el step se
      construye normalmente.
- [ ] Los 9 bugs de pseudo-código SPEC_01 están corregidos (tests afirman
      nombres nativos: `executor`, `evaluator`, `selector`, `choices`, `steps`).
- [ ] Router: cada `choice.name ==` su key en `cfg.cases`.
- [ ] Cobertura de tests ≥ 90% en `workflow_factory.py`.
