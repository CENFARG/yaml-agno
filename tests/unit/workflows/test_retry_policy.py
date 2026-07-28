"""RED tests for RetryPolicy (SPEC_05 Slice B).

Strict TDD — these tests are written BEFORE the implementation exists.
They cover all 3 in-scope requirements (error classification delegation,
exponential backoff with jitter, synchronous error reporting) and their
5 active scenarios from ``specs/workflows-runtime-spec.md``.

Tagged ``@pytest.mark.unit``. Deterministic: a ``sleep_fn`` and
``random_fn`` callable injected through the constructor allow zero-delay
and deterministic jitter for testing (no global monkeypatching).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from core_infrastructure.errors import ErrorClassification

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_error_manager(classify_returns: ErrorClassification) -> MagicMock:
    """Return a mock ErrorHandlingManager whose classify() always
    returns the given classification. ``report()`` is a plain
    MagicMock (not a coroutine — it must be sync).
    """
    em = MagicMock()
    em.classify.return_value = classify_returns
    return em


async def _fail_twice_then_succeed() -> str:
    """Coroutine that raises TimeoutError twice, then returns 'ok'."""
    _fail_twice_then_succeed.calls = getattr(_fail_twice_then_succeed, "calls", 0) + 1  # type: ignore[attr-defined]
    if _fail_twice_then_succeed.calls < 3:  # type: ignore[attr-defined]
        raise TimeoutError("transient timeout")
    return "ok"


async def _always_fail() -> str:
    """Coroutine that always raises ValueError."""
    raise ValueError("permanent failure")


# ---------------------------------------------------------------------------
# Task 1.1 — TRANSIENT retries then succeeds
# ---------------------------------------------------------------------------


def test_transient_retries_three_attempts() -> None:
    """TRANSIENT twice then success; assert 3 total invocations (REQ-001).

    Scenario: TRANSIENT retries to success after 3 attempts.
    """
    call_count = 0

    async def flaky_work() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("transient")
        return "success"

    error_manager = _make_error_manager(ErrorClassification.TRANSIENT)
    # Import here to confirm the module will exist after GREEN.
    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=3, base_delay=0.0)
    result = asyncio.run(rp.execute_with_retry(flaky_work, error_manager))

    assert result == "success"
    assert call_count == 3


# ---------------------------------------------------------------------------
# Task 1.2 — PERMANENT fails fast, no sleep
# ---------------------------------------------------------------------------


def test_permanent_fails_fast_no_sleep() -> None:
    """PERMANENT: exactly 1 attempt, sleep_fn never called (REQ-001).

    Scenario: PERMANENT fails fast with no retry.
    """
    call_count = 0
    sleep_calls = []

    async def _sleep(delay: float) -> None:
        sleep_calls.append(delay)

    async def work() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("permanent failure")

    error_manager = _make_error_manager(ErrorClassification.PERMANENT)

    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=3, base_delay=0.0, sleep_fn=_sleep)

    with pytest.raises(ValueError, match="permanent failure"):
        asyncio.run(rp.execute_with_retry(work, error_manager))

    assert call_count == 1
    assert sleep_calls == []


# ---------------------------------------------------------------------------
# Task 1.3 — max_retries=0 yields single attempt
# ---------------------------------------------------------------------------


def test_max_retries_zero_yields_single_attempt() -> None:
    """max_retries=0: exactly 1 attempt and error re-raised (REQ-001).

    Scenario: max_retries=0 yields single attempt.
    """
    call_count = 0

    async def work() -> str:
        nonlocal call_count
        call_count += 1
        raise TimeoutError("transient")

    error_manager = _make_error_manager(ErrorClassification.TRANSIENT)

    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=0, base_delay=0.0)

    with pytest.raises(TimeoutError, match="transient"):
        asyncio.run(rp.execute_with_retry(work, error_manager))

    assert call_count == 1


# ---------------------------------------------------------------------------
# Task 1.4 — calculate_delay ceiling (no jitter)
# ---------------------------------------------------------------------------


def test_calculate_delay_ceiling() -> None:
    """jitter=False, base=2.0, max=60.0 → [2.0, 4.0, 8.0] (REQ-002).

    Scenario: configurable params produce expected backoff ceiling.
    """
    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=3, base_delay=2.0, max_delay=60.0, jitter=False)

    assert rp.calculate_delay(0) == 2.0
    assert rp.calculate_delay(1) == 4.0
    assert rp.calculate_delay(2) == 8.0


def test_calculate_delay_respects_max_delay() -> None:
    """Attempt 6 yields 2*2^6=128 but max_delay=60.0 caps it (REQ-002)."""
    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=10, base_delay=2.0, max_delay=60.0, jitter=False)

    assert rp.calculate_delay(6) == 60.0


# ---------------------------------------------------------------------------
# Task 1.5 — jitter within ±50%
# ---------------------------------------------------------------------------


def test_jitter_within_50_percent() -> None:
    """100 calls with controlled random_fn; all delays within [1.0, 3.0] (REQ-002).

    Scenario: jitter bounds within ±50%.
    """
    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(
        max_retries=3,
        base_delay=2.0,
        jitter=True,
        random_fn=lambda lo, hi: (lo + hi) / 2.0,  # always midpoint
    )

    for _ in range(100):
        delay = rp.calculate_delay(0)
        assert 1.0 <= delay <= 3.0, f"delay {delay} out of [1.0, 3.0]"


# ---------------------------------------------------------------------------
# Task 1.6 — report() called synchronously, not awaited
# ---------------------------------------------------------------------------


def test_report_called_sync_not_awaited() -> None:
    """report() called with attempt in context dict; NOT a coroutine (REQ-003).

    Scenario: report called synchronously on each failure.
    """
    call_count = 0

    async def work() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError(f"transient-{call_count}")
        return "ok"

    error_manager = MagicMock()
    error_manager.classify.return_value = ErrorClassification.TRANSIENT
    # report is a plain MagicMock — NOT a coroutine

    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=3, base_delay=0.0)

    result = asyncio.run(rp.execute_with_retry(work, error_manager))

    assert result == "ok"
    assert call_count == 3
    # report() must have been called twice (on failure 1 and 2, not on success)
    assert error_manager.report.call_count == 2

    # Verify the first call has "attempt" in the context dict
    first_call_args = error_manager.report.call_args_list[0]
    context = first_call_args[1].get("context")  # keyword arg
    assert context is not None
    assert "attempt" in context


# ---------------------------------------------------------------------------
# Additional — RATE_LIMIT is also retryable
# ---------------------------------------------------------------------------


def test_rate_limit_is_retryable() -> None:
    """classify returns RATE_LIMIT → is_retryable returns True (REQ-001)."""
    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=3, base_delay=0.0)
    error_manager = _make_error_manager(ErrorClassification.RATE_LIMIT)

    assert rp.is_retryable(ValueError("rate limited"), error_manager) is True


def test_validation_is_not_retryable() -> None:
    """classify returns VALIDATION → is_retryable returns False (REQ-001)."""
    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=3, base_delay=0.0)
    error_manager = _make_error_manager(ErrorClassification.VALIDATION)

    assert rp.is_retryable(ValueError("validation failure"), error_manager) is False


def test_auth_is_not_retryable() -> None:
    """classify returns AUTH → is_retryable returns False (REQ-001)."""
    from yaml_agno.workflows.retry_policy import RetryPolicy

    rp = RetryPolicy(max_retries=3, base_delay=0.0)
    error_manager = _make_error_manager(ErrorClassification.AUTH)

    assert rp.is_retryable(ValueError("auth failure"), error_manager) is False
