"""Feature-flag persistence (SPEC_23 §2.6, TASK_238).

Feature flags live in ``yamlagno.feature_flags`` (see
``db/models/feature_flag.py``) with a ``UNIQUE(name, tenant_id)`` constraint.
Resolution order is **tenant-exact > global**: when a tenant row exists for a
flag name it wins; otherwise the global row (``tenant_id IS NULL``) applies.
This repository performs the lookup in Python over ``find_all`` — the core
``GenericRepository`` owns storage; this class owns the yaml-agno flag
resolution policy (no custom SQL, no re-implementation of storage).
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

from core_infrastructure.database.ports import GenericRepository
from core_infrastructure.feature_flags.models import FeatureFlag
from core_infrastructure.feature_flags.ports import FeatureFlagManager

from yaml_agno.db.models.feature_flag import FeatureFlagRecord

__all__ = ["FlagRepository"]

# core-cenf-py does not publish py.typed yet (registered debt, pyproject
# [[tool.mypy.overrides]]): the GenericRepository[T] Protocol degrades to
# Any under mypy, so find_all() results are cast back to the entity type.
_EntityList = list[FeatureFlagRecord]


class FlagRepository:
    """Resolves feature flags over the ``yamlagno.feature_flags`` table.

    Args:
        repo: The core ``GenericRepository`` bound to ``FeatureFlagRecord``.
            Injected by the wiring layer (``db.get_repository(...)`` inside a
            transaction) — never constructed here.
    """

    def __init__(self, repo: GenericRepository[FeatureFlagRecord]) -> None:
        self._repo = repo

    async def get_flag(self, name: str, tenant_id: UUID | None = None) -> FeatureFlagRecord | None:
        """Resolve the effective flag row for ``name`` under ``tenant_id``.

        Resolution: tenant-exact row wins; otherwise the global row
        (``tenant_id IS NULL``). Returns None when neither exists.

        Args:
            name: The flag name (e.g. ``enable_experimental_rag``).
            tenant_id: Optional tenant scope. When None, only the global row
                is considered.

        Returns:
            The effective :class:`FeatureFlagRecord`, or None if unknown.
        """
        rows = cast(_EntityList, await self._repo.find_all(filters={"name": name}))

        tenant_match = next(
            (row for row in rows if row.tenant_id is not None and row.tenant_id == tenant_id),
            None,
        )
        if tenant_match is not None:
            return tenant_match

        global_row = next((row for row in rows if row.tenant_id is None), None)
        return global_row

    async def seed_flags(self, adapter: FeatureFlagManager, *, tenant_id: UUID | None = None) -> None:
        """Register flag definitions on a core :class:`FeatureFlagManager`.

        For each flag name, the tenant-exact row wins over the global row.
        Flags are registered with the core adapter's ``set_flag`` (the core
        owns the enablement rules); this class only selects *which* row is the
        effective definition.

        Args:
            adapter: The core ``FeatureFlagManager`` to seed (e.g. the one
                returned by ``bootstrap.build_flag_manager``).
            tenant_id: Optional tenant scope to prefer tenant rows for.
        """
        rows = cast(_EntityList, await self._repo.find_all())
        effective: dict[str, FeatureFlagRecord] = {}

        for row in rows:
            current = effective.get(row.name)
            if current is None:
                effective[row.name] = row
                continue
            # Tenant-exact row beats the global row for the requested tenant.
            if (
                row.tenant_id is not None
                and current.tenant_id is None
                and tenant_id is not None
                and row.tenant_id == tenant_id
            ):
                effective[row.name] = row

        for name, row in effective.items():
            adapter.set_flag(FeatureFlag(key=name, enabled=row.enabled))
