# Spec: circuit-breaker-foundation

> SPEC_09 slice A — foundational, zero-dependency `CircuitBreaker` state machine.
> Pure Python stdlib only (`time`, `enum`, `typing`). No core-cenf, no Agno,
> no telemetry, no retry.

## Purpose

Protect downstream callers from cascading failures with a 3-state finite state
machine (`CLOSED → OPEN → HALF_OPEN`). Rate-based tripping gated by a
`min_requests` floor prevents false trips on cold start. Time-based recovery
plus a bounded `HALF_OPEN` probe window prevents flapping. This slice is the
self-contained prerequisite that unblocks SPEC_05 `ResilientExecutor` (slice C).

## Requirements

The words "MUST", "MUST NOT", "SHOULD", and "MAY" follow RFC 2119.

### REQ-001: `CircuitState` enum

1. The module MUST define `CircuitState(str, Enum)` with exactly three members:
   `CLOSED = "closed"`, `OPEN = "open"`, `HALF_OPEN = "half_open"`.
2. `CircuitState` MUST NOT carry behavior beyond membership and string value.

### REQ-002: `CircuitBreaker` constructor defaults

1. The constructor MUST accept `failure_threshold: float`, `recovery_timeout:
   float`, `min_requests: int`, and `half_open_max_calls: int`.
2. The constructor defaults MUST be `failure_threshold=50.0`,
   `recovery_timeout=30.0`, `min_requests=10`, `half_open_max_calls=3`.
3. The constructor MUST initialize the instance to `CircuitState.CLOSED` with
   all counters (`failure_count`, `success_count`, `total_requests`,
   `half_open_calls`) at `0` and `last_failure_time` at `0`.

### REQ-003: `record_success` counter update

1. `record_success()` MUST increment `total_requests` and `success_count`.
2. In `HALF_OPEN`, `record_success()` MUST increment `half_open_calls` and,
   once `success_count >= half_open_max_calls`, transition to `CLOSED` and
   reset `failure_count`, `success_count`, and `half_open_calls` to `0`.
3. In `CLOSED` or `OPEN`, `record_success()` MUST NOT mutate `state`.

### REQ-004: `record_failure` counter update

1. `record_failure()` MUST increment `total_requests` and `failure_count` and
   set `last_failure_time` to the current time.
2. In `HALF_OPEN`, `record_failure()` MUST transition to `OPEN`.
3. In `CLOSED`, `record_failure()` MUST transition to `OPEN` only when
   `_should_trip()` returns `True`.

### REQ-005: `_should_trip` rate-based with `min_requests` gate

1. `_should_trip()` MUST return `False` when
   `total_requests < min_requests`.
2. Once `total_requests >= min_requests`, `_should_trip()` MUST return `True`
   when `(failure_count / total_requests) * 100 >= failure_threshold`, else
   `False`.
3. `_should_trip()` MUST guard against division by zero.

### REQ-006: `allow_request` admission by state

1. In `CLOSED`, `allow_request()` MUST return `True`.
2. In `OPEN`, `allow_request()` MUST return `False` while
   `current_time - last_failure_time < recovery_timeout`.
3. In `OPEN`, once `current_time - last_failure_time >= recovery_timeout`,
   `allow_request()` MUST transition to `HALF_OPEN`, reset `half_open_calls`
   to `0`, and return `True`.
4. In `HALF_OPEN`, `allow_request()` MUST return `True` while
   `half_open_calls < half_open_max_calls`, else `False`.

### REQ-007: `async execute` wrapper

1. `execute(func, *args, **kwargs)` MUST be a coroutine.
2. If `allow_request()` returns `False`, `execute` MUST raise
   `CircuitBreakerOpenError` and MUST NOT call `func`.
3. `execute` MUST `await func(*args, **kwargs)`.
4. On success, `execute` MUST call `record_success()` and return the result.
5. On exception from `func`, `execute` MUST call `record_failure()` and
   re-raise the original exception unchanged (no swallowing, no wrapping
   beyond the `CircuitBreakerOpenError` path in item 2).

### REQ-008: `get_state_metrics` shape

1. `get_state_metrics()` MUST return a `dict[str, Any]` with the keys
   `state`, `failure_rate`, `total_requests`, `success_count`,
   `failure_count`, `last_failure_time`.
2. `state` MUST be the `CircuitState`'s string value.
3. `failure_rate` MUST be `(failure_count / total_requests) * 100` rounded to
   two decimals, and MUST be `0.0` when `total_requests == 0` (zero-division
   guard).

### REQ-009: `CircuitBreakerOpenError` exception

1. The module MUST define `CircuitBreakerOpenError(Exception)`.
2. `CircuitBreakerOpenError` MUST be a subclass of the built-in `Exception`
   and MUST introduce no other public surface.

### REQ-010: Zero external dependencies

1. The module MUST import only from the Python standard library
   (`time`, `enum`, `typing`, `__future__`).
2. The module MUST NOT import from core-cenf, Agno, or any other yaml-agno
   module.
3. `resilience/__init__.py` MUST re-export `CircuitBreaker`,
   `CircuitBreakerOpenError`, and `CircuitState` and nothing else in
   `__all__`.

### REQ-011 (DEFERRED — out of scope for this slice)

The following are explicitly DEFERRED and MUST NOT be implemented in slice A:

1. **Telemetry / instrumentation** (slice B: `telemetry/metrics.py`,
   `telemetry/tracing.py`) — no metrics emission, no tracing spans.
2. **`ResilientExecutor`** (slice C: composition with SPEC_05 `RetryPolicy`)
   — no retry, no `should_retry`/`is_retryable` reconciliation.
3. **Error classification** — remains in core-cenf
   `ErrorHandlingManager.classify()`. `record_failure()` MUST treat any
   raised `Exception` as a failure without inspecting type or category.

## Scenarios

### Scenario: CLOSED allows all requests (golden path)

```gherkin
Feature: CircuitBreaker state machine

  Scenario: CLOSED admits requests and counts successes
    Given a CircuitBreaker with default thresholds
    And the breaker state is CLOSED
    When allow_request is called
    Then it returns True
    When record_success is called 3 times
    Then success_count is 3
    And total_requests is 3
    And the state remains CLOSED
```

### Scenario: Trip after threshold AND min_requests reached

```gherkin
  Scenario: Rate-based trip CLOSED -> OPEN
    Given a CircuitBreaker with failure_threshold=50.0 and min_requests=10
    And the breaker state is CLOSED
    When record_failure is called 6 times
    And record_success is called 4 times
    Then total_requests is 10
    And failure_count is 6
    And the failure_rate is 60.0
    And the state transitions to OPEN
```

### Scenario: No trip below min_requests gate

```gherkin
  Scenario: min_requests gate suppresses trip on cold start
    Given a CircuitBreaker with failure_threshold=50.0 and min_requests=10
    And the breaker state is CLOSED
    When record_failure is called 5 times
    Then total_requests is 5
    And _should_trip returns False
    And the state remains CLOSED
```

### Scenario: OPEN blocks requests

```gherkin
  Scenario: OPEN rejects until recovery_timeout elapses
    Given a CircuitBreaker in state OPEN
    And last_failure_time set to now
    When allow_request is called with elapsed < recovery_timeout
    Then it returns False
    And the state remains OPEN
```

### Scenario: OPEN transitions to HALF_OPEN after timeout

```gherkin
  Scenario: OPEN -> HALF_OPEN on recovery_timeout
    Given a CircuitBreaker in state OPEN
    And recovery_timeout=30.0
    When allow_request is called with elapsed >= recovery_timeout
    Then it returns True
    And the state transitions to HALF_OPEN
    And half_open_calls is reset to 0
```

### Scenario: HALF_OPEN closes on successive successes

```gherkin
  Scenario: HALF_OPEN -> CLOSED when probe successes reach cap
    Given a CircuitBreaker in state HALF_OPEN with half_open_max_calls=3
    When record_success is called 3 times
    Then success_count is 3
    And the state transitions to CLOSED
    And failure_count, success_count, and half_open_calls are reset to 0
```

### Scenario: HALF_OPEN reopens on any failure

```gherkin
  Scenario: HALF_OPEN -> OPEN on a single probe failure
    Given a CircuitBreaker in state HALF_OPEN
    When record_failure is called once
    Then the state transitions to OPEN
    And last_failure_time is updated
```

### Scenario: async execute success path

```gherkin
  Scenario: execute awaits func and records success
    Given a CircuitBreaker in state CLOSED
    And an async func that returns "ok"
    When execute is called with func
    Then it returns "ok"
    And success_count is 1
    And total_requests is 1
```

### Scenario: async execute blocked when OPEN

```gherkin
  Scenario: execute raises CircuitBreakerOpenError when OPEN
    Given a CircuitBreaker in state OPEN with elapsed < recovery_timeout
    And an async func that returns "ok"
    When execute is called with func
    Then it raises CircuitBreakerOpenError
    And func is never awaited
    And total_requests remains 0
```

### Scenario: async execute records failure and re-raises

```gherkin
  Scenario: execute records failure and propagates the original exception
    Given a CircuitBreaker in state CLOSED
    And an async func that raises ValueError("boom")
    When execute is called with func
    Then it raises ValueError("boom")
    And failure_count is 1
    And total_requests is 1
```

### Scenario: metrics shape and zero-division guard

```gherkin
  Scenario: get_state_metrics returns the documented shape
    Given a fresh CircuitBreaker with zero requests
    When get_state_metrics is called
    Then the result contains keys state, failure_rate, total_requests,
      success_count, failure_count, last_failure_time
    And state is "closed"
    And failure_rate is 0.0
    And total_requests is 0
```
