"""DiVariableCacheRecord — ``yamlagno_di_variable_cache`` (SPEC_03 §3.5).

TTL-bounded cache of resolved DI variable values (provider_name + variable_key
-> variable_value). The ``expires_at > created_at`` CHECK is a storage-level
sanity guard; the application must still filter ``expires_at > NOW()`` on read.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TenantMixin, TimestampMixin


class DiVariableCacheRecord(TimestampMixin, TenantMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_di_variable_cache``."""

    __tablename__ = "yamlagno_di_variable_cache"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider_name", "variable_key",
            name="ya_di_tenant_provider_key_unique",
        ),
        CheckConstraint(
            "expires_at > created_at", name="ya_di_expires_future",
        ),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    variable_key: Mapped[str] = mapped_column(String(255), nullable=False)
    variable_value: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
