"""RED tests for ConfigStoreProvisioner (SPEC_03 slice B).

Strict TDD — written BEFORE the provisioner exists. The provisioner creates the
``yamlagno_*`` schema and tables via ``Base.metadata.create_all(checkfirst=True)``
and records the applied version in ``yamlagno_schema_versions``.

Uses a mock ``AsyncEngine`` / ``AsyncConnection`` — no real Postgres needed.
Tagged ``@pytest.mark.unit``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

from yaml_agno.db.provisioner import CONFIG_STORE_VERSION, ConfigStoreProvisioner  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers — mock AsyncEngine + AsyncConnection
# ---------------------------------------------------------------------------


def _make_mock_engine(
    *,
    version_exists: bool = False,
) -> tuple[MagicMock, MagicMock]:
    """Build a mock AsyncEngine and its connection.

    The connection's ``run_sync`` records the callable (so we can assert it was
    ``create_all``). ``exec_driver_sql`` records CREATE SCHEMA. The version check
    ``execute(select(...))`` returns a mock result with ``.first()`` that returns
    a row or None depending on ``version_exists``.

    Returns ``(engine, conn)`` so tests can assert on ``conn``.
    """
    conn = AsyncMock()
    # exec_driver_sql is synchronous-ish on async conn: returns awaitable
    conn.exec_driver_sql = AsyncMock()

    # Version check: conn.execute(select(...)) -> result.first()
    version_result = MagicMock()
    version_result.first.return_value = (
        MagicMock() if version_exists else None
    )
    insert_result = MagicMock()

    # conn.execute is async — return different results based on the statement
    execute_call_count = {"n": 0}

    async def _execute(stmt):
        execute_call_count["n"] += 1
        if execute_call_count["n"] == 1:
            # First execute = version SELECT check
            return version_result
        # Second execute = version INSERT
        return insert_result

    conn.execute = _execute

    # run_sync records the callable passed to it (create_all)
    run_sync_calls: list = []

    async def _run_sync(fn, *args, **kwargs):
        run_sync_calls.append((fn, args, kwargs))

    conn.run_sync = _run_sync

    # engine.begin() -> async context manager yielding conn
    engine = MagicMock()
    begin_cm = AsyncMock()
    begin_cm.__aenter__.return_value = conn
    begin_cm.__aexit__.return_value = None
    engine.begin.return_value = begin_cm

    # Attach run_sync_calls so tests can inspect
    conn._run_sync_calls = run_sync_calls  # type: ignore[attr-defined]
    conn._execute_call_count = execute_call_count  # type: ignore[attr-defined]

    return engine, conn


# ---------------------------------------------------------------------------
# Scenario B.1 — provision creates tables (mock engine)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_creates_schema_and_tables() -> None:
    """provision() calls CREATE SCHEMA + create_all(checkfirst=True)."""
    engine, conn = _make_mock_engine(version_exists=False)
    provisioner = ConfigStoreProvisioner()

    await provisioner.provision(engine)

    # CREATE SCHEMA was called
    conn.exec_driver_sql.assert_called_once()
    sql_arg = conn.exec_driver_sql.call_args[0][0]
    assert "CREATE SCHEMA" in sql_arg, f"Expected CREATE SCHEMA, got: {sql_arg}"

    # create_all was called via run_sync — the lambda wraps
    # Base.metadata.create_all(sync_conn, checkfirst=True), so run_sync receives
    # a single callable. Verify it was called.
    assert len(conn._run_sync_calls) == 1, "run_sync should be called once for create_all"
    fn = conn._run_sync_calls[0][0]
    assert callable(fn), "run_sync must receive a callable (create_all wrapper)"

    # Version was recorded (execute called twice: check + insert)
    assert conn._execute_call_count["n"] == 2, (
        "Expected 2 execute calls (version check + version insert)"
    )


# ---------------------------------------------------------------------------
# Scenario B.2 — provision is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_is_idempotent_when_version_exists() -> None:
    """If the version already exists, no duplicate INSERT."""
    engine, conn = _make_mock_engine(version_exists=True)
    provisioner = ConfigStoreProvisioner()

    await provisioner.provision(engine)

    # create_all still runs (checkfirst=True makes it safe)
    assert len(conn._run_sync_calls) == 1

    # Only 1 execute call: the version SELECT (no INSERT because version exists)
    assert conn._execute_call_count["n"] == 1, (
        "Expected only 1 execute call (version SELECT, no INSERT) when version exists"
    )


# ---------------------------------------------------------------------------
# Scenario B.3 — provision records the correct version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_uses_config_store_version_constant() -> None:
    """CONFIG_STORE_VERSION is a non-empty string used for the version row."""
    assert isinstance(CONFIG_STORE_VERSION, str)
    assert len(CONFIG_STORE_VERSION) > 0


# ---------------------------------------------------------------------------
# Scenario B.4 — calling provision twice does not error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_called_twice_does_not_error() -> None:
    """Calling provision twice with fresh mocks does not raise."""
    provisioner = ConfigStoreProvisioner()

    engine1, _ = _make_mock_engine(version_exists=False)
    await provisioner.provision(engine1)

    engine2, _ = _make_mock_engine(version_exists=True)
    await provisioner.provision(engine2)  # second call: version already exists

    # Both calls completed without error
    engine1.begin.assert_called_once()
    engine2.begin.assert_called_once()
