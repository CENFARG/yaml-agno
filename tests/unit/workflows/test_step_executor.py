"""RED tests for StepExecutor (SPEC_05 Slice C).

Strict TDD — these tests are written BEFORE the implementation exists.
They cover the step-executor capability: CB-then-RetryPolicy composition
and parallel execution via asyncio.TaskGroup.

Tagged ``@pytest.mark.unit``. Deterministic: a ``time_fn`` callable
injected into ``CircuitBreaker`` replaces real-time for deterministic CB
state transitions (mirrors ``test_circuit_breaker.py`` pattern).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from core_infrastructure.errors import ErrorClassification

from yaml_agno.resilience import CircuitBreaker, CircuitBreakerOpenError, CircuitState

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_error_manager(classify_returns: ErrorClassification) -> MagicMock:
    """Return a mock ErrorHandlingManager whose classify() always
    returns the given classification.
    """
    em = MagicMock()
    em.classify.return_value = classify_returns
    return em


# ---------------------------------------------------------------------------
# Task 2.1 — CB closed, step succeeds
# ---------------------------------------------------------------------------


def test_cb_closed_succeeds() -> None:
    """CB CLOSED + fake work returns value; cb.success_count == 1.

    Scenario: CB closed, step succeeds (REQ: CB-then-RetryPolicy composition).
    """
    cb = CircuitBreaker()

    async def work() -> str:
        return "step-done"

    from yaml_agno.workflows.step_executor import StepExecutor

    executor = StepExecutor(
        error_manager=_make_error_manager(ErrorClassification.TRANSIENT),
        circuit_breaker=cb,
    )

    result: str = asyncio.run(executor.execute_step(work))

    assert result == "step-done"
    assert cb.success_count == 1
    assert cb.total_requests == 1


# ---------------------------------------------------------------------------
# Task 2.2 — CB open rejects immediately, no work invoked
# ---------------------------------------------------------------------------


def test_cb_open_rejects_immediately_no_work_invoked() -> None:
    """Forced OPEN; assert CircuitBreakerOpenError + work counter == 0.

    Scenario: CB open rejects immediately (REQ: CB-then-RetryPolicy composition).
    """
    clock: dict[str, float] = {"now": 1000.0}
    cb = CircuitBreaker(recovery_timeout=60.0, time_fn=lambda: clock["now"])
    # Force OPEN state.
    cb.state = CircuitState.OPEN
    cb.last_failure_time = 1000.0

    call_count = 0

    async def work() -> str:
        nonlocal call_count
        call_count += 1
        return "should-not-run"

    from yaml_agno.workflows.step_executor import StepExecutor

    executor = StepExecutor(
        error_manager=_make_error_manager(ErrorClassification.TRANSIENT),
        circuit_breaker=cb,
    )

    with pytest.raises(CircuitBreakerOpenError):
        asyncio.run(executor.execute_step(work))

    assert call_count == 0
    assert cb.total_requests == 0


# ---------------------------------------------------------------------------
# Task 2.2b — CB OPEN + RetryPolicy combined: fail-fast, no retry
# ---------------------------------------------------------------------------


def test_cb_open_with_retry_policy_fails_fast() -> None:
    """CB OPEN + RetryPolicy active: CircuitBreakerOpenError is PERMANENT.

    When both CircuitBreaker and RetryPolicy are composed and the CB is
    OPEN, the ``CircuitBreakerOpenError`` is classified PERMANENT so the
    retry policy fails immediately — work is never invoked, the error is
    reported exactly once for observability, and exactly one attempt is
    made (no retries).

    This verifies the CONTRACT that ``error_manager.classify`` determines
    retry eligibility: a structural CB-open state must not be treated as a
    transient failure.

    Scenario: CB-OPEN + RetryPolicy combined path
    (REQ: CB-then-RetryPolicy composition, fail-fast on structural CB-open).
    """
    clock: dict[str, float] = {"now": 1000.0}
    cb = CircuitBreaker(recovery_timeout=60.0, time_fn=lambda: clock["now"])
    # Force OPEN state.
    cb.state = CircuitState.OPEN
    cb.last_failure_time = 1000.0

    call_count = 0

    async def work() -> str:
        nonlocal call_count
        call_count += 1
        return "should-not-run"

    from yaml_agno.workflows.retry_policy import RetryPolicy
    from yaml_agno.workflows.step_executor import StepExecutor

    rp = RetryPolicy(max_retries=3, base_delay=0.0)
    error_manager = _make_error_manager(ErrorClassification.PERMANENT)

    executor = StepExecutor(
        error_manager=error_manager,
        circuit_breaker=cb,
        retry_policy=rp,
    )

    with pytest.raises(CircuitBreakerOpenError):
        asyncio.run(executor.execute_step(work))

    # Work was never invoked (CB rejected before calling work).
    assert call_count == 0
    # Exactly one classification call → one attempt, zero retries.
    assert error_manager.classify.call_count == 1
    # CB-open error was reported exactly once for observability.
    error_manager.report.assert_called_once()
    reported_exc = error_manager.report.call_args[0][0]
    assert isinstance(reported_exc, CircuitBreakerOpenError)


# ---------------------------------------------------------------------------
# Task 2.3 — TRANSIENT retries through CB re-entry
# ---------------------------------------------------------------------------


def test_transient_retries_through_cb_reentry() -> None:
    """2 TRANSIENT fails then success; assert cb.execute called 3 times.

    Each retry attempt re-enters the CB (cb.total_requests == 3). The final
    attempt succeeds, so cb.success_count == 1 and cb.failure_count == 2.

    Scenario: TRANSIENT retries through CB (REQ: CB-then-RetryPolicy composition).
    """
    cb = CircuitBreaker()

    call_count = 0

    async def flaky_work() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError(f"transient-{call_count}")
        return "recovered"

    # RetryPolicy with no backoff delay (unit-test friendly injectables).
    from yaml_agno.workflows.retry_policy import RetryPolicy
    from yaml_agno.workflows.step_executor import StepExecutor

    rp = RetryPolicy(max_retries=3, base_delay=0.0)
    error_manager = _make_error_manager(ErrorClassification.TRANSIENT)

    executor = StepExecutor(
        error_manager=error_manager,
        circuit_breaker=cb,
        retry_policy=rp,
    )

    result: str = asyncio.run(executor.execute_step(flaky_work))

    assert result == "recovered"
    assert call_count == 3
    # Each attempt passed through the circuit breaker.
    assert cb.total_requests == 3
    assert cb.success_count == 1
    assert cb.failure_count == 2


# ---------------------------------------------------------------------------
# Task 2.4 — parallel steps via TaskGroup
# ---------------------------------------------------------------------------


def test_parallel_steps_via_taskgroup() -> None:
    """3 concurrent async works; collect all results.

    Scenario: parallel steps execute concurrently (REQ: parallel execution).
    """

    async def work_a() -> str:
        await asyncio.sleep(0)
        return "a"

    async def work_b() -> str:
        await asyncio.sleep(0)
        return "b"

    async def work_c() -> str:
        await asyncio.sleep(0)
        return "c"

    from yaml_agno.workflows.step_executor import StepExecutor

    executor = StepExecutor(
        error_manager=_make_error_manager(ErrorClassification.TRANSIENT),
    )

    results: list[str] = asyncio.run(
        executor.execute_parallel_step(work_a, work_b, work_c)
    )

    assert sorted(results) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Task 2.5 — one parallel failure cancels siblings
# ---------------------------------------------------------------------------


def test_parallel_one_failure_cancels_siblings() -> None:
    """One raises; TaskGroup propagates; assert sibling cancellation.

    Scenario: one parallel failure surfaces (REQ: parallel execution).
    """
    started: list[str] = []

    async def success_work(name: str) -> str:
        started.append(name)
        await asyncio.sleep(0.2)  # long enough for the failing task to explode
        return name

    async def failing_work() -> str:
        started.append("failing")
        await asyncio.sleep(0)
        raise ValueError("boom-parallel")

    from yaml_agno.workflows.step_executor import StepExecutor

    executor = StepExecutor(
        error_manager=_make_error_manager(ErrorClassification.TRANSIENT),
    )

    with pytest.raises(ExceptionGroup) as exc_info:  # type: ignore[attr-defined]
        asyncio.run(
            executor.execute_parallel_step(
                lambda: success_work("x"),  # type: ignore[arg-type]
                failing_work,
                lambda: success_work("y"),  # type: ignore[arg-type]
            )
        )

    # TaskGroup wraps the first failure in an ExceptionGroup.
    # At least one ValueError should be inside.
    errors = exc_info.value.exceptions  # type: ignore[attr-defined]
    assert any(isinstance(e, ValueError) for e in errors)
    # The failing task did start.
    assert "failing" in started
