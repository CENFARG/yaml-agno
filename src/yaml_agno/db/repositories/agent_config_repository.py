"""AgentConfigRepository — CRUD over yamlagno_agent_configs (SPEC_03 §7.2, slice C).

Thin wrapper over the core-cenf ``GenericRepository[T]``. yaml-agno does NOT
subclass a ``BaseRepository`` or manage transactions directly. Every method
opens ``async with db.transaction()``, calls ``db.get_repository()`` INSIDE the
``async with`` block (required by the core adapter's contextvar binding), and
commits.

Multi-tenant isolation is EXPLICIT: every method passes ``tenant_id`` in the
``filters={}`` dict. The core ``GenericRepository`` does NOT auto-scope by the
tenant contextvar; ``set_tenant_id()`` drives logging/tracing only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import yaml

from yaml_agno.db.models.agent_config import AgentConfigRecord
from yaml_agno.models.config.agent_config import AgentConfig

if TYPE_CHECKING:
    from core_infrastructure.database import DatabaseManager


class AgentConfigRepository:
    """CRUD over ``yamlagno_agent_configs`` using core-cenf GenericRepository.

    Note:
        - ``db.get_repository()`` MUST be called inside ``async with
          db.transaction()`` because the core adapter binds the session to a
          contextvar (``_active_session``) set by ``transaction()``. Calling
          ``get_repository()`` outside raises ``RuntimeError``.
        - ``config_jsonb`` is validated against the imported Pydantic
          ``AgentConfig`` (SPEC_02) before insert; this class performs no schema
          redefinition.
        - Return types are adapter-dependent (ORM entities for SQLAlchemyAdapter,
          dicts for MemoryDatabaseAdapter). This class returns whatever the
          adapter returns; callers that need a stable shape should normalize at
          the boundary.
    """

    def __init__(self, db: DatabaseManager) -> None:
        """Initialize with a core-cenf DatabaseManager.

        Args:
            db: The core-cenf ``DatabaseManager`` (Protocol). The concrete
                adapter (SQLAlchemyAdapter / MemoryDatabaseAdapter) is swappable.
        """
        self._db = db

    async def get_by_name(
        self, tenant_id: UUID, name: str,
    ) -> AgentConfigRecord | None:
        """Return the active agent config for ``tenant_id`` + ``name``, or None.

        Filters: ``{tenant_id, name, is_active: True}``, limit 1.

        Args:
            tenant_id: The tenant to scope the query to (explicit WHERE filter).
            name: The agent config name (unique per tenant).

        Returns:
            The matching ``AgentConfigRecord``, or ``None`` if no active config
            exists for this tenant+name.
        """
        async with self._db.transaction() as tx:
            repo = self._db.get_repository(AgentConfigRecord)
            rows = await repo.find_all(
                filters={
                    "tenant_id": tenant_id,
                    "name": name,
                    "is_active": True,
                },
                limit=1,
            )
            await tx.commit()
            return rows[0] if rows else None

    async def list_by_tenant(
        self, tenant_id: UUID,
    ) -> list[AgentConfigRecord]:
        """Return all agent configs for ``tenant_id``.

        Filters: ``{tenant_id}`` only — returns both active and inactive configs.

        Args:
            tenant_id: The tenant to scope the query to.

        Returns:
            A list of ``AgentConfigRecord`` for the tenant (may be empty).
        """
        async with self._db.transaction() as tx:
            repo = self._db.get_repository(AgentConfigRecord)
            rows = await repo.find_all(filters={"tenant_id": tenant_id})
            await tx.commit()
            return list(rows)

    async def save(
        self, tenant_id: UUID, config: AgentConfig,
    ) -> AgentConfigRecord:
        """Serialize the Pydantic config and insert it as a new row.

        The Pydantic ``AgentConfig`` (SPEC_02) is the single source of truth for
        validation. This method serializes it into ``config_jsonb`` (via
        ``model_dump()``) and ``config_yaml`` (via ``yaml.dump``), constructs an
        ``AgentConfigRecord``, and inserts it.

        Args:
            tenant_id: The tenant the config belongs to.
            config: The validated Pydantic ``AgentConfig`` to persist.

        Returns:
            The inserted ``AgentConfigRecord`` (with id populated by the adapter).
        """
        config_dict = config.model_dump()
        config_yaml_str = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

        record = AgentConfigRecord(
            tenant_id=tenant_id,
            name=config.name,
            version=1,
            config_yaml=config_yaml_str,
            config_jsonb=config_dict,
            # Explicit is_active so the row is deterministic regardless of the
            # adapter's default handling (same philosophy as the explicit
            # tenant_id filter — never rely on implicit adapter behavior).
            is_active=True,
        )

        async with self._db.transaction() as tx:
            repo = self._db.get_repository(AgentConfigRecord)
            inserted: AgentConfigRecord = await repo.insert(record)
            await tx.commit()
            return inserted

    async def delete(self, tenant_id: UUID, name: str) -> None:
        """Delete the agent config for ``tenant_id`` + ``name``.

        Idempotent: if no matching row exists, this is a no-op (no error).

        Args:
            tenant_id: The tenant to scope the query to.
            name: The agent config name to delete.
        """
        async with self._db.transaction() as tx:
            repo = self._db.get_repository(AgentConfigRecord)
            rows = await repo.find_all(
                filters={"tenant_id": tenant_id, "name": name},
                limit=1,
            )
            if rows:
                await repo.delete(rows[0].id)
            await tx.commit()


__all__ = ["AgentConfigRepository"]
