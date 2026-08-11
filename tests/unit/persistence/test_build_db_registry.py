"""RED tests for build_db_registry (SPEC_03 §7.4 bootstrap wiring).

Strict TDD — written BEFORE ``yaml_agno.persistence.registry`` exists.

Contract (SPEC_03 §7.4): ``build_db_registry(config, secrets)`` iterates the
``databases`` and ``vector_databases`` config blocks, builds each Agno
``Db`` / ``VectorDb`` from its DSN (ConfigManager) + password
(SecretManager), and registers it under its ref.

Design decisions (documented in the module docstring once GREEN):
- ``build_db_registry`` is **async** because ``SecretManager.get_secret()`` is
  async (verified in core ``secrets/ports.py``).
- Factories are DI-injectable: ``db_factory(db_ref, dsn)`` and
  ``vector_db_factory(db_ref, dsn, table_name)``. Defaults build Agno
  ``PostgresDb`` / ``PgVector`` with clear ``ImportError`` if the underlying
  driver package is missing. Tests ALWAYS inject fakes so no asyncpg /
  pgvector is required.
- Config entry shape::

    databases:
      primary_pg:
        dsn: postgresql+asyncpg://user:{password}@host:5432/db
        password_ref: db.primary.password   # optional; replaces {password}
    vector_databases:
      kb_vectors:
        dsn: postgresql+asyncpg://user:{password}@host:5432/db
        table_name: kb_documents
        password_ref: db.kb.password        # optional

Tagged ``@pytest.mark.unit``.
"""

from __future__ import annotations

import pytest
from core_infrastructure.config.adapters.in_memory_config_adapter import (
    InMemoryConfigAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import (
    InMemorySecretAdapter,
)

pytestmark = pytest.mark.unit

from yaml_agno.persistence.registry import (  # noqa: E402
    build_db_registry,
)


class _FakeDb:
    def __init__(self, ref: str, dsn: str) -> None:
        self.ref = ref
        self.dsn = dsn


class _FakeVectorDb:
    def __init__(self, ref: str, dsn: str, table_name: str) -> None:
        self.ref = ref
        self.dsn = dsn
        self.table_name = table_name


def _config_with(
    databases: dict | None = None,
    vector_databases: dict | None = None,
) -> InMemoryConfigAdapter:
    cfg: dict = {}
    if databases is not None:
        cfg["databases"] = databases
    if vector_databases is not None:
        cfg["vector_databases"] = vector_databases
    return InMemoryConfigAdapter(cfg)


# ---------------------------------------------------------------------------
# Scenario 1 — registers dbs and vector_dbs from config blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_registers_db_under_its_ref() -> None:
    """A databases entry must be built by db_factory and registered by ref."""
    config = _config_with(
        databases={
            "primary_pg": {
                "dsn": "postgresql+asyncpg://user:pass@host:5432/db",
            },
        },
    )
    secrets = InMemorySecretAdapter()

    def db_factory(db_ref: str, dsn: str) -> _FakeDb:
        return _FakeDb(db_ref, dsn)

    registry = await build_db_registry(config, secrets, db_factory=db_factory)

    db = registry.get("primary_pg")
    assert isinstance(db, _FakeDb)
    assert db.ref == "primary_pg"
    assert db.dsn == "postgresql+asyncpg://user:pass@host:5432/db"


@pytest.mark.asyncio
async def test_build_registers_vector_db_with_table_name() -> None:
    """A vector_databases entry must be built and registered by ref."""
    config = _config_with(
        vector_databases={
            "kb_vectors": {
                "dsn": "postgresql+asyncpg://user:pass@host:5432/db",
                "table_name": "kb_documents",
            },
        },
    )
    secrets = InMemorySecretAdapter()

    def vector_db_factory(db_ref: str, dsn: str, table_name: str) -> _FakeVectorDb:
        return _FakeVectorDb(db_ref, dsn, table_name)

    registry = await build_db_registry(
        config,
        secrets,
        vector_db_factory=vector_db_factory,
    )

    vdb = registry.get_vector_db("kb_vectors")
    assert isinstance(vdb, _FakeVectorDb)
    assert vdb.ref == "kb_vectors"
    assert vdb.table_name == "kb_documents"


# ---------------------------------------------------------------------------
# Scenario 2 — password resolution via SecretManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_resolves_password_placeholder_from_secrets() -> None:
    """{password} in the DSN must be replaced from SecretManager when
    password_ref is present (never logged, only substituted in memory)."""
    config = _config_with(
        databases={
            "primary_pg": {
                "dsn": "postgresql+asyncpg://user:{password}@host:5432/db",
                "password_ref": "db.primary.password",
            },
        },
    )
    secrets = InMemorySecretAdapter()
    secrets.set_secret("db.primary.password", "s3cr3t")

    captured: dict[str, str] = {}

    def db_factory(db_ref: str, dsn: str) -> _FakeDb:
        captured["dsn"] = dsn
        return _FakeDb(db_ref, dsn)

    await build_db_registry(config, secrets, db_factory=db_factory)

    assert "s3cr3t" in captured["dsn"]
    assert "{password}" not in captured["dsn"]


# ---------------------------------------------------------------------------
# Scenario 3 — empty / missing blocks yield an empty registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_with_no_blocks_returns_empty_registry() -> None:
    """Missing databases/vector_databases blocks must NOT error; the registry
    is empty and lookups fail fast with ValueError."""
    config = InMemoryConfigAdapter({"app.name": "test"})
    secrets = InMemorySecretAdapter()

    registry = await build_db_registry(config, secrets)

    with pytest.raises(ValueError, match="primary_pg"):
        registry.get("primary_pg")
    with pytest.raises(ValueError, match="kb_vectors"):
        registry.get_vector_db("kb_vectors")


# ---------------------------------------------------------------------------
# Scenario 4 — fail-fast on malformed entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_missing_dsn_raises_clear_error() -> None:
    """An entry without a dsn must fail fast with a clear message."""
    config = _config_with(databases={"primary_pg": {}})
    secrets = InMemorySecretAdapter()

    with pytest.raises(ValueError, match="dsn"):
        await build_db_registry(config, secrets)


@pytest.mark.asyncio
async def test_build_vector_db_missing_table_name_raises() -> None:
    """A vector_databases entry without table_name must fail fast."""
    config = _config_with(
        vector_databases={"kb_vectors": {"dsn": "postgresql+asyncpg://host/db"}},
    )
    secrets = InMemorySecretAdapter()

    with pytest.raises(ValueError, match="table_name"):
        await build_db_registry(config, secrets)
