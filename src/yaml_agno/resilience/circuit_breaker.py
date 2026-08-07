"""Circuit breaker state machine (SPEC_09 §4.1).

A pure, dependency-free rate-based circuit breaker. Tracks success/failure
counts and transitions between CLOSED, OPEN, and HALF_OPEN. Does NOT
classify errors — the caller decides what counts as a failure
(SPEC_09 §4 @ai-directive: classification belongs to core-cenf
``ErrorHandlingManager.classify``).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum
from typing import Any

__all__ = ["CircuitBreaker", "CircuitBreakerOpenError", "CircuitState"]


class CircuitBreakerOpenError(Exception):
    """Raised when ``CircuitBreaker.execute`` rejects a request.

    The circuit is OPEN and no HALF_OPEN probe is available.
    """


class CircuitState(str, Enum):  # noqa: UP042 -- SPEC_09 §4.1 literal: (str, Enum), not StrEnum
    """Lifecycle states of the circuit breaker (SPEC_09 §4.1).

    CLOSED allows normal passthrough; OPEN rejects requests immediately;
    HALF_OPEN admits a bounded probe window to test recovery.
    """

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
        time_fn: Callable returning the current monotonic time, in seconds.
            Defaults to :func:`time.time`; inject a deterministic clock for
            testing.
    """

    def __init__(
        self,
        failure_threshold: float = 50.0,  # % of failures to open
        recovery_timeout: float = 30.0,  # Seconds before HALF_OPEN
        min_requests: int = 10,  # Minimum requests to evaluate
        half_open_max_calls: int = 3,  # Max calls in HALF_OPEN
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.min_requests = min_requests
        self.half_open_max_calls = half_open_max_calls
        self.time_fn = time_fn

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.total_requests = 0
        self.last_failure_time = 0.0
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
        self.last_failure_time = self.time_fn()

        if self.state == CircuitState.HALF_OPEN or self._should_trip():
            self.state = CircuitState.OPEN

    def _should_trip(self) -> bool:
        """Return True if the failure rate warrants opening the circuit.

        Returns False until ``min_requests`` have been observed. Guards
        against division by zero (the ``min_requests`` floor of at least 1
        plus the ``total_requests`` check makes the denominator positive on
        every reachable evaluation).
        """
        if self.total_requests < self.min_requests:
            return False

        if self.total_requests == 0:
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
            if self.time_fn() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls

        return False  # type: ignore[unreachable] # exhaustive enum guard, defensive only

    async def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
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
        except Exception:
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
