"""Unit tests for HotReloadCoordinator (SPEC_23 §2.7, TASK_2311/TASK_2312).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Uses lightweight fakes that
record whether reload()/refresh() were invoked — the coordinator MUST delegate,
never re-implement materialization/swap.

Covers:
  - reload_now() calls the core config.reload() and flags.refresh().
  - start() schedules the periodic loop; stop() cancels it.
"""

from __future__ import annotations

import asyncio

import pytest

from yaml_agno.config.hotreload import HotReloadCoordinator


class FakeConfig:
    """ConfigManager double recording reload() calls."""

    def __init__(self) -> None:
        self.reloads = 0

    async def reload(self) -> None:
        self.reloads += 1


class FakeFlags:
    """FeatureFlagManager double recording refresh() calls."""

    def __init__(self) -> None:
        self.refreshes = 0

    async def refresh(self) -> None:
        self.refreshes += 1


@pytest.mark.unit
async def test_reload_now_invokes_core_reload_and_refresh() -> None:
    """TASK_2311/TASK_2312 — reload_now MUST call core reload() + flags.refresh()."""
    cfg = FakeConfig()
    flags = FakeFlags()
    coordinator = HotReloadCoordinator(cfg, flags, interval_s=1)

    await coordinator.reload_now()

    assert cfg.reloads == 1
    assert flags.refreshes == 1


@pytest.mark.unit
async def test_start_schedules_periodic_reload_until_stopped() -> None:
    """start() MUST run the loop (calling core methods) until stop() cancels it."""
    cfg = FakeConfig()
    flags = FakeFlags()
    coordinator = HotReloadCoordinator(cfg, flags, interval_s=0.01)

    await coordinator.start()
    await asyncio.sleep(0.05)  # allow several ticks
    await coordinator.stop()

    assert cfg.reloads >= 1
    assert flags.refreshes == cfg.reloads  # one refresh per reload tick


@pytest.mark.unit
async def test_stop_before_start_is_safe() -> None:
    """stop() MUST be a no-op when the coordinator was never started."""
    coordinator = HotReloadCoordinator(FakeConfig(), FakeFlags(), interval_s=1)
    await coordinator.stop()
    assert coordinator._task is None


@pytest.mark.unit
def test_interval_is_configurable() -> None:
    """The reload interval MUST be configurable via the constructor."""
    coordinator = HotReloadCoordinator(FakeConfig(), FakeFlags(), interval_s=5)
    assert coordinator._interval_s == 5
