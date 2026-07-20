# Proposal: workflows-loop-body-fix

## Why

SPEC_02's `StepConfig` validator forbids the `steps` field on
`StepType.LOOP` — only `Parallel`/`Steps`/`Condition` may carry nested
steps. As a result `WorkflowFactory._build_step` builds every Loop with
`steps=[]` (see `workflow_factory.py:392-411` and the in-source comment
that explicitly defers this to SPEC_05). A Loop with an empty body
cannot iterate over meaningful work, so non-trivial Loop workflows are
unreachable today. This is the foundational "Loop body gap" debt called
out by SPEC_05 slice A; closing it unblocks realistic Loop workflows and
is a prerequisite for SPEC_29 (human-review gates, which sit inside Loop
bodies).

## What Changes

- **Schema relaxation** — `StepConfig.validate_type_specific_fields`
  (`workflow_config.py:84-85`) admits `StepType.LOOP` into the set of
  types allowed to carry nested `steps`. Error message is updated to
  name the new allowed set.
- **Factory build** — the `StepType.LOOP` branch in
  `WorkflowFactory._build_step` (`workflow_factory.py:393-411`) drops the
  `steps=[]` literal and the SPEC_05 TODO comment, and instead builds
  nested steps via the same recursive `_build_step` loop already used by
  the `Parallel`/`Steps` branches. `max_iterations` and `end_condition`
  behavior is unchanged.
- **Tests** — update the existing Loop test docstring that asserts the
  "empty body" behavior, and add a positive test that asserts a Loop
  WITH body steps is built with the nested `Step` primitives in order.

## Impact

- **Affected files**: 2 source + 2 test files (see Tasks).
- **Public contract**: this RELAXES a config-level restriction; YAML that
  was previously rejected (`type: Loop` with a `steps:` block) is now
  accepted. No previously-valid YAML becomes invalid. No factory return
  type changes — the Loop is still `agno.workflow.loop.Loop`.
- **Risk**: Low. Pure relaxation plus reusing the existing recursive
  builder already proven by Parallel/Steps. No network, no LLM, no
  session is introduced at build time.
- **Rollback**: revert the 2 source changes; tests will follow.

## Non-Goals

- No new fields on `StepConfig` (the existing `steps` field is reused).
- No change to `end_condition` / `max_iterations` semantics.
- No change to the other 6 primitive branches.
- No SPEC_29 review-gate wiring inside Loop bodies — that is later work
  that depends on this slice landing first.

## Out of Scope

Nested-workflow executors (`type: Workflow`), Loop runtime semantics
beyond construction, and any change to `WorkflowConfig` (top-level
schema) remain untouched.
