# WorkflowFactory Specification

> **Origen**: SPEC_01 §4 (Cognitive Workflow Triggers) + §5.1 escenarios 4.x.
> **Contrato shipped**: `src/yaml_agno/models/config/workflow_config.py`
>   (`WorkflowConfig`, `StepConfig` + `StepType` importado de `agno.workflow.types`).
> **Agno verificado** (v2.6.18, rutas absolutas bajo
>   `C:/Dropbox/DOC.RECA/06-Software/agno/libs/agno/agno/workflow/`):
>   - `cel.py:87-96` — `is_cel_expression()` regex `^[a-zA-Z_][a-zA-Z0-9_]*$`
>     (identificador simple, sin puntos → callable; todo lo demás → CEL).
>   - `cel.py:99,116,136` — `evaluate_cel_condition_evaluator`,
>     `evaluate_cel_loop_end_condition`, `evaluate_cel_router_selector`.
>   - `step.py` — `Step(name, agent|team|executor|workflow, ...)`, exactamente uno.
>   - `parallel.py:62` — `Parallel(*steps, name=None, description=None)`.
>   - `condition.py:95` — `Condition(steps, evaluator=True, else_steps=None, ...)`.
>   - `router.py:85` — `Router(choices, selector=None, name=None, ...)`.
>   - `loop.py:93` — `Loop(steps, max_iterations=3, end_condition=None, ...)`.
>   - `workflow.py:457` — `Workflow(name=, steps=[...])` (NO existe `add_step`).
> **Alcance**: SPEC_01 slice #4. No `.run()`, no session/db, no hot-reload,
>   no ACID entre steps, no Scheduler. Solo traducción YAML→Agno.

## Purpose

`WorkflowFactory.build(cfg, agents, teams, callables=None)` traduce un
`WorkflowConfig` ya validado por Pydantic (16 fields por `StepConfig`) a una
instancia de `agno.workflow.workflow.Workflow`, despachando cada `StepConfig`
a la primitiva correcta de Agno y resolviendo referencias (agentes, equipos,
callables, expresiones CEL).

## Requirements

### Requirement: WorkflowFactory.build retorna un agno.Workflow válido

`build(cfg, agents, teams, callables=None)` DEBE retornar un objeto
`isinstance(agno.workflow.workflow.Workflow)`. La fábrica construye las
primitivas y las pasa como `steps=[...]` al constructor de `Workflow`
(`workflow.py:457`); **MUST NOT** usar `add_step` (no existe).
`cfg.name` → `Workflow(name=)`, `cfg.description` → `Workflow(description=)`
(si no es None). Session, db, model y user_id son runtime-only y se omiten.

- **MUST**: retornar `isinstance(agno.Workflow)`.
- **MUST NOT**: invocar `add_step` ni `add_steps`.
- **MUST NOT**: pasar `db=`, `session_id=`, `user_id=`, `model=` al constructor.

#### Scenario: Golden path — workflow lineal de 2 Steps con agentes

- GIVEN un `WorkflowConfig` con `name="w"` y dos `StepConfig` tipo `Step`
  con `agent="a1"` y `agent="a2"`
- AND `agents={"a1": agentA, "a2": agentB}` ya construidos
- WHEN se llama `WorkflowFactory.build(cfg, agents, teams={})`
- THEN el retorno es `isinstance(agno.Workflow)`
- AND `workflow.steps` tiene exactamente 2 elementos
- AND cada elemento es `isinstance(agno.workflow.step.Step)`

#### Scenario: Workflow con description propagada

- GIVEN `cfg.description="pipeline de facturacion"`
- WHEN `build(cfg, agents, teams)`
- THEN `workflow.description == "pipeline de facturacion"`
- AND ningún kwarg runtime (`db`, `session_id`, `user_id`) es pasado

### Requirement: Despacho por cfg.type a la primitiva Agno correcta

Para cada `StepConfig`, `build` DEBE despachar `cfg.type` a la primitiva
Agno nativa correspondiente. La tabla es excluyente (un `StepConfig` produce
exactamente UNA primitiva):

| `cfg.type`        | Primitiva Agno construida             |
|-------------------|---------------------------------------|
| `Step`            | `agno.workflow.step.Step`             |
| `Parallel`        | `agno.workflow.parallel.Parallel`     |
| `Steps`           | `agno.workflow.steps.Steps`           |
| `Condition`       | `agno.workflow.condition.Condition`   |
| `Router`          | `agno.workflow.router.Router`         |
| `Loop`            | `agno.workflow.loop.Loop`             |
| `Workflow`        | `agno.workflow.workflow.Workflow` (anidado) |

- **MUST**: `cfg.type` ya es un `agno.workflow.types.StepType` (Pydantic lo
  coerciona). La fábrica NO re-valida el enum.
- **MUST**: la primitiva es resuelta perezosamente vía `DependencyManager`
  (solo la referenciada se importa, SPEC_01 §1.3).

#### Scenario: Cada tipo produce su primitiva (tabla excluyente)

- GIVEN 7 `WorkflowConfig`, cada uno con un único `StepConfig` de `type`
  distinto (`Step`, `Parallel`, `Steps`, `Condition`, `Router`, `Loop`,
  `Workflow`) y los refs de ejecutor válidos para cada caso
- WHEN se llama `build` para cada cfg
- THEN cada `workflow.steps[0]` es `isinstance` de la primitiva listada en la tabla
- AND los 7 isinstance checks son disjuntos (ningún elemento es de dos primitivas)

### Requirement: Resolución del ejecutor del Step

Para un `StepConfig` de tipo `Step`, `build` DEBE resolver el ejecutor
usando exactamente UNA de estas fuentes, en orden de exclusividad:

1. `cfg.agent` → `agents[cfg.agent]` (instancia ya construida).
2. `cfg.team` → `teams[cfg.team]` (instancia ya construida).
3. `cfg.function` → callable resuelto desde `callables` (ver Requirement
   dedicado a resolución CEL/callable).
4. `cfg.workflow` → workflow anidado (referencia opaca en este slice).

- **MUST**: si `cfg.agent` está seteado, pasar `Step(agent=agents[cfg.agent])`.
- **MUST**: si `cfg.team` está seteado, pasar `Step(team=teams[cfg.team])`.
- **MUST NOT**: instanciar agentes/equipos (recibe el dict ya construido).
- **MUST**: pasar `cfg.step` como `name=` (Agno `Step(name=)`).

#### Scenario: Step con agent resuelto desde el dict

- GIVEN un `StepConfig(step="s", type=Step, agent="a1")`
- AND `agents={"a1": agentA}`
- WHEN `build(cfg, agents, teams)`
- THEN `workflow.steps[0].agent is agentA`
- AND `workflow.steps[0].name == "s"`

#### Scenario: Step con team resuelto desde el dict

- GIVEN un `StepConfig(step="s", type=Step, team="t1")`
- AND `teams={"t1": teamX}`
- WHEN `build(cfg, agents, teams)`
- THEN `workflow.steps[0].team is teamX`

### Requirement: Resolución híbrida CEL/callable

Para todo campo de expresión (`condition`, `end_condition`, `expression`,
`function`), `build` DEBE aplicar el despacho híbrido alineado con
`agno.workflow.cel.is_cel_expression` (regex `^[a-zA-Z_][a-zA-Z0-9_]*$`,
sin puntos):

1. Si el string matchea identificador simple (sin puntos, sin operadores) →
   **callable ref**: se resuelve desde `callables` (dict `{name: callable}`).
   Si `callables is None` o la key falta → **MUST** elevar `ValueError`
   mencionando el nombre no resuelto.
2. En caso contrario → **CEL expression**: se pasa como `str` al constructor
   de la primitiva Agno correspondiente. Agno compila y evalúa nativamente
   (`cel-python`); la fábrica **MUST NOT** pre-compilar ni pre-validar.

- **MUST**: reutilizar `agno.workflow.cel.is_cel_expression` (no reimplementar).
- **MUST NOT**: permitir `.` en el detector de callable ref (rompería CEL
  con dotted-access como `session_state.retry_count < 3`).
- **MUST**: el callable resuelto se pasa como objeto callable al kwarg
  Agno correspondiente (`executor=`, `evaluator=`, `selector=`, `end_condition=`).

#### Scenario: CEL expression pasada como string a Condition.evaluator

- GIVEN un `StepConfig(type=Condition, condition="input.contains(\"urgent\")")`
- WHEN `build(cfg, agents, teams, callables=None)`
- THEN se construye `Condition(steps=..., evaluator="input.contains(\"urgent\")")`
- AND el `evaluator` pasado es `str` (no se compila en la fábrica)

#### Scenario: Identificador simple resuelto como callable

- GIVEN `StepConfig(type=Condition, condition="check_threshold")`
- AND `callables={"check_threshold": some_fn}`
- WHEN `build(cfg, agents, teams, callables)`
- THEN `Condition(evaluator=some_fn)` (callable resuelto, no string)
- AND `some_fn is callables["check_threshold"]`

#### Scenario: RED — callable ref no resuelto

- GIVEN `StepConfig(type=Condition, condition="missing_fn")`
- AND `callables=None`
- WHEN `build(cfg, agents, teams, callables)`
- THEN se eleva `ValueError`
- AND `str(exc)` contiene `"missing_fn"`

### Requirement: Router — cases dict → choices list

Para un `StepConfig` de tipo `Router`, `build` DEBE construir
`Router(choices=[...], selector=...)` donde:

- `choices` es la lista de sub-primitivas (Steps) construidas a partir de
  los **valores** de `cfg.cases`. Cada choice DEBE tener su `name` igual a
  la **key** del `cases` que la originó (para que el selector CEL pueda
  retornar el nombre string y Agno lo resuelva vía `_step_name_map`,
  `router.py:503`).
- `selector` proviene de `cfg.expression` vía el despacho híbrido (CEL como
  string; identificador simple como callable desde `callables`).

- **MUST**: cada `choice.name == <key en cases>`.
- **MUST**: `selector` es `str` si `cfg.expression` es CEL, callable si es
  identificador simple.
- **MUST NOT**: usar las keys de `cases` como nombres de step (las keys son
  valores del selector, no step ids; ver `workflow_config.py` docstring).

#### Scenario: Router con 3 cases y CEL selector

- GIVEN `StepConfig(type=Router, expression="input.category",
  cases={"billing": "<StepConfig A>", "support": "<StepConfig B>",
         "sales": "<StepConfig C>"})`
- WHEN `build(cfg, agents, teams)`
- THEN `Router.choices` tiene 3 elementos cuyos `.name` son
  `"billing"`, `"support"`, `"sales"` respectivamente
- AND `Router.selector == "input.category"` (CEL string)

#### Scenario: Router con callable selector

- GIVEN `StepConfig(type=Router, expression="pick_route",
  cases={"a": ..., "b": ...})`
- AND `callables={"pick_route": fn}`
- WHEN `build(cfg, agents, teams, callables)`
- THEN `Router.selector is fn` (callable)

### Requirement: Condition — evaluator / if_true / if_false

Para un `StepConfig` de tipo `Condition`, `build` DEBE construir
`Condition(steps=<built sub-step from if_true>, evaluator=<resolved>,
else_steps=<built sub-step from if_false or None>)`.

- `cfg.condition` → `evaluator` vía despacho híbrido.
- `cfg.if_true` (step id) → resolver la sub-primitiva referenciada y pasarla
  como `steps=`.
- `cfg.if_false` → resolver y pasar como `else_steps=`; si es None, omitir
  el kwarg (Agno default `None`).

- **MUST**: `if_true`/`if_false` son **step ids** (strings) resueltos contra
  los StepConfigs del mismo workflow, ya validados como existentes por
  `WorkflowConfig.validate_steps_integrity` (no dangling).

#### Scenario: Condition con if_true e if_false

- GIVEN `StepConfig(type=Condition, step="c", condition="amount > 1000",
  if_true="approve", if_false="reject")`
- AND steps `approve` y `reject` definidos en el mismo workflow
- WHEN `build(cfg, agents, teams)`
- THEN `Condition.evaluator == "amount > 1000"` (CEL string)
- AND `Condition.steps` corresponde a la primitiva construida para `approve`
- AND `Condition.else_steps` corresponde a la primitiva de `reject`

#### Scenario: Condition sin if_false (else_steps None)

- GIVEN `StepConfig(type=Condition, condition="flag", if_true="s1", if_false=None)`
- WHEN `build(cfg, agents, teams)`
- THEN `Condition.else_steps is None` (no se pasa el kwarg)

### Requirement: Loop — steps / max_iterations / end_condition

Para un `StepConfig` de tipo `Loop`, `build` DEBE construir
`Loop(steps=<built sub-steps>, max_iterations=cfg.max_iterations or 3,
end_condition=<resolved or None>)`.

- `cfg.steps` (lista de StepConfigs anidados) → construir recursivamente
  y pasar como `steps=`.
- `cfg.max_iterations` → `max_iterations=`; si es None, omitir (Agno default 3).
- `cfg.end_condition` → `end_condition=` vía despacho híbrido; si None, omitir.

- **MUST**: el callable de `end_condition` toma `List[StepOutput]` (NO
  `StepInput`) — Agno lo invoca así (`loop.py:76`).

#### Scenario: Loop con CEL end_condition y max_iterations

- GIVEN `StepConfig(type=Loop, step="l", max_iterations=10,
  end_condition="all_success", steps=[<StepConfig intento>])`
- WHEN `build(cfg, agents, teams)`
- THEN `Loop.max_iterations == 10`
- AND `Loop.end_condition == "all_success"` (CEL string)
- AND `Loop.steps` contiene la primitiva construida para `intento`

#### Scenario: Loop con callable end_condition

- GIVEN `StepConfig(type=Loop, end_condition="should_stop",
  steps=[...])` y `callables={"should_stop": fn}`
- WHEN `build(cfg, agents, teams, callables)`
- THEN `Loop.end_condition is fn`

### Requirement: Pasos anidados recursivos (Parallel / Steps / Condition)

Para `StepConfig` con `cfg.steps` (lista de StepConfigs anidados — válido
solo para `Parallel`, `Steps`, `Condition`), `build` DEBE construir cada
sub-StepConfig recursivamente con el mismo pipeline de despacho y pasarlos
como args/kwargs a la primitiva contenedora:

- `Parallel(*built_substeps, name=cfg.step)` — variadic posicional.
- `Steps(*built_substeps, name=cfg.step)` — variadic posicional.
- `Condition(steps=built_substeps, ...)` — los anidados van al branch `if_true`.

- **MUST**: la recursión soporta cualquier profundidad (Parallel dentro de
  Parallel dentro de Condition dentro de Loop, etc.).
- **MUST NOT**: romper la profundidad máxima de pila para workflows razonables.

#### Scenario: Parallel con 3 sub-steps anidados

- GIVEN `StepConfig(type=Parallel, step="p",
  steps=[<StepConfig v1>, <StepConfig v2>, <StepConfig v3>])`
- WHEN `build(cfg, agents, teams)`
- THEN `workflow.steps[0]` es `isinstance(agno.Parallel)`
- AND contiene 3 sub-primitivas (una por StepConfig anidado)

#### Scenario: Anidamiento profundo (Parallel dentro de Condition)

- GIVEN `StepConfig(type=Condition, step="c", condition="x",
  if_true="<StepConfig Parallel con 2 anidados>", if_false=...)`
- WHEN `build(cfg, agents, teams)`
- THEN `Condition.steps` es un `agno.Parallel` con 2 sub-primitivas

### Requirement: execute / finally_ — validate-and-warn (semántica diferida)

`cfg.execute` (yaml-agno own) y `cfg.finally_` (yaml-agno own) son fields
NO nativos de Agno. En este slice la fábrica **NO** implementa su semántica
completa (espejar/saltar steps, orden de cleanup). En su lugar:

- **MUST**: si `cfg.execute is False`, registrar un **warning** con el
  `step_id` y proseguir la construcción normalmente.
- **MUST**: si `cfg.finally_ is True`, registrar un **warning** con el
  `step_id` y proseguir la construcción normalmente.
- **MUST NOT**: alterar el orden de steps, duplicarlos ni omitirlos por
  estos flags. La semántica real se difiere a SPEC_05.
- **MUST**: usar el logger de yaml-agno (`agno.utils.log.logger` u otro
  logger del proyecto) — visible en tests via `caplog`.

#### Scenario: execute=False registra warning pero construye el step

- GIVEN `StepConfig(type=Step, step="s", agent="a1", execute=False)`
- WHEN `build(cfg, agents, teams)`
- THEN se registra un warning cuyo mensaje contiene `"s"` y `"execute"`
- AND `workflow.steps[0]` sigue siendo `isinstance(agno.Step)`
- AND el step NO es omitido ni duplicado

#### Scenario: finally_=True registra warning pero construye el step

- GIVEN `StepConfig(type=Step, step="cleanup", function="fn", finally_=True)`
- AND `callables={"fn": f}`
- WHEN `build(cfg, agents, teams, callables)`
- THEN se registra un warning cuyo mensaje contiene `"cleanup"` y `"finally"`
- AND el step se construye normalmente en su posición

### Requirement: Slot opaco human_review (deferred SPEC_29)

`cfg.human_review` (`dict[str, Any] | None`) es un slot opaco. En este slice
la fábrica **MUST NOT** procesarlo, validarlo ni pasarlo a las primitivas
Agno. Su presencia **MUST NOT** causar error; se preserva en `cfg` pero no
se cablea. La traducción a `agno.workflow.types.HumanReview` es SPEC_29.

- **MUST**: `build` ignora `cfg.human_review` completamente.
- **MUST NOT**: elevar error por `human_review` no vacío.

#### Scenario: human_review presente, sin error y sin cableado

- GIVEN `StepConfig(type=Router, step="r", expression="e",
  cases={"a": ...}, human_review={"requires_confirmation": True})`
- WHEN `build(cfg, agents, teams)`
- THEN no se eleva error
- AND `Router.human_review` no recibe data derivada de `cfg.human_review`

### Requirement: NO re-validación de invariantes de WorkflowConfig

`WorkflowConfig` ya valida en su boundary (Pydantic
`validate_steps_integrity`): unicidad de `step` ids y validez de branch refs
(`if_true`, `if_false`, `cases.values()`). La fábrica **MUST NOT** re-validar
esas invariantes — son responsabilidad del schema.

- **MUST NOT**: re-validar unicidad de step ids.
- **MUST NOT**: re-validar que `if_true`/`if_false`/`cases.values()` apunten
  a steps existentes.
- **MUST**: asumir que el `cfg` recibido ya pasó validación.

#### Scenario: Branch ref válido ya garantizado por el schema

- GIVEN un `WorkflowConfig` válido (step ids únicos, branch refs válidos)
- WHEN `build(cfg, agents, teams)`
- THEN la fábrica resuelve `if_true`/`if_false`/`cases` por confianza (no re-check)
- AND no eleva error de integridad

### Requirement: Referencia de ejecutor faltante — error claro

Si un `StepConfig` referencia un `agent` o `team` cuyo nombre **no existe**
en el dict correspondiente, `build` DEBE elevar `ValueError` con un mensaje
que incluya el nombre faltante, **antes** de invocar al constructor de la
primitiva Agno.

- **MUST**: el mensaje contiene el nombre del agente/equipo no encontrado.
- **SHOULD**: el mensaje sugiere verificar la sección `agents:` / `teams:`.
- **MUST**: no se construye una primitiva parcial.

#### Scenario: RED — agente referenciado no existe

- GIVEN `StepConfig(type=Step, step="s", agent="ghost")`
- AND `agents={}` (vacío)
- WHEN `build(cfg, agents, teams)`
- THEN se eleva `ValueError`
- AND `str(exc)` contiene `"ghost"`
- AND `agno.Step` NUNCA es instanciado

#### Scenario: RED — equipo referenciado no existe

- GIVEN `StepConfig(type=Step, step="s", team="ghost_team")`
- AND `teams={}`
- WHEN `build(cfg, agents, teams)`
- THEN se eleva `ValueError`
- AND `str(exc)` contiene `"ghost_team"`
