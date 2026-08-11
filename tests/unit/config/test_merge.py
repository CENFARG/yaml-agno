"""Unit tests for multi-tenant YAML deep merge (SPEC_23 §2.8, TASK_2313).

RED-GREEN strict TDD. Tagged @pytest.mark.unit.

Covers:
  - tenant override deep-merges over default (tenant wins on conflict).
  - nested sections merge recursively without replacing whole sections.
  - an empty/None tenant returns the default unchanged.
  - merge_tenant delegates to _deep_merge with the right argument order.
"""

from __future__ import annotations

import pytest

from yaml_agno.config.merge import _deep_merge, _merge_tenant


@pytest.mark.unit
def test_tenant_override_deep_merges() -> None:
    """TASK_2313 — tenant persistence.pool_size=50 MUST merge over default=20."""
    default = {
        "app": {"name": "yaml-agno", "env": "dev"},
        "persistence": {
            "pool_size": 20,
            "pool_max_overflow": 5,
            "statement_timeout_ms": 5000,
        },
    }
    tenant = {
        "persistence": {
            "pool_size": 50,
            "statement_timeout_ms": 9000,
        }
    }
    merged = _merge_tenant(default, tenant)

    assert merged["persistence"]["pool_size"] == 50
    # The un-overridden sibling survives (deep merge, not section replace).
    assert merged["persistence"]["pool_max_overflow"] == 5
    assert merged["persistence"]["statement_timeout_ms"] == 9000
    assert merged["app"] == {"name": "yaml-agno", "env": "dev"}


@pytest.mark.unit
def test_deep_merge_does_not_mutate_inputs() -> None:
    """_deep_merge MUST return a new dict and leave both inputs untouched."""
    default = {"a": {"x": 1, "y": 2}}
    tenant = {"a": {"y": 3}}
    out = _deep_merge(default, tenant)
    assert out == {"a": {"x": 1, "y": 3}}
    assert default == {"a": {"x": 1, "y": 2}}  # not mutated
    assert tenant == {"a": {"y": 3}}  # not mutated


@pytest.mark.unit
def test_deep_merge_scalar_override() -> None:
    """A scalar tenant value MUST replace the default scalar."""
    default = {"flags": {"enable_experimental_rag": False}}
    tenant = {"flags": {"enable_experimental_rag": True}}
    assert _deep_merge(default, tenant)["flags"]["enable_experimental_rag"] is True


@pytest.mark.unit
def test_merge_tenant_none_returns_default() -> None:
    """SPEC_23 §2.8 — a None tenant MUST return the default unchanged."""
    default = {"persistence": {"pool_size": 20}}
    assert _merge_tenant(default, None) == default


@pytest.mark.unit
def test_merge_tenant_empty_returns_default() -> None:
    """An empty tenant dict MUST return the default unchanged."""
    default = {"persistence": {"pool_size": 20}}
    assert _merge_tenant(default, {}) == default
