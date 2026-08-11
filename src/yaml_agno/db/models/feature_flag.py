"""FeatureFlagRecord — ``yamlagno.feature_flags`` (SPEC_23 §5).

Runtime feature-flag definitions. Resolution order is **tenant-exact >
global**: a row with ``tenant_id`` set wins for that tenant; the global row
(``tenant_id IS NULL``) is the fallback. The ``UNIQUE(name, tenant_id)``
constraint allows one global row and many tenant overrides per flag name.

Multi-tenant note: unlike TenantMixin-backed tables, ``tenant_id`` here is
NULLABLE — the global row IS the tenant-scope ``NULL``. The application-layer
resolution (tenant-exact > global) lives in ``config.flags_repository``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TimestampMixin


class FeatureFlagRecord(TimestampMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_feature_flags``."""

    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("name", "tenant_id", name="uq_feature_flags_name_tenant"),
        {"schema": "yamlagno"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    percent: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    variant_rules: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    # created_at / updated_at come from TimestampMixin.
