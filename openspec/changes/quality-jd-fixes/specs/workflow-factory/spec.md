# Delta: quality-jd-fixes → workflow-factory

> Judgment Day Round 2 remediation: 1 mypy annotation fix + 4 test-gap
> closures. Zero behavioral changes to production code. RFC 2119.

## MODIFIED Requirements

### Requirement: `_STEP_BUILDERS` type-safe dispatch table

The module-level `_STEP_BUILDERS` table SHALL be annotated as
`Mapping[StepType, Callable[..., _BuiltStep]]` instead of `dict[...]` so the
immutable `MappingProxyType` value type-checks under `mypy --strict`.

`collections.abc.Mapping` MUST be imported alongside the existing `Callable`
import. No runtime behavior changes; the table already wraps in
`MappingProxyType` at construction.

(Previously: `dict[StepType, Callable[..., _BuiltStep]]` — broke `mypy --strict`.)

#### Scenario: mypy passes after annotation fix
- GIVEN the fix applied at `workflow_factory.py:75`
- WHEN `mypy src/yaml_agno --strict` is run
- THEN it SHALL report zero errors on `workflow_factory.py`

#### Scenario: dispatch table still resolves all 5 composite types
- GIVEN a `StepConfig` of each composite type (Steps, Parallel, Condition, Router, Loop)
- WHEN `WorkflowFactory.build()` dispatches via `_STEP_BUILDERS.get(t)`
- THEN the correct builder SHALL be invoked (existing behavior, zero regression)

## ADDED Requirements

### Requirement: StepType.FUNCTION dispatch through build()

A `StepConfig` with `type="Function"` (not `type="Step"`) and `function="my_fn"`
MUST route through `_build_step_executor` via the fold at `_build_step:281`
(`t in (StepType.STEP, StepType.FUNCTION)`) and produce an `agno.Step` with
`executor` set to the resolved callable.

#### Scenario: type="Function" + function resolves to callable
- GIVEN `StepConfig(step="s", type="Function", function="my_fn")`
- AND `callables={"my_fn": fn}`
- WHEN `WorkflowFactory.build(cfg, agents={}, teams={}, callables=callables)` is called
- THEN the result step SHALL be `isinstance(Step)` with `step.executor is fn`

#### Scenario: Edge — type="Function" with CEL-looking string raises
- GIVEN `StepConfig(step="s", type="Function", function="a.b.c")`
- WHEN `WorkflowFactory.build()` is called
- THEN it SHALL raise `ValueError` mentioning `"s"` (executor requires callable)

### Requirement: Agent-precedence when function and agent are both set

When a `StepConfig` has both `agent` and `function` populated,
`_build_step_executor` MUST resolve `agent` first (line 349) and return a
`Step(agent=...)` — `agent` wins, `function` is unreachable. This documents
the existing precedence; a schema-level guard rejecting the combo is deferred.

#### Scenario: agent + function → agent wins
- GIVEN `StepConfig(step="s", type="Step", agent="a1", function="my_fn")`
- AND `agents={"a1": agentA}`, `callables={"my_fn": fn}`
- WHEN `WorkflowFactory.build(cfg, agents, teams={}, callables=callables)` is called
- THEN the result step SHALL have `step.agent is agentA`
- AND `step.executor` SHALL be `None`

#### Scenario: function-only still works (agent-precedence does NOT regress)
- GIVEN `StepConfig(step="s", type="Function", function="my_fn")` with no agent
- WHEN built with a callable registry containing `"my_fn"`
- THEN `step.executor is fn` and `step.agent is None`

### Requirement: step_executor forwarding in defensive branch resolution

When a `StepExecutor` is passed to `WorkflowFactory.build()`, it MUST be
forwarded through all group builders — including defensive code paths that
resolve dangling `if_true`/`if_false`/`cases` references — so recursive
`_build_step` calls inside those paths receive it.

#### Scenario: defensive Condition branch forwards step_executor
- GIVEN a `WorkflowConfig` built via `model_construct` with a Condition whose
  `if_true` points to a `ghost` step_id absent from `step_index`
- AND a `StepExecutor` instance is passed to `build()`
- WHEN `build()` resolves the defensive branch (empty `if_steps`)
- THEN `step_executor` SHALL NOT be lost or dropped (it was passed to every
  recursive `_build_step` frame, including the dead branch lookup)

#### Scenario: defensive Router choice skip keeps step_executor
- GIVEN a Router with `cases={"a": "ghost", "b": "real_step"}` via `model_construct`
- AND a `StepExecutor` instance is passed to `build()`
- WHEN the ghost case is skipped defensively and `real_step` is resolved
- THEN the `real_step` choice SHALL receive `step_executor` in its
  `_build_step` call (passthrough preserved)

### Requirement: Router expression=None → selector=None default

When a Router `StepConfig` has `expression=None` (not set),
`_build_router_group` SHALL default `selector` to `None` and construct
`Router(selector=None, ...)`. This is the null-selector path where Agno
handles routing internally.

#### Scenario: expression=None yields selector=None
- GIVEN `StepConfig(step="r", type="Router", cases={"a": "step_a"})` with no expression
- AND `StepConfig(step="step_a", type="Step", agent="a1")`
- WHEN `WorkflowFactory.build(cfg, agents, teams={})` is called
- THEN the result `Router.selector` SHALL be `None`
- AND `router.choices[0].name` SHALL be `"a"` (cases still resolved)

#### Scenario: expression set still passes through (no regression)
- GIVEN a Router with `expression="input.cat"` (CEL string)
- WHEN built
- THEN `router.selector` SHALL be `"input.cat"` (existing behavior)
