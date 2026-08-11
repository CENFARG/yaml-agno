"""Unit tests for the SPEC_23 ORM records (SPEC_23 §5).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. These tests validate the
DeclarativeBase mapping (columns, schema, constraints) WITHOUT a database —
importing the models has no DB side effects.

Covers:
  - FeatureFlagRecord maps to schema yamlagno.feature_flags with the
    UNIQUE(name, tenant_id) constraint.
  - SecretAuditRecord maps to schema yamlagno.secret_audit with the
    hit IN ('cache','remote','miss') check and append-only columns.
  - Both records register on the shared Base.metadata.
"""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from yaml_agno.db.base import Base
from yaml_agno.db.models.feature_flag import FeatureFlagRecord
from yaml_agno.db.models.secret_audit import SecretAuditRecord


@pytest.mark.unit
def test_feature_flag_table_mapping() -> None:
    """FeatureFlagRecord MUST target schema yamlagno, table feature_flags."""
    assert FeatureFlagRecord.__tablename__ == "feature_flags"
    table = FeatureFlagRecord.__table__
    assert table.schema == "yamlagno"
    assert "name" in table.c
    assert "tenant_id" in table.c
    assert "enabled" in table.c
    assert "percent" in table.c
    assert "variant_rules" in table.c
    assert "description" in table.c
    assert "updated_at" in table.c
    assert "updated_by" in table.c


@pytest.mark.unit
def test_feature_flag_unique_name_tenant_constraint() -> None:
    """SPEC_23 §5 — UNIQUE(name, tenant_id) MUST be declared."""
    constraints = FeatureFlagRecord.__table__.constraints
    uniques = [c for c in constraints if isinstance(c, UniqueConstraint)]
    assert any(
        sorted(c.columns.keys()) == ["name", "tenant_id"] for c in uniques
    ), f"missing UNIQUE(name, tenant_id); got {[c.columns.keys() for c in uniques]}"


@pytest.mark.unit
def test_secret_audit_table_mapping() -> None:
    """SecretAuditRecord MUST target schema yamlagno, table secret_audit."""
    assert SecretAuditRecord.__tablename__ == "secret_audit"
    table = SecretAuditRecord.__table__
    assert table.schema == "yamlagno"
    assert "secret_name" in table.c
    assert "actor" in table.c
    assert "tenant_id" in table.c
    assert "hit" in table.c
    assert "ok" in table.c
    assert "accessed_at" in table.c
    assert "trace_id" in table.c


@pytest.mark.unit
def test_secret_audit_hit_check_constraint() -> None:
    """SPEC_23 §5 — hit MUST be constrained to cache|remote|miss."""
    checks = [
        c
        for c in SecretAuditRecord.__table__.constraints
        if isinstance(c, CheckConstraint)
    ]
    assert len(checks) == 1
    assert "cache" in checks[0].sqltext.text
    assert "remote" in checks[0].sqltext.text
    assert "miss" in checks[0].sqltext.text


@pytest.mark.unit
def test_records_registered_on_shared_base_metadata() -> None:
    """Both records MUST be registered on the shared Base.metadata."""
    tables = Base.metadata.tables
    assert "yamlagno.feature_flags" in tables
    assert "yamlagno.secret_audit" in tables


@pytest.mark.unit
def test_feature_flag_record_constructible_without_db() -> None:
    """The record MUST be constructible in Python (no DB required)."""
    from uuid import uuid4

    row = FeatureFlagRecord(
        name="new_rag_engine",
        tenant_id=uuid4(),
        enabled=True,
        percent=50,
        variant_rules={"tenant": ["acme"]},
        description="staged rollout",
        updated_by="test",
    )
    assert row.name == "new_rag_engine"
    assert row.enabled is True
    assert row.percent == 50


@pytest.mark.unit
def test_secret_audit_record_constructible_without_db() -> None:
    """The audit record MUST be constructible in Python (no DB required)."""
    row = SecretAuditRecord(
        secret_name="db_password",
        actor="yaml-agno",
        hit="miss",
        ok=False,
    )
    assert row.secret_name == "db_password"
    assert row.hit == "miss"
    assert row.ok is False
