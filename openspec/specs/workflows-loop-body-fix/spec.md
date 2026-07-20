# Spec: workflows-loop-body-fix

## Purpose

Close the SPEC_05 slice A "Loop body gap": allow a `StepType.LOOP` config
to declare a nested `steps` body, and have `WorkflowFactory` build that
body recursively into the resulting `agno.workflow.loop.Loop` — instead
of hard-coding `Loop(steps=[])`.

## Requirements

### Requirement: Loop type accepts nested steps at config time

The `StepConfig` schema MUST accept a non-empty `steps` list when
`type == StepType.LOOP`. A `StepConfig(type="Loop", steps=[...])` MUST
validate successfully and MUST NOT raise from
`validate_type_specific_fields`.

#### Scenario: Loop with a nested body validates

- **WHEN** a `StepConfig` is constructed with `step="l"`,
  `type="Loop"`, and `steps=[{"step": "inner", "type": "Step",
  "agent": "a1"}]`
- **THEN** construction succeeds with no `ValidationError`
- **AND** `cfg.steps` is the provided list (length 1)

#### Scenario: Loop with end_condition AND body validates

- **WHEN** a `StepConfig` is constructed with `type="Loop"`,
  `max_iterations=5`, `end_condition="all_done == true"`, and a non-empty
  `steps` list
- **THEN** construction succeeds
- **AND** both `cfg.max_iterations == 5` and `cfg.end_condition` equals
  the CEL string

#### Scenario: Other types still reject nested steps

- **WHEN** a `StepConfig` is constructed with `type="Step"` and a
  non-empty `steps` list
- **THEN** construction raises `ValidationError`
- **AND** the error message lists the allowed types as
  `Parallel/Steps/Condition/Loop`

### Requirement: Factory builds nested steps into the Loop body

`WorkflowFactory._build_step`, when dispatched on `StepType.LOOP`, MUST
recursively build every entry in `step_cfg.steps` via the same
`_build_step` recursion used by the `Parallel`/`Steps` branches, and
pass the resulting list as `Loop(steps=[...])`.

#### Scenario: Loop body is built from a single nested Step

- **GIVEN** a `WorkflowConfig` whose top-level step is `type="Loop"`
  with `steps=[{"step": "inner", "type": "Step", "agent": "a1"}]`, and
  an `agents={"a1": <Agent>}` registry
- **WHEN** `WorkflowFactory.build` is called
- **THEN** the resulting `Workflow.steps[0]` is an `agno.workflow.loop.Loop`
- **AND** `Loop.steps` has length 1
- **AND** that element is an `agno.workflow.step.Step` with
  `name == "inner"` and `agent is <Agent>`

#### Scenario: Loop preserves max_iterations and end_condition alongside body

- **GIVEN** a `type="Loop"` step with `max_iterations=7`,
  `end_condition="k == true"` (CEL), and a 2-entry `steps` body
- **WHEN** built
- **THEN** the `Loop.max_iterations == 7`
- **AND** `Loop.end_condition == "k == true"` (CEL string passed through)
- **AND** `len(Loop.steps) == 2`

#### Scenario: Empty Loop body still works (backward compatible)

- **GIVEN** a `type="Loop"` step with NO `steps` field (or `steps=[]`)
- **WHEN** built
- **THEN** construction succeeds
- **AND** `Loop.steps == []` (existing behavior preserved)

### Requirement: Backward compatibility for previously-valid YAML

Any YAML that validated under the prior (stricter) schema MUST continue
to validate and produce the same factory output shape. Only the Loop
restriction is relaxed; the `Step`, `Router`, and other branches MUST
still reject `steps` as before.

#### Scenario: Parallel and Steps still accept nested steps

- **WHEN** `StepConfig(type="Parallel", steps=[...])` and
  `StepConfig(type="Steps", steps=[...])` are constructed
- **THEN** both succeed (unchanged behavior)
