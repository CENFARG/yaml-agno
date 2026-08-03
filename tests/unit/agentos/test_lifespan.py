"""Unit tests for LifespanAdapter — SPEC_12 Slice 2, TASK_008.

Covers the lifespan-adapter delta spec (5 requirements, 3 LIFESPAN scenarios)
with 7 TDD test cases:

    1.  LifespanAdapter creation — empty adapter is valid
    2.  add_component registers a lifespan-aware component with setup/teardown
    3.  LIFO shutdown order — first registered shuts down LAST
    4.  add_startup callback runs BEFORE component starts
    5.  add_shutdown callback runs DURING teardown after component stops
    6.  Exception in one component does NOT prevent others from shutting down
    7.  No asyncio.gather is used (architectural constraint)

Strict TDD: RED → GREEN → REFACTOR. Tests written BEFORE implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_ordered_component(name: str, order: list[str]):
    """Create a mock component whose start/stop append to a shared order list."""
    comp = MagicMock()
    comp._name = name

    async def _start():
        order.append(f"{name}.start")

    async def _stop():
        order.append(f"{name}.stop")

    comp.start = AsyncMock(side_effect=_start)
    comp.stop = AsyncMock(side_effect=_stop)
    return comp


# ═══════════════════════════════════════════════════════════════════════════
# Test cases
# ═══════════════════════════════════════════════════════════════════════════


class TestLifespanAdapterCreation:
    async def test_empty_adapter_is_valid(self):
        """A LifespanAdapter with no components yields cleanly."""
        from yaml_agno.agentos.lifespan import LifespanAdapter

        adapter = LifespanAdapter()

        async with adapter:
            pass

        # No exception was raised — the async context manager works with zero components


class TestAddComponent:
    async def test_add_component_runs_setup_and_teardown(self):
        """A registered component's start() is called on entry and stop() on exit."""
        from yaml_agno.agentos.lifespan import LifespanAdapter

        comp = MagicMock()
        comp.start = AsyncMock()
        comp.stop = AsyncMock()

        adapter = LifespanAdapter()
        adapter.add_component(comp)

        async with adapter:
            comp.start.assert_awaited_once()

        comp.stop.assert_awaited_once()


class TestLifoShutdownOrder:
    async def test_first_registered_shuts_down_last(self):
        """LIFO composition: component registered first stops LAST."""
        from yaml_agno.agentos.lifespan import LifespanAdapter

        order: list[str] = []
        mcp = _make_ordered_component("mcp", order)
        scheduler = _make_ordered_component("scheduler", order)

        adapter = LifespanAdapter()
        adapter.add_component(mcp)       # registered 1st
        adapter.add_component(scheduler)  # registered 2nd

        async with adapter:
            pass

        # Start order: registration order (mcp first, then scheduler)
        assert order[0] == "mcp.start", f"Start order: {order}"
        assert order[1] == "scheduler.start", f"Start order: {order}"
        # Shutdown order: LIFO — scheduler stops FIRST, then mcp
        assert order[2] == "scheduler.stop", (
            f"LIFO shutdown: scheduler (registered 2nd) must stop BEFORE mcp. Got: {order}"
        )
        assert order[3] == "mcp.stop", (
            f"LIFO shutdown: mcp (registered 1st) must stop AFTER scheduler. Got: {order}"
        )


class TestStartupCallbacks:
    async def test_startup_callback_runs_before_components(self):
        """add_startup() callbacks run BEFORE component.start()."""
        from yaml_agno.agentos.lifespan import LifespanAdapter

        order: list[str] = []
        comp = _make_ordered_component("comp", order)

        async def _init_logging():
            order.append("init_logging")

        startup_cb = AsyncMock(side_effect=_init_logging)

        adapter = LifespanAdapter()
        adapter.add_startup(startup_cb)
        adapter.add_component(comp)

        async with adapter:
            pass

        startup_cb.assert_awaited_once()
        # startup callback runs BEFORE component starts
        assert order[0] == "init_logging", f"Startup callback should run first. Got: {order}"
        assert order[1] == "comp.start", f"Component should start after callbacks. Got: {order}"


class TestShutdownCallbacks:
    async def test_shutdown_callback_runs_during_teardown(self):
        """add_shutdown() callbacks run during teardown (LIFO relative to components)."""
        from yaml_agno.agentos.lifespan import LifespanAdapter

        order: list[str] = []
        comp = _make_ordered_component("comp", order)

        async def _flush_metrics():
            order.append("flush_metrics")

        shutdown_cb = AsyncMock(side_effect=_flush_metrics)

        adapter = LifespanAdapter()
        adapter.add_component(comp)
        adapter.add_shutdown(shutdown_cb)

        async with adapter:
            pass

        shutdown_cb.assert_awaited_once()
        comp.stop.assert_awaited_once()
        # LIFO for shutdown: shutdown_cb registered AFTER comp, so called BEFORE comp.stop
        assert order[0] == "comp.start", f"Start first: {order}"
        assert order[1] == "flush_metrics", (
            f"Shutdown callback (registered after component) should run BEFORE "
            f"component.stop due to LIFO stack. Got: {order}"
        )
        assert order[2] == "comp.stop", f"Component stops last: {order}"


class TestExceptionPropagation:
    async def test_exception_in_one_component_does_not_block_others(self):
        """When one component raises during teardown, others still shut down."""
        from yaml_agno.agentos.lifespan import LifespanAdapter

        order: list[str] = []
        mcp = _make_ordered_component("mcp", order)
        scheduler = _make_ordered_component("scheduler", order)

        # scheduler will fail during stop (override the ordered one)
        async def _failing_stop():
            order.append("scheduler.stop")
            raise RuntimeError("scheduler crash")

        scheduler.stop = AsyncMock(side_effect=_failing_stop)

        adapter = LifespanAdapter()
        adapter.add_component(mcp)
        adapter.add_component(scheduler)

        with pytest.raises(RuntimeError, match="scheduler crash"):
            async with adapter:
                pass

        # mcp should still have been stopped (cleanup must not be abandoned)
        assert "mcp.stop" in order, (
            f"Exception in scheduler.stop should NOT prevent mcp.stop. Got: {order}"
        )


class TestNoAsyncioGather:
    async def test_no_asyncio_gather_in_lifespan_module(self):
        """Architectural constraint: LifespanAdapter MUST NOT use asyncio.gather."""
        import inspect

        from yaml_agno.agentos.lifespan import LifespanAdapter

        source = inspect.getsource(LifespanAdapter)
        assert "asyncio.gather" not in source, (
            "asyncio.gather is forbidden in LifespanAdapter. "
            "Use AsyncExitStack for LIFO composition."
        )
