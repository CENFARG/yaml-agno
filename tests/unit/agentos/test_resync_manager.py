"""Unit tests for ``ResyncManager`` — SPEC_12 Slice 3, T005a-e.

Strict TDD: RED → GREEN → REFACTOR cycle per task.

Tasks:
    T005a — ResyncManager construction and CircuitBreaker wiring
    T005b — resync_now() with CircuitBreaker guard
    T005c — Semaphore concurrency control
    T005d — watch() with debounce
    T005e — attach pattern
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from yaml_agno.models.config.agentos_config import ResyncSettings

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════════════
# T005a — ResyncManager construction and CB wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestResyncManagerConstruction:
    """T005a: CircuitBreaker configured from ResyncSettings on construction."""

    def test_breaker_configured_from_settings(self, mocker: MockerFixture) -> None:
        """CircuitBreaker instantiated with settings values (rate-based thresholds)."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(
                failure_threshold=30.0,
                min_requests=3,
                recovery_timeout=60,
            ),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        assert mgr._breaker.failure_threshold == 30.0
        assert mgr._breaker.min_requests == 3
        assert mgr._breaker.recovery_timeout == 60.0

    def test_semaphore_initialized_with_max_concurrent(self, mocker: MockerFixture) -> None:
        """asyncio.Semaphore initialized from settings.max_concurrent."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(max_concurrent=2),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        # semaphore._value reflects permits (non-public but reliable for asyncio.Semaphore)
        assert mgr._sem._value == 2

    def test_agentos_starts_none(self, mocker: MockerFixture) -> None:
        """_os starts as None — set later via attach()."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        assert mgr._os is None

    def test_default_settings_produce_defaults(self, mocker: MockerFixture) -> None:
        """Default ResyncSettings use CircuitBreaker factory defaults where applicable."""
        from yaml_agno.agentos.resync_manager import ResyncManager
        from yaml_agno.resilience.circuit_breaker import CircuitState

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        assert mgr._breaker.state == CircuitState.CLOSED
        assert mgr._breaker.failure_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# T005e — attach pattern
# ═══════════════════════════════════════════════════════════════════════════


class TestAttachPattern:
    """T005e: attach() sets the AgentOS reference post-construction."""

    def test_attach_sets_agentos_reference(self, mocker: MockerFixture) -> None:
        """attach(os_instance) stores the AgentOS reference."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )
        assert mgr._os is None

        os_mock = mocker.Mock()
        mgr.attach(os_mock)

        assert mgr._os is os_mock

    def test_attach_overwrites_previous(self, mocker: MockerFixture) -> None:
        """Calling attach() again updates the reference (re-attach scenario)."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        first = mocker.Mock(name="os_v1")
        second = mocker.Mock(name="os_v2")
        mgr.attach(first)
        assert mgr._os is first
        mgr.attach(second)
        assert mgr._os is second


# ═══════════════════════════════════════════════════════════════════════════
# T005b — resync_now() with CircuitBreaker guard
# ═══════════════════════════════════════════════════════════════════════════


class TestResyncNow:
    """T005b: resync_now() executes reload → resync, guarded by CircuitBreaker."""

    @pytest.mark.asyncio
    async def test_resync_success_calls_reload_and_resync(self, mocker: MockerFixture) -> None:
        """On success: ConfigManager.reload() → AgentOS.resync() → record_success()."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        cfg = mocker.Mock()
        cfg.reload = mocker.AsyncMock()
        os_mock = mocker.Mock()
        obs = mocker.Mock()

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True),
            obs=obs,
            config=cfg,
        )
        mgr.attach(os_mock)

        await mgr.resync_now()

        cfg.reload.assert_awaited_once()
        os_mock.resync.assert_called_once()
        obs.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_resync_blocked_by_open_circuit(self, mocker: MockerFixture) -> None:
        """When breaker is OPEN, resync_now() raises ResyncBlockedError."""
        from yaml_agno.agentos.resync_manager import ResyncBlockedError, ResyncManager

        cfg = mocker.Mock()
        os_mock = mocker.Mock()
        obs = mocker.Mock()

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(
                enabled=True,
                failure_threshold=50.0,
                min_requests=2,
                recovery_timeout=1,
            ),
            obs=obs,
            config=cfg,
        )
        mgr.attach(os_mock)

        # Force 2 failures → 100% >= 50%, >= 2 min_requests → OPEN
        cfg.reload = mocker.AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            await mgr.resync_now()
        with pytest.raises(RuntimeError):
            await mgr.resync_now()
        # Third call should be blocked by OPEN circuit
        with pytest.raises(ResyncBlockedError, match="circuit open"):
            await mgr.resync_now()

        # ConfigManager.reload should have been called exactly 2 times
        assert cfg.reload.await_count == 2

    @pytest.mark.asyncio
    async def test_resync_failure_records_and_logs(self, mocker: MockerFixture) -> None:
        """On failure: record_failure() → obs.error() → re-raise."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        cfg = mocker.Mock()
        cfg.reload.side_effect = RuntimeError("config parse error")
        os_mock = mocker.Mock()
        obs = mocker.Mock()

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True),
            obs=obs,
            config=cfg,
        )
        mgr.attach(os_mock)

        with pytest.raises(RuntimeError, match="config parse error"):
            await mgr.resync_now()

        obs.error.assert_called_once()
        assert "resync.failed" in str(obs.error.call_args)
        os_mock.resync.assert_not_called()

    @pytest.mark.asyncio
    async def test_resync_without_attach_raises(self, mocker: MockerFixture) -> None:
        """resync_now() without prior attach() raises RuntimeError with clear message."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        with pytest.raises(RuntimeError, match="attach"):
            await mgr.resync_now()

    @pytest.mark.asyncio
    async def test_resync_success_records_breaker_success(self, mocker: MockerFixture) -> None:
        """After successful resync, CircuitBreaker records a success."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        cfg = mocker.Mock()
        cfg.reload = mocker.AsyncMock()
        os_mock = mocker.Mock()
        obs = mocker.Mock()

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True),
            obs=obs,
            config=cfg,
        )
        mgr.attach(os_mock)

        # Spy on breaker.record_success
        record_spy = mocker.spy(mgr._breaker, "record_success")

        await mgr.resync_now()

        record_spy.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# T005c — Semaphore concurrency control
# ═══════════════════════════════════════════════════════════════════════════


class TestSemaphoreConcurrency:
    """T005c: Semaphore serializes concurrent resync_now() calls."""

    @pytest.mark.asyncio
    async def test_semaphore_serializes_concurrent_calls(self, mocker: MockerFixture) -> None:
        """With max_concurrent=1, calls execute sequentially, never interleaved."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        call_order: list[str] = []
        cfg = mocker.Mock()

        async def slow_reload() -> None:
            call_order.append("enter")
            await asyncio.sleep(0.05)
            call_order.append("exit")

        cfg.reload = slow_reload
        os_mock = mocker.Mock()
        obs = mocker.Mock()

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True, max_concurrent=1),
            obs=obs,
            config=cfg,
        )
        mgr.attach(os_mock)

        t1 = asyncio.create_task(mgr.resync_now())
        await asyncio.sleep(0.01)  # Let t1 enter the semaphore
        t2 = asyncio.create_task(mgr.resync_now())

        await asyncio.gather(t1, t2)

        # t1 enters, t1 exits, t2 enters, t2 exits — never interleaved
        assert call_order == ["enter", "exit", "enter", "exit"]

    @pytest.mark.asyncio
    async def test_semaphore_max_concurrent_2_allows_two(self, mocker: MockerFixture) -> None:
        """With max_concurrent=2, two concurrent calls enter simultaneously."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        concurrent: list[int] = []
        peak: list[int] = []
        cfg = mocker.Mock()

        async def tracked_reload() -> None:
            concurrent.append(1)
            peak.append(len(concurrent))
            await asyncio.sleep(0.05)
            concurrent.pop()

        cfg.reload = tracked_reload
        os_mock = mocker.Mock()
        obs = mocker.Mock()

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True, max_concurrent=2),
            obs=obs,
            config=cfg,
        )
        mgr.attach(os_mock)

        t1 = asyncio.create_task(mgr.resync_now())
        await asyncio.sleep(0.01)
        t2 = asyncio.create_task(mgr.resync_now())

        await asyncio.gather(t1, t2)

        # Peak concurrency should be 2 (both entered at the same time)
        assert max(peak) == 2


# ═══════════════════════════════════════════════════════════════════════════
# T005d — watch() with debounce
# ═══════════════════════════════════════════════════════════════════════════


class TestWatch:
    """T005d: watch() debounces filesystem events and triggers resync."""

    @pytest.mark.asyncio
    async def test_watch_does_nothing_when_disabled(self, mocker: MockerFixture) -> None:
        """When watch=False, watch() returns immediately — no watcher created."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True, watch=False),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        # Should return immediately without error
        await mgr.watch()

    @pytest.mark.asyncio
    async def test_watch_returns_when_not_enabled(self, mocker: MockerFixture) -> None:
        """When enabled=False, watch() returns immediately."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=False, watch=True),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        await mgr.watch()
        # No exception = pass

    @pytest.mark.asyncio
    async def test_debounce_task_cancelled_on_new_event(self, mocker: MockerFixture) -> None:
        """New event cancels existing debounce task and starts a fresh one."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True, watch=True, debounce_ms=100),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        # Mock resync_now to prevent actual work; keep real asyncio.sleep
        mocker.patch.object(mgr, "resync_now", new_callable=mocker.AsyncMock)

        # Start a debounce timer
        mgr._start_debounce_timer()
        assert mgr._debounce_task is not None
        first_task = mgr._debounce_task

        # Start another — should cancel the first
        mgr._start_debounce_timer()
        assert mgr._debounce_task is not None
        assert mgr._debounce_task is not first_task

        # Yield to let cancellation propagate through real asyncio.sleep
        await asyncio.sleep(0)
        assert first_task.cancelled()

    @pytest.mark.asyncio
    async def test_debounce_executes_resync_after_sleep(self, mocker: MockerFixture) -> None:
        """After debounce_ms sleep, resync_now() is called."""
        from yaml_agno.agentos.resync_manager import ResyncManager

        mgr = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True, watch=True, debounce_ms=50),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        resync_spy = mocker.patch.object(mgr, "resync_now", new_callable=mocker.AsyncMock)

        # Simulate debounce by directly calling _start_debounce_timer
        mgr._start_debounce_timer()

        # Let the debounce task execute (real sleep is short: 50ms)
        await asyncio.sleep(0.1)

        resync_spy.assert_called_once()
