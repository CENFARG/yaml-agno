"""RED tests for CircuitBreaker state machine (SPEC_09 slice A).

Strict TDD — these tests are written BEFORE the implementation exists.
They cover all 10 in-scope requirements (REQ-001..010) and the 10 active
scenarios from ``specs/circuit-breaker-foundation/spec.md``.

Tagged ``@pytest.mark.unit``. Deterministic: a ``time_fn`` callable injected
through the constructor drives the clock (no global monkeypatching).
"""

from __future__ import annotations

import asyncio

import pytest

from yaml_agno.resilience import CircuitBreaker, CircuitBreakerOpenError, CircuitState

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# REQ-001 — CircuitState enum members
# REQ-009 — CircuitBreakerOpenError is an Exception
# ---------------------------------------------------------------------------


def test_circuit_state_enum_members() -> None:
    """CircuitState has exactly CLOSED/OPEN/HALF_OPEN with string values."""
    assert CircuitState.CLOSED.value == "closed"
    assert CircuitState.OPEN.value == "open"
    assert CircuitState.HALF_OPEN.value == "half_open"
    assert {m.value for m in CircuitState} == {"closed", "open", "half_open"}


def test_circuit_breaker_open_error_is_exception() -> None:
    """CircuitBreakerOpenError MUST subclass the built-in Exception."""
    assert issubclass(CircuitBreakerOpenError, Exception)


# ---------------------------------------------------------------------------
# REQ-002 — constructor defaults and zeroed counters
# ---------------------------------------------------------------------------


def test_defaults_match_spec_09() -> None:
    """Constructor defaults are 50.0 / 30.0 / 10 / 3; counters start at zero."""
    cb = CircuitBreaker()
    assert cb.failure_threshold == 50.0
    assert cb.recovery_timeout == 30.0
    assert cb.min_requests == 10
    assert cb.half_open_max_calls == 3

    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0
    assert cb.success_count == 0
    assert cb.total_requests == 0
    assert cb.half_open_calls == 0
    assert cb.last_failure_time == 0


def test_constructor_accepts_overrides() -> None:
    """Constructor MUST accept overrides for every threshold."""
    cb = CircuitBreaker(
        failure_threshold=10.0,
        recovery_timeout=5.0,
        min_requests=3,
        half_open_max_calls=1,
    )
    assert cb.failure_threshold == 10.0
    assert cb.recovery_timeout == 5.0
    assert cb.min_requests == 3
    assert cb.half_open_max_calls == 1


# ---------------------------------------------------------------------------
# REQ-003.1 — record_success increments counters in CLOSED
# ---------------------------------------------------------------------------


def test_record_success_increments_counters_closed() -> None:
    """CLOSED golden path: allow_request True, record_success increments."""
    cb = CircuitBreaker()
    assert cb.allow_request() is True

    for _ in range(3):
        cb.record_success()

    assert cb.success_count == 3
    assert cb.total_requests == 3
    assert cb.state is CircuitState.CLOSED


# ---------------------------------------------------------------------------
# REQ-005 — _should_trip rate-based with min_requests gate
# ---------------------------------------------------------------------------


def test_min_requests_gate_prevents_trip() -> None:
    """5 failures of 5 requests stays CLOSED (below min_requests=10 floor)."""
    cb = CircuitBreaker(failure_threshold=50.0, min_requests=10)

    for _ in range(5):
        cb.record_failure()

    assert cb.total_requests == 5
    assert cb._should_trip() is False
    assert cb.state is CircuitState.CLOSED


def test_failure_rate_trips_at_threshold() -> None:
    """Crossing the failure-rate threshold on a CLOSED breaker trips to OPEN.

    record_failure is the only path that calls _should_trip. After 4 successes
    and 5 failures (total=9, below the floor) the gate still holds; the 10th
    request — a failure — pushes total to 10 with 6 failures (60% >= 50%) and
    trips the circuit.
    """
    cb = CircuitBreaker(failure_threshold=50.0, min_requests=10)

    for _ in range(4):
        cb.record_success()
    for _ in range(5):
        cb.record_failure()

    assert cb.total_requests == 9
    assert cb.failure_count == 5
    assert cb.state is CircuitState.CLOSED  # below min_requests floor

    cb.record_failure()  # total=10, failures=6 -> 60% >= 50%

    assert cb.total_requests == 10
    assert cb.failure_count == 6
    assert cb._should_trip() is True
    assert cb.state is CircuitState.OPEN


# ---------------------------------------------------------------------------
# REQ-006 — allow_request state transitions
# ---------------------------------------------------------------------------


def test_open_blocks_until_recovery_timeout() -> None:
    """OPEN rejects until recovery_timeout elapses, then flips to HALF_OPEN."""
    clock = {"now": 1000.0}
    cb = CircuitBreaker(
        failure_threshold=50.0,
        recovery_timeout=30.0,
        min_requests=3,
        time_fn=lambda: clock["now"],
    )
    # Force OPEN.
    for _ in range(3):
        cb.record_failure()
    assert cb.state is CircuitState.OPEN
    assert cb.last_failure_time == 1000.0

    # Before timeout: still OPEN, rejected.
    clock["now"] = 1010.0
    assert cb.allow_request() is False
    assert cb.state is CircuitState.OPEN

    # After timeout: transition to HALF_OPEN, admit the probe, reset counter.
    clock["now"] = 1030.0
    assert cb.allow_request() is True
    assert cb.state is CircuitState.HALF_OPEN
    assert cb.half_open_calls == 0


# ---------------------------------------------------------------------------
# REQ-003.2 — HALF_OPEN closes on successive successes
# ---------------------------------------------------------------------------


def test_half_open_success_closes_circuit() -> None:
    """3 successive HALF_OPEN successes -> CLOSED, counters reset."""
    cb = CircuitBreaker(half_open_max_calls=3)
    cb.state = CircuitState.HALF_OPEN

    cb.record_success()
    cb.record_success()
    assert cb.state is CircuitState.HALF_OPEN  # not yet at cap

    cb.record_success()
    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0
    assert cb.success_count == 0
    assert cb.half_open_calls == 0


# ---------------------------------------------------------------------------
# REQ-004.2 — HALF_OPEN reopens on any failure
# ---------------------------------------------------------------------------


def test_half_open_failure_reopens() -> None:
    """A single HALF_OPEN failure -> OPEN."""
    cb = CircuitBreaker()
    cb.state = CircuitState.HALF_OPEN

    cb.record_failure()

    assert cb.state is CircuitState.OPEN
    assert cb.last_failure_time > 0


# ---------------------------------------------------------------------------
# REQ-007 — async execute wrapper
# ---------------------------------------------------------------------------


async def _ok() -> str:
    return "ok"


async def _boom() -> None:
    raise ValueError("boom")


def test_execute_records_success_and_returns_result() -> None:
    """execute() awaits func, records success, returns the result."""
    cb = CircuitBreaker()

    result = asyncio.run(cb.execute(_ok))

    assert result == "ok"
    assert cb.success_count == 1
    assert cb.total_requests == 1


def test_execute_raises_when_open() -> None:
    """execute() rejects with CircuitBreakerOpenError and never calls func."""
    clock = {"now": 100.0}
    cb = CircuitBreaker(
        recovery_timeout=1000.0,
        time_fn=lambda: clock["now"],
    )
    # Force OPEN with last_failure_time pinned to "now".
    cb.state = CircuitState.OPEN
    cb.last_failure_time = 100.0
    # Elapsed is 0 << 1000 -> allow_request returns False, stays OPEN.

    calls = {"n": 0}

    async def _spy() -> str:
        calls["n"] += 1
        return "should-not-run"

    with pytest.raises(CircuitBreakerOpenError):
        asyncio.run(cb.execute(_spy))

    assert calls["n"] == 0
    assert cb.total_requests == 0
    assert cb.state is CircuitState.OPEN


def test_execute_records_failure_and_reraises() -> None:
    """execute() records failure and propagates the original exception."""
    cb = CircuitBreaker()

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(cb.execute(_boom))

    assert cb.failure_count == 1
    assert cb.total_requests == 1


# ---------------------------------------------------------------------------
# REQ-008 — get_state_metrics shape + zero-division guard
# ---------------------------------------------------------------------------


def test_get_state_metrics_shape_and_zero_div_guard() -> None:
    """Metrics dict has all documented keys; failure_rate is 0.0 at zero reqs."""
    cb = CircuitBreaker()

    metrics = cb.get_state_metrics()

    assert set(metrics.keys()) == {
        "state",
        "failure_rate",
        "total_requests",
        "success_count",
        "failure_count",
        "last_failure_time",
    }
    assert metrics["state"] == "closed"
    assert metrics["failure_rate"] == 0.0
    assert metrics["total_requests"] == 0
    assert metrics["success_count"] == 0
    assert metrics["failure_count"] == 0
    assert metrics["last_failure_time"] == 0
