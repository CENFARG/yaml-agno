"""Unit tests for build_flag_manager (SPEC_23 §2.6, TASK_239/TASK_2310).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Uses the real core
MemoryFeatureFlagAdapter — no files, no network.

Covers:
  - is_enabled() delegates to the core (fail-safe False for unknown flags).
  - unknown flag returns False without raising.
  - tenant override via FlagContext rules (TASK_2310).
  - hot-reload refresh() is a no-op for the memory adapter.
"""

from __future__ import annotations

import pytest
from core_infrastructure.feature_flags.models import FeatureFlag, FlagContext

from yaml_agno.config.bootstrap import build_flag_manager


@pytest.mark.unit
def test_is_enabled_delegates_to_core() -> None:
    """TASK_239 — is_enabled() MUST be owned by the core adapter."""
    flags = [FeatureFlag(key="enable_experimental_rag", enabled=False)]
    manager = build_flag_manager("dev", flags)
    assert manager.is_enabled("enable_experimental_rag") is False


@pytest.mark.unit
def test_unknown_flag_fails_safe_to_false() -> None:
    """SPEC_23 §3 — unknown flags MUST return False without raising."""
    manager = build_flag_manager("dev", [])
    assert manager.is_enabled("does_not_exist") is False


@pytest.mark.unit
def test_enabled_flag_returns_true() -> None:
    """An enabled flag without rules MUST evaluate True."""
    manager = build_flag_manager(
        "dev", [FeatureFlag(key="new_rag_engine", enabled=True)]
    )
    assert manager.is_enabled("new_rag_engine") is True


@pytest.mark.unit
def test_tenant_override_via_context() -> None:
    """TASK_2310 — a rule-scoped flag MUST only enable for the matching tenant."""
    manager = build_flag_manager(
        "dev",
        [
            FeatureFlag(
                key="new_rag_engine",
                enabled=True,
                rules=[{"attribute": "tenant_id", "operator": "eq", "value": "tenant_acme"}],
            )
        ],
    )
    acme = FlagContext(tenant_id="tenant_acme")
    globex = FlagContext(tenant_id="tenant_globex")
    assert manager.is_enabled("new_rag_engine", acme) is True
    assert manager.is_enabled("new_rag_engine", globex) is False


@pytest.mark.unit
def test_get_all_flags_evaluates_against_context() -> None:
    """get_all_flags() MUST evaluate every flag against the provided context."""
    manager = build_flag_manager(
        "dev",
        [
            FeatureFlag(key="a", enabled=True),
            FeatureFlag(
                key="b",
                enabled=True,
                rules=[{"attribute": "tenant_id", "operator": "eq", "value": "t1"}],
            ),
        ],
    )
    result = manager.get_all_flags(FlagContext(tenant_id="t1"))
    assert result == {"a": True, "b": True}
    result_other = manager.get_all_flags(FlagContext(tenant_id="t2"))
    assert result_other == {"a": True, "b": False}


@pytest.mark.unit
async def test_refresh_is_safe_for_memory_adapter() -> None:
    """SPEC_23 §3 — refresh() MUST be callable (no-op) without raising."""
    manager = build_flag_manager("dev", [FeatureFlag(key="x", enabled=True)])
    await manager.refresh()
    assert manager.is_enabled("x") is True
