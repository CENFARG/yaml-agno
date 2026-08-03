"""RetryPolicy: classification-driven exponential backoff with jitter (SPEC_05 §4.3).

A pure, dependency-free retry policy that delegates error classification
to `core_infrastructure.errors.ErrorHandlingManager.classify()`.
Owns retry math ONLY — never wraps CircuitBreaker, never reimplements
Agno's model-level or HITL retry.

Design: Slice B (pure RetryPolicy). CB-awareness is composed in Slice C.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from typing import Any

from core_infrastructure.errors import ErrorClassification, ErrorHandlingManager

__all__ = ["RetryPolicy"]


class RetryPolicy:
    """Classification-driven retry with exponential backoff and jitter.

    Delegates error classification to ``ErrorHandlingManager.classify()``,
    retries on ``TRANSIENT`` / ``RATE_LIMIT``, and fails fast on
    ``PERMANENT`` / ``VALIDATION`` / ``AUTH``.

    All timing and randomness are injectable through constructor-only
    arguments (``sleep_fn``, ``random_fn``), mirroring ``CircuitBreaker``'s
    ``time_fn`` pattern for deterministic unit testing.

    Args:
        max_retries: Maximum number of retry attempts after the initial
            failure (default 3; 0 = single attempt, no retry).
        base_delay: Initial backoff delay in seconds (default 2.0).
        max_delay: Ceiling for backoff in seconds (default 60.0).
        jitter: When True, apply ±50 % jitter to each calculated delay
            (default True).
        sleep_fn: Async callable that sleeps for a duration in seconds.
            Override in tests with a no-op for zero-delay execution.
        random_fn: Callable `(lo, hi) -> float` returning a random float
            in [lo, hi]. Override in tests for deterministic jitter.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        *,
        sleep_fn: Callable[[float], Any] = asyncio.sleep,
        random_fn: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.sleep_fn = sleep_fn
        self.random_fn = random_fn

    def is_retryable(
        self,
        error: Exception,
        error_manager: ErrorHandlingManager,
    ) -> bool:
        """Return True if the error should trigger a retry.

        Delegates to ``error_manager.classify()``. Only ``TRANSIENT`` and
        ``RATE_LIMIT`` are considered retryable.
        """
        classification = error_manager.classify(error)
        return classification in (
            ErrorClassification.TRANSIENT,
            ErrorClassification.RATE_LIMIT,
        )

    def calculate_delay(self, attempt: int) -> float:
        """Compute the backoff delay for a given retry attempt (0-indexed).

        Formula: ``min(base_delay * 2^attempt, max_delay)``.
        When ``jitter`` is True, the result is multiplied by a random
        factor in ``[0.5, 1.5]`` ( ±50 %).

        Args:
            attempt: Zero-based attempt number (0 = first retry).

        Returns:
            Delay in seconds.
        """
        delay: float = min(self.base_delay * (2**attempt), self.max_delay)
        if self.jitter:
            delay = delay * self.random_fn(0.5, 1.5)
        return delay

    async def execute_with_retry(
        self,
        func: Callable[..., Any],
        error_manager: ErrorHandlingManager,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute an async callable with classification-driven retry.

        Args:
            func: Async callable to execute.
            error_manager: ErrorHandlingManager for classification and
                reporting. ``classify()`` determines retry eligibility;
                ``report()`` is called synchronously on each transient
                failure.
            *args: Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            The result of ``func``.

        Raises:
            The original exception if unretryable or max_retries exhausted.
        """
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                if not self.is_retryable(exc, error_manager):
                    raise

                if attempt == self.max_retries:
                    raise

                error_manager.report(exc, context={"attempt": attempt})
                delay = self.calculate_delay(attempt)
                await self.sleep_fn(delay)
