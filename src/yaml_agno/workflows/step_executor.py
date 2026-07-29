"""StepExecutor: composes CircuitBreaker + RetryPolicy (SPEC_05 Slice C).

A thin executor that wraps an opaque async callable and composes resilience
primitives around it. NEVER imports Agno ``Step`` / ``StepInput`` /
``RunContext`` — the callable contract is the only coupling point.

Design: CB short-circuits first inside RetryPolicy's retry loop.
Parallel execution uses ``asyncio.TaskGroup`` (never ``asyncio.gather``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from core_infrastructure.errors import ErrorHandlingManager

from yaml_agno.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from yaml_agno.workflows.retry_policy import RetryPolicy

__all__ = ["StepExecutor"]


class StepExecutor:
    """Compose CircuitBreaker and RetryPolicy around step execution.

    Wraps an opaque ``Callable[[], Awaitable[Any]]`` — the concrete binding
    to Agno's ``step.aexecute`` lives outside this class (follow-up slice).

    Composition order (when both CB and RetryPolicy are present)::

        RetryPolicy.execute_with_retry(lambda: cb.execute(work))

    - CB short-circuits first: if OPEN, raises ``CircuitBreakerOpenError``
      (classified PERMANENT → fail-fast).
    - Each retry attempt re-enters the CB, so the CB counts every attempt.

    Parallel execution delegates to ``asyncio.TaskGroup`` for structured
    concurrency.

    Args:
        error_manager: ``ErrorHandlingManager`` for error classification
            and reporting. Required.
        circuit_breaker: Optional ``CircuitBreaker``. If provided, each
            step execution is gated through the CB.
        retry_policy: Optional ``RetryPolicy``. If provided, transient
            failures are retried with backoff. When combined with
            ``circuit_breaker``, the CB is called on every attempt.
    """

    def __init__(
        self,
        error_manager: ErrorHandlingManager,
        circuit_breaker: CircuitBreaker | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.error_manager = error_manager
        self.circuit_breaker = circuit_breaker
        self.retry_policy = retry_policy

    async def execute_step(
        self,
        work: Callable[[], Any],
    ) -> Any:
        """Execute a single async work callable through the resilience stack.

        Resilience composition (ordered by priority):

        1. *Both* CB and RetryPolicy: CB inside the retry loop.
        2. *CB only*: gated through the CB with no retry.
        3. *RetryPolicy only*: classification-driven retry with no CB gate.
        4. *Neither*: bare ``await work()``.

        Args:
            work: An async callable returning any value.

        Returns:
            The result of ``work()``.

        Raises:
            CircuitBreakerOpenError: If the CB is OPEN (only when
                ``circuit_breaker`` is provided).
            Exception: Any exception raised by ``work``, possibly after
                retry exhaustion.
        """
        if self.circuit_breaker is not None and self.retry_policy is not None:
            # Full composition: CB inside the retry loop.
            # Each retry re-enters the CB, so the CB counts every attempt.
            # Local bind to help mypy narrow the type through the lambda capture.
            cb = self.circuit_breaker
            try:
                return await self.retry_policy.execute_with_retry(
                    lambda: cb.execute(work),
                    self.error_manager,
                )
            except CircuitBreakerOpenError as exc:
                # Structural CB-open state is classified PERMANENT by the
                # retry policy → fail-fast. Report for observability before
                # re-raising so the error manager records the open circuit.
                self.error_manager.report(
                    exc, context={"circuit_breaker": "open"}
                )
                raise

        if self.circuit_breaker is not None:
            try:
                return await self.circuit_breaker.execute(work)
            except CircuitBreakerOpenError as exc:
                # Structural CB-open state → fail-fast. Report for
                # observability before re-raising so the error manager
                # records the open circuit (parity with the combined
                # CB+RetryPolicy path, JD-02).
                self.error_manager.report(
                    exc, context={"circuit_breaker": "open"}
                )
                raise

        if self.retry_policy is not None:
            return await self.retry_policy.execute_with_retry(
                work,
                self.error_manager,
            )

        return await work()

    async def execute_parallel_step(
        self,
        *works: Callable[[], Any],
    ) -> list[Any]:
        """Execute multiple async callables concurrently via TaskGroup.

        Uses ``asyncio.TaskGroup`` for structured concurrency (Python 3.12+).
        Every callable is submitted as a task; results are collected in
        completion order. If any task raises, the TaskGroup cancels all
        siblings and propagates the exception as an ``ExceptionGroup``.

        Args:
            *works: Variadic async callables to execute concurrently.

        Returns:
            List of results in completion order (not callable argument
            order).

        Raises:
            ExceptionGroup: If any task raises. All sibling tasks are
                cancelled.
        """
        results: list[Any] = []

        async def _run_and_collect(w: Callable[[], Any]) -> None:
            result = await w()
            results.append(result)

        async with asyncio.TaskGroup() as tg:
            for w in works:
                tg.create_task(_run_and_collect(w))

        return results
