# Tasks: CircuitBreaker Foundation (SPEC_09 Slice A)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150 (module) + ~220 (tests) = ~370 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Pure CircuitBreaker state machine + error + package | PR 1 | `pytest tests/unit/resilience/` | N/A — pure in-process, no I/O; verify via `python -c "from yaml_agno.resilience import CircuitBreaker, CircuitBreakerOpenError, CircuitState"` | Delete `src/yaml_agno/resilience/` + `tests/unit/resilience/` in one revert; no consumers exist |

## Phase 1: Baseline / Scaffolding

- [x] 1.1 Create `src/yaml_agno/resilience/__init__.py` re-exporting `CircuitBreaker`, `CircuitBreakerOpenError`, `CircuitState` (REQ-010.3).
- [x] 1.2 Create `tests/unit/resilience/__init__.py` and a stub `test_circuit_breaker.py` so collection is green before any logic exists.

## Phase 2: RED — Failing Tests First (strict TDD)

- [x] 2.1 `test_circuit_state_enum_members` — asserts `CLOSED="closed"`, `OPEN="open"`, `HALF_OPEN="half_open"` (REQ-001, Scenario: metrics shape).
- [x] 2.2 `test_defaults_match_spec_09` — parametrized assertion of defaults `50.0 / 30.0 / 10 / 3` and zeroed counters (REQ-002).
- [x] 2.3 `test_circuit_breaker_open_error_is_exception` — `issubclass(CircuitBreakerOpenError, Exception)` (REQ-009).
- [x] 2.4 `test_record_success_increments_counters_closed` (REQ-003.1, Scenario: CLOSED golden path).
- [x] 2.5 `test_min_requests_gate_prevents_trip` — 5 failures of 5 requests, `_should_trip` False, state stays CLOSED (REQ-005.1, Scenario: no trip below gate).
- [x] 2.6 `test_failure_rate_trips_at_threshold` — 6 failures of 10 requests, CLOSED→OPEN (REQ-005.2, REQ-004.3, Scenario: rate-based trip).
- [x] 2.7 `test_open_blocks_until_recovery_timeout` — `allow_request` False while elapsed < timeout, True after, state flips to HALF_OPEN, `half_open_calls` reset (REQ-006.2-3, Scenario: OPEN blocks + OPEN→HALF_OPEN).
- [x] 2.8 `test_half_open_success_closes_circuit` — 3 successes in HALF_OPEN→CLOSED, counters reset (REQ-003.2, Scenario: HALF_OPEN→CLOSED).
- [x] 2.9 `test_half_open_failure_reopens` — one failure in HALF_OPEN→OPEN (REQ-004.2, Scenario: HALF_OPEN→OPEN).
- [x] 2.10 `test_execute_raises_when_open` — `pytest.raises(CircuitBreakerOpenError)`, func never awaited (REQ-007.2, Scenario: execute blocked).
- [x] 2.11 `test_execute_records_success_and_returns_result` — async stub returns value, success_count increments (REQ-007.1,3,4, Scenario: execute success).
- [x] 2.12 `test_execute_records_failure_and_reraises` — async stub raises ValueError, failure_count increments, ValueError propagates unchanged (REQ-007.5, Scenario: execute failure).
- [x] 2.13 `test_get_state_metrics_shape_and_zero_div_guard` — keys present, `state="closed"`, `failure_rate=0.0` when zero requests (REQ-008, Scenario: metrics shape).

## Phase 3: GREEN — Implement to Pass

- [x] 3.1 Create `src/yaml_agno/resilience/circuit_breaker.py` with the literal source from design §Interfaces (REQ-001..010): `CircuitBreakerOpenError`, `CircuitState`, `CircuitBreaker`.
- [x] 3.2 Run `pytest tests/unit/resilience/` until all 13 tests are GREEN; add the minimum code per failing test, no extra behavior.

## Phase 4: Verification

- [x] 4.1 `pytest tests/unit/resilience/ -v` — all scenarios green.
- [x] 4.2 `ruff check src/yaml_agno/resilience/` — clean.
- [x] 4.3 `mypy src/yaml_agno/resilience/` — clean per project config.
- [x] 4.4 Smoke import: `python -c "from yaml_agno.resilience import CircuitBreaker, CircuitBreakerOpenError, CircuitState; print('ok')"` after `pip install -e .`.
- [x] 4.5 GATE VQ — confirm REQ coverage matrix (REQ-001..010 each has a passing scenario) and that DEFERRED REQ-011 items (telemetry B, ResilientExecutor C, error classification) are absent from the diff.

## Phase 5: Commit

- [x] 5.1 Commit as a single PR with conventional-commit message `feat(resilience): add CircuitBreaker state machine (SPEC_09 slice A)`.
