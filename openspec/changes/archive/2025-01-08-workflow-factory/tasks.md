---
change: workflow-factory
spec: SPEC_01
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/workflow-factory/proposal.md
  - spec: openspec/changes/workflow-factory/specs/workflow-factory/spec.md (13 reqs, 22 scenarios)
  - design: openspec/changes/workflow-factory/design.md (literal code, 6 ADRs)
  - explore: engram project `doc.reca`, topic_key `sdd/workflow-factory/explore` (obs #1962 — 7-primitive matrix + CEL API verified against Agno source)
  - spec: engram `sdd/workflow-factory/spec` (obs #1964)
  - design: engram `sdd/workflow-factory/design` (obs #1965)
  - proposal: engram `sdd/workflow-factory/proposal` (obs #1963)
  - shipped_contract: src/yaml_agno/models/config/workflow_config.py (WorkflowConfig + StepConfig, 16 fields — consumed read-only)
strict_tdd: true
test_command: "python -m pytest"
---

# Tasks: WorkflowFactory — StepConfig -> agno.Workflow (SPEC_01 slice #4)

> El slice más duro de SPEC_01: traduce `WorkflowConfig` + 3 registries
> (`agents`/`teams`/`callables`) a un `agno.Workflow` con 7 primitivas nativas.
> **STRICT TDD**: cada tarea conductual arranca con RED (`tests/unit/factories/
> test_workflow_factory.py`), luego GREEN (`workflow_factory.py` literal del
> design), luego REFACTOR. Marker `@pytest.mark.unit` a nivel módulo.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~180-220 impl (`workflow_factory.py`) + ~15 (`__init__.py`) + ~280-340 tests; total ~480-580 |
| 400-line budget risk | Medium (impl+tests combinados rozan el presupuesto; impl sola lo respeta) |
| Chained PRs recommended | No (PR único pero grande — impl + tests cohesivos, no separables sin romper GREEN) |
| Suggested split | single PR (impl y tests son inseparables por TDD; el design provee código literal) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (no split needed) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | WorkflowFactory completo (impl + tests + re-export) | PR único | base = feature branch del slice; impl y tests co-dependientes por TDD |

## Open Items (CRÍTICO — resolver en apply)

- **DIVERGENCIA spec vs design sobre `_resolve_callable_or_cel` en
  Condition/Router/Loop**: la spec (Req "Resolución híbrida CEL/callable") dice
  que el despacho híbrido aplica a `condition`/`expression`/`end_condition`/
  `function` (los 4), y sus scenarios afirman que un identificador simple
  (`"check_threshold"`, `"pick_route"`, `"should_stop"`) se resuelve como
  callable desde `callables`. PERO el código literal del design SOLO llama a
  `_resolve_callable_or_cel` en el branch `function`; para `condition`/
  `expression`/`end_condition` pasa el string crudo sin resolver. Apply DEBE
  reconciliar: la versión correcta es la del design literal (Agno acepta `str`
  y compila perezosamente — un "identificador simple" como evaluator también es
  CEL válido para Agno porque pasa `is_cel_expression`... salvo que NO, porque
  `is_cel_expression("check_threshold")` retorna `False`). **Acción apply**:
  hacer que `_build_condition`/`_build_router`/`_build_loop` invoquen
  `_resolve_callable_or_cel` antes de pasar el evaluator/selector/end_condition,
  para satisfacer los scenarios "callable selector"/"callable end_condition"/
  "identificador simple resuelto como callable". Los tests RED lo fuerzan.
- **`StepType.WORKFLOW` y nested-workflow executor**: design lanza
  `NotImplementedError` (slice #4 no lo implementa). Spec no lista scenarios
  para este caso — está fuera de scope. Mantener el raise.

## Phase 1: Baseline — directorios y anclas

- [x] 1.1 Confirmar `src/yaml_agno/factories/__init__.py` existe con
  `AgentFactory`, `TeamFactory` re-exportados (baseline limpio, sin
  `WorkflowFactory` aún). **Req: n/a (ancla estructural).**
- [x] 1.2 Confirmar `tests/unit/factories/__init__.py` + `test_agent_factory.py`
  + `test_team_factory.py` existen (patrón de marker `pytestmark =
  pytest.mark.unit`). **Req: n/a (ancla estructural).**

## Phase 2: RED — `tests/unit/factories/test_workflow_factory.py`

> Un único archivo de tests cubriendo los 22 scenarios del spec. Se escribe
> TODO antes de GREEN (RED puro). Usa `StepConfig`/`WorkflowConfig` directos
> (sin YAML parsing), registries como dicts de stubs o `Agent`/`Team` sin
> modelo, inline executor callables (`def fn(si): return si`). Marker
> `pytestmark = pytest.mark.unit`. Ningún test llama `.run()`.

- [x] 2.1 RED `test_build_returns_agno_workflow` — 2 Steps lineales con agents;
  assert `isinstance(result, agno.Workflow)`, `len(steps)==2`, cada step
  `isinstance(agno.Step)`. **Scenario: Golden path — workflow lineal de 2 Steps con agentes. Req: build retorna agno.Workflow.**
- [x] 2.2 RED `test_build_propagates_description` — `cfg.description="x"`;
  assert `result.description=="x"`; afirmar que NO se pasa `db`/`session_id`/
  `user_id` (inspeccionar kwargs via mock o asserts estructurales).
  **Scenario: Workflow con description propagada. Req: build retorna agno.Workflow.**
- [x] 2.3 RED `test_dispatch_parallel_variadic` — `StepConfig(type=Parallel,
  steps=[{...}, {...}, {...}])`; assert `isinstance(result.steps[0],
  agno.Parallel)` y contiene 3 sub-primitivas, `.name==cfg.step`.
  **Scenario: Parallel con 3 sub-steps anidados. Req: Pasos anidados recursivos + Despacho por cfg.type.**
- [x] 2.4 RED `test_dispatch_condition_cel_evaluator_and_branches` —
  `condition="amount > 1000"` (CEL), `if_true="approve"`, `if_false="reject"`,
  con steps `approve`/`reject` presentes; assert `Condition.evaluator=="amount >
  1000"` (str), `steps` corresponde a `approve`, `else_steps` a `reject`.
  **Scenario: Condition con if_true e if_false. Req: Condition evaluator/if_true/if_false.**
- [x] 2.5 RED `test_dispatch_condition_else_steps_none_when_no_if_false` —
  `if_false=None`; assert `Condition.else_steps is None`.
  **Scenario: Condition sin if_false (else_steps None). Req: Condition evaluator/if_true/if_false.**
- [x] 2.6 RED `test_dispatch_condition_callable_evaluator` — `condition=
  "check_threshold"` (identificador simple) + `callables={"check_threshold":
  fn}`; assert `Condition.evaluator is fn`. **Scenario: Identificador simple
  resuelto como callable. Req: Resolución híbrida CEL/callable.** [ver Open Item]
- [x] 2.7 RED `test_dispatch_router_cases_named_by_key_cel_selector` —
  `expression="input.category"`, `cases={"billing": sidA, "support": sidB,
  "sales": sidC}`; assert `Router.choices` tiene 3 elementos cuyos `.name` son
  `"billing"`/`"support"`/`"sales"` (NO los step-ids), y `selector==
  "input.category"` (CEL str). **Scenario: Router con 3 cases y CEL selector. Req: Router cases→choices (A3).**
- [x] 2.8 RED `test_dispatch_router_callable_selector` — `expression=
  "pick_route"` + `callables={"pick_route": fn}`; assert `Router.selector is
  fn`. **Scenario: Router con callable selector. Req: Resolución híbrida + Router.** [ver Open Item]
- [x] 2.9 RED `test_dispatch_loop_cel_end_condition_and_max_iter` —
  `type=Loop`, `max_iterations=10`, `end_condition="all_success"`,
  `steps=[{intento}]`; assert `Loop.max_iterations==10`, `end_condition==
  "all_success"` (CEL str), `steps` contiene la primitiva de `intento`.
  **Scenario: Loop con CEL end_condition y max_iterations. Req: Loop steps/max_iterations/end_condition.**
- [x] 2.10 RED `test_dispatch_loop_callable_end_condition` — `end_condition=
  "should_stop"` + `callables={"should_stop": fn}`; assert `Loop.end_condition
  is fn`. **Scenario: Loop con callable end_condition. Req: Resolución híbrida.** [ver Open Item]
- [x] 2.11 RED `test_dispatch_loop_default_max_iterations` — `max_iterations=
  None`; assert `Loop.max_iterations==3` (default Agno).
  **Req implícito: Loop defaults.**
- [x] 2.12 RED `test_step_executor_agent_resolved` — `StepConfig(type=Step,
  step="s", agent="a1")` + `agents={"a1": agentA}`; assert
  `result.steps[0].agent is agentA`, `.name=="s"`. **Scenario: Step con agent resuelto desde el dict. Req: Resolución del ejecutor.**
- [x] 2.13 RED `test_step_executor_team_resolved` — `team="t1"` + `teams=
  {"t1": teamX}`; assert `result.steps[0].team is teamX`. **Scenario: Step con team resuelto. Req: Resolución del ejecutor.**
- [x] 2.14 RED `test_step_executor_function_callable` — `function="my_fn"` +
  `callables={"my_fn": fn}`; assert `result.steps[0].executor is fn`.
  **Req: Resolución del ejecutor + híbrida.**
- [x] 2.15 RED `test_step_executor_function_cel_string_raises` — `function=
  "a.b.c"` (CEL-looking); assert `ValueError` mencionando el step-id.
  **Req: Resolución del ejecutor (CEL string no válido para executor).**
- [x] 2.16 RED `test_step_executor_missing_agent_raises` — `agent="ghost"` +
  `agents={}`; assert `ValueError` (o `KeyError`) cuyo `str(exc)` contiene
  `"ghost"`; afirmar que `agno.Step` NUNCA fue instanciado (count==0 via spy).
  **Scenario: RED — agente referenciado no existe. Req: Referencia de ejecutor faltante.**
- [x] 2.17 RED `test_step_executor_missing_team_raises` — `team="ghost_team"`
  + `teams={}`; assert error cuyo `str` contiene `"ghost_team"`. **Scenario: RED — equipo referenciado no existe. Req: Referencia de ejecutor faltante.**
- [x] 2.18 RED `test_callable_ref_unresolvable_raises` — `condition=
  "missing_fn"` + `callables=None`; assert `ValueError`/`KeyError` cuyo `str`
  contiene `"missing_fn"`. **Scenario: RED — callable ref no resuelto. Req: Resolución híbrida.** [ver Open Item]
- [x] 2.19 RED `test_execute_false_warns_and_builds` — `execute=False` en un
  StepConfig; usar `caplog` (level WARNING) — assert mensaje contiene el
  step-id y `"execute"`; Y `result.steps[0]` sigue siendo `agno.Step` (no
  omitido/duplicado, `len==1`). **Scenario: execute=False registra warning. Req: execute/finally_ validate-and-warn.**
- [x] 2.20 RED `test_finally_true_warns_and_builds` — `finally_=True` (alias
  `finally`); `caplog` assert mensaje contiene step-id y `"finally"`; Y el
  step se construye en su posición. **Scenario: finally_=True registra warning. Req: execute/finally_ validate-and-warn.**
- [x] 2.21 RED `test_nested_parallel_inside_condition` — Condition cuyo
  `if_true` apunta a un step que es `type=Parallel` con 2 anidados; assert
  `Condition.steps` es `agno.Parallel` con 2 sub-primitivas. **Scenario: Anidamiento profundo (Parallel dentro de Condition). Req: Pasos anidados recursivos.**
- [x] 2.22 RED `test_seven_type_dispatch_disjoint` — parametrizado (o 7
  asserts): un workflow por cada `StepType` (`Step`, `Parallel`, `Steps`,
  `Condition`, `Router`, `Loop`, `Workflow`-raises); assert cada
  `result.steps[0]` es `isinstance` de la primitiva correcta Y los isinstance
  son disjuntos. Para `Workflow` (nested) assert `NotImplementedError`.
  **Scenario: Cada tipo produce su primitiva (tabla excluyente). Req: Despacho por cfg.type.**
- [x] 2.23 RED `test_human_review_present_no_error_no_wiring` — `human_review=
  {"requires_confirmation": True}` en un Router; assert `build` no eleva error
  Y `Router` no recibe data derivada. **Scenario: human_review presente sin error ni cableado. Req: Slot opaco human_review.**
- [x] 2.24 RED `test_branch_ref_trust_no_revalidation` — config válido con
  refs de branch correctos; assert build resuelve por confianza sin re-validar
  unicidad (no eleva error de integridad). **Scenario: Branch ref válido garantizado por schema. Req: NO re-validación.**
- [x] 2.25 RED `test_cel_string_passthrough_condition` — `condition=
  'input.contains("urgent")'` + `callables=None`; assert
  `Condition.evaluator == 'input.contains("urgent")'` (str crudo, no
  compilado). **Scenario: CEL expression pasada como string a Condition.evaluator. Req: Resolución híbrida.**

## Phase 3: GREEN — `src/yaml_agno/factories/workflow_factory.py` + re-export

> Implementación del código LITERAL del design §Literal Code. Orden: helpers
> y dispatcher primero, luego cada branch, luego ensamblado. **REFACTOR** al
> final si hay lógica compartida extraíble (mantener tests verde).

- [x] 3.1 Crear `src/yaml_agno/factories/workflow_factory.py` con: docstring
  del design, imports (`agno.workflow.*`, `is_cel_expression`, `StepConfig`,
  `WorkflowConfig`, `logging`), `_logger`, alias `_BuiltStep`, y class
  `WorkflowFactory` con `build()` (ensamblado: `step_index`, loop sobre
  `cfg.steps`, `Workflow(name=, description=, steps=)`). **Req: build retorna agno.Workflow.**
- [x] 3.2 Implementar `_resolve_callable_or_cel(value, callables)` —
  reusar `is_cel_expression(value)`: False → lookup `callables[value]` o
  `KeyError`; True → return str. **Req: Resolución híbrida CEL/callable.**
- [x] 3.3 Implementar `_build_step(step_cfg, ...)` dispatcher — switch sobre
  `step_cfg.type` (StepType): STEP/FUNCTION → `_build_step_executor`; STEPS →
  `Steps(name=, steps=[build...])`; PARALLEL → `Parallel(*built, name=)`;
  CONDITION → branch con `evaluator`/`steps`/`else_steps`; ROUTER →
  `choices` nombradas por case KEY (A3) + `selector`; LOOP → `steps`/
  `max_iterations or 3`/`end_condition`; WORKFLOW → `NotImplementedError`.
  Emitir `_logger.warning` para `execute=False`/`finally_=True` al inicio.
  **Req: Despacho por cfg.type + execute/finally_ validate-and-warn.**
- [x] 3.4 Implementar `_build_step_executor(step_cfg, agents, teams,
  callables)` — resolver UNA fuente (agent/team/function/workflow) en orden;
  `KeyError` claro si missing, `ValueError` si no-source, `NotImplementedError`
  si `workflow`. Mapear `function` vía `_resolve_callable_or_cel` (CEL str →
  `ValueError`). **Req: Resolución del ejecutor + Referencia faltante.**
- [x] 3.5 En `_build_condition`: invocar `_resolve_callable_or_cel` sobre
  `step_cfg.condition` antes de pasar como `evaluator=` (satisface scenario
  callable evaluator — ver Open Item). Branch `if_true`/`if_false` resueltos
  vía `step_index`; omitir `else_steps` si `if_false` es None.
  **Req: Condition + Resolución híbrida.**
- [x] 3.6 En `_build_router`: invocar `_resolve_callable_or_cel` sobre
  `step_cfg.expression` antes de pasar como `selector=` (ver Open Item).
  `choices` construidas recursivamente; override `.name = case_key` (A3).
  **Req: Router + Resolución híbrida.**
- [x] 3.7 En `_build_loop`: invocar `_resolve_callable_or_cel` sobre
  `step_cfg.end_condition` antes de pasar como `end_condition=` (ver Open
  Item). `max_iterations or 3`. **Req: Loop + Resolución híbrida.**
- [x] 3.8 Modificar `src/yaml_agno/factories/__init__.py`: añadir
  `from yaml_agno.factories.workflow_factory import WorkflowFactory` y
  `"WorkflowFactory"` a `__all__`. **Req: import desde el paquete raíz (implícito).**

## Phase 4: Verificación (GREEN conductual)

- [x] 4.1 `python -m pytest -m unit tests/unit/factories/test_workflow_factory.py`
  verde (todos los scenarios RED ahora GREEN).
- [x] 4.2 `python -m pytest` verde global (regression: agent/team tests sin
  cambios).
- [x] 4.3 `ruff check src/yaml_agno/factories/ tests/unit/factories/` sin
  findings.
- [x] 4.4 `mypy src/yaml_agno/factories/workflow_factory.py` sin errores
  (atención al `_BuiltStep` union y al `built_choice.name = case_key` que
  puede necesitar `# type: ignore[union-attr]`).
- [x] 4.5 Smoke import: `python -c "from yaml_agno.factories import
  WorkflowFactory; print(WorkflowFactory)"` sin error.
- [x] 4.6 Smoke runtime: script ad-hoc que construya un `WorkflowConfig`
  (Condition + Router + Loop + Parallel anidado) y llame `WorkflowFactory.build
  (cfg, agents={}, teams={}, callables={...})` — afirmar `isinstance(result,
  agno.Workflow)`. NO llamar `.run()`. **Scenario implícito: ensamblado
  end-to-end.**
- [x] 4.7 `git diff --name-only specs/ openspec/specs/` vacío (SPEC_01 y
  SPEC_02 sin mutar). `git diff --name-only src/yaml_agno/models/config/
  workflow_config.py` vacío (contrato consumido read-only).
- [x] 4.8 Assert estructural: `git diff --stat` confirma solo 2 archivos
  tocados (`workflow_factory.py` new, `__init__.py` modified) + 1 test new.

## Phase 5: Commit granular (conventional commits)

- [x] 5.1 `test: add WorkflowFactory RED tests (22 scenarios)` (Phase 2 —
  archivo de tests completo, RED esperado en CI).
- [x] 5.2 `feat: implement WorkflowFactory StepConfig→agno.Workflow translation`
  (Phase 3 — impl completa + re-export).
- [x] 5.3 `docs: clarify CEL/callable dispatch in Condition/Router/Loop`
  (si el Open Item requirió ajustar la impl vs el código literal del design —
  documentar la reconciliación inline). Opcional; solo si hubo divergencia.
  → Divergencia reconciliada inline en el docstring de `workflow_factory.py`
  (sección HYBRID CEL/CALLABLE RESOLUTION + nota Open Item #1); no se requirió
  commit de docs separado.

## TDD Compliance Matrix

| Spec Requirement | RED Task | GREEN Task | Scenario Count |
|-----------------|----------|------------|----------------|
| build retorna agno.Workflow | 2.1, 2.2 | 3.1 | 2 |
| Despacho por cfg.type (7 primitivas) | 2.3, 2.22 | 3.3 | 2 (tabla excluyente + nested) |
| Resolución del ejecutor (Step) | 2.12, 2.13 | 3.4 | 2 |
| Resolución híbrida CEL/callable | 2.6, 2.8, 2.10, 2.14, 2.15, 2.18, 2.25 | 3.2, 3.5, 3.6, 3.7 | 7 |
| Router cases→choices (A3) | 2.7, 2.8 | 3.6 | 2 |
| Condition evaluator/if_true/if_false | 2.4, 2.5, 2.6 | 3.5 | 3 |
| Loop steps/max_iter/end_condition | 2.9, 2.10, 2.11 | 3.7 | 3 |
| Pasos anidados recursivos | 2.3, 2.21 | 3.3 | 2 |
| execute/finally_ validate-and-warn | 2.19, 2.20 | 3.3 | 2 |
| Slot opaco human_review | 2.23 | 3.3 (no-op) | 1 |
| NO re-validación WorkflowConfig | 2.24 | 3.1 (trust) | 1 |
| Referencia de ejecutor faltante | 2.16, 2.17 | 3.4 | 2 |
| (implícito) import desde paquete raíz | 4.5 | 3.8 | 1 |

**Total: 13 requirements → 25 RED tests → 8 GREEN impl tasks → 22+ spec scenarios cubiertos.**

## Implementation Order

1. **Helpers primero**: `_resolve_callable_or_cel` (3.2) — pilar de la
   resolución híbrida, sin dependencias internas.
2. **Dispatcher**: `_build_step` switch (3.3) — estructura que delega a los
   branches; puede arrancar con raises/stubs y poblarse.
3. **Executor resolution**: `_build_step_executor` (3.4) — el branch más
   simple y testable aislado (4 fuentes, orden estricto).
4. **Branches complejos en orden de dificultad creciente**:
   - Parallel/Steps (3.3, recursión simple, variadic) → ya en el dispatcher.
   - Loop (3.7) — añade `_resolve_callable_or_cel` a end_condition.
   - Condition (3.5) — añade branch resolution vía `step_index`.
   - Router (3.6) — el más sutil: override `.name = case_key` (A3).
5. **Ensamblado final**: `build()` (3.1) — construye `step_index`, loopea,
   retorna `Workflow(steps=...)`.
6. **Re-export**: `__init__.py` (3.8).

**Paralelismo**: ninguna tarea es paralela — todas son secuenciales dentro del
ciclo RED→GREEN→REFACTOR. Phase 2 (tests) es un solo archivo escrito de una
vez (RED puro); Phase 3 (impl) se popula task por task hasta GREEN total.
