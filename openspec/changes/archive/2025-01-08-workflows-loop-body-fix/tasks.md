# Tasks: workflows-loop-body-fix

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~80-120 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Relax validator + factory Loop body build + tests | PR 1 | `pytest tests/unit/factories/test_workflow_factory.py::TestLoopDispatch tests/unit/models/test_workflow_config.py -k "loop or Loop"` | N/A — pure-construction unit tests, no workflow run | Revert `workflow_config.py:84` tuple + `workflow_factory.py:392-411` branch |

## Phase 1: Schema relaxation (RED→GREEN)

- [x] 1.1 Add `test_loop_with_body_ok` to `tests/unit/models/test_workflow_config.py` (RED: asserts `StepConfig(type="Loop", steps=[...])` validates) — next to `test_loop_with_iterations_ok:204`.
- [x] 1.2 MODIFY `src/yaml_agno/models/config/workflow_config.py:84` — add `StepType.LOOP` to the validator tuple; update error message to `"Nested steps only allowed for Parallel/Steps/Condition/Loop types."`
- [x] 1.3 Update the `steps` field docstring (`workflow_config.py:56`) to `"Nested steps (Parallel/Steps/Condition/Loop)."`.
- [x] 1.4 Confirm `test_loop_with_body_ok` now passes (GREEN); confirm `test_loop_fields_on_non_loop_rejected` still passes (other types still reject).

## Phase 2: Factory Loop branch (RED→GREEN)

- [x] 2.1 Add `test_dispatch_loop_builds_nested_body` and `test_dispatch_loop_empty_body_backward_compat` to `TestLoopDispatch` in `tests/unit/factories/test_workflow_factory.py` (RED for the nested-body case).
- [x] 2.2 MODIFY `src/yaml_agno/factories/workflow_factory.py:392-411` — replace the `steps=[]` literal and SPEC_05 TODO comment with the recursive `_build_step` list-comprehension mirroring the Parallel/Steps branches; keep `max_iterations` / `end_condition` logic unchanged; drop the now-unneeded `# type: ignore[arg-type]`.
- [x] 2.3 Confirm both new tests pass (GREEN) and the existing `test_dispatch_loop_cel_end_condition_and_max_iter`, `test_dispatch_loop_callable_end_condition`, `test_dispatch_loop_default_max_iterations` still pass.

## Phase 3: Cleanup

- [x] 3.1 Edit the `test_dispatch_loop_cel_end_condition_and_max_iter` docstring (`test_workflow_factory.py:344-346`) to remove the now-false "schema forbids steps on Loop type" note.
- [x] 3.2 Run the full factory + config test modules: `pytest tests/unit/factories/test_workflow_factory.py tests/unit/models/test_workflow_config.py` — all green.
- [x] 3.3 Run `pytest -q` repo-wide to confirm no regressions outside the two touched modules.
