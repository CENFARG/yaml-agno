# Exploration: quality-jd-fixes

> Scope: bounded investigation of the 8 Judgment Day Round 2 findings (Judge A obs #2732, Judge B obs #2733) in `yaml-agno`. No fixes proposed — current-state understanding only.
> Date: 2026-08-08. Branch under investigation: `quality/jd-fixes`.

## Current State

The project is on branch `quality/jd-fixes` with **3 remediation commits already landed** (2026-08-07 23:56–23:58) and **1 uncommitted working-tree change**. All 104 tests in the affected suites pass; `ruff` passes; `mypy --strict` currently fails with **1 error** caused by the uncommitted change.

### Per-finding status

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| 1 | **StepType.FUNCTION never tested** (WARNING) | **OPEN — test gap confirmed** | Fold at `workflow_factory.py:281` (`if t in (StepType.STEP, StepType.FUNCTION)`). Every workflow test uses `type="Step"` — incl. all function-executor tests (`test_workflow_factory.py:454,466,793,815,853`). Model-level discriminator test (`test_workflow_config.py:312-320`) iterates all 8 StepType members but only for `StepConfig` construction, not factory dispatch. If Agno drops/renames FUNCTION, the fold silently mis-dispatches (falls through to `_STEP_BUILDERS.get(FUNCTION)` → None → ValueError at line 306). |
| 2 | Dead mock `_settings.enabled = True` (test lines 529,575,601,626) | **ALREADY REMEDIATED** | Commit `4c5bcc8` "test: remove dead _settings.enabled mock setup in agentos_factory tests" (2026-08-07 23:58). `grep _settings` in `test_agentos_factory.py` returns zero hits. The factory reads `config.mcp.enabled`, never lifecycle internals. |
| 3 | Redundant `kwargs.pop("config")`/`("resync")` in `_assemble_app` lines 340,343 | **ALREADY REMEDIATED** | Commit `96593e6` "refactor: remove redundant kwargs.pop in _assemble_app" (2026-08-07 23:57). Current `_assemble_app` (lines 325-338) is a clean `return AgentOS(**kwargs)`; `_pop_owned_keys` (lines 388-408) already strips `config`/`resync`. |
| 4 | Missing edge case `type="Function"` + `agent=` both set | **OPEN — gap confirmed** | `_build_step_executor` (`workflow_factory.py:349-418`) checks `agent` first, then `team`, then `function` — agent wins, function path unreachable when both set. No test exercises this precedence. Note: `StepConfig.validate_type_specific_fields` (workflow_config.py:72-101) does NOT forbid `agent` + `function` together, so the combo is schema-valid. |
| 5 | `step_executor` passthrough untested in defensive-branch resolution tests | **OPEN — gap confirmed** | Defensive tests (`test_workflow_factory.py:707-765`: missing `if_true`/`if_false`/case) build without `step_executor`. The passthrough is wired (`workflow_factory.py:317,509,548,592,668,722`) but never asserted in a defensive-branch scenario (e.g. Condition missing branch + step_executor given). |
| 6 | Router `expression=None` → `selector=None` not tested | **OPEN — gap confirmed** | `_build_router_group` (lines 674-679): `selector: Any = None; if step_cfg.expression is not None: selector = _resolve_callable_or_cel(...)`. All Router tests pass an `expression` (lines 296,318,597,643,757); none asserts `router.selector is None` when expression omitted. |
| 7 | `_STEP_BUILDERS` mutable dict → MappingProxyType | **IN PROGRESS — breaks mypy** | Uncommitted working-tree diff wraps the dict in `MappingProxyType` (`workflow_factory.py:744`) but **keeps the `dict[...]` annotation** → `mypy: Incompatible types in assignment (expression has type MappingProxyType..., variable has type dict...)` at line 744. `ruff` passes. Fix requires annotation `Mapping[StepType, Callable[..., _BuiltStep]]` (import from `collections.abc`). |
| 8 | `_build_mcp_config` comment "warn once" vs warns every call | **ALREADY REMEDIATED** | Commit `382ca8e` "docs: fix misleading 'warn once' comment in _build_mcp_config" (2026-08-07 23:56). Current comment (line 547): "warn per build call". Behavior matches comment. |

## Affected Areas

- `src/yaml_agno/factories/workflow_factory.py` — findings #1, #4, #5, #6, #7. Fold at :281; executor precedence at :349-418; router selector default at :674-679; `_STEP_BUILDERS` at :744.
- `tests/unit/factories/test_workflow_factory.py` — findings #1, #4, #5, #6 (all test gaps live here; 883 lines).
- `src/yaml_agno/factories/agentos_factory.py` — findings #2, #3, #8 (already remediated; verify-only).
- `tests/unit/factories/test_agentos_factory.py` — finding #2 (already remediated).
- `src/yaml_agno/models/config/workflow_config.py` — finding #4 context: no validator forbidding agent+function coexistence (lines 72-101).

## Approaches (remediation options for the OPEN findings)

1. **Pure test-gap closure (F1, F4, F5, F6)** — add targeted tests: `type="Function"` dispatch, agent-over-function precedence, step_executor passthrough in defensive branches, Router expression=None → selector=None.
   - Pros: Zero production-code risk; directly addresses the WARNING and 3 suggestions; strict-TDD project convention.
   - Cons: Tests document current precedence behavior without a schema-level guard for #4.
   - Effort: Low

2. **Test gap + schema guard for #4** — also add a `model_validator` on `StepConfig` rejecting `agent`+`function` simultaneously.
   - Pros: Prevents the ambiguous combo at the boundary (fail-fast per project philosophy).
   - Cons: Slightly larger surface; must align with SPEC_02/SSOT and could surprise existing configs (none use the combo today, verified).
   - Effort: Low-Medium

3. **Fix the in-progress F7 (MappingProxyType) annotation** — change `dict[...]` → `Mapping[...]` so mypy passes.
   - Pros: Completes the already-started hardening; restores `mypy --strict` green (1 error currently).
   - Cons: None material.
   - Effort: Trivial

## Recommendation

Landed commits already close #2, #3, #8 — treat those as verify-only. The active remediation should: (a) fix the `_STEP_BUILDERS` annotation to restore mypy (#7), and (b) close the four test gaps (#1, #4, #5, #6) with new tests. Decide whether #4 is test-only (Approach 1) or also schema-guarded (Approach 2) during design — the precedence behavior is deterministic and documented, so test-only is defensible for a low-risk change.

## Risks

- The uncommitted `_STEP_BUILDERS` change is currently the ONLY blocker on `mypy --strict`; committing it as-is ships a type error.
- Finding #1 is a WARNING, not a suggestion: if Agno's StepType loses FUNCTION in a future upgrade, the fold fails with a misleading "Unsupported step type" ValueError at build time rather than a clear rename error. The test gap is the guard.
- Scope discipline: findings #2/#3/#8 are already committed on this branch — do not re-implement them; verify-only.
- The previous SDD pipeline (obs #2728-2731, topic `sdd/quality-jd-fixes/*`) scoped **5** findings; Judge B's #4/#5/#6 (edge-case tests) were NOT in that scope. The spec/design/tasks may need a delta to cover them.

## Ready for Proposal

Yes — current state is fully mapped. Orchestrator should tell the user: 3/8 findings already fixed and committed; 1 in-progress (breaks mypy, needs annotation fix); 4 open test-gap findings ready to scope.
