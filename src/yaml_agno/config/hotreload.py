"""Hot-reload coordinator (SPEC_23 §2.7, TASK_2310).

A single background loop re-materializes config and re-refreshes flags on an
interval, so feature flags and settings can change without a restart. The
coordinator is *composition-only*: it drives the config/flag managers that
the wiring layer injected, it does not re-read YAML itself.

State machine: stopped → running → stopped.

```mermaid
stateDiagram-v2
    [*] --> Stopped
    Stopped --> Running: start()
    Running --> Running: interval elapses -> reload_now()
    Running --> Stopped: stop()
    Stopped --> [*]
```
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.feature_flags.ports import FeatureFlagManager

__all__ = ["HotReloadCoordinator"]


class HotReloadCoordinator:
    """Periodically re-materializes config and re-refreshes feature flags.

    Args:
        config: The yaml-agno config adapter (implements the core
            :class:`ConfigManager` protocol plus ``reload()``).
        flags: The core :class:`FeatureFlagManager`.
        interval_s: Reload interval in seconds.
    """

    def __init__(self, config: ConfigManager, flags: FeatureFlagManager, *, interval_s: int = 30) -> None:
        self._config = config
        self._flags = flags
        self._interval_s = interval_s
        self._task: asyncio.Task[Any] | None = None

    async def reload_now(self) -> None:
        """Re-materialize config and refresh flags immediately."""
        await self._config.reload()
        await self._flags.refresh()

    async def start(self) -> None:
        """Start the background reload loop (idempotent)."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="hotreload-coordinator")

    async def stop(self) -> None:
        """Stop the background loop and await its cancellation (idempotent)."""
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            await self.reload_now()
