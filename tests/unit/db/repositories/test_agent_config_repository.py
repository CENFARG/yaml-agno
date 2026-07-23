"""RED tests for AgentConfigRepository (SPEC_03 slice C).

Strict TDD — written BEFORE the repository exists. The repository is a thin
wrapper over core-cenf ``GenericRepository[T]``, obtained via
``db.get_repository(AgentConfigRecord)`` inside ``async with db.transaction()``.

Uses mock ``DatabaseManager`` and mock ``GenericRepository`` — no real DB.

Tagged ``@pytest.mark.unit``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.unit

from yaml_agno.db.models.agent_config import AgentConfigRecord  # noqa: E402
from yaml_agno.db.repositories.agent_config_repository import (  # noqa: E402
    AgentConfigRepository,
)
from yaml_agno.models.config.agent_config import AgentConfig  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers — mock DatabaseManager with async transaction + mock GenericRepository
# ---------------------------------------------------------------------------


class _MockTransactionScope:
    """Async context manager that mimics TransactionScope (commit/rollback)."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _MockTransactionScope:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class _MockDatabaseManager:
    """Mock DatabaseManager Protocol for unit tests.

    ``transaction()`` yields a ``_MockTransactionScope``.
    ``get_repository()`` returns a ``MagicMock`` whose async methods are
    pre-configured by the test.
    """

    def __init__(self) -> None:
        self._tx = _MockTransactionScope()
        self.mock_repo = MagicMock()
        # GenericRepository methods are async coroutines
        self.mock_repo.find_by_id = AsyncMock()
        self.mock_repo.find_all = AsyncMock(return_value=[])
        self.mock_repo.insert = AsyncMock()
        self.mock_repo.update = AsyncMock()
        self.mock_repo.delete = AsyncMock()
        self.mock_repo.count = AsyncMock(return_value=0)

    def transaction(self) -> _MockTransactionScope:
        return self._tx

    def get_repository(self, entity_type: type) -> Any:
        return self.mock_repo


def _make_agent_config_record(
    tenant_id: UUID | None = None,
    name: str = "test-agent",
) -> AgentConfigRecord:
    return AgentConfigRecord(
        tenant_id=tenant_id or uuid4(),
        name=name,
        version=1,
        config_yaml="name: test-agent\nmodel: openai:gpt-4o\n",
        config_jsonb={"name": "test-agent", "model": "openai:gpt-4o"},
        tags=[],
        metadata_={},
    )


# ---------------------------------------------------------------------------
# Scenario C.1 — get_by_name returns active config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_name_returns_matching_record() -> None:
    """get_by_name filters by {tenant_id, name, is_active: True} and returns row."""
    db = _MockDatabaseManager()
    tenant_id = uuid4()
    expected = _make_agent_config_record(tenant_id=tenant_id, name="agent-1")
    db.mock_repo.find_all.return_value = [expected]

    repo = AgentConfigRepository(db)
    result = await repo.get_by_name(tenant_id, "agent-1")

    assert result is expected
    db.mock_repo.find_all.assert_awaited_once()
    call_kwargs = db.mock_repo.find_all.call_args.kwargs
    assert call_kwargs["filters"] == {
        "tenant_id": tenant_id,
        "name": "agent-1",
        "is_active": True,
    }
    assert call_kwargs.get("limit") == 1
    assert db._tx.committed is True


# ---------------------------------------------------------------------------
# Scenario C.2 — get_by_name returns None when no match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_name_returns_none_when_no_match() -> None:
    """get_by_name returns None when find_all returns empty list."""
    db = _MockDatabaseManager()
    db.mock_repo.find_all.return_value = []

    repo = AgentConfigRepository(db)
    result = await repo.get_by_name(uuid4(), "missing-agent")

    assert result is None
    assert db._tx.committed is True


# ---------------------------------------------------------------------------
# Scenario C.3 — save serializes Pydantic config and inserts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_inserts_record_with_serialized_config() -> None:
    """save() serializes AgentConfig.model_dump() into config_jsonb and inserts."""
    db = _MockDatabaseManager()
    tenant_id = uuid4()

    config = AgentConfig(
        name="my-agent",
        model="openai:gpt-4o",
        instructions="Be helpful",
    )
    # insert returns the record back (with id populated)
    db.mock_repo.insert.return_value = _make_agent_config_record(
        tenant_id=tenant_id, name="my-agent",
    )

    repo = AgentConfigRepository(db)
    await repo.save(tenant_id, config)

    db.mock_repo.insert.assert_awaited_once()
    inserted: AgentConfigRecord = db.mock_repo.insert.call_args.args[0]
    assert isinstance(inserted, AgentConfigRecord)
    assert inserted.tenant_id == tenant_id
    assert inserted.name == "my-agent"
    # config_jsonb must contain the serialized Pydantic config
    assert "name" in inserted.config_jsonb
    assert inserted.config_jsonb["name"] == "my-agent"
    assert inserted.config_jsonb["model"] == "openai:gpt-4o"
    # config_yaml must be a non-empty string
    assert isinstance(inserted.config_yaml, str)
    assert len(inserted.config_yaml) > 0
    assert db._tx.committed is True


# ---------------------------------------------------------------------------
# Scenario C.4 — list_by_tenant returns all configs for tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_tenant_returns_all_configs() -> None:
    """list_by_tenant filters by {tenant_id} only and returns all rows."""
    db = _MockDatabaseManager()
    tenant_id = uuid4()
    records = [
        _make_agent_config_record(tenant_id=tenant_id, name="agent-a"),
        _make_agent_config_record(tenant_id=tenant_id, name="agent-b"),
    ]
    db.mock_repo.find_all.return_value = records

    repo = AgentConfigRepository(db)
    result = await repo.list_by_tenant(tenant_id)

    assert result == records
    assert len(result) == 2
    call_kwargs = db.mock_repo.find_all.call_args.kwargs
    assert call_kwargs["filters"] == {"tenant_id": tenant_id}
    assert db._tx.committed is True


# ---------------------------------------------------------------------------
# Scenario C.5 — delete removes by tenant+name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_existing_config() -> None:
    """delete() finds the row by {tenant_id, name} then calls repo.delete(id)."""
    db = _MockDatabaseManager()
    tenant_id = uuid4()
    record_id = uuid4()
    existing = _make_agent_config_record(tenant_id=tenant_id, name="agent-1")
    existing.id = record_id
    db.mock_repo.find_all.return_value = [existing]

    repo = AgentConfigRepository(db)
    await repo.delete(tenant_id, "agent-1")

    # find_all called with tenant_id + name filter
    call_kwargs = db.mock_repo.find_all.call_args.kwargs
    assert call_kwargs["filters"] == {
        "tenant_id": tenant_id,
        "name": "agent-1",
    }
    # delete called with the record's id
    db.mock_repo.delete.assert_awaited_once_with(record_id)
    assert db._tx.committed is True


@pytest.mark.asyncio
async def test_delete_is_noop_when_config_not_found() -> None:
    """delete() is a no-op when no row matches tenant+name."""
    db = _MockDatabaseManager()
    db.mock_repo.find_all.return_value = []

    repo = AgentConfigRepository(db)
    await repo.delete(uuid4(), "nonexistent")

    db.mock_repo.delete.assert_not_awaited()
    assert db._tx.committed is True
