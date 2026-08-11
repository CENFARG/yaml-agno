"""SecretAuditRecord — ``yamlagno.secret_audit`` (SPEC_23 §5).

Append-only audit trail for secret access. Every row records WHO accessed
WHICH secret, WHEN, and whether the access was a cache hit, a remote (storage)
hit, or a miss. The ``hit IN ('cache','remote','miss')`` CHECK constrains the
kind; ``ok`` records whether the access succeeded.

Append-only note: rows are inserted, never updated/deleted. Time-based
partitioning (SPEC_23 §5) is DDL-level (V023 migration), not enforced on the
ORM model — the declarative record is the logical shape, partitions are the
physical storage detail.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base


class SecretAuditRecord(Base):
    """Persistence row for ``yamlagno.yamlagno_secret_audit``."""

    __tablename__ = "secret_audit"
    __table_args__ = (
        CheckConstraint("hit IN ('cache','remote','miss')", name="valid_hit_kind"),
        {"schema": "yamlagno"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    secret_name: Mapped[str] = mapped_column(String(256), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    hit: Mapped[str] = mapped_column(String(16), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accessed_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"), nullable=False,
    )
    trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)
