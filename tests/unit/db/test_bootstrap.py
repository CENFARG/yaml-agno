"""RED tests for bootstrap_database (SPEC_03 slice E).

Strict TDD — written BEFORE the bootstrap exists. The bootstrap is a thin
wiring function that calls the provisioner to materialize the schema.

Uses a mock AsyncEngine — no real Postgres.

Tagged ``@pytest.mark.unit``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: E402

from yaml_agno.db.bootstrap import bootstrap_database  # noqa: E402

# ---------------------------------------------------------------------------
# Scenario E.1 — bootstrap calls provisioner.provision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_calls_provisioner() -> None:
    """bootstrap_database(engine) delegates to ConfigStoreProvisioner.provision."""
    engine = MagicMock(spec=AsyncEngine)
    conn = AsyncMock()
    conn.exec_driver_sql = AsyncMock()
    conn.run_sync = AsyncMock()
    conn.execute = AsyncMock()
    conn.execute.return_value = MagicMock(first=MagicMock(return_value=None))

    begin_cm = AsyncMock()
    begin_cm.__aenter__.return_value = conn
    begin_cm.__aexit__.return_value = None
    engine.begin.return_value = begin_cm

    # bootstrap_database should accept an AsyncEngine and call provisioner
    await bootstrap_database(engine)

    # The engine.begin() must have been entered (provisioner runs DDL)
    engine.begin.assert_called_once()
    conn.run_sync.assert_awaited()


# ---------------------------------------------------------------------------
# Scenario E.2 — bootstrap returns None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_returns_none() -> None:
    """bootstrap_database returns None (provisions schema, no return value)."""
    engine = MagicMock(spec=AsyncEngine)
    conn = AsyncMock()
    conn.exec_driver_sql = AsyncMock()
    conn.run_sync = AsyncMock()
    conn.execute = AsyncMock()
    conn.execute.return_value = MagicMock(first=MagicMock(return_value=None))

    begin_cm = AsyncMock()
    begin_cm.__aenter__.return_value = conn
    begin_cm.__aexit__.return_value = None
    engine.begin.return_value = begin_cm

    result = await bootstrap_database(engine)
    assert result is None


# ---------------------------------------------------------------------------
# Scenario E.3 — bootstrap is idempotent-safe (no error on second call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_does_not_raise_on_provisioner_success() -> None:
    """bootstrap_database completes without raising when provisioner succeeds."""
    engine = MagicMock(spec=AsyncEngine)
    conn = AsyncMock()
    conn.exec_driver_sql = AsyncMock()
    conn.run_sync = AsyncMock()
    conn.execute = AsyncMock()
    conn.execute.return_value = MagicMock(first=MagicMock(return_value=None))

    begin_cm = AsyncMock()
    begin_cm.__aenter__.return_value = conn
    begin_cm.__aexit__.return_value = None
    engine.begin.return_value = begin_cm

    # Should not raise
    await bootstrap_database(engine)
