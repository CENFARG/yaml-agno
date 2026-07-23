"""Schema provisioner for the yamlagno config store (SPEC_03 §6.1, slice B).

Uses SQLAlchemy ORM ``Base.metadata.create_all(checkfirst=True)`` to materialize
the ``yamlagno_*`` schema and tables on demand. Version-tracked in
``yamlagno_schema_versions``. This is the ONLY place yaml-agno touches DDL;
core-cenf owns sessions/transactions.

The provisioner takes an ``AsyncEngine`` (not a ``DatabaseManager``) because it
runs DDL during SCHEMA BOOTSTRAP, before the core ``GenericRepository`` layer is
ready for CRUD. Per SPEC_03 §6.1 @ai-directive, this is intentional and NOT a
violation of the "consume core" rule (the core CRUD layer does not exist yet at
provisioning time).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from yaml_agno.db.models import Base
from yaml_agno.db.models.schema_version import SchemaVersionRecord

#: The version string recorded in ``yamlagno_schema_versions`` when the config
#: store schema is provisioned. This gates ``checkfirst`` re-runs so idempotent
#: provisioning does not duplicate the version row.
CONFIG_STORE_VERSION = "0.3.0"

#: The SQL schema name for all ``yamlagno_*`` tables.
CONFIG_STORE_SCHEMA = "yamlagno"


class ConfigStoreProvisioner:
    """Creates the ``yamlagno`` schema and tables on demand.

    This class is idempotent: calling ``provision()`` multiple times is safe.
    ``create_all(checkfirst=True)`` skips tables that already exist, and the
    version row is only inserted if it is not already present.
    """

    def __init__(self, schema: str = CONFIG_STORE_SCHEMA) -> None:
        """Initialize the provisioner.

        Args:
            schema: The SQL schema name for ``yamlagno_*`` tables.
                Defaults to ``"yamlagno"``.
        """
        self._schema = schema

    async def provision(self, engine: AsyncEngine) -> None:
        """Create the schema + tables if missing and record the version.

        Args:
            engine: An async SQLAlchemy engine (same DSN as the
                ``DatabaseManager``). The provisioner uses ``engine.begin()``
                to run DDL in a transaction.

        Note:
            ``checkfirst=True`` makes this method idempotent. The version row
            in ``yamlagno_schema_versions`` is only inserted if it does not
            already exist.
        """
        async with engine.begin() as conn:
            # Create the schema if it does not exist (Postgres needs this
            # before create_all can place tables under it).
            await conn.exec_driver_sql(
                f'CREATE SCHEMA IF NOT EXISTS "{self._schema}"'
            )
            # Materialize all yamlagno_* tables registered on Base.metadata.
            # checkfirst=True ensures idempotency (no error on re-run).
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, checkfirst=True,
                )
            )
            # Record the applied version (idempotent: only insert if missing).
            await self._mark_version(conn)

    async def _mark_version(self, conn: Any) -> None:
        """Record the schema version if it is not already present.

        Uses the raw connection directly (Core-style select/insert), NOT
        ``db.get_repository()`` — at provisioning time the core
        ``GenericRepository`` layer is not yet ready for CRUD. This is
        intentional per SPEC_03 §6.1 @ai-directive.
        """
        exists = await conn.execute(
            select(SchemaVersionRecord).where(
                SchemaVersionRecord.component == "config_store",
                SchemaVersionRecord.version == CONFIG_STORE_VERSION,
            )
        )
        if exists.first() is None:
            await conn.execute(
                SchemaVersionRecord.__table__.insert().values(  # type: ignore[attr-defined]
                    component="config_store",
                    version=CONFIG_STORE_VERSION,
                )
            )


__all__ = ["CONFIG_STORE_SCHEMA", "CONFIG_STORE_VERSION", "ConfigStoreProvisioner"]
