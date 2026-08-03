"""ResyncManager — debounced hot-reload of AgentOS (SPEC_12 Slice 3).

Watches YAML config path for changes, debounces multiple events, and
triggers ``ConfigManager.reload()`` → ``AgentOS.resync()`` guarded by
a rate-based ``CircuitBreaker`` from SPEC_09.

Design (sdd/control-plane-s3/design):
    - Constructor-injected ``ConfigManager`` and ``ObservabilityManager``.
    - ``CircuitBreaker`` instantiated from ``ResyncSettings`` (not injected —
      all parameters come from config).
    - ``attach()`` pattern decouples construction from AgentOS wiring
      (AgentOS does not exist at ``__init__`` time).
    - ``anyio.Path.watch()`` for filesystem events (already in dep tree).
    - Debounce via cancel-and-restart ``asyncio.Task``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yaml_agno.agentos.errors import ResyncBlockedError
from yaml_agno.resilience.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from yaml_agno.models.config.agentos_config import ResyncSettings

__all__ = ["ResyncBlockedError", "ResyncManager"]


class ResyncManager:
    """Debounced hot-reload manager for AgentOS configuration.

    Watches the YAML config file directory for changes. On each change,
    debounces multiple events into a single ``ConfigManager.reload()``
    followed by ``AgentOS.resync()``, guarded by a rate-based
    ``CircuitBreaker``.

    Args:
        config_path: Path to the watched AgentOS YAML config file.
        settings: ``ResyncSettings`` with thresholds, debounce, etc.
        obs: ``ObservabilityManager`` from core-cenf.
        config: ``ConfigManager`` from core-cenf (injected).
    """

    def __init__(
        self,
        config_path: Path,
        settings: ResyncSettings,
        obs: Any,
        config: Any,
    ) -> None:
        self._cfg = config_path
        self._settings = settings
        self._obs = obs
        self._config = config
        self._os: Any = None  # Set via attach()

        self._breaker = CircuitBreaker(
            failure_threshold=settings.failure_threshold,
            recovery_timeout=float(settings.recovery_timeout),
            min_requests=settings.min_requests,
        )
        self._sem = asyncio.Semaphore(settings.max_concurrent)
        self._debounce_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def attach(self, agentos: Any) -> None:
        """Set the AgentOS reference post-construction.

        The AgentOS instance does not exist at ``__init__`` time — it is
        created during ``AgentOSFactory.build()``. Call this AFTER
        ``AgentOS(**kwargs)`` to wire the target.

        Args:
            agentos: The constructed ``agno.os.AgentOS`` instance.
        """
        self._os = agentos

    async def watch(self) -> None:
        """Watch the config file directory for changes (debounced).

        Returns immediately if ``watch=False`` or ``enabled=False``.
        Uses ``anyio.Path.watch()`` to observe the parent directory
        of ``config_path``. Each modification event resets the debounce
        timer; after ``debounce_ms`` milliseconds of inactivity,
        ``resync_now()`` is called.
        """
        if not self._settings.watch or not self._settings.enabled:
            return

        try:
            import anyio

            watch_path = anyio.Path(self._cfg).parent
            async with watch_path.watch() as events:
                async for _event in events:
                    self._start_debounce_timer()
        except ImportError:
            self._obs.error("resync.watch.missing_anyio", error="anyio not installed")

    async def resync_now(self) -> None:
        """Execute a single config-reload-and-resync cycle.

        Guarded by:
        - Semaphore (concurrency control).
        - ``CircuitBreaker.allow_request()`` (raises ``ResyncBlockedError``
          when OPEN).
        - ConfigManager.reload() → AgentOS.resync().

        Raises:
            ResyncBlockedError: Circuit breaker is OPEN.
            RuntimeError: ``attach()`` was not called before ``resync_now()``.
        """
        if self._os is None:
            raise RuntimeError(
                "ResyncManager.attach() must be called before resync_now()"
            )

        async with self._sem:
            if not self._breaker.allow_request():
                raise ResyncBlockedError("circuit open")

            try:
                await self._config.reload()
                self._os.resync()
                self._breaker.record_success()
            except Exception as e:
                self._breaker.record_failure()
                self._obs.error("resync.failed", error=str(e))
                raise

    def get_breaker_metrics(self) -> dict[str, Any]:
        """Return CircuitBreaker state metrics for observability.

        Returns:
            Dict with state, failure_rate, total_requests, success_count,
            failure_count, last_failure_time.
        """
        return self._breaker.get_state_metrics()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_debounce_timer(self) -> None:
        """Cancel any pending debounce and start a fresh timer.

        The timer sleeps for ``debounce_ms`` milliseconds, then calls
        ``resync_now()``. If a new event arrives before the sleep
        completes, the old task is cancelled and a new one starts.
        """
        self._cancel_debounce()

        async def _debounce() -> None:
            await asyncio.sleep(self._settings.debounce_ms / 1000)
            await self.resync_now()

        self._debounce_task = asyncio.create_task(_debounce())

    def _cancel_debounce(self) -> None:
        """Cancel the pending debounce task, if any."""
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
