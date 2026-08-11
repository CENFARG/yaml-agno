"""Unit tests for the FlagRepository (SPEC_23 §5, TASK_2315).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. The repository consumes the
core GenericRepository Protocol — this test uses an in-memory double; the
testcontainer-backed query is covered at integration level.

Covers:
  - tenant row overrides the global default row (ORDER BY tenant_id NULLS LAST).
  - a name with only a global row resolves to the global value.
  - an unknown name returns None.
  - seeded flags are set on the core MemoryFeatureFlagAdapter.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from core_infrastructure.database.ports import GenericRepository

from yaml_agno.config.flags_repository import FlagRepository
from yaml_agno.db.models.feature_flag import FeatureFlagRecord


class InMemoryFlagRepo(GenericRepository[FeatureFlagRecord]):
    """GenericRepository double storing FeatureFlagRecord rows in a dict."""

    def __init__(self, rows: list[FeatureFlagRecord] | None = None) -> None:
        self._rows: dict[Any, FeatureFlagRecord] = {}
        self._seq = 1
        for row in rows or []:
            self._add(row)

    def _add(self, row: FeatureFlagRecord) -> None:
        self._rows[self._seq] = row
        self._seq += 1

    async def find_by_id(self, id: Any) -> FeatureFlagRecord | None:
        return self._rows.get(id)

    async def find_all(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeatureFlagRecord]:
        rows = list(self._rows.values())
        if filters:
            for key, value in filters.items():
                rows = [r for r in rows if getattr(r, key) == value]
        if order_by:
            rows.sort(key=lambda r: getattr(r, order_by) or "")
        return rows[offset : offset + limit]

    async def insert(self, entity: FeatureFlagRecord) -> FeatureFlagRecord:
        self._add(entity)
        return entity

    async def update(self, entity: FeatureFlagRecord) -> FeatureFlagRecord:
        for key, row in self._rows.items():
            if row.name == entity.name:
                self._rows[key] = entity
                return entity
        raise ValueError(f"not found: {entity.name}")

    async def delete(self, id: Any) -> None:
        self._rows.pop(id, None)

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        return len(await self.find_all(filters))


def _row(
    name: str,
    enabled: bool,
    tenant_id: UUID | None,
) -> FeatureFlagRecord:
    return FeatureFlagRecord(
        name=name,
        tenant_id=tenant_id,
        enabled=enabled,
        percent=0,
        variant_rules=None,
        description=None,
        updated_by="test",
    )


@pytest.mark.unit
async def test_tenant_row_overrides_global_default() -> None:
    """TASK_2315 — a tenant-exact row MUST win over the global (tenant_id NULL) row."""
    tenant = uuid4()
    repo = InMemoryFlagRepo(
        [
            _row("new_rag_engine", False, None),
            _row("new_rag_engine", True, tenant),
        ]
    )
    repository = FlagRepository(repo)

    result = await repository.get_flag("new_rag_engine", tenant_id=tenant)
    assert result is not None
    assert result.enabled is True
    assert result.tenant_id == tenant


@pytest.mark.unit
async def test_global_row_used_when_no_tenant_row() -> None:
    """Without a tenant-exact row, the global default MUST be returned."""
    repo = InMemoryFlagRepo([_row("stable_flag", True, None)])
    repository = FlagRepository(repo)

    result = await repository.get_flag("stable_flag", tenant_id=uuid4())
    assert result is not None
    assert result.enabled is True
    assert result.tenant_id is None


@pytest.mark.unit
async def test_unknown_flag_returns_none() -> None:
    """An unknown flag name MUST return None (no crash)."""
    repo = InMemoryFlagRepo([_row("known", True, None)])
    repository = FlagRepository(repo)

    result = await repository.get_flag("does_not_exist", tenant_id=None)
    assert result is None


@pytest.mark.unit
async def test_seed_flags_sets_definitions_on_core_adapter() -> None:
    """Seeded rows MUST be registered on the core MemoryFeatureFlagAdapter."""
    from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
        MemoryFeatureFlagAdapter,
    )

    repo = InMemoryFlagRepo(
        [
            _row("new_rag_engine", False, None),
            _row("new_rag_engine", True, uuid4()),
        ]
    )
    repository = FlagRepository(repo)
    adapter = MemoryFeatureFlagAdapter()

    await repository.seed_flags(adapter, tenant_id=None)
    # Global row seeded as a plain definition on the core adapter.
    assert isinstance(adapter.is_enabled("new_rag_engine"), bool)
    assert adapter.is_enabled("new_rag_engine") is False


@pytest.mark.unit
async def test_seed_flags_applies_tenant_row() -> None:
    """Seeding with a tenant MUST register the tenant-enabled row."""
    from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
        MemoryFeatureFlagAdapter,
    )

    tenant = uuid4()
    repo = InMemoryFlagRepo(
        [
            _row("new_rag_engine", False, None),
            _row("new_rag_engine", True, tenant),
        ]
    )
    repository = FlagRepository(repo)
    adapter = MemoryFeatureFlagAdapter()

    await repository.seed_flags(adapter, tenant_id=tenant)
    assert adapter.is_enabled("new_rag_engine") is True
    assert len(adapter.get_all_flags()) == 1
