"""RED tests for resolve_user_id (SPEC_04 leaf).

Covers the 7 cases from design.md §Testing Strategy:
  1. Golden path — human principal.
  2. Golden path — system principal literal.
  3. Golden path — system principal template expanded.
  4. RED — missing tenant_id raises UserIdentityResolutionError.
  5. RED — missing principal AND missing system_user_id raises.
  6. RED — template without context dict raises.
  7. RED — template with missing key raises (chained from KeyError).

These tests reference ``yaml_agno.memory.user_identity`` which does NOT exist
yet (RED phase). They MUST fail on ImportError until Phase 2.1 lands.
"""

from types import SimpleNamespace

import pytest

from yaml_agno.memory.user_identity import (
    UserIdentityResolutionError,
    resolve_user_id,
)

pytestmark = pytest.mark.unit


def _cfg(system_user_id: str | None) -> SimpleNamespace:
    """Minimal memory_cfg stub carrying only ``system_user_id``."""
    return SimpleNamespace(system_user_id=system_user_id)


class TestResolveUserIdGoldenPaths:
    """GREEN scenarios — the resolver returns the composite user_id."""

    def test_golden_human_principal(self) -> None:
        """Human principal wins; system_user_id is ignored."""
        cfg = _cfg("agent:ignored")
        result = resolve_user_id(cfg, principal_id="alice", tenant_id="acme")
        assert result == "acme:alice"

    def test_golden_system_principal_literal(self) -> None:
        """No human principal -> system_user_id literal used as principal."""
        cfg = _cfg("agent:facturacion")
        result = resolve_user_id(cfg, principal_id=None, tenant_id="acme")
        assert result == "acme:agent:facturacion"

    def test_golden_system_principal_template_expanded(self) -> None:
        """system_user_id template expanded against context dict."""
        cfg = _cfg("workflow:{workflow_id}")
        result = resolve_user_id(
            cfg,
            principal_id=None,
            tenant_id="acme",
            context={"workflow_id": "wf-42"},
        )
        assert result == "acme:workflow:wf-42"


class TestResolveUserIdFailFast:
    """RED scenarios — the resolver raises instead of falling back to 'default'."""

    def test_red_missing_tenant_raises(self) -> None:
        """tenant_id=None MUST raise before resolving the principal."""
        cfg = _cfg("agent:x")
        with pytest.raises(UserIdentityResolutionError) as exc_info:
            resolve_user_id(cfg, principal_id="alice", tenant_id=None)
        msg = str(exc_info.value)
        assert "tenant_id" in msg

    def test_red_missing_principal_and_system_user_id_raises(self) -> None:
        """No human principal AND no system_user_id MUST raise (no 'default')."""
        cfg = _cfg(None)
        with pytest.raises(UserIdentityResolutionError) as exc_info:
            resolve_user_id(cfg, principal_id=None, tenant_id="acme")
        msg = str(exc_info.value)
        assert "default" in msg

    def test_red_template_without_context_raises(self) -> None:
        """Template system_user_id with context=None MUST raise."""
        cfg = _cfg("workflow:{workflow_id}")
        with pytest.raises(UserIdentityResolutionError) as exc_info:
            resolve_user_id(cfg, principal_id=None, tenant_id="acme", context=None)
        msg = str(exc_info.value)
        assert "context" in msg

    def test_red_template_missing_key_raises_chained_from_keyerror(self) -> None:
        """Template referencing a key absent from context raises, chained from KeyError."""
        cfg = _cfg("workflow:{workflow_id}")
        with pytest.raises(UserIdentityResolutionError) as exc_info:
            resolve_user_id(
                cfg,
                principal_id=None,
                tenant_id="acme",
                context={"agent_id": "a"},  # missing workflow_id
            )
        # The underlying KeyError MUST be preserved as __cause__.
        assert isinstance(exc_info.value.__cause__, KeyError)
