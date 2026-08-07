"""LifespanAdapter — AsyncExitStack LIFO composition for MCP/scheduler/OTel/user.

TASK_008 — SPEC_12 Slice 2, PR 2. Composes multiple lifespan-aware components
into a single FastAPI-compatible async context manager using ``AsyncExitStack``.

Design (sdd/control-plane-s2/design):
    - Uses ``AsyncExitStack`` for LIFO cleanup — first registered component
      shuts down LAST.
    - Explicitly forbids ``asyncio.gather`` (spec §7.3 hard requirement).
    - Each component provides ``start()`` and ``stop()`` methods.
    - ``add_startup()`` / ``add_shutdown()`` allow non-component callbacks
      (e.g., logging init, metrics reset) outside the component chain.
    - ``__aenter__`` starts all components in registration order.
    - ``__aexit__`` tears down in LIFO order (reverse registration).
      If one component raises during teardown, remaining components still
      get their ``stop()`` called (best-effort cleanup).

@ai-directive: SSOT is specs/SPEC_12_CONTROL_PLANE.md §7 (LifespanAdapter).
    Use ``contextlib.AsyncExitStack``, NEVER ``asyncio.gather``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Any, Protocol

__all__ = ["LifespanAdapter"]


# ═══════════════════════════════════════════════════════════════════════════
# Protocol
# ═══════════════════════════════════════════════════════════════════════════


class LifespanComponent(Protocol):
    """A duck-typed component with async ``start()`` and ``stop()`` methods.

    Any object with these two async methods can be registered via
    ``LifespanAdapter.add_component()``. The adapter calls ``start()``
    during ``__aenter__`` and ``stop()`` during ``__aexit__``.
    """

    async def start(self) -> None:
        """Start the component. Called on ``__aenter__`` in registration order."""

    async def stop(self) -> None:
        """Stop the component. Called on ``__aexit__`` in LIFO order."""


# Type aliases for readability.
_AsyncCallable = Callable[[], Awaitable[Any]]


# ═══════════════════════════════════════════════════════════════════════════
# LifespanAdapter
# ═══════════════════════════════════════════════════════════════════════════


class LifespanAdapter:
    """Composes multiple lifespan-aware components into one async context manager.

    Each registered component is started in registration order and shut down in
    LIFO (reverse registration) order via ``AsyncExitStack``. Startup and
    shutdown callbacks run alongside components with the same LIFO semantics.

    Usage::

        adapter = LifespanAdapter()
        adapter.add_component(mcp_lifecycle)
        adapter.add_component(scheduler)
        adapter.add_startup(init_logging)
        adapter.add_shutdown(flush_metrics)

        async with adapter:
            # All components started, callbacks run
            yield
        # All components stopped in LIFO order, callbacks run

    Example (FastAPI lifespan)::

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            adapter = LifespanAdapter()
            adapter.add_component(mcp_lifecycle)
            adapter.add_component(scheduler)
            async with adapter:
                yield
    """

    def __init__(self) -> None:
        self._components: list[LifespanComponent] = []
        self._startup_callbacks: list[_AsyncCallable] = []
        self._shutdown_callbacks: list[_AsyncCallable] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_component(self, component: LifespanComponent) -> None:
        """Register a lifespan-aware component.

        Components are started in registration order and stopped in reverse
        (LIFO) order. Each component must implement async ``start()`` and
        ``stop()`` methods.

        Args:
            component: Any object with ``async start()`` and ``async stop()``.
        """
        self._components.append(component)

    def add_startup(self, callback: _AsyncCallable) -> None:
        """Register a startup-only callback (no paired teardown).

        Runs BEFORE all component ``start()`` calls, in registration order.
        Useful for one-shot initialization like logging config or env checks.

        Args:
            callback: An async callable ``() -> Any``.
        """
        self._startup_callbacks.append(callback)

    def add_shutdown(self, callback: _AsyncCallable) -> None:
        """Register a shutdown-only callback (no paired startup).

        Runs DURING teardown in LIFO order relative to components. A callback
        registered after a component will run BEFORE that component's ``stop()``
        (as if pushed onto the exit stack after the component).

        Args:
            callback: An async callable ``() -> Any``.
        """
        self._shutdown_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Async Context Manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> LifespanAdapter:
        """Start all components and run startup callbacks.

        Order:
            1. Push shutdown callbacks onto ``AsyncExitStack`` (LIFO).
            2. Push component ``stop()`` callbacks onto the stack (LIFO).
            3. Run startup callbacks (registration order).
            4. Start components (registration order).

        Returns:
            ``self`` — the adapter itself, for use as ``async with adapter:``.
        """
        self._stack = AsyncExitStack()

        # --- Push shutdown handlers first (LIFO: last pushed = first called) ---
        # Push in registration order so the LAST-registered component's stop is
        # pushed LAST (top of LIFO stack → called FIRST on exit). This achieves
        # the LIFO composition contract: component registered last shuts down first.
        for component in self._components:
            self._stack.push_async_callback(component.stop)

        for cb in self._shutdown_callbacks:
            self._stack.push_async_callback(cb)

        # --- Run startup callbacks in registration order ---
        for cb in self._startup_callbacks:
            await cb()

        # --- Start components in registration order ---
        for component in self._components:
            await component.start()

        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        """Tear down all components in LIFO order via ``AsyncExitStack``.

        ``AsyncExitStack.__aexit__`` calls each registered callback in reverse
        push order (LIFO). If one callback raises, remaining callbacks are still
        called (best-effort cleanup), and the FIRST exception is re-raised.
        """
        await self._stack.aclose()
