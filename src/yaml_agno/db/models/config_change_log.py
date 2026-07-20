"""ConfigChangeLogRecord — ``yamlagno_config_change_log`` (SPEC_03 §3.6).

Config-store audit log (config.created / config.updated / config.deleted /
flag.toggled). Does NOT replicate Agno RunEvents. Uses TimestampMixin for
``created_at``/``updated_at`` and an explicit tenant FK (not TenantMixin)
because the table also carries correlation/causation UUIDs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TimestampMixin


class ConfigChangeLogRecord(TimestampMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_config_change_log``."""

    __tablename__ = "yamlagno_config_change_log"
    __table_args__ = (
        CheckConstraint(
            "processing_attempts >= 0", name="ya_ccl_positive_attempts",
        ),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    event_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="1.0",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("yamlagno.yamlagno_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    correlation_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True,
    )
    causation_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True,
    )
    # created_at / updated_at come from TimestampMixin.
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    processing_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
