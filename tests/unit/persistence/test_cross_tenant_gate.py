"""Cross-tenant isolation GATE (SPEC_03 §5.2 Scenario 5 / DECISIONES 2.9).

THE GATE: a tenant MUST NOT be able to read, list, or delete another tenant's
configs. yaml-agno uses **explicit** ``tenant_id`` filters (NO RLS — decision
2.9, inviolable): every AgentConfigRepository call scopes the query with
``filters={"tenant_id": ...}``.

These tests seed a GenericRepository double (InMemoryFlagRepo pattern from
``tests/unit/config/test_flag_repository.py``) with rows from TWO tenants,
including rows that share the SAME ``name``, and prove the repository never
leaks cross-tenant data.

Strict TDD — written BEFORE any persistence/ code changes; the repository
under test already exists and is GREEN (baseline 94 passed). These tests
guard the invariant for SPEC_03 closure.

Tagged ``@pytest.mark.unit``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from core_infrastructure.database.ports import GenericRepository

pytestmark = pytest.mark.unit

from yaml_agno.db.models.agent_config import AgentConfigRecord  # noqa: E402
from yaml_agno.db.repositories.agent_config_repository import (  # noqa: E402
    AgentConfigRepository,
)
from yaml_agno.models.config.agent_config import AgentConfig  # noqa: E402


class InMemoryAgentConfigRepo(GenericRepository[AgentConfigRecord]):
    """GenericRepository double storing AgentConfigRecord rows in a dict."""

    def __init__(self, rows: list[AgentConfigRecord] | None = None) -> None:
        self._rows: dict[Any, AgentConfigRecord] = {}
        self._seq = 1
        for row in rows or []:
            self._add(row)

    def _add(self, row: AgentConfigRecord) -> None:
        if row.id is None:  # pragma: no cover — defensive, never hit in tests
            row.id = uuid4()
        self._rows[row.id] = row

    async def find_by_id(self, id: Any) -> AgentConfigRecord | None:
        return self._rows.get(id)

    async def find_all(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentConfigRecord]:
        rows = list(self._rows.values())
        if filters:
            for key, value in filters.items():
                rows = [r for r in rows if getattr(r, key) == value]
        if order_by:
            rows.sort(key=lambda r: getattr(r, order_by) or "")
        return rows[offset : offset + limit]

    async def insert(self, entity: AgentConfigRecord) -> AgentConfigRecord:
        self._add(entity)
        return entity

    async def update(self, entity: AgentConfigRecord) -> AgentConfigRecord:
        for key, row in self._rows.items():
            if row.id == entity.id:
                self._rows[key] = entity
                return entity
        raise ValueError(f"not found: {entity.id}")

    async def delete(self, id: Any) -> None:
        self._rows.pop(id, None)

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        return len(await self.find_all(filters))


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


class _FakeDatabaseManager:
    """DatabaseManager double: yields a transaction scope and returns the
    in-memory GenericRepository double from get_repository()."""

    def __init__(self, repo: InMemoryAgentConfigRepo) -> None:
        self._repo = repo
        self._tx = _MockTransactionScope()

    def transaction(self) -> _MockTransactionScope:
        return self._tx

    def get_repository(self, entity_type: type) -> InMemoryAgentConfigRepo:
        return self._repo


def _repository(rows: list[AgentConfigRecord]) -> AgentConfigRepository:
    db = _FakeDatabaseManager(InMemoryAgentConfigRepo(rows))
    return AgentConfigRepository(db)


def _row(tenant_id: UUID, name: str, version: int = 1) -> AgentConfigRecord:
    return AgentConfigRecord(
        tenant_id=tenant_id,
        name=name,
        version=version,
        config_yaml=f"name: {name}\nmodel: openai:gpt-4o\n",
        config_jsonb={"name": name, "model": "openai:gpt-4o"},
        tags=[],
        metadata_={},
        is_active=True,
    )


# ---------------------------------------------------------------------------
# GATE-01 — a tenant cannot LIST another tenant's configs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_tenant_never_returns_other_tenants_rows() -> None:
    """Given the store holds rows for tenants A and B, list_by_tenant(A) MUST
    return ONLY A's rows — never B's."""
    tenant_a, tenant_b = uuid4(), uuid4()
    repository = _repository(
        [
            _row(tenant_a, "agent-a1"),
            _row(tenant_a, "agent-a2"),
            _row(tenant_b, "agent-b1"),
        ]
    )

    result = await repository.list_by_tenant(tenant_a)

    names = {r.name for r in result}
    assert names == {"agent-a1", "agent-a2"}
    assert "agent-b1" not in names
    assert all(r.tenant_id == tenant_a for r in result)


# ---------------------------------------------------------------------------
# GATE-02 — a tenant cannot READ another tenant's config by name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_name_never_leaks_same_named_row_from_other_tenant() -> None:
    """Given BOTH tenants have a config named 'shared-agent', get_by_name(A,
    'shared-agent') MUST return A's row — NOT B's."""
    tenant_a, tenant_b = uuid4(), uuid4()
    row_a = _row(tenant_a, "shared-agent", version=3)
    row_b = _row(tenant_b, "shared-agent", version=1)
    repository = _repository([row_a, row_b])

    result = await repository.get_by_name(tenant_a, "shared-agent")

    assert result is not None
    assert result.tenant_id == tenant_a
    assert result.version == 3  # A's row, not B's (version 1)


@pytest.mark.asyncio
async def test_get_by_name_returns_none_when_only_other_tenant_has_name() -> None:
    """If ONLY tenant B has a config, get_by_name(A, name) MUST return None."""
    tenant_a, tenant_b = uuid4(), uuid4()
    repository = _repository([_row(tenant_b, "b-only-agent")])

    result = await repository.get_by_name(tenant_a, "b-only-agent")

    assert result is None


# ---------------------------------------------------------------------------
# GATE-03 — a tenant cannot DELETE another tenant's config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_scoped_to_tenant_preserves_other_tenants_row() -> None:
    """delete(A, 'shared-agent') MUST remove ONLY A's row; B's same-named row
    MUST remain readable afterwards."""
    tenant_a, tenant_b = uuid4(), uuid4()
    repository = _repository([_row(tenant_a, "shared-agent"), _row(tenant_b, "shared-agent")])

    await repository.delete(tenant_a, "shared-agent")

    # A no longer has it…
    assert await repository.get_by_name(tenant_a, "shared-agent") is None
    # …but B still does.
    remaining = await repository.get_by_name(tenant_b, "shared-agent")
    assert remaining is not None
    assert remaining.tenant_id == tenant_b


# ---------------------------------------------------------------------------
# GATE-04 — save always stamps the caller's tenant_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_stamps_caller_tenant_id() -> None:
    """save(A, config) MUST persist the row under tenant A — the caller's
    tenant_id — never a bare/global scope."""
    tenant_a = uuid4()
    repository = _repository([])

    saved = await repository.save(
        tenant_a,
        AgentConfig(name="my-agent", model="openai:gpt-4o"),
    )

    assert saved.tenant_id == tenant_a
    # And it is visible only to tenant A.
    assert await repository.get_by_name(tenant_a, "my-agent") is not None
