# Design: circuit-breaker-foundation

> Technical design for SPEC_09 slice A — the foundational, zero-dependency
> `CircuitBreaker` state machine that unblocks SPEC_05 `ResilientExecutor`
> (slice C). Pure Python, no core-cenf, no Agno imports.

## Technical Approach

A single self-contained module `src/yaml_agno/resilience/circuit_breaker.py`
implementing a 3-state finite state machine (`CLOSED → OPEN → HALF_OPEN`) with
rate-based tripping gated by a `min_requests` floor, time-based recovery, and a
bounded `HALF_OPEN` probe window. The class exposes `record_success`,
`record_failure`, `allow_request`, an `async execute()` wrapper, and
`get_state_metrics()`. A dedicated `CircuitBreakerOpenError` is raised when a
request is rejected. `__init__.py` re-exports the public surface.

This is a verbatim transcription of the literal code in SPEC_09 §4.1 (lines
336–485) plus the `CircuitBreakerOpenError` class that §4.1 references
(`raise CircuitBreakerOpenError(...)`) without inlining. No error
classification lives here (SPEC_09 §4 @ai-directive: classification belongs to
core-cenf `ErrorHandlingManager.classify()`).

## Architecture Decisions

### Decision: pure state machine, no error classification

- **Choice**: `CircuitBreaker` only counts success/failure and transitions state. `execute()` treats any raised `Exception` as a failure; the caller (slice C `ResilientExecutor`) decides what counts via SPEC_05 classification.
- **Alternatives considered**: inline `ErrorCategory` enum + `type(e).__name__` matching inside the breaker.
- **Rationale**: SPEC_09 §4 @ai-directive explicitly forbids classification in the breaker; keeping it pure makes it unit-testable with trivial stubs and avoids the SPEC_09/SPEC_05 `should_retry` divergence flagged in exploration risk (a).

### Decision: rate-based trip with `min_requests` gate

- **Choice**: `_should_trip` returns `False` until `total_requests >= min_requests` (default 10), then trips when `failure_count / total_requests * 100 >= failure_threshold` (default 50.0%).
- **Alternatives considered**: absolute failure-count threshold (e.g. "trip after N failures"); sliding-window percentile.
- **Rationale**: rate-based avoids false trips on low-traffic cold start; the `min_requests` floor is the literal default from SPEC_09 §4.1 line 362 and matches DEFER002 in `.chats/decisions.yaml`.

### Decision: time-based recovery + bounded `HALF_OPEN` probe

- **Choice**: `OPEN → HALF_OPEN` fires inside `allow_request()` when `time.time() - last_failure_time >= recovery_timeout` (30.0s). `HALF_OPEN` admits up to `half_open_max_calls` (3) probes; on success count reaching the cap it closes, on any failure it re-opens.
- **Alternatives considered**: external timer/thread to flip state; single-probe half-open.
- **Rationale**: lazy transition inside `allow_request()` keeps the machine single-threaded and deterministic; multi-probe `HALF_OPEN` reduces flapping on noisy recovery. Literal from SPEC_09 §4.1 lines 420–440.

### Decision: `async execute()` wrapper

- **Choice**: `execute(func, *args, **kwargs)` awaits `func`, records success/failure, and re-raises on failure. Rejects with `CircuitBreakerOpenError` when `allow_request()` is False.
- **Alternatives considered**: sync-only `execute`; separate `call_sync`/`call_async`.
- **Rationale**: SPEC_09 §4.1 line 442 declares it `async`; Agno model calls are async, so this is the only call shape slice C needs.

### Decision: `CircuitBreakerOpenError` defined in this module

- **Choice**: `class CircuitBreakerOpenError(Exception)` lives in `circuit_breaker.py` and is re-exported from `resilience/__init__.py`.
- **Alternatives considered**: define it in a future `resilience/errors.py`; import from core-cenf.
- **Rationale**: SPEC_09 §4.1 raises it but never inlines a definition; the slice must be self-contained with zero deps, so the exception co-locates with its sole raiser.

## Data Flow

```
caller (slice C ResilientExecutor)
   │
   ▼
CircuitBreaker.execute(func, *args, **kwargs)
   │
   ├─ allow_request()? ── no ──▶ raise CircuitBreakerOpenError
   │      │
   │      ├─ CLOSED            ▶ True
   │      ├─ OPEN + elapsed    ▶ state=HALF_OPEN, True
   │      ├─ OPEN + not elapsed▶ False
   │      └─ HALF_OPEN < cap   ▶ True
   │
   ├─ await func(*args, **kwargs) ── success ──▶ record_success() ──▶ return result
   │                                       │
   │                                       └─ HALF_OPEN && success_count >= half_open_max_calls
   │                                          ▶ state=CLOSED, reset counters
   │
   └─ exception ──▶ record_failure() ──▶ re-raise
                          │
                          ├─ HALF_OPEN ▶ state=OPEN
                          └─ CLOSED && _should_trip() ▶ state=OPEN
```

State transitions: **5** total — `CLOSED→OPEN` (rate trip), `CLOSED→OPEN` (n/a, same path), `OPEN→HALF_OPEN` (timeout in `allow_request`), `HALF_OPEN→CLOSED` (probe successes reach cap), `HALF_OPEN→OPEN` (any probe failure). Distinct transition edges: **4** (`CLOSED→OPEN`, `OPEN→HALF_OPEN`, `HALF_OPEN→CLOSED`, `HALF_OPEN→OPEN`).

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/resilience/__init__.py` | Create | Re-exports `CircuitBreaker`, `CircuitState`, `CircuitBreakerOpenError`. |
| `src/yaml_agno/resilience/circuit_breaker.py` | Create | Literal `CircuitState(str, Enum)`, `CircuitBreaker`, `CircuitBreakerOpenError` from SPEC_09 §4.1. |

## Interfaces / Contracts

### `src/yaml_agno/resilience/circuit_breaker.py`

Literal source (SPEC_09 §4.1 lines 336–485), English Google docstrings, plus the referenced `CircuitBreakerOpenError`:

```python
"""Circuit breaker state machine (SPEC_09 §4.1).

A pure, dependency-free rate-based circuit breaker. Tracks success/failure
counts and transitions between CLOSED, OPEN, and HALF_OPEN. Does NOT
classify errors — the caller decides what counts as a failure
(SPEC_09 §4 @ai-directive: classification belongs to core-cenf
``ErrorHandlingManager.classify``).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable

__all__ = ["CircuitBreaker", "CircuitBreakerOpenError", "CircuitState"]


class CircuitBreakerOpenError(Exception):
    """Raised when ``CircuitBreaker.execute`` rejects a request.

    The circuit is OPEN and no HALF_OPEN probe is available.
    """


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreaker:
    """Rate-based circuit breaker that prevents cascading failures.

    States:
        CLOSED: Normal passthrough.
        OPEN: Reject requests immediately.
        HALF_OPEN: Admit a bounded number of probes to test recovery.

    Args:
        failure_threshold: Failure percentage that trips the circuit.
        recovery_timeout: Seconds before transitioning OPEN -> HALF_OPEN.
        min_requests: Minimum observations before the failure rate is
            evaluated.
        half_open_max_calls: Maximum probe calls admitted in HALF_OPEN.
    """

    def __init__(
        self,
        failure_threshold: float = 50.0,  # % of failures to open
        recovery_timeout: float = 30.0,  # Seconds before HALF_OPEN
        min_requests: int = 10,  # Minimum requests to evaluate
        half_open_max_calls: int = 3,  # Max calls in HALF_OPEN
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.min_requests = min_requests
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.total_requests = 0
        self.last_failure_time = 0
        self.half_open_calls = 0

    def record_success(self) -> None:
        """Record a successful request and update the circuit state.

        In HALF_OPEN, successive successes close the circuit once
        ``half_open_max_calls`` is reached.
        """
        self.total_requests += 1
        self.success_count += 1

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.half_open_calls = 0

    def record_failure(self) -> None:
        """Record a failed request and possibly trip the circuit.

        In HALF_OPEN a single failure re-opens the circuit; in CLOSED the
        failure-rate threshold (``_should_trip``) decides.
        """
        self.total_requests += 1
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif self._should_trip():
            self.state = CircuitState.OPEN

    def _should_trip(self) -> bool:
        """Return True if the failure rate warrants opening the circuit.

        Returns False until ``min_requests`` have been observed.
        """
        if self.total_requests < self.min_requests:
            return False

        failure_rate = (self.failure_count / self.total_requests) * 100
        return failure_rate >= self.failure_threshold

    def allow_request(self) -> bool:
        """Return whether a request should be admitted under the current state.

        CLOSED admits all; OPEN admits none until ``recovery_timeout``
        elapses, then transitions to HALF_OPEN; HALF_OPEN admits up to
        ``half_open_max_calls`` probe requests.
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls

        return False

    async def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Run ``func`` through the circuit breaker.

        Args:
            func: Async callable to execute.
            *args: Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            The result of ``func``.

        Raises:
            CircuitBreakerOpenError: If the circuit is OPEN and no probe
                is allowed.
        """
        if not self.allow_request():
            raise CircuitBreakerOpenError("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

    def get_state_metrics(self) -> dict[str, Any]:
        """Return state metrics for observability.

        Returns:
            Dict with: state, failure_rate, total_requests, success_count,
            failure_count, last_failure_time.
        """
        failure_rate = 0.0
        if self.total_requests > 0:
            failure_rate = (self.failure_count / self.total_requests) * 100

        return {
            "state": self.state.value,
            "failure_rate": round(failure_rate, 2),
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
        }
```

### `src/yaml_agno/resilience/__init__.py`

```python
"""yaml-agno resilience primitives (SPEC_09 §4.1).

Public API:
    from yaml_agno.resilience import CircuitBreaker, CircuitBreakerOpenError
    from yaml_agno.resilience import CircuitState
"""

from yaml_agno.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)

__all__ = ["CircuitBreaker", "CircuitBreakerOpenError", "CircuitState"]
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `record_success` / `record_failure` counter math and idempotent resets on `HALF_OPEN→CLOSED`. | Direct calls, assert internal counters + `state`. |
| Unit | `_should_trip` respects `min_requests` gate (no trip below floor, trip at threshold %). | Parametrized: `(total, failures, expected_trip)`. |
| Unit | `allow_request` state transitions: CLOSED always True; OPEN False until `recovery_timeout` then flips to HALF_OPEN; HALF_OPEN caps at `half_open_max_calls`. | Monkeypatch `time.time` / `CircuitBreaker.last_failure_time`. |
| Unit | `execute` happy path awaits and records success; raises `CircuitBreakerOpenError` when OPEN; records failure and re-raises on exception. | `asyncio.run` with async stubs that succeed/raise; `pytest.mark.asyncio`. |
| Unit | `get_state_metrics` shape and `failure_rate` rounding, including the `total_requests == 0` zero-division guard. | Direct assertion on dict. |
| Unit | Constructor defaults match SPEC_09 §4.1 (50.0 / 30.0 / 10 / 3) and override path works. | Parametrized instantiation. |

## TDD

Strict TDD (project mode: enabled). Order:

1. RED: `test_circuit_breaker_open_error_is_exception` — import fails (module absent).
2. RED: `test_defaults_match_spec_09` — assert the four defaults.
3. RED: `test_min_requests_gate_prevents_trip` — 5 failures of 5 requests does NOT trip (below `min_requests=10`).
4. RED: `test_failure_rate_trips_at_threshold` — 6 failures of 10 requests trips CLOSED→OPEN.
5. RED: `test_open_blocks_until_recovery_timeout` — `allow_request()` False in OPEN, True after monkeypatched elapsed time, and state flips to HALF_OPEN.
6. RED: `test_half_open_success_closes_circuit` — 3 successive HALF_OPEN successes → CLOSED, counters reset.
7. RED: `test_half_open_failure_reopens` — any HALF_OPEN failure → OPEN.
8. RED: `test_execute_raises_when_open` — `pytest.raises(CircuitBreakerOpenError)`.
9. RED: `test_execute_records_success_and_returns_result` — async stub returns value, `success_count` increments.
10. RED: `test_execute_records_failure_and_reraises` — async stub raises, `failure_count` increments, original exception propagates.
11. RED: `test_get_state_metrics_shape_and_zero_div_guard`.

Each RED lands the minimum code from the literal block above to go GREEN. No refactor step changes behavior — the source is already literal.

## Verification

- `pytest tests/unit/resilience/` green (strict TDD, RED→GREEN per step above).
- `ruff check src/yaml_agno/resilience/` clean.
- `mypy src/yaml_agno/resilience/` clean (project config).
- `python -c "from yaml_agno.resilience import CircuitBreaker, CircuitBreakerOpenError, CircuitState; print('ok')"` succeeds after `pip install -e .`.
- BDD coverage: SPEC_09 scenario "circuit breaker state changes to OPEN / subsequent requests rejected / CircuitBreakerOpenError is raised" (lines 698–700) maps to TDD steps 4, 8.

## Rollback

Delete the two files; the package had no prior `resilience/` namespace and no
caller imports it yet (slice C has not landed):

```
rm src/yaml_agno/resilience/__init__.py
rm src/yaml_agno/resilience/circuit_breaker.py
rmdir src/yaml_agno/resilience
rm -rf tests/unit/resilience
```

No migration, no feature flag, no downstream consumer to coordinate. Fully
reversible in one commit.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary. Pure in-process state machine.

## Open Questions

- None for slice A. The `should_retry` vs `is_retryable` divergence
  (exploration risk a) is a slice C concern and does not affect this
  self-contained breaker.
