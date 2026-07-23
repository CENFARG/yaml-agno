"""RED tests for TenantResolver (SPEC_03 slice D).

Strict TDD — written BEFORE the resolver exists. The TenantResolver PARSES the
``{tenant_id}:{principal_id}`` composite built by ``resolve_user_id()`` (SPEC_04).
It never builds a composite and never does I/O.

Tagged ``@pytest.mark.unit``. No mocks needed — pure parsing.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# import target (fails until GREEN)
# ---------------------------------------------------------------------------

from yaml_agno.tenant.resolver import TenantResolver  # noqa: E402

# ---------------------------------------------------------------------------
# Scenario D.1 — extract_tenant parses prefix
# ---------------------------------------------------------------------------


def test_extract_tenant_returns_prefix_before_first_colon() -> None:
    """extract_tenant('acme:user-123') -> 'acme'."""
    resolver = TenantResolver()
    assert resolver.extract_tenant("acme:user-123") == "acme"


# ---------------------------------------------------------------------------
# Scenario D.2 — extract_principal parses suffix
# ---------------------------------------------------------------------------


def test_extract_principal_returns_suffix_after_first_colon() -> None:
    """extract_principal('acme:user-123') -> 'user-123'."""
    resolver = TenantResolver()
    assert resolver.extract_principal("acme:user-123") == "user-123"


# ---------------------------------------------------------------------------
# Scenario D.3 — no colon raises ValueError
# ---------------------------------------------------------------------------


def test_extract_tenant_raises_value_error_on_no_colon() -> None:
    """extract_tenant('no-colon') raises ValueError."""
    resolver = TenantResolver()
    with pytest.raises(ValueError, match="colon"):
        resolver.extract_tenant("no-colon-here")


def test_extract_principal_raises_value_error_on_no_colon() -> None:
    """extract_principal('no-colon') raises ValueError."""
    resolver = TenantResolver()
    with pytest.raises(ValueError, match="colon"):
        resolver.extract_principal("no-colon-here")


def test_extract_tenant_raises_value_error_on_empty_string() -> None:
    """extract_tenant('') raises ValueError."""
    resolver = TenantResolver()
    with pytest.raises(ValueError):
        resolver.extract_tenant("")


# ---------------------------------------------------------------------------
# Scenario D.4 — principal with embedded colons
# ---------------------------------------------------------------------------


def test_extract_tenant_with_embedded_colons_in_principal() -> None:
    """extract_tenant('acme:user:with:colons') -> 'acme' (before FIRST colon)."""
    resolver = TenantResolver()
    assert resolver.extract_tenant("acme:user:with:colons") == "acme"


def test_extract_principal_with_embedded_colons() -> None:
    """extract_principal('acme:user:with:colons') -> 'user:with:colons'."""
    resolver = TenantResolver()
    assert resolver.extract_principal("acme:user:with:colons") == "user:with:colons"


# ---------------------------------------------------------------------------
# Round-trip with resolve_user_id (SPEC_04 single-seam rule)
# ---------------------------------------------------------------------------


def test_resolver_round_trips_with_resolve_user_id_composite() -> None:
    """The composite built by resolve_user_id must round-trip through the resolver.

    This verifies the single-seam rule: resolve_user_id() BUILDS the composite,
    TenantResolver only PARSES it. Never invert.
    """
    from yaml_agno.memory.user_identity import resolve_user_id

    tenant = "acme-corp"
    principal = "user-42"
    composite = resolve_user_id(
        memory_cfg=None,
        principal_id=principal,
        tenant_id=tenant,
    )
    # The composite must contain the separator.
    assert ":" in composite

    resolver = TenantResolver()
    assert resolver.extract_tenant(composite) == tenant
    assert resolver.extract_principal(composite) == principal


# ---------------------------------------------------------------------------
# Edge: empty tenant or principal parts
# ---------------------------------------------------------------------------


def test_extract_tenant_with_empty_tenant_part() -> None:
    """:user -> tenant is empty string (still valid partition, tenant is '')."""
    resolver = TenantResolver()
    assert resolver.extract_tenant(":user-1") == ""


def test_extract_principal_with_empty_principal_part() -> None:
    """acme: -> principal is empty string."""
    resolver = TenantResolver()
    assert resolver.extract_principal("acme:") == ""
