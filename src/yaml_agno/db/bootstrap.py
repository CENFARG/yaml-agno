"""Bootstrap for the yaml-agno config store schema (SPEC_03 §7.1, slice E).

Thin wiring function that ``YamlAgentOS`` calls at startup to materialize the
``yamlagno_*`` schema. Delegates all DDL to the ``ConfigStoreProvisioner``.

This function takes an ``AsyncEngine`` (not a ``DatabaseManager``) because the
provisioner runs DDL during schema bootstrap, before the core
``GenericRepository`` layer is ready for CRUD. The ``DatabaseManager`` Protocol
does not expose its engine, so the caller (e.g. ``build_database_manager`` or
``YamlAgentOS``) must pass the same engine the ``DatabaseManager`` was built
with. See SPEC_03 §6.1 and §7.1.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from yaml_agno.db.provisioner import ConfigStoreProvisioner


async def bootstrap_database(engine: AsyncEngine) -> None:
    """Provision the ``yamlagno_*`` schema and tables.

    Creates the schema and all config-store tables via
    ``Base.metadata.create_all(checkfirst=True)`` and records the applied
    version in ``yamlagno_schema_versions``. Idempotent — safe to call at every
    startup.

    Args:
        engine: An async SQLAlchemy engine. This must be the same engine the
            ``DatabaseManager`` was built with (same DSN), so the provisioned
            tables are visible to subsequent CRUD operations.
    """
    provisioner = ConfigStoreProvisioner()
    await provisioner.provision(engine)


__all__ = ["bootstrap_database"]
