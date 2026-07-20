# Design: workflows-loop-body-fix

## Overview

Two literal edits close the Loop body gap: relax one validator line in
`StepConfig`, and replace the `steps=[]` literal in the factory's Loop
branch with the same recursive build loop already used by the
`Parallel`/`Steps` branches. No new fields, no new types, no new public
API.

## Files Touched

| File | Change |
|------|--------|
| `src/yaml_agno/models/config/workflow_config.py` | Relax nested-steps validator to admit `StepType.LOOP`; update error message. |
| `src/yaml_agno/factories/workflow_factory.py` | Loop branch builds nested steps recursively; remove `steps=[]` literal and SPEC_05 TODO comment. |
| `tests/unit/models/test_workflow_config.py` | Add positive test: Loop WITH body validates; ensure non-Loop types still reject. |
| `tests/unit/factories/test_workflow_factory.py` | Update existing Loop test docstring; add test asserting Loop builds nested Step body. |

## Change 1 — Schema relaxation

**File**: `src/yaml_agno/models/config/workflow_config.py`
**Current** (lines 83-85):

```python
# (1) Nested steps apply to Parallel, Steps and Condition.
if self.steps and t not in (StepType.PARALLEL, StepType.STEPS, StepType.CONDITION):
    raise ValueError("Nested steps only allowed for Parallel/Steps/Condition types.")
```

**After**:

```python
# (1) Nested steps apply to Parallel, Steps, Condition and Loop
#     (SPEC_05 slice A: Loop body relaxation).
if self.steps and t not in (StepType.PARALLEL, StepType.STEPS, StepType.CONDITION, StepType.LOOP):
    raise ValueError("Nested steps only allowed for Parallel/Steps/Condition/Loop types.")
```

Also update the field docstring at line 56 from
`"Nested steps (Parallel/Steps/Condition)."` to
`"Nested steps (Parallel/Steps/Condition/Loop)."` for SSOT consistency.

The class-level docstring listing "4 type-specific groups" (lines 68-70)
remains accurate: nested-steps now covers 4 types but is still one
group.

## Change 2 — Factory Loop branch

**File**: `src/yaml_agno/factories/workflow_factory.py`
**Current** (lines 392-411):

```python
# --- Loop (max_iterations + optional end_condition) ---
if t == StepType.LOOP:
    # NOTE: StepConfig's validator forbids `steps` on Loop type (only
    # Parallel/Steps/Condition allow nested steps), so the Loop body is
    # structurally empty here. Non-empty Loop bodies need a dedicated
    # field in SPEC_02 or a schema relaxation — tracked for SPEC_05
    # (workflows runtime). Until then Loop builds with steps=[].
    # Open Item #1: resolve end_condition via _resolve_callable_or_cel.
    end_condition: Any = None
    if step_cfg.end_condition is not None:
        end_condition = WorkflowFactory._resolve_callable_or_cel(
            step_cfg.end_condition, callables
        )
    return Loop(
        steps=[],  # type: ignore[arg-type]
        name=step_cfg.step,
        description=step_cfg.description,
        max_iterations=step_cfg.max_iterations if step_cfg.max_iterations is not None else 3,
        end_condition=end_condition,
    )
```

**After**:

```python
# --- Loop (nested body + max_iterations + optional end_condition) ---
if t == StepType.LOOP:
    # SPEC_05 slice A: Loop body now builds recursively, mirroring the
    # Parallel/Steps branches. The validator admits `steps` on Loop.
    nested = [
        WorkflowFactory._build_step(
            step_cfg=StepConfig(**raw),
            agents=agents,
            teams=teams,
            callables=callables,
            step_index=step_index,
        )
        for raw in step_cfg.steps
    ]
    # Open Item #1: resolve end_condition via _resolve_callable_or_cel.
    end_condition: Any = None
    if step_cfg.end_condition is not None:
        end_condition = WorkflowFactory._resolve_callable_or_cel(
            step_cfg.end_condition, callables
        )
    return Loop(
        steps=nested,
        name=step_cfg.step,
        description=step_cfg.description,
        max_iterations=step_cfg.max_iterations if step_cfg.max_iterations is not None else 3,
        end_condition=end_condition,
    )
```

The `# type: ignore[arg-type]` is dropped because `nested` is a real
`list` (the prior ignore was needed only because `[]` confused mypy on
the Agno overload).

## Change 3 — Tests

**File**: `tests/unit/models/test_workflow_config.py`

Add a positive case next to `test_loop_with_iterations_ok` (line 204):

```python
def test_loop_with_body_ok(self) -> None:
    """SPEC_05 slice A: Loop now accepts nested steps."""
    s = StepConfig(
        step="l", type="Loop",
        steps=[{"step": "inner", "type": "Step", "agent": "a1"}],
        max_iterations=5, end_condition="done == true",
    )
    assert s.type.value == "Loop"
    assert len(s.steps) == 1
    assert s.max_iterations == 5
```

The existing `test_loop_fields_on_non_loop_rejected` (line 193) still
guards `max_iterations` on non-Loop types and stays unchanged.

**File**: `tests/unit/factories/test_workflow_factory.py`

1. Edit `test_dispatch_loop_cel_end_condition_and_max_iter` (line 337):
   remove the "Note: the shipped StepConfig schema forbids steps on Loop
   type" paragraph from the docstring — that note is now false.

2. Add a new test in `TestLoopDispatch`:

```python
def test_dispatch_loop_builds_nested_body(self) -> None:
    """SPEC_05 slice A: Loop body steps are built recursively."""
    agent = _agent("a1")
    cfg = _workflow_cfg([
        StepConfig(step="l", type="Loop", max_iterations=4,
                   end_condition="k == true",
                   steps=[{"step": "inner", "type": "Step", "agent": "a1"}]),
    ])
    result = WorkflowFactory.build(cfg, agents={"a1": agent}, teams={})
    loop = result.steps[0]
    assert isinstance(loop, Loop)
    assert loop.max_iterations == 4
    assert loop.end_condition == "k == true"
    assert len(loop.steps) == 1
    assert isinstance(loop.steps[0], Step)
    assert loop.steps[0].name == "inner"
    assert loop.steps[0].agent is agent

def test_dispatch_loop_empty_body_backward_compat(self) -> None:
    """Loop with no steps still builds Loop(steps=[])."""
    cfg = _workflow_cfg([StepConfig(step="l", type="Loop")])
    result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
    loop = result.steps[0]
    assert isinstance(loop, Loop)
    assert loop.steps == []
```

The `_agent` / `_workflow_cfg` / `Step` / `Loop` imports are already in
scope at the top of the test file (lines 34-53).

## Threat Matrix

| Case | Risk | RED test | Mitigation |
|------|------|----------|------------|
| Schema relaxation leaks to wrong type (e.g. Step now accepts `steps`) | Medium | `StepConfig(type="Step", steps=[...])` still raises in `test_workflow_config.py` | Validator tuple is extended, not replaced; existing rejection tests still run. |
| Factory builds wrong primitive for nested Loop body | Medium | `test_dispatch_loop_builds_nested_body` asserts `isinstance(loop.steps[0], Step)` | Reuses the proven `_build_step` recursion. |
| Backward-compat regression — empty Loop body breaks | Low | `test_dispatch_loop_empty_body_backward_compat` | `nested` list-comprehension yields `[]` when `step_cfg.steps` is empty. |
| `max_iterations` / `end_condition` regression on Loop | Low | Existing `test_dispatch_loop_cel_end_condition_and_max_iter` + new nested-body test both assert these | Resolver + default logic unchanged. |

Rows marked N/A: none — all four risks above are explicit.

## Edge Cases

- Empty `steps` on Loop → list-comprehension yields `[]`, identical to
  prior behavior. Verified by the backward-compat test.
- Loop body referencing a step-id that needs `step_index` (Condition /
  Router style): out of scope — the body is built from raw dicts via
  `StepConfig(**raw)` exactly as Parallel/Steps do today, so
  `if_true`/`if_false`/`cases` semantics inside a Loop body inherit the
  existing Parallel/Steps behavior unchanged.

## Rollback

Revert Change 1 (validator tuple) and Change 2 (Loop branch). Tests in
Change 3 will then fail clearly, which is expected on rollback.
