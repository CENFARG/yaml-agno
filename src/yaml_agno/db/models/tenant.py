"""TenantRecord — ``yamlagno_tenants`` (SPEC_03 §3.1).

Root identity for the config store and the anchor for multi-tenant isolation.
The ``org_has_no_parent`` CHECK enforces kind<->parent consistency only;
cycle prevention (A->B->A) MUST be validated at the application layer before
insert/update — a CHECK cannot express acyclicity.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TimestampMixin


class TenantRecord(TimestampMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_tenants``."""

    __tablename__ = "yamlagno_tenants"
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9-]+$'", name="slug_format"),
        CheckConstraint(
            "tenant_kind IN ('org','org_user_roles','user')",
            name="valid_tenant_kind",
        ),
        CheckConstraint(
            "tenant_kind <> 'org' OR parent_org_id IS NULL",
            name="org_has_no_parent",
        ),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    tenant_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="org",
    )
    parent_org_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("yamlagno.yamlagno_tenants.id", ondelete="SET NULL"),
        nullable=True,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    # created_at / updated_at come from TimestampMixin.
