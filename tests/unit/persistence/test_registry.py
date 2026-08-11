"""RED tests for the DbRegistry (SPEC_03 §7.4).

Strict TDD — written BEFORE ``yaml_agno.persistence.registry`` exists.
The contract is canonical from SPEC_03 §7.4: a pure lookup table holding
pre-built Agno ``Db`` / ``VectorDb`` instances keyed by YAML ref. Missing
refs MUST raise ``ValueError`` naming the ref (fail-fast for SPEC_31 /
SPEC_32 consumers).

Tagged ``@pytest.mark.unit``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from yaml_agno.persistence.registry import (  # noqa: E402
    DbRegistry,
    InMemoryDbRegistry,
)


class _FakeDb:
    """Stand-in for an Agno BaseDb instance (construction is not our concern)."""

    def __init__(self, ref: str) -> None:
        self.ref = ref


class _FakeVectorDb:
    """Stand-in for an Agno VectorDb instance."""

    def __init__(self, ref: str) -> None:
        self.ref = ref


# ---------------------------------------------------------------------------
# Scenario 1 — DbRegistry is a Protocol (static contract, no instantiation)
# ---------------------------------------------------------------------------


def test_db_registry_is_a_protocol() -> None:
    """DbRegistry must be a Protocol so adapters implement it structurally."""
    from typing import Protocol

    assert issubclass(DbRegistry, Protocol)


# ---------------------------------------------------------------------------
# Scenario 2 — InMemoryDbRegistry registers and resolves db refs
# ---------------------------------------------------------------------------


def test_register_db_then_get_returns_same_instance() -> None:
    """register_db(key, db) then get(key) returns the SAME object."""
    registry = InMemoryDbRegistry()
    db = _FakeDb("primary_pg")

    registry.register_db("primary_pg", db)

    assert registry.get("primary_pg") is db


def test_register_vector_db_then_get_vector_db_returns_same_instance() -> None:
    """register_vector_db(key, vdb) then get_vector_db(key) returns SAME object."""
    registry = InMemoryDbRegistry()
    vdb = _FakeVectorDb("kb_vectors")

    registry.register_vector_db("kb_vectors", vdb)

    assert registry.get_vector_db("kb_vectors") is vdb


def test_db_and_vector_db_namespaces_are_independent() -> None:
    """A db and a vector_db may share the same ref string without collision."""
    registry = InMemoryDbRegistry()
    db = _FakeDb("shared")
    vdb = _FakeVectorDb("shared")

    registry.register_db("shared", db)
    registry.register_vector_db("shared", vdb)

    assert registry.get("shared") is db
    assert registry.get_vector_db("shared") is vdb


# ---------------------------------------------------------------------------
# Scenario 3 — missing refs fail fast with ValueError naming the ref
# ---------------------------------------------------------------------------


def test_get_missing_db_ref_raises_value_error_naming_ref() -> None:
    """get() on an unregistered db_ref MUST raise ValueError naming the ref."""
    registry = InMemoryDbRegistry()
    registry.register_db("primary_pg", _FakeDb("primary_pg"))

    with pytest.raises(ValueError, match="other_pg"):
        registry.get("other_pg")


def test_get_vector_db_missing_ref_raises_value_error_naming_ref() -> None:
    """get_vector_db() on an unregistered ref MUST raise ValueError naming it."""
    registry = InMemoryDbRegistry()

    with pytest.raises(ValueError, match="kb_vectors"):
        registry.get_vector_db("kb_vectors")
